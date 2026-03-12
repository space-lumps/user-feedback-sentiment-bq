# User Feedback Sentiment (BigQuery + GPT-4o)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python](https://img.shields.io/badge/python-3.11-blue?logo=python&logoColor=white)](https://www.python.org/)
[![BigQuery](https://img.shields.io/badge/Google%20BigQuery-4285F4?logo=google-cloud&logoColor=white)](https://cloud.google.com/bigquery)
[![OpenAI](https://img.shields.io/badge/OpenAI-GPT--4o-412991?logo=openai&logoColor=white)](https://openai.com/)

This project analyzes structured user feedback (thumbs up/down, flags, and comments) using a fine-grained LLM-based sentiment scoring system. It processes data from a BigQuery table, generates numerical sentiment scores and aspect labels via OpenAI’s GPT-4o, and stores the results back in BigQuery for visualization and monitoring.

## 💡 Features

- Classifies sentiment as positive or negative with **numerical intensity from -2 to +2**
- Uses GPT-4o to analyze comment tone and identify specific aspects being addressed
- Saves structured output to a BigQuery table for downstream use in dashboards (e.g. Metabase)
- Designed for batch re-processing and easy automation via scheduled queries or Cloud Functions

## 🛠️ Stack

- Python 3.11
- OpenAI GPT-4o API
- Google BigQuery
- `.env` for secret management (for local testing only--prod version incorporates Google Secret manager)
- Optional: Metabase (for visualizations), Slack (for alerts)

## 🗂️ Project Structure

```
user-feedback-sentiment-bq/
├── test_llm_pipeline.py       # Test script to run on sample CSV data
├── main_llm_pipeline.py       # Production script for full BigQuery dataset
├── prompts.py                 # Modular prompt templates for GPT-4o
├── utils.py                   # Utilities for API calls, error handling, etc.
├── requirements.txt
└── .env.example               # Example environment variable setup
```

## ⚙️ How It Works

1. Query feedback from BigQuery (e.g. thumbs up/down with free-text comments)
2. For each row, send a prompt to GPT-4o to:
   - Assign a sentiment score from -2 to +2
   - Extract the topic or aspect of the original system message being commented on
3. Return structured JSON output
4. Insert results back into a BigQuery output table (e.g. `Model.feedback_sentiment_output`)

## 🧪 Running the Pipeline Locally

1. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Set up your `.env`**:
   ```
   OPENAI_API_KEY=your-key-here
   BIGQUERY_PROJECT=your-gcp-project
   BIGQUERY_DATASET=your-dataset
   ```

3. **Run the test script** (20-row sample):
   ```bash
   python test_llm_pipeline.py
   ```

4. **Run full BigQuery pipeline**:
   ```bash
   python main_llm_pipeline.py
   ```

## 📈 Example Output Schema

| feedback_id | sentiment_score | sentiment_label     | comment_aspect       | model_used |
|-------------|------------------|----------------------|-----------------------|-------------|
| 12345       | -2               | strongly negative    | message clarity       | gpt-4o      |
| 12346       | +1               | slightly positive    | system tone           | gpt-4o      |

## 🔮 Future Plans

- Add support for multilingual feedback
- Hook into Slack or email alerts on extreme negative feedback
- Compare LLM model performance (Claude vs GPT-4o)
- Export labeled data for model fine-tuning

## 📄 License

MIT License. Feel free to use and adapt this pipeline for your own feedback analysis workflows.

Copyright 2025-2026 Corin Stedman (space-lumps)

See the [LICENSE](LICENSE) file for full details.

---

Built with care to bring nuance to user sentiment.
