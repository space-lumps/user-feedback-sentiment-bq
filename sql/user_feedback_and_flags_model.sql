-- ----------------------------------------------------------------------
-- Model: user_feedback_and_flags_model
-- Purpose: Combines and deduplicates user feedback messages and manual flags into a single, clean dataset
--          suitable for downstream LLM-based sentiment scoring.
-- 
-- Source tables:
--   - fact_chat_msg_feedback
--   - fact_chat_manualflag
-- 
-- Output: Materialized as table `user_feedback_and_flags` in the demo_dataset schema
-- Note: This is a demo version — all referenced tables are prefixed with 'demo_dataset'.
-- ----------------------------------------------------------------------

WITH message_feedback_raw AS (
  SELECT 
      msg.created_at AS `timestamp`             -- Timestamp of the message
    , msg.text_content AS system_message        -- AI-generated message
    , feedback.comment AS user_comment          -- User feedback comment
    , 'message_feedback' AS source_type         -- Source label
    , activity.name AS activity_name
    , users.user_type_name
    , users.user_id
    , chat.id AS chat_id
    , msg.id AS message_id
    , feedback.feedback AS user_feedback_type
    , ROW_NUMBER() OVER (
      PARTITION BY users.user_id, msg.id, feedback.comment
      ORDER BY feedback.created_at DESC
    ) AS rn_feedback    -- Safe deduplication: keep latest distinct comment per user-message
  FROM `demo_dataset.fact_chat` AS chat
  LEFT JOIN `demo_dataset.fact_chat_msg` AS msg ON msg.chat_id = chat.id
  LEFT JOIN `demo_dataset.fact_chat_msg_feedback` AS feedback ON feedback.chat_message_id = msg.id
  LEFT JOIN `demo_dataset.fact_chat_activity` AS activity ON activity.id = chat.activity_id
  LEFT JOIN `demo_dataset.dim_users` AS users ON users.user_id = chat.user_id
  WHERE feedback.comment IS NOT NULL
    AND feedback.comment <> ''
    AND feedback.feedback IS NOT NULL
),
-- Note: User flags are attached to individual messages (via chat_message_id),
--       not to the chat level. Therefore, we join on msg.user_id here
--       to align user context correctly with the flagged message.
user_flags_raw AS (
  SELECT 
      msg.created_at AS `timestamp`
    , msg.text_content AS system_message
    , flag.comment AS user_comment
    , 'user_flag' AS source_type
    , activity.display_name AS activity_name
    , users.user_type_name
    , chat.user_id
    , chat.id AS chat_id
    , msg.id AS message_id
    , 'flag' AS user_feedback_type
    , ROW_NUMBER() OVER (
      PARTITION BY chat.user_id, msg.id, flag.comment
      ORDER BY flag.created_at DESC
    ) AS rn_flag    -- Safe deduplication: keep latest distinct flag comment per user-message
  FROM `demo_dataset.fact_chat` AS chat
  LEFT JOIN `demo_dataset.fact_chat_msg` AS msg ON msg.chat_id = chat.id
  LEFT JOIN `demo_dataset.fact_chat_manualflag` AS flag ON flag.chat_message_id = msg.id
  LEFT JOIN `demo_dataset.fact_chat_activity` AS activity ON activity.id = chat.activity_id
  LEFT JOIN `demo_dataset.dim_users` AS users ON users.user_id = msg.user_id
  WHERE flag.comment IS NOT NULL
    AND flag.comment <> ''
)

-- Final output: union both sources and keep only top-ranked deduped rows
SELECT
    `timestamp`
  , system_message
  , user_comment
  , source_type
  , activity_name
  , user_type_name
  , user_id
  , chat_id
  , message_id
  , user_feedback_type
FROM message_feedback_raw
WHERE rn_feedback = 1    -- Keep only most recent unique feedback entry

UNION ALL

SELECT
    `timestamp`
  , system_message
  , user_comment
  , source_type
  , activity_name
  , user_type_name
  , user_id
  , chat_id
  , message_id
  , user_feedback_type
FROM user_flags_raw
WHERE rn_flag = 1    -- Keep only most recent unique flag entry
