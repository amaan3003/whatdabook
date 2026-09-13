import unittest

from scipy.sparse import csr_matrix

from evaluate_current_model import (
    recommend_from_seeds,
    top_neighbors,
    top_unseen_popular,
)


class CurrentModelEvaluationTests(unittest.TestCase):
    def test_sparse_neighbors_match_deployed_dense_sort_order(self):
        similarity = csr_matrix(
            [
                [1.0, 0.8, 0.9, 0.0],
                [0.8, 1.0, 0.7, 0.6],
                [0.9, 0.7, 1.0, 0.5],
                [0.0, 0.6, 0.5, 1.0],
            ]
        )

        neighbors = top_neighbors(similarity, count=2)

        self.assertEqual(neighbors[0], [2, 1])
        self.assertEqual(neighbors[1], [0, 2])

    def test_user_recommendations_favor_repeated_candidates_and_remove_likes(self):
        neighbors = [
            [1, 2, 3],
            [0, 2, 3],
            [0, 1, 3],
            [0, 1, 2],
        ]

        recommendations = recommend_from_seeds([0, 1], neighbors, count=2)

        self.assertEqual(recommendations, [2, 3])

    def test_popularity_baseline_skips_books_already_seen(self):
        recommendations = top_unseen_popular(
            ranked_book_ids=[10, 11, 12, 13],
            seen_book_ids={10, 12},
            count=2,
        )

        self.assertEqual(recommendations, [11, 13])


if __name__ == "__main__":
    unittest.main()
