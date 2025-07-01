import pandas as pd
import openai
import os
import json
import re
from dotenv import load_dotenv

# Load env
load_dotenv()
client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Load input CSV
df = pd.read_csv("user_feedback_and_flags.csv")

# # Sample first 20 rows for testing
# df_sample = df.head(20)

results = []

for idx, row in df.iterrows():
	user_id = row.get("user_id")
	chat_id = row.get("chat_id")
	message_id = row.get("message_id")
	timestamp = row.get("timestamp")
	system_message = row.get("system_message")
	user_comment = row.get("user_comment")
	source_type = row.get("source_type")
	user_feedback_type = row.get("user_feedback_type")

	if not system_message or not user_comment:
		print(f"⚠️ Skipping row {idx} due to missing text")
		continue

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
		response = client.chat.completions.create(
			model="gpt-4o",
			messages=[
				{"role": "system", "content": "You are a helpful assistant that only responds with valid JSON."},
				{"role": "user", "content": prompt}
			],
			temperature=0,
			max_tokens=60
		)

		raw_output = response.choices[0].message.content

		print(f"\n🔍 Row {idx} raw LLM response:\n{raw_output}\n")

		# Clean and parse the JSON
		clean_output = re.sub(r"^```(?:json)?|```$", "", raw_output.strip()).strip()
		parsed = json.loads(clean_output)

		results.append({
			"user_id": user_id,
			"chat_id": chat_id,
			"message_id": message_id,
			"timestamp": timestamp,
			"user_comment": user_comment,
			"system_message": system_message,
			"source_type": source_type,
			"user_feedback_type": user_feedback_type,
			"sentiment_score": parsed["sentiment_score"],
			"sentiment_type": parsed["sentiment_type"],
			"aspect": parsed["aspect"]
		})
	except Exception as e:
		print(f"❌ Error on row: {idx} -", e)

# ✅ Save output for Metabase testing
output_path = "sample_output_fulldataset.csv"
if results:
	pd.DataFrame(results).to_csv(output_path, index=False)
	print(f"✅ Done! Output saved to {output_path}")
else:
	print("⚠️ No results to write.")
