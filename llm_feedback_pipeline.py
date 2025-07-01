import openai
import pandas as pd
from google.cloud import bigquery
from pandas_gbq import to_gbq
import os
import json
import time
import requests
# from dotenv import load_dotenv
from google.cloud import secretmanager

# Config
project_id = "your-project-id"
dataset = "your_dataset"
source_model = "Model.user_feedback_and_flags"
output_table = "feedback_sentiment_output"

# Option one: load environment variables
# load_dotenv()
# openai.api_key = os.getenv("OPENAI_API_KEY")
# slack_webhook = os.getenv("SLACK_WEBHOOK_URL")

# Better option: retrieve secrets from Google Cloud Secret Manager
def get_secret(secret_id, project_id):
	client = secretmanager.SecretManagerServiceClient()
	secret_path = f"projects/{project_id}/secrets/{secret_id}/versions/latest"
	response = client.access_secret_version(name=secret_path)
	return response.payload.data.decode("UTF-8")

# Example secretkey retrieval:
openai.api_key = get_secret("openai-api-key", project_id)
slack_webhook = get_secret("slack-webhook-url", project_id)

assert openai.api_key, "Missing OpenAI API key from Secret Manager"
assert slack_webhook is not None, "Missing Slack webhook (set to empty string if intentionally disabled)"


# Initialize BigQuery client
bq_client = bigquery.Client()

# Query for new rows that haven't been processed yet
QUERY = f'''
SELECT *
FROM `{project_id}.{dataset}.{source_model}`
WHERE NOT EXISTS (
  SELECT 1 FROM `{project_id}.{dataset}.{output_table}` AS out
  WHERE out.user_id = {source_model}.user_id
    AND out.message_id = {source_model}.message_id
    AND out.user_comment = {source_model}.user_comment
)
'''

def build_prompt(system_message, user_comment):
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
	for attempt in range(retries):
		try:
			response = openai.chat.completions.create(
				model=model,
				messages=[
					{"role": "system", "content": "You are a helpful assistant that only responds with valid JSON."},
					{"role": "user", "content": prompt_text}
				],
				temperature=temperature,
				max_tokens=max_tokens
			)
			raw_output = response.choices[0].message.content.strip()
			
			# Some LLM responses may include markdown-style code blocks (e.g., ```json ... ```)
			# even when instructed not to. This strips those wrappers to ensure valid JSON parsing.
			if raw_output.startswith("```"):
				raw_output = raw_output.strip("```").strip("json").strip()
			return raw_output
		except Exception as e:
			print(f"❌ Error from OpenAI (attempt {attempt + 1}): {e}")
			time.sleep(2)
	return None

def send_slack_notification(message):
	if not slack_webhook:
		print("ℹ️ No Slack webhook configured.")
		return
	try:
		requests.post(slack_webhook, json={"text": message})
	except Exception as e:
		print("⚠️ Failed to send Slack alert:", e)

def main():
	df = bq_client.query(QUERY).to_dataframe()

	if df.empty:
		print("🟡 No new rows to process.")
		return

	results = []

	for idx, row in df.iterrows():
		prompt = build_prompt(row["system_message"], row["user_comment"])
		raw_response = send_prompt(prompt)
		if not raw_response:
			print(f"❌ Empty or failed response on row: {idx}")
			continue

		try:
			parsed = json.loads(raw_response)
			results.append({
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
				"llm_timestamp": pd.Timestamp.utcnow()
			})
		except Exception as e:
			print(f"❌ Failed to parse response on row {idx}:\n{raw_response}\n{e}")

	if results:
		result_df = pd.DataFrame(results)
		to_gbq(result_df, f"{dataset}.{output_table}", project_id=project_id, if_exists="append")
		print(f"✅ {len(results)} rows written to {output_table}.")
		send_slack_notification(f"✅ LLM pipeline processed {len(results)} new rows.")
	else:
		print("⚠️ No valid responses to write.")

if __name__ == "__main__":
	main()
