import re

import requests


PIRATEREADS_BASE_URL = "https://api.piratereads.com"
REQUEST_TIMEOUT_SECONDS = 15
MAX_LIKED_BOOKS = 10
MAX_DISLIKED_BOOKS = 5

def extract_user_id(url: str):
    if not isinstance(url, str):
        return None

    match = re.search(r"/user/show/(\d+)", url)
    return match.group(1) if match else None



def scrape_goodreads(user_url):
    user_id = extract_user_id(user_url)
    if user_id is None:
        return None

    url = f"{PIRATEREADS_BASE_URL}/{user_id}/read"

    try:
        response = requests.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
        data = response.json()
    except (requests.RequestException, ValueError):
        return None

    if not isinstance(data, dict) or not isinstance(data.get("books"), list):
        return None

    return data


def build_reading_profile(goodreads_data):
    """Extract a small set of strong taste signals from Goodreads data."""
    if not isinstance(goodreads_data, dict):
        return None

    books = goodreads_data.get("books")
    if not isinstance(books, list):
        return None

    liked_books = []
    disliked_books = []
    seen_titles = set()

    for book in books:
        if not isinstance(book, dict):
            continue

        title = book.get("book_title") or book.get("title")
        if not isinstance(title, str):
            continue

        title = " ".join(title.split())[:200]
        normalized_title = title.casefold()
        if not title or normalized_title in seen_titles:
            continue

        try:
            rating = float(book.get("rating"))
        except (TypeError, ValueError):
            continue

        if not 1 <= rating <= 5:
            continue

        if rating >= 4:
            liked_books.append((title, rating))
            seen_titles.add(normalized_title)
        elif rating <= 2:
            disliked_books.append((title, rating))
            seen_titles.add(normalized_title)

    liked_books.sort(key=lambda item: item[1], reverse=True)
    disliked_books.sort(key=lambda item: item[1])

    profile = {
        "liked_books": [title for title, _ in liked_books[:MAX_LIKED_BOOKS]],
        "disliked_books": [
            title for title, _ in disliked_books[:MAX_DISLIKED_BOOKS]
        ],
    }

    if not profile["liked_books"] and not profile["disliked_books"]:
        return None

    return profile
