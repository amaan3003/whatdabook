import unittest
from unittest.mock import Mock, patch

import requests

from book_metadata import amazon_search_url, fetch_book_metadata


class BookMetadataTests(unittest.TestCase):
    @patch("book_metadata.requests.get")
    def test_returns_open_library_card_metadata(self, mock_get):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "docs": [
                {
                    "key": "/works/OL893415W",
                    "title": "Unrelated Result",
                    "author_name": ["Wrong Author"],
                },
                {
                    "key": "/works/OL893414W",
                    "title": "Dune",
                    "author_name": ["Frank Herbert"],
                    "cover_i": 11481354,
                    "first_publish_year": 1965,
                },
            ]
        }
        mock_get.return_value = response

        metadata = fetch_book_metadata("Dune")

        self.assertEqual(metadata["title"], "Dune")
        self.assertEqual(metadata["authors"], ["Frank Herbert"])
        self.assertEqual(metadata["first_publish_year"], 1965)
        self.assertEqual(metadata["details_url"], "https://openlibrary.org/works/OL893414W")
        self.assertIn("11481354", metadata["cover_url"])

    @patch("book_metadata.requests.get")
    def test_network_failure_returns_useful_title_only_fallback(self, mock_get):
        mock_get.side_effect = requests.Timeout

        metadata = fetch_book_metadata("Dune")

        self.assertEqual(metadata["title"], "Dune")
        self.assertEqual(metadata["authors"], [])
        self.assertIsNone(metadata["cover_url"])
        self.assertIn("amazon.com", metadata["amazon_url"])

    def test_amazon_search_url_encodes_the_title(self):
        url = amazon_search_url("Dune & Messiah")

        self.assertIn("Dune+%26+Messiah", url)
        self.assertIn("i=stripbooks", url)


if __name__ == "__main__":
    unittest.main()
