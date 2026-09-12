import unittest

import pandas as pd

from prepare_evaluation_data import split_ratings


class EvaluationSplitTests(unittest.TestCase):
    def test_hides_each_eligible_users_last_positive_rating(self):
        ratings = pd.DataFrame(
            [
                {"user_id": 1, "book_id": 10, "rating": 2},
                {"user_id": 1, "book_id": 11, "rating": 5},
                {"user_id": 1, "book_id": 12, "rating": 4},
                {"user_id": 2, "book_id": 20, "rating": 3},
                {"user_id": 2, "book_id": 21, "rating": 2},
                {"user_id": 3, "book_id": 30, "rating": 5},
                {"user_id": 4, "book_id": 40, "rating": 4},
                {"user_id": 4, "book_id": 41, "rating": 5},
            ]
        )

        train_ratings, test_ratings = split_ratings(ratings)

        self.assertEqual(test_ratings["user_id"].tolist(), [1, 4])
        self.assertEqual(test_ratings["book_id"].tolist(), [12, 41])
        self.assertEqual(len(train_ratings) + len(test_ratings), len(ratings))
        self.assertIn(3, train_ratings["user_id"].tolist())

    def test_same_input_always_produces_same_split(self):
        ratings = pd.DataFrame(
            [
                {"user_id": 1, "book_id": 10, "rating": 5},
                {"user_id": 1, "book_id": 11, "rating": 4},
            ]
        )

        first_train, first_test = split_ratings(ratings)
        second_train, second_test = split_ratings(ratings)

        pd.testing.assert_frame_equal(first_train, second_train)
        pd.testing.assert_frame_equal(first_test, second_test)

    def test_rejects_missing_columns(self):
        ratings = pd.DataFrame([{"user_id": 1, "rating": 5}])

        with self.assertRaisesRegex(ValueError, "Missing required columns: book_id"):
            split_ratings(ratings)

    def test_rejects_invalid_ratings(self):
        ratings = pd.DataFrame(
            [{"user_id": 1, "book_id": 10, "rating": "excellent"}]
        )

        with self.assertRaisesRegex(ValueError, "invalid ratings"):
            split_ratings(ratings)

    def test_rejects_duplicate_user_book_pairs(self):
        ratings = pd.DataFrame(
            [
                {"user_id": 1, "book_id": 10, "rating": 5},
                {"user_id": 1, "book_id": 10, "rating": 4},
            ]
        )

        with self.assertRaisesRegex(ValueError, "duplicate user-book pairs"):
            split_ratings(ratings)


if __name__ == "__main__":
    unittest.main()
