# ----------------------------------------------------------------------
# test_llm_on_full_dataset.py
#
# LOCAL DEMO MODE
# This script defaults to sample_feedback.csv (committed fake data)
# so anyone can clone and run it immediately without BigQuery, API keys,
# or real production data.
#
# To run on your own full dataset:
#   - Change input_path below to your CSV file path
#   - Optionally remove or comment out any cleaning filters if not needed
# ----------------------------------------------------------------------

import json
import os
import re

import pandas as pd
from dotenv import load_dotenv
from openai import OpenAI

# Load .env for OpenAI API key
load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Input and output filenames
# Default: uses the committed sample_feedback.csv so script runs locally without real data
# To run on your own full dataset, change this path to your CSV file
input_path = "sample_feedback.csv"
# input_path = "user_feedback_and_flags.csv"  # <-- uncomment for real/large data
output_path = "sample_llm_output_full_test.csv"  # Renamed slightly to avoid confusion

# Load your dataset
df = pd.read_csv(input_path)
df = df.reset_index(drop=True)
df = df[df["system_message"].notnull() & df["system_message"].str.strip().ne("")]


results = []

# Loop through each row
for idx, row in df.iterrows():
    system_message = str(row["system_message"])
    user_comment = str(row["user_comment"])

    # Build the prompt
    prompt = f"""
You are a sentiment analysis engine.

Given the following AI-generated system message and a user comment in response to it, return a JSON object with:

- "sentiment_score": integer from -2 (very negative) to +2 (very positive)
- "sentiment_type": one of ["complaint", "suggestion", "compliment", "neutral"]
- "aspect": one of ["response_quality", "completeness", "speed_or_timing", "interface_or_functionality", "praise"]

System Message: {system_message}

User Comment: {user_comment}

Output JSON:
"""

    try:
        print(f"Processing row {idx + 1} of {len(df)}...")
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": "You are a helpful assistant that only responds with valid JSON.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0,
            max_tokens=60,
        )

        # clean raw input (is this the right label or is it cleaning raw output)
        raw_output = response.choices[0].message.content

        # Debug raw output (for debugging only)
        # print(f"DEBUG raw response for row {row.get('user_id')}:\n{raw_output}\n---")

        # Robust markdown/JSON wrapper removal
        clean_output = re.sub(
            r"^```(?:json)?\s*|\s*```$",
            "",
            raw_output.strip(),
            flags=re.IGNORECASE | re.MULTILINE,
        )
        clean_output = clean_output.strip()

        # Additional safety: remove any leading "json" or trailing junk
        clean_output = re.sub(
            r"^(json\s*|\s*json$)", "", clean_output, flags=re.IGNORECASE
        ).strip()

        try:
            parsed = json.loads(clean_output)
        except json.JSONDecodeError as json_err:
            print(f"❌ JSON parse failed on row {row.get('user_id')}: {json_err}")
            print(f"Cleaned content was:\n{clean_output}")
            continue

        # Add original row data + LLM response
        results.append(
            {
                "user_id": row.get("user_id"),
                "chat_id": row.get("chat_id"),
                "message_id": row.get("message_id"),
                "timestamp": row.get("timestamp"),
                "user_comment": user_comment,
                "system_message": system_message,
                "source_type": row.get("source_type"),
                "user_feedback_type": row.get("user_feedback_type"),
                "sentiment_score": parsed["sentiment_score"],
                "sentiment_type": parsed["sentiment_type"],
                "aspect": parsed["aspect"],
            }
        )

    except Exception as e:
        print(f"❌ Error on row: {row.get('user_id')} - {e}")

# Convert to DataFrame and export to CSV
if results:
    pd.DataFrame(results).to_csv(output_path, index=False)
    print(f"✅ Done! Output saved to {output_path}")
else:
    print("⚠️ No results to write.")
