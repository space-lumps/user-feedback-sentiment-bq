# ----------------------------------------------------------------------
# llm_feedback_pipeline.py
#
# LLM sentiment pipeline for user feedback.
#
# Production mode:
# - queries new unprocessed user feedback from BigQuery
# - analyzes sentiment using OpenAI GPT-4o
# - parses structured JSON output
# - appends results to a BigQuery output table
#
# Local test mode:
# - reads sample input from a CSV file
# - runs the same prompt/parse logic locally
# - saves results to a local CSV file
#
# Designed for scheduled GCP execution (e.g., Cloud Functions, Composer).
# Uses Secret Manager for secure API key handling in production, with
# .env-based environment variables available for local testing.
# Includes retry logic, Slack alerting, and error handling.
# ----------------------------------------------------------------------
import json
import os
import time

import pandas as pd
import requests
from dotenv import load_dotenv
# from google.cloud import bigquery, secretmanager  # uncomment for Production mode
from openai import OpenAI

# Production config
project_id = "demo-project-id"
dataset = "demo_dataset"
source_model = "user_feedback_and_flags"
output_table = "feedback_sentiment_output"

# Local development mode:
# Load secrets from a local .env file instead of Secret Manager.
load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
slack_webhook = os.getenv("SLACK_WEBHOOK_URL")

# Local test input/output files.
# INPUT_CSV should contain the same columns expected from the BigQuery source model.
INPUT_CSV = "sample_feedback.csv"
OUTPUT_CSV = "simulated_full_pipeline_local_test.csv"

# ========================================================================
# PRODUCTION MODE (BigQuery)
# Uncomment this block when running against warehouse data
# ========================================================================
# # Production option: retrieve secrets from Google Cloud Secret Manager
# def get_secret(secret_id, project_id):
#     client = secretmanager.SecretManagerServiceClient()
#     secret_path = f"projects/{project_id}/secrets/{secret_id}/versions/latest"
#     response = client.access_secret_version(name=secret_path)
#     return response.payload.data.decode("UTF-8")

# # Example secretkey retrieval for production:
# client.api_key = get_secret("openai-api-key", project_id)
# slack_webhook = get_secret("slack-webhook-url", project_id)

# assert client.api_key, "Missing OpenAI API key from Secret Manager"
# assert (
#     slack_webhook is not None
# ), "Missing Slack webhook (set to empty string if intentionally disabled)"

# # Initialize BigQuery client for Production mode
# bq_client = bigquery.Client()

# # Production-only BigQuery query.
# # Used when running against the warehouse instead of local CSV input.
# QUERY = f"""
# SELECT *
# FROM `{project_id}.{dataset}.{source_model}` AS src
# WHERE NOT EXISTS (
#   SELECT 1 FROM `{project_id}.{dataset}.{output_table}` AS out
#   WHERE out.user_id = src.user_id
#     AND out.message_id = src.message_id
#     AND out.user_comment = src.user_comment
# )
# """
# ========================================================================


def build_prompt(system_message, user_comment):
    """
    Build a structured prompt that asks the model to classify each feedback row
    into a constrained JSON schema for downstream parsing.
    """
    return f"""You are a sentiment analysis engine.

Given the following AI-generated system message and a user comment in response to it, return a JSON object with:

- "sentiment_score": integer from -2 (very negative) to +2 (very positive)
- "sentiment_type": one of ["complaint", "suggestion", "compliment", "neutral"]
- "aspect": one of ["response_quality", "completeness", "speed_or_timing", "interface_or_functionality", "praise"]

System Message: {system_message}

User Comment: {user_comment}

Output JSON:
"""


def send_prompt(prompt_text, model="gpt-4o", max_tokens=60, temperature=0, retries=3):
    """
    Send the prompt to OpenAI with basic retry logic.
    Returns the raw model output as a string, or None after repeated failures.
    """
    for attempt in range(retries):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a helpful assistant that only responds with valid JSON.",
                    },
                    {"role": "user", "content": prompt_text},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
            )
            raw_output = response.choices[0].message.content.strip()

            # Some LLM responses may include markdown-style code blocks (e.g., ```json ... ```)
            # even when instructed not to. This strips those wrappers to ensure valid JSON parsing.
            if raw_output.startswith("```"):
                raw_output = raw_output.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
            return raw_output
        except Exception as e:
            print(f"❌ Error from OpenAI (attempt {attempt + 1}): {e}")
            time.sleep(2)
    return None


