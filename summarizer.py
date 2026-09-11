import os

import requests
from dotenv import load_dotenv


load_dotenv()

DEEPSEEK_API_KEY = os.getenv("TENSORX_API")
DEEPSEEK_ENDPOINT = "https://api.tensorix.ai/v1/chat/completions"
REQUEST_TIMEOUT_SECONDS = 30


def _format_book_list(book_titles):
    return "\n".join(f"- {title}" for title in book_titles)


def build_summary_prompt(description: str, reading_profile=None) -> str:
    """Build the normal prompt and add personal sections when history exists."""
    liked_books = []
    disliked_books = []

    if isinstance(reading_profile, dict):
        liked_books = reading_profile.get("liked_books") or []
        disliked_books = reading_profile.get("disliked_books") or []

    has_reading_profile = bool(liked_books or disliked_books)

    personalized_output = ""
    reading_context = ""
    if has_reading_profile:
        personalized_output = """
*🎯 Why you might like it*
[2 personalised bullet points based on the reading history]

*⚠️ Why you might not like it*
[2 personalised bullet points based on the reading history]
"""
        reading_context = f"""
Reader preference data:
Books rated 4 or 5:
{_format_book_list(liked_books) if liked_books else "- No positive ratings available"}

Books rated 1 or 2:
{_format_book_list(disliked_books) if disliked_books else "- No negative ratings available"}
"""

    return f"""Format this book info into a clean Telegram message. Use this exact structure:

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
{personalized_output}
*📊 Final Verdict:*
[1-2 lines on reviews/popularity and final verdict]

Rules:
- Use *bold* for labels only
- Keep it simple and readable
- No extra commentary
- Space between sections
- Keep general reader opinions separate from personalised reasons
- Base personalised reasons only on the provided reading history
- Do not claim certainty about the reader's preferences
- If preference evidence is limited, say so clearly

Book info:
{description}
{reading_context}"""


def summarize(description: str, reading_profile=None) -> str:
    """Generate a formatted book summary with optional personalisation."""
    if not isinstance(description, str) or not description.strip():
        raise ValueError("Book information is empty.")

    if not DEEPSEEK_API_KEY:
        raise RuntimeError("The summary service is not configured.")

    payload = {
        "model": "deepseek/deepseek-v4-flash-0731",
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a book information formatter and reading-taste "
                    "assistant. Return ONLY a clean, well-spaced message with emojis."
                ),
            },
            {
                "role": "user",
                "content": build_summary_prompt(description, reading_profile),
            },
        ],
        "max_tokens": 700,
        "temperature": 0.2,
    }
    headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}"}

    try:
        response = requests.post(
            DEEPSEEK_ENDPOINT,
            json=payload,
            headers=headers,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
    except (requests.RequestException, ValueError, KeyError, IndexError, TypeError) as error:
        raise RuntimeError("The summary service could not produce a response.") from error

    if not isinstance(content, str) or not content.strip():
        raise RuntimeError("The summary service returned an empty response.")

    return content.strip()
