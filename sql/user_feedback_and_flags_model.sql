-- Combine and dedupe user feedback and flags for LLM sentiment scoring
-- This model merges chat_messagefeedback and manual flags into one consistent structure

WITH message_feedback_raw AS (
	SELECT 
		  msg.created_at AS `timestamp`						-- Timestamp of the message
		, msg.text_content AS system_message				-- AI-generated message
		, mf.comment AS user_comment						-- User feedback comment
		, 'message_feedback' AS source_type					-- Source label
		, act.name AS activity_name
		, ub.user_type_full_name
		, ub.user_id
		, chat.id AS chat_id
		, msg.id AS message_id
		, mf.feedback AS user_feedback_type  -- Renamed from 'chat_experience' for consistency with 'flag' values in the combined output
		, ROW_NUMBER() OVER (
			PARTITION BY ub.user_id, msg.id, mf.comment
			ORDER BY mf.created_at DESC
		) AS rn_feedback  -- Safe deduplication: keep latest distinct comment per user-message
	FROM `Coach.chat_chat` AS chat
	LEFT JOIN `Coach.chat_chatmessage` AS msg ON msg.chat_id = chat.id
	LEFT JOIN `Coach.chat_messagefeedback` AS mf ON mf.chat_message_id = msg.id
	LEFT JOIN `Coach.chat_activity` AS act ON act.id = chat.activity_id
	LEFT JOIN `Model.user_base` AS ub ON ub.user_id = chat.user_id
	WHERE mf.comment IS NOT NULL
	  AND mf.comment <> ''
	  AND mf.feedback IS NOT NULL
),

user_flags_raw AS (
	SELECT 
		  msg.created_at AS `timestamp`
		, msg.text_content AS system_message
		, flag.comment AS user_comment
		, 'user_flag' AS source_type
		, act.display_name AS activity_name
		, ub.user_type_full_name
		, chat.user_id
		, chat.id AS chat_id
		, msg.id AS message_id
		, 'flag' AS user_feedback_type  -- Hardcoded to distinguish flags from positive/negative chat_experience
		, ROW_NUMBER() OVER (
			PARTITION BY chat.user_id, msg.id, flag.comment
			ORDER BY flag.created_at DESC
		) AS rn_flag  -- Safe deduplication: keep latest distinct flag comment per user-message
	FROM `Coach.chat_chat` AS chat
	LEFT JOIN `Coach.chat_chatmessage` AS msg ON msg.chat_id = chat.id
	LEFT JOIN `Coach.chat_manualflag` AS flag ON flag.chat_message_id = msg.id
	LEFT JOIN `Coach.chat_activity` AS act ON act.id = chat.activity_id
	LEFT JOIN `Model.user_base` AS ub ON ub.user_id = msg.user_id
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
	, user_type_full_name
	, user_id
	, chat_id
	, message_id
	, user_feedback_type
FROM message_feedback_raw
WHERE rn_feedback = 1  -- Keep only most recent unique feedback entry

UNION ALL

SELECT
	  `timestamp`
	, system_message
	, user_comment
	, source_type
	, activity_name
	, user_type_full_name
	, user_id
	, chat_id
	, message_id
	, user_feedback_type
FROM user_flags_raw
WHERE rn_flag = 1  -- Keep only most recent unique flag entry