def send_slack_notification(message):
    """
    Send a Slack notification if a webhook is configured.
    Safe to no-op in local development when Slack is disabled.
    """
    if not slack_webhook:
        print("ℹ️  No Slack webhook configured.")
        return
    try:
        response = requests.post(
            slack_webhook,
            json={"text": message},
            timeout=10,
        )
        response.raise_for_status()

    except requests.exceptions.RequestException as e:
        print("⚠️ Slack notification failed:", e)


def load_input_data():
    """
    Load local test data and validate that it matches the schema expected
    by the downstream parsing and output logic.
    """
    df = pd.read_csv(INPUT_CSV)

    required_columns = [
        "user_id",
        "chat_id",
        "message_id",
        "timestamp",
        "user_comment",
        "system_message",
        "source_type",
        "user_feedback_type",
    ]

    missing_columns = [column for column in required_columns if column not in df.columns]
    if missing_columns:
        raise ValueError(f"Missing required columns in {INPUT_CSV}: {missing_columns}")

    return df


def save_results_locally(result_df, processed_count):
    """
    Save processed results to a local CSV file.

    If the file already exists, append new results and remove duplicates
    based on user_id, message_id, and user_comment.
    """
    if os.path.exists(OUTPUT_CSV):
        existing_df = pd.read_csv(OUTPUT_CSV)
        result_df = pd.concat([existing_df, result_df], ignore_index=True)
        result_df = result_df.drop_duplicates(
            subset=["user_id", "message_id", "user_comment"],
            keep="last",
        )

    result_df.to_csv(OUTPUT_CSV, index=False)
    print(f"✅ Processed {processed_count} rows and saved results to local file: {OUTPUT_CSV}.")
    send_slack_notification(f"✅ LLM pipeline processed {processed_count} rows.")


def save_results_to_bq(result_df, processed_count):
    """
    Append processed results to the BigQuery output table.
    Used in production mode.
    """
    from pandas_gbq import to_gbq

    to_gbq(
        result_df,
        f"{dataset}.{output_table}",
        project_id=project_id,
        if_exists="append",
    )

    print(f"✅ Processed {processed_count} rows and saved results to Bigquery table: {output_table}.")
    send_slack_notification(f"✅ LLM pipeline processed {processed_count} new rows.")


def main():
    # Active mode: local CSV testing.
    df = load_input_data()

    # Production mode:
    # Uncomment the BigQuery line below and comment out load_input_data()
    # when running this pipeline against warehouse data.
    # df = bq_client.query(QUERY).to_dataframe()

    if df.empty:
        print("🟡 No new rows to process.")
        return

    results = []

    for idx, row in df.iterrows():
        print(f"Processing row {idx + 1} of {len(df)}...")
        prompt = build_prompt(row["system_message"], row["user_comment"])
        raw_response = send_prompt(prompt)
        if not raw_response:
            print(f"❌ Empty or failed response on row: {idx}")
            continue

        try:
            parsed = json.loads(raw_response)
            required_keys = ["sentiment_score", "sentiment_type", "aspect"]
            missing_keys = [key for key in required_keys if key not in parsed]
            if missing_keys:
                raise ValueError(f"Missing keys in model response: {missing_keys}")
            results.append(
                {
                    "user_id": row["user_id"],
                    "chat_id": row["chat_id"],
                    "message_id": row["message_id"],
                    "timestamp": row["timestamp"],
                    "user_comment": row["user_comment"],
                    "system_message": row["system_message"],
                    "source_type": row["source_type"],
                    "user_feedback_type": row["user_feedback_type"],
                    "sentiment_score": parsed["sentiment_score"],
                    "sentiment_type": parsed["sentiment_type"],
                    "aspect": parsed["aspect"],
                    "llm_timestamp": pd.Timestamp.utcnow(),
                }
            )
        except Exception as e:
            print(f"❌ Failed to parse response on row {idx}:\n{raw_response}\n{e}")

    if results:
        result_df = pd.DataFrame(results)
        # Choose exactly one output path:
        # - local CSV for testing
        # - BigQuery table for production
        save_results_locally(result_df, len(results))

        # save_results_to_bq(result_df, len(results))

    else:
        print("⚠️ No valid responses to write.")


if __name__ == "__main__":
    main()
