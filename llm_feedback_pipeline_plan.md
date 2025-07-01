**LLM Sentiment Scoring Pipeline for User Feedback and Flags**

---

### 📖 Overview

This document outlines the complete implementation plan for an LLM-based sentiment scoring pipeline that analyzes user feedback and flags from our app and widget. The goal is to extract structured, fine-grained sentiment labels and topic aspects using OpenAI or Claude.

---

### ✅ Scope

- Input: Model-generated view of all user feedback and manual flags
- Output: Scored results in a BigQuery table
- Pipeline: Scheduled Python job via the team's existing GCP orchestration process

---

### 🔗 Source Model: `Model.user_feedback_and_flags`

This BigQuery model combines all relevant user comments from message feedback and manual flags.

**Columns in the model:**

- `timestamp` (TIMESTAMP)
- `system_message` (STRING)
- `user_comment` (STRING)
- `source_type` (STRING) — e.g., 'message\_feedback', 'user\_flag'
- `activity_name` (STRING)
- `user_type_full_name` (STRING)
- `user_id` (INT64)
- `chat_id` (INT64)
- `message_id` (INT64)
- `user_feedback_type` (STRING) — e.g., 'positive', 'negative', 'flag'

**Why use a model?**

- The feedback data comes from multiple sources
- Logic can be centralized and updated in one place
- Easier to iterate on JOINs, filters, and transformations

**Why not a table (yet)?**

- Low volume (\~100 rows/year)
- No need for persistent state tracking
- Processing state is captured in the output table itself

**Consider switching to a table later if:**

- You want to manually reprocess or add retry logic
- Feedback volume increases significantly
- You want to expose per-row processing state (e.g. `llm_processed`, timestamps, flags)

---

### 📅 Scheduling Recommendation

- **Frequency:** Once per **week**
- **Tool:** Use the team’s existing GCP orchestration tool (e.g., Cloud Function, Composer, or similar)
- **Trigger:** Pull and process new feedback only
- **Suggested Cron:** `0 13 * * 1` (every Monday @ 8am UTC / 3am CDT)

---

### 💪 Output Table: `feedback_sentiment_output`

Stores all LLM-processed feedback entries.

**Schema:**

- `user_id` (INT64)
- `chat_id` (INT64)
- `message_id` (INT64)
- `timestamp` (TIMESTAMP)
- `user_comment` (STRING)
- `system_message` (STRING)
- `source_type` (STRING)
- `user_feedback_type` (STRING)
- `sentiment_score` (INT64, range −2 to +2)
- `sentiment_type` (STRING: complaint, suggestion, compliment, neutral)
- `aspect` (STRING: response\_quality, completeness, speed\_or\_timing, interface\_or\_functionality, praise)
- `llm_timestamp` (TIMESTAMP: indicates when the analysis took place)

**How we track processed rows:** Instead of including a `llm_processed` flag in the model, we check whether each `(user_id, message_id, user_comment)` already exists in the output table. This eliminates the need for marking rows and avoids reprocessing.

---

### 📄 Python Pipeline Summary

This is meant as a general overview of the process. All of this is already built into the .py project file, but will need slight edits and tweaks to be fully production-ready.

**Step-by-step:**

1. **Query new rows**:

```sql
SELECT *
FROM `your-project.your-dataset.Model.user_feedback_and_flags`
WHERE NOT EXISTS (
  SELECT 1 FROM `your-project.your-dataset.feedback_sentiment_output` AS out
  WHERE out.user_id = user_feedback_and_flags.user_id
    AND out.message_id = user_feedback_and_flags.message_id
    AND out.user_comment = user_feedback_and_flags.user_comment
)
```

2. **Loop through each row**, build the prompt, and send `system_message` and `user_comment` to GPT-4 or Claude.

3. **Receive and parse the structured JSON response**:

```json
{
  "sentiment_score": -1,
  "sentiment_type": "complaint",
  "aspect": "completeness"
}
```

4. **Merge this result with original fields** and load into BigQuery:

```python
from pandas_gbq import to_gbq

to_gbq(df, 'your_dataset.feedback_sentiment_output', project_id='your-project', if_exists='append')
```

---

### 🧠 Example LLM Prompt Template (Python)

```python
def build_prompt(system_message, user_comment):
    return f"""
You are a sentiment analysis engine.

Given the following AI-generated system message and a user comment in response to it, return a JSON object with:

- "sentiment_score": integer from -2 (very negative) to +2 (very positive)
- "sentiment_type": one of ["complaint", "suggestion", "compliment", "neutral"]
- "aspect": one of ["response_quality", "completeness", "speed_or_timing", "interface_or_functionality", "praise"]

System Message: {system_message}

User Comment: {user_comment}

Output JSON:
"""
```

---

### 🔌 OpenAI Prompt Execution

```python
import openai
import os
import json

openai.api_key = os.getenv("OPENAI_API_KEY")

def send_prompt(prompt_text, model="gpt-4", max_tokens=60, temperature=0):
    try:
        response = openai.ChatCompletion.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are a helpful assistant that only responds with valid JSON."},
                {"role": "user", "content": prompt_text}
            ],
            temperature=temperature,
            max_tokens=max_tokens,
            stop=None
        )
        return response["choices"][0]["message"]["content"]
    except Exception as e:
        print("Error from OpenAI:", e)
        return None
```

---

### 🔌 Claude Prompt Execution (Anthropic API)

```python
import anthropic
import os

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

def send_prompt_claude(prompt_text, model="claude-3-opus-20240229", max_tokens=60):
    try:
        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=0,
            messages=[
                {"role": "user", "content": prompt_text}
            ]
        )
        return response.content[0].text
    except Exception as e:
        print("Error from Claude:", e)
        return None
```

---

### ⚖️ Prompt Configuration Details

- Prompt is assembled and sent in Python code
- Use `temperature = 0` for deterministic responses
- Limit `max_tokens = 60` to control cost and output size
- Controlled vocabularies ensure consistent values for `aspect` and `sentiment_type`
- Only `system_message` and `user_comment` are passed to the LLM — other metadata is used only for post-processing

---

### 🚀 Deployment Notes

- Store OpenAI/Claude API key in Secret Manager -- this will need to be added to the .py project file
- Use a service account with BigQuery read/write access
- Use Slack (built-in, just add your API key) or email alert if any new rows are processed

---

### ✨ Future Enhancements

- Move model to a table for persistent tracking
- Version and log prompt behavior for auditing

---

Contact: @YourName | Last updated: 2025-06-27

