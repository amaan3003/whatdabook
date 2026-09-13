"""Fetch optional display metadata for Telegram recommendation cards."""

from difflib import SequenceMatcher
import re
from urllib.parse import urlencode

import requests


OPEN_LIBRARY_SEARCH_URL = "https://openlibrary.org/search.json"
OPEN_LIBRARY_BASE_URL = "https://openlibrary.org"
OPEN_LIBRARY_COVER_URL = "https://covers.openlibrary.org/b/id/{cover_id}-L.jpg"
REQUEST_TIMEOUT_SECONDS = 8
USER_AGENT = "WhatDaBook/1.0 (https://github.com/amaan3003/whatdabook)"


def _normalized_title(title):
    return " ".join(re.findall(r"[a-z0-9]+", title.casefold()))


def _title_similarity(requested_title, candidate_title):
    requested = _normalized_title(requested_title)
    candidate = _normalized_title(candidate_title)
    if not requested or not candidate:
        return 0.0
    if requested in candidate or candidate in requested:
        return 1.0
    return SequenceMatcher(None, requested, candidate).ratio()


def amazon_search_url(title):
    return "https://www.amazon.com/s?" + urlencode(
        {"k": title, "i": "stripbooks"}
    )


def fetch_book_metadata(title):
    """Return the best credible Open Library match or a title-only fallback."""
    fallback = {
        "title": title,
        "authors": [],
        "first_publish_year": None,
        "cover_url": None,
        "details_url": None,
        "amazon_url": amazon_search_url(title),
    }

    try:
        response = requests.get(
            OPEN_LIBRARY_SEARCH_URL,
            params={
                "title": title,
                "limit": 3,
                "fields": "key,title,author_name,cover_i,first_publish_year",
            },
            headers={"User-Agent": USER_AGENT},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        documents = response.json().get("docs", [])
    except (requests.RequestException, ValueError, AttributeError):
        return fallback

    credible_matches = [
        document
        for document in documents
        if isinstance(document, dict)
        and isinstance(document.get("title"), str)
        and _title_similarity(title, document["title"]) >= 0.65
    ]
    if not credible_matches:
        return fallback

    match = max(
        credible_matches,
        key=lambda document: _title_similarity(title, document["title"]),
    )
    cover_id = match.get("cover_i")
    work_key = match.get("key")
    authors = match.get("author_name")
    if isinstance(authors, list):
        authors = [author for author in authors if isinstance(author, str)]
    else:
        authors = []

    return {
        **fallback,
        "authors": authors,
        "first_publish_year": match.get("first_publish_year"),
        "cover_url": (
            OPEN_LIBRARY_COVER_URL.format(cover_id=cover_id) if cover_id else None
        ),
        "details_url": (
            f"{OPEN_LIBRARY_BASE_URL}{work_key}"
            if isinstance(work_key, str) and work_key.startswith("/")
            else None
        ),
    }


def fetch_recommendation_metadata(titles):
    """Fetch a small recommendation list sequentially to respect the public API."""
    return [fetch_book_metadata(title) for title in titles]
