import unittest
from unittest.mock import Mock, patch

import requests

from bookRatingScraper import (
    build_reading_profile,
    extract_rated_books,
    extract_user_id,
    scrape_goodreads,
)
from summarizer import build_summary_prompt


class ReadingProfileTests(unittest.TestCase):
    def test_builds_profile_and_ignores_unusable_entries(self):
        data = {
            "books": [
                {"book_title": "Dune", "rating": 5},
                {"book_title": "The Hobbit", "rating": "4"},
                {"book_title": "Neutral Book", "rating": 3},
                {"book_title": "Not For Me", "rating": 1},
                {"book_title": "dune", "rating": 4},
                {"book_title": "Missing Rating"},
                {"book_title": "Invalid Rating", "rating": "excellent"},
                {"rating": 5},
                "not a book",
            ]
        }

        profile = build_reading_profile(data)

        self.assertEqual(profile["liked_books"], ["Dune", "The Hobbit"])
        self.assertEqual(profile["disliked_books"], ["Not For Me"])

    def test_returns_none_without_preference_signals(self):
        data = {"books": [{"book_title": "Neutral Book", "rating": 3}]}

        self.assertIsNone(build_reading_profile(data))
        self.assertIsNone(build_reading_profile({"books": []}))
        self.assertIsNone(build_reading_profile(None))

    def test_extracts_all_valid_ratings_for_opted_in_training(self):
        data = {
            "books": [
                {"book_title": "Dune", "rating": "5"},
                {"book_title": "Neutral Book", "rating": 3},
                {"book_title": "Unrated Book", "rating": 0},
                {"book_title": "DUNE", "rating": 4},
            ]
        }

        self.assertEqual(
            extract_rated_books(data),
            [
                {"book_title": "Dune", "rating": 5},
                {"book_title": "Neutral Book", "rating": 3},
            ],
        )

    def test_extracts_goodreads_user_id(self):
        self.assertEqual(
            extract_user_id("https://www.goodreads.com/user/show/12345-reader"),
            "12345",
        )
        self.assertIsNone(extract_user_id("https://www.goodreads.com/book/show/12345"))


class GoodreadsRequestTests(unittest.TestCase):
    @patch("bookRatingScraper.requests.get")
    def test_request_failure_returns_none(self, mock_get):
        mock_get.side_effect = requests.Timeout

        result = scrape_goodreads("https://www.goodreads.com/user/show/12345-reader")

        self.assertIsNone(result)

    @patch("bookRatingScraper.requests.get")
    def test_invalid_response_shape_returns_none(self, mock_get):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"unexpected": "data"}
        mock_get.return_value = response

        result = scrape_goodreads("https://www.goodreads.com/user/show/12345-reader")

        self.assertIsNone(result)


class SummaryPromptTests(unittest.TestCase):
    def test_adds_personal_sections_when_profile_exists(self):
        profile = {
            "liked_books": ["Dune"],
            "disliked_books": ["Not For Me"],
        }

        prompt = build_summary_prompt("Example book information", profile)

        self.assertIn("Why you might like it", prompt)
        self.assertIn("Why you might not like it", prompt)
        self.assertIn("Dune", prompt)
        self.assertIn("Not For Me", prompt)

    def test_keeps_generic_prompt_without_profile(self):
        prompt = build_summary_prompt("Example book information")

        self.assertNotIn("Why you might like it", prompt)
        self.assertNotIn("Reader preference data", prompt)
        self.assertIn("What people liked", prompt)
        self.assertIn("Final Verdict", prompt)


if __name__ == "__main__":
    unittest.main()
