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
            {"role": "system", "content": "You are a book info formatter. Return ONLY a clean, well-spaced message with emojis."},
            {"role": "user", "content": f"""Format this book info into a clean Telegram message. Use this exact structure:

📖 *Title:* [book name]

*Author:* [author name]

*Genre:* [genre]

*📄 Description:*
[2-3 line simple description]

*🧠 Summary:*
[3-4 lines covering plot, themes, style]


*✅ What people liked*
[2 bullet points about what people liked in the book]
*❌ What people disliked*
[2 bullet points about what people disliked in the book]

*📊 Final Verdict:*
[1-2 lines on reviews/popularity and final verdict]


Rules:
- Use *bold* for labels only
- Keep it simple and readable
- No extra commentary
- Space between sections

Book info:
{description}"""}
        ],
        "max_tokens": 500,
        "temperature": 0.2
    }

    response = requests.post(DEEPSEEK_ENDPOINT, json=payload, headers=HEADERS)
    return response.json()["choices"][0]["message"]["content"]