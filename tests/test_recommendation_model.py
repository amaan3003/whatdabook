import unittest

from recommendationModel import get_genres, get_similar_books


class GenreRecommendationTests(unittest.TestCase):
    def test_extracts_genres_with_common_llm_formatting(self):
        summary = "📖 *Title:* Dune\n\n🎭 **Genre:** Sci-Fi / Adventure"

        genres = get_genres(summary)

        self.assertEqual(genres, ["science fiction", "adventure"])

    def test_returns_books_for_a_common_atomic_genre(self):
        recommendations = get_similar_books(["Fantasy"], n=3)

        self.assertEqual(len(recommendations), 3)
        self.assertTrue(all(isinstance(title, str) for title in recommendations))

    def test_returns_no_books_for_an_unknown_genre(self):
        recommendations = get_similar_books(["totally invented genre"], n=3)

        self.assertEqual(recommendations, [])


if __name__ == "__main__":
    unittest.main()
