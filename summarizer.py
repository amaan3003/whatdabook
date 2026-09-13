import os
import json

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
    existing_rating = None

    if isinstance(reading_profile, dict):
        liked_books = reading_profile.get("liked_books") or []
        disliked_books = reading_profile.get("disliked_books") or []
        possible_existing_rating = reading_profile.get("existing_rating")
        if (
            isinstance(possible_existing_rating, dict)
            and isinstance(possible_existing_rating.get("book_title"), str)
            and possible_existing_rating.get("rating") in {1, 2, 3, 4, 5}
        ):
            existing_rating = possible_existing_rating

    has_reading_profile = bool(liked_books or disliked_books or existing_rating)

    personalized_output = ""
    personalized_rules = ""
    reading_context = ""
    if has_reading_profile:
        if existing_rating:
            rating = existing_rating["rating"]
            rating_stars = "★" * rating + "☆" * (5 - rating)
            rating_title = existing_rating["book_title"]
            rating_output = f"""
*⭐ Your Goodreads Rating:*
{rating_stars} {rating}/5
[Clearly state that the reader already rated this book on Goodreads]
"""
            score_rules = """
- Use the exact Goodreads rating shown in the required structure
- Do not include or calculate a Personal Match score for an already-rated book
- Keep the personalised reasons consistent with the reader's actual rating
"""
            existing_rating_context = f"""
The photographed book confidently matches this Goodreads entry:
- {rating_title}: {rating}/5
"""
        else:
            rating_output = """
*⭐ Personal Match:*
[Exactly five star symbols using ★ for filled and ☆ for empty] [integer score]/5
[One short sentence explaining the strongest evidence for the score]
"""
            score_rules = """
- Include the Personal Match section
- Treat Personal Match as a taste-match score, not a statistical probability
- Personal Match must be a whole number from 0 to 5 with exactly five symbols
- Score 5 for a very strong match, 4 for a clear match, 3 for a genuinely mixed
  match, 2 for more conflicts than similarities, 1 for a strong mismatch, and
  0 when there is no meaningful taste overlap
- Do not choose 3 merely because evidence is limited or uncertain; use 3 only
  when concrete positive and negative evidence are reasonably balanced
- Explain limited confidence separately from the numeric score
- Mention at least one provided book title as evidence for the score
- Base the score on connections to both liked and disliked books; do not use
  the photographed book's general popularity as the score
"""
            existing_rating_context = ""

        personalized_output = f"""
{rating_output}

*🎯 Why you might like it*
[2 personalised bullet points based on the reading history]

*⚠️ Why you might not like it*
[2 personalised bullet points based on the reading history]
"""
        personalized_rules = score_rules
        reading_context = f"""
Reader preference data:
Books rated 4 or 5:
{_format_book_list(liked_books) if liked_books else "- No positive ratings available"}

Books rated 1 or 2:
{_format_book_list(disliked_books) if disliked_books else "- No negative ratings available"}
{existing_rating_context}
"""

    return f"""Format this book info into a clean Telegram message. Use this exact structure:

📖 *Title:* [book name]

*Author:* [author name]

*Genre:* [genre]

*📖 What it's about:*
[4-5 spoiler-free lines covering the premise, main themes, and writing style]

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
- Keep the What it's about section spoiler-free
- Keep general reader opinions separate from personalised reasons
- Base personalised reasons only on the provided reading history
- Do not claim certainty about the reader's preferences
- If preference evidence is limited, say so clearly
{personalized_rules}

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


def _parse_similar_book_suggestions(content, count):
    if not isinstance(content, str):
        return []

    array_start = content.find("[")
    array_end = content.rfind("]")
    if array_start == -1 or array_end <= array_start:
        return []

    try:
        suggestions = json.loads(content[array_start : array_end + 1])
    except (json.JSONDecodeError, TypeError):
        return []

    if not isinstance(suggestions, list):
        return []

    cleaned_suggestions = []
    seen = set()
    for suggestion in suggestions:
        if not isinstance(suggestion, str):
            continue
        suggestion = " ".join(suggestion.split())[:200]
        normalized = suggestion.casefold()
        if not suggestion or normalized in seen:
            continue
        cleaned_suggestions.append(suggestion)
        seen.add(normalized)
        if len(cleaned_suggestions) == count:
            break

    return cleaned_suggestions


def suggest_similar_books(book_text, genres=None, count=5):
    """Use DeepSeek only when the local similar-books model has no result."""
    if not isinstance(book_text, str) or not book_text.strip():
        return []
    if not DEEPSEEK_API_KEY:
        raise RuntimeError("The fallback recommendation service is not configured.")

    genre_context = ", ".join(genres or []) or "No reliable genre was extracted"
    prompt = f"""Identify the book from this cover text and recommend {count} real,
published books that are meaningfully similar in themes, tone, or reading
experience. Prefer precise matches over globally popular books. Do not include
the photographed book itself.

Return only a JSON array of strings. Format every string as:
"Book Title — Author"

Extracted genres: {genre_context}

Cover text:
{book_text[:3000]}
"""
    payload = {
        "model": "deepseek/deepseek-v4-flash-0731",
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a careful book discovery assistant. Recommend only "
                    "real published books and follow the requested JSON format."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "max_tokens": 300,
        "temperature": 0.3,
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
        raise RuntimeError("The fallback recommender could not respond.") from error

    return _parse_similar_book_suggestions(content, count)
