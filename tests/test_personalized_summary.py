import unittest
from unittest.mock import Mock, patch

import requests

from bookRatingScraper import (
    build_reading_profile,
    extract_rated_books,
    extract_user_id,
    find_existing_rating,
    scrape_goodreads,
)
from summarizer import (
    _parse_similar_book_suggestions,
    build_summary_prompt,
    suggest_similar_books,
)


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

    def test_finds_existing_rating_from_multiline_cover_text(self):
        data = {
            "books": [
                {"book_title": "Dune (Dune, #1)", "rating": 5},
                {"book_title": "The Hobbit", "rating": 4},
            ]
        }

        match = find_existing_rating("DUNE\nFRANK HERBERT", data)

        self.assertEqual(match, {"book_title": "Dune (Dune, #1)", "rating": 5})

    def test_does_not_match_short_title_inside_unrelated_cover_text(self):
        data = {"books": [{"book_title": "It", "rating": 4}]}

        match = find_existing_rating("An International History\nJohn Smith", data)

        self.assertIsNone(match)


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

        self.assertIn("Personal Match", prompt)
        self.assertIn("whole number from 0 to 5", prompt)
        self.assertIn("exactly five symbols", prompt)
        self.assertIn("not a statistical probability", prompt)
        self.assertIn("Why you might like it", prompt)
        self.assertIn("Why you might not like it", prompt)
        self.assertIn("Dune", prompt)
        self.assertIn("Not For Me", prompt)

    def test_keeps_generic_prompt_without_profile(self):
        prompt = build_summary_prompt("Example book information")

        self.assertNotIn("Personal Match", prompt)
        self.assertNotIn("Why you might like it", prompt)
        self.assertNotIn("Reader preference data", prompt)
        self.assertIn("What it's about", prompt)
        self.assertIn("spoiler-free", prompt)
        self.assertNotIn("*📄 Description:*", prompt)
        self.assertNotIn("*🧠 Summary:*", prompt)
        self.assertIn("What people liked", prompt)
        self.assertIn("Final Verdict", prompt)

    def test_uses_actual_goodreads_rating_for_an_already_read_book(self):
        profile = {
            "liked_books": ["Dune"],
            "disliked_books": [],
            "existing_rating": {
                "book_title": "Dune (Dune, #1)",
                "rating": 5,
            },
        }

        prompt = build_summary_prompt("DUNE\nFRANK HERBERT", profile)

        self.assertIn("Your Goodreads Rating", prompt)
        self.assertIn("★★★★★ 5/5", prompt)
        self.assertIn("already rated this book", prompt)
        self.assertNotIn("*⭐ Personal Match:*", prompt)

    def test_middle_match_score_requires_mixed_evidence(self):
        profile = {"liked_books": ["Dune"], "disliked_books": []}

        prompt = build_summary_prompt("Example book information", profile)

        self.assertIn("Do not choose 3 merely because evidence is limited", prompt)
        self.assertIn("positive and negative evidence", prompt)


class SimilarBookFallbackTests(unittest.TestCase):
    def test_parses_json_even_when_wrapped_in_a_code_fence(self):
        content = '```json\n["Book One — Author A", "Book Two — Author B"]\n```'

        suggestions = _parse_similar_book_suggestions(content, count=5)

        self.assertEqual(
            suggestions,
            ["Book One — Author A", "Book Two — Author B"],
        )

    def test_rejects_malformed_fallback_output(self):
        self.assertEqual(_parse_similar_book_suggestions("not json", count=5), [])

    @patch("summarizer.DEEPSEEK_API_KEY", "test-key")
    @patch("summarizer.requests.post")
    def test_requests_similar_books_with_limited_cover_context(self, mock_post):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": '["A Suitable Boy — Vikram Seth"]',
                    }
                }
            ]
        }
        mock_post.return_value = response

        suggestions = suggest_similar_books(
            "BANARAS TALKIES",
            genres=["indian literature"],
            count=1,
        )

        self.assertEqual(suggestions, ["A Suitable Boy — Vikram Seth"])
        payload = mock_post.call_args.kwargs["json"]
        self.assertIn("BANARAS TALKIES", payload["messages"][1]["content"])
        self.assertIn("indian literature", payload["messages"][1]["content"])


if __name__ == "__main__":
    unittest.main()
