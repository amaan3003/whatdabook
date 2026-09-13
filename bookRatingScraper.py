import re
from difflib import SequenceMatcher

import requests


PIRATEREADS_BASE_URL = "https://api.piratereads.com"
REQUEST_TIMEOUT_SECONDS = 15
MAX_LIKED_BOOKS = 10
MAX_DISLIKED_BOOKS = 5


def _normalize_book_text(value):
    if not isinstance(value, str):
        return ""
    return " ".join(re.findall(r"[a-z0-9]+", value.casefold()))


def _title_variants(title):
    variants = {_normalize_book_text(title)}
    for separator in (" (", " ["):
        if separator in title:
            variants.add(_normalize_book_text(title.split(separator, 1)[0]))
    return {variant for variant in variants if variant}


def find_existing_rating(book_text, goodreads_data):
    """Find a confidently recognized cover in the user's complete rated history."""
    if not isinstance(book_text, str) or not book_text.strip():
        return None

    rated_books = extract_rated_books(goodreads_data)
    if not rated_books:
        return None

    normalized_lines = [
        _normalize_book_text(line)
        for line in book_text.splitlines()
        if _normalize_book_text(line)
    ]
    line_windows = set(normalized_lines)
    for window_size in (2, 3):
        for start in range(len(normalized_lines) - window_size + 1):
            line_windows.add(" ".join(normalized_lines[start : start + window_size]))

    normalized_cover = _normalize_book_text(book_text)
    best_match = None
    best_score = 0.0

    for book in rated_books:
        for title_variant in _title_variants(book["book_title"]):
            exact_line_match = title_variant in line_windows
            safe_substring_match = (
                len(title_variant) >= 4
                and f" {title_variant} " in f" {normalized_cover} "
            )
            fuzzy_score = max(
                (
                    SequenceMatcher(None, title_variant, line).ratio()
                    for line in line_windows
                ),
                default=0.0,
            )

            score = 1.0 if exact_line_match or safe_substring_match else fuzzy_score
            if score >= 0.88 and score > best_score:
                best_match = book
                best_score = score

    return best_match

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


def extract_rated_books(goodreads_data):
    """Return unique book titles with valid 1-5 star ratings."""
    if not isinstance(goodreads_data, dict):
        return []

    books = goodreads_data.get("books")
    if not isinstance(books, list):
        return []

    rated_books = []
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

        if rating not in {1, 2, 3, 4, 5}:
            continue

        rated_books.append({"book_title": title, "rating": int(rating)})
        seen_titles.add(normalized_title)

    return rated_books


def build_reading_profile(goodreads_data):
    """Extract a small set of strong taste signals from Goodreads data."""
    rated_books = extract_rated_books(goodreads_data)

    liked_books = [
        (book["book_title"], book["rating"])
        for book in rated_books
        if book["rating"] >= 4
    ]
    disliked_books = [
        (book["book_title"], book["rating"])
        for book in rated_books
        if book["rating"] <= 2
    ]

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
