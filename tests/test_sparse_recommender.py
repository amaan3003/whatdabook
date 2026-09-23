import unittest
from unittest.mock import patch

import pandas as pd
from scipy.sparse import csr_matrix, issparse

import userBasedMLmodel as model


class SparseRecommenderTests(unittest.TestCase):
    def test_loaded_model_stays_sparse(self):
        self.assertTrue(issparse(model.similarity))

    def test_matches_previous_ranking_including_ties_zeros_and_negative_scores(self):
        dense = [
            [1.0, 0.8, 0.8, 0.0, -0.1],
            [0.8, 1.0, 0.0, 0.0, -0.1],
            [0.8, 0.0, 1.0, 0.3, 0.0],
            [0.0, 0.0, 0.3, 1.0, 0.0],
            [-0.1, -0.1, 0.0, 0.0, 1.0],
        ]
        names = pd.Index(['A', 'B', 'C', 'D', 'E'])
        with patch.object(model, 'similarity', csr_matrix(dense)), patch.object(
            model, 'book_names', names
        ):
            for index, title in enumerate(names):
                for count in (1, 3, 10):
                    expected = sorted(enumerate(dense[index]), key=lambda x: x[1], reverse=True)
                    self.assertEqual(
                        model.recommend(title, count),
                        [names[i] for i, _ in expected[1:count + 1]],
                    )
            self.assertEqual(model.recommend('Unknown'), [])

    def test_only_one_row_is_expanded(self):
        original = csr_matrix.toarray
        shapes = []

        def observe(matrix, *args, **kwargs):
            shapes.append(matrix.shape)
            return original(matrix, *args, **kwargs)

        with patch.object(csr_matrix, 'toarray', observe):
            model.recommend(model.book_names[0])
        self.assertEqual(shapes, [(1, model.similarity.shape[1])])
