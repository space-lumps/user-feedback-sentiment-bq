import pandas as pd
import openai
import os
import json
from dotenv import load_dotenv

# Load .env for OpenAI API key
load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

# Input and output filenames
input_path = "user_feedback_and_flags.csv"
output_path = "llm_output_test.csv"

# Load your dataset
df = pd.read_csv(input_path)
df = df.reset_index(drop=True)
df = df[df["system_message"].notnull() & df["system_message"].str.strip().ne("")]


results = []

# Loop through each row
for _, row in df.iterrows():
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
		response = openai.chat.completions.create(
			model="gpt-4o",
			messages=[
				{"role": "system", "content": "You are a helpful assistant that only responds with valid JSON."},
				{"role": "user", "content": prompt}
			],
			temperature=0,
			max_tokens=60
		)

		content = response.choices[0].message.content.strip()
		parsed = json.loads(content)

		# Add original row data + LLM response
		results.append({
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
			"aspect": parsed["aspect"]
		})

	except Exception as e:
		print(f"❌ Error on row: {row.get('user_id')} - {e}")

# Convert to DataFrame and export to CSV
if results:
	pd.DataFrame(results).to_csv(output_path, index=False)
	print(f"✅ Done! Output saved to {output_path}")
else:
	print("⚠️ No results to write.")
