import requests
import os
from dotenv import load_dotenv

load_dotenv()

DEEPSEEK_API_KEY = os.getenv("TENSORX_API")
DEEPSEEK_ENDPOINT = "https://api.tensorix.ai/v1/chat/completions"
HEADERS = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}"}

def summarize(description: str) -> str:
    payload = {
        "model": "deepseek/deepseek-v4-flash",
        "messages": [
            {"role": "system", "content": "You are a book summarizer. Give genre, plot & public reception in 4-5 lines."},
            {"role": "user", "content": f"Summarize this book:\n{description}"}
        ],
        "max_tokens": 300,
        "temperature": 0.2
    }

    response = requests.post(DEEPSEEK_ENDPOINT, json=payload, headers=HEADERS)
    return response.json()["choices"][0]["message"]["content"]
