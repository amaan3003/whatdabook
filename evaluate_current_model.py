"""Evaluate WhatDaBook's saved personalized recommender offline.

The script uses the existing model artifacts without importing
``userBasedMLmodel.py`` because that module converts the entire similarity
matrix to a dense array. Keeping the matrix sparse makes full-dataset
evaluation practical while preserving the current recommendation rules.
"""

from argparse import ArgumentParser
from collections import Counter
from dataclasses import dataclass
from math import log2
from pathlib import Path
import pickle

import pandas as pd
from scipy.sparse import load_npz


DEFAULT_DATA_DIRECTORY = Path("data/processed/goodbooks-10k")
DEFAULT_BOOKS_PATH = Path("data/raw/goodbooks-10k/books.csv")
DEFAULT_REPORT_PATH = Path("reports/current_model_evaluation.md")
POSITIVE_RATING_MINIMUM = 4
SEED_NEIGHBORS = 5
RECOMMENDATION_COUNT = 10


@dataclass
class RankingTotals:
    users: int = 0
    hits: int = 0
    reciprocal_rank: float = 0.0
    discounted_gain: float = 0.0

    def add(self, recommendations, target):
        self.users += 1
        try:
            rank = recommendations.index(target) + 1
        except ValueError:
            return

        self.hits += 1
        self.reciprocal_rank += 1 / rank
        self.discounted_gain += 1 / log2(rank + 1)

    def metrics(self):
        if not self.users:
            return {"hit_rate": 0.0, "mrr": 0.0, "ndcg": 0.0}
        return {
            "hit_rate": self.hits / self.users,
            "mrr": self.reciprocal_rank / self.users,
            "ndcg": self.discounted_gain / self.users,
        }


def parse_arguments():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--similarity", type=Path, default=Path("similarity.npz"))
    parser.add_argument("--book-names", type=Path, default=Path("book_names.pkl"))
    parser.add_argument("--books", type=Path, default=DEFAULT_BOOKS_PATH)
    parser.add_argument(
        "--train",
        type=Path,
        default=DEFAULT_DATA_DIRECTORY / "train_ratings.csv",
    )
    parser.add_argument(
        "--test",
        type=Path,
        default=DEFAULT_DATA_DIRECTORY / "test_ratings.csv",
    )
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT_PATH)
    return parser.parse_args()


def top_neighbors(similarity, count=SEED_NEIGHBORS):
    """Return each row's neighbors using the deployed model's sort rules."""
    if similarity.shape[0] != similarity.shape[1]:
        raise ValueError("The similarity matrix must be square.")

    neighbors = []
    for row_number in range(similarity.shape[0]):
        row = similarity.getrow(row_number)
        # The deployed code sorts a dense row by score descending. Python's
        # stable sort leaves tied scores in ascending matrix-index order.
        ranked_positions = sorted(
            range(len(row.indices)),
            key=lambda position: (-row.data[position], row.indices[position]),
        )
        ranked_indices = [row.indices[position] for position in ranked_positions]
        neighbors.append(ranked_indices[1 : count + 1])
    return neighbors


def recommend_from_seeds(seed_indices, neighbors, count=RECOMMENDATION_COUNT):
    """Pool five neighbors per liked title, as recommend_for_user currently does."""
    candidates = []
    for seed_index in seed_indices:
        candidates.extend(neighbors[seed_index])

    liked_indices = set(seed_indices)
    candidates = [index for index in candidates if index not in liked_indices]
    return [index for index, _ in Counter(candidates).most_common(count)]


def validate_inputs(similarity, model_names, books, train, test):
    if similarity.shape[0] != len(model_names):
        raise ValueError("Similarity rows and saved book names have different lengths.")
    if len(set(model_names)) != len(model_names):
        raise ValueError("The saved model contains duplicate book titles.")

    for frame_name, frame in (("train", train), ("test", test)):
        missing = {"user_id", "book_id", "rating"} - set(frame.columns)
        if missing:
            raise ValueError(f"{frame_name} data is missing: {', '.join(sorted(missing))}")

    if {"book_id", "title"} - set(books.columns):
        raise ValueError("Book metadata must contain book_id and title.")
    if test["user_id"].duplicated().any():
        raise ValueError("Each test user must have exactly one hidden book.")


def popularity_ranking(train):
    """Rank books by positive-rating count, then book ID for stable ties."""
    positive = train.loc[train["rating"] >= POSITIVE_RATING_MINIMUM]
    counts = positive.groupby("book_id").size().rename("positive_ratings")
    ranked = counts.reset_index().sort_values(
        ["positive_ratings", "book_id"], ascending=[False, True]
    )
    return ranked["book_id"].astype(int).tolist()


def top_unseen_popular(ranked_book_ids, seen_book_ids, count=RECOMMENDATION_COUNT):
    recommendations = []
    for book_id in ranked_book_ids:
        if book_id not in seen_book_ids:
            recommendations.append(book_id)
            if len(recommendations) == count:
                break
    return recommendations


def evaluate(similarity, model_names, books, train, test, progress_every=10_000):
    validate_inputs(similarity, model_names, books, train, test)

    model_names = list(model_names)
    model_index_by_title = {title: index for index, title in enumerate(model_names)}
    title_by_book_id = books.set_index("book_id")["title"].to_dict()
    hidden_by_user = test.set_index("user_id")["book_id"].astype(int).to_dict()
    neighbors = top_neighbors(similarity)
    popular_books = popularity_ranking(train)

    overall_model = RankingTotals()
    evaluable_model = RankingTotals()
    baseline = RankingTotals()
    users_with_model_history = 0
    hidden_titles_in_model = 0
    users_fully_evaluable = 0
    total_model_recommendations = 0
    repeated_read_recommendations = 0
    recommended_model_indices = set()

    grouped_train = train.groupby("user_id", sort=False)
    for position, (user_id, history) in enumerate(grouped_train, start=1):
        if user_id not in hidden_by_user:
            continue

        hidden_book_id = hidden_by_user[user_id]
        hidden_title = title_by_book_id.get(hidden_book_id)
        target_model_index = model_index_by_title.get(hidden_title)
        if target_model_index is not None:
            hidden_titles_in_model += 1

        seen_book_ids = set(history["book_id"].astype(int))
        seen_titles = {
            title_by_book_id[book_id]
            for book_id in seen_book_ids
            if book_id in title_by_book_id
        }
        positive_book_ids = history.loc[
            history["rating"] >= POSITIVE_RATING_MINIMUM, "book_id"
        ].astype(int)
        seed_indices = [
            model_index_by_title[title_by_book_id[book_id]]
            for book_id in positive_book_ids
            if book_id in title_by_book_id
            and title_by_book_id[book_id] in model_index_by_title
        ]

        recommendation_indices = recommend_from_seeds(seed_indices, neighbors)
        recommendation_titles = [model_names[index] for index in recommendation_indices]
        overall_model.add(recommendation_indices, target_model_index)

        if seed_indices:
            users_with_model_history += 1
            total_model_recommendations += len(recommendation_indices)
            recommended_model_indices.update(recommendation_indices)
            repeated_read_recommendations += sum(
                title in seen_titles for title in recommendation_titles
            )

        if seed_indices and target_model_index is not None:
            users_fully_evaluable += 1
            evaluable_model.add(recommendation_indices, target_model_index)

        baseline_recommendations = top_unseen_popular(popular_books, seen_book_ids)
        baseline.add(baseline_recommendations, hidden_book_id)

        if progress_every and position % progress_every == 0:
            print(f"  Evaluated {position:,} training users...")

    total_users = len(test)
    if overall_model.users != total_users:
        missing_users = total_users - overall_model.users
        raise ValueError(f"{missing_users:,} test users have no training history.")

    return {
        "total_users": total_users,
        "model_books": len(model_names),
        "goodbooks_books": books["book_id"].nunique(),
        "catalog_title_matches": books["title"].isin(model_index_by_title).sum(),
        "hidden_titles_in_model": hidden_titles_in_model,
        "users_with_model_history": users_with_model_history,
        "users_fully_evaluable": users_fully_evaluable,
        "overall_model": overall_model.metrics(),
        "evaluable_model": evaluable_model.metrics(),
        "baseline": baseline.metrics(),
        "average_recommendations": (
            total_model_recommendations / users_with_model_history
            if users_with_model_history
            else 0.0
        ),
        "repeat_rate": (
            repeated_read_recommendations / total_model_recommendations
            if total_model_recommendations
            else 0.0
        ),
        "recommended_catalog_coverage": len(recommended_model_indices) / len(model_names),
    }


def percent(value):
    return f"{value * 100:.2f}%"


def build_report(results):
    total = results["total_users"]
    overall = results["overall_model"]
    evaluable = results["evaluable_model"]
    baseline = results["baseline"]
    baseline_lift = (
        overall["hit_rate"] / baseline["hit_rate"]
        if baseline["hit_rate"]
        else 0.0
    )
    matched_hidden = results["hidden_titles_in_model"]
    matched_history = results["users_with_model_history"]
    fully_evaluable = results["users_fully_evaluable"]

    return f"""# Current personalized model evaluation

This report evaluates the saved `similarity.npz` and `book_names.pkl`
artifacts against the deterministic Goodbooks-10k holdout split. For each
user, one book rated 4 or 5 is hidden. The model receives the remaining
positively rated books and succeeds when the hidden title appears in its top
{RECOMMENDATION_COUNT} recommendations.

## Results

- Test users: {total:,}
- Exact catalog-title matches: {results['catalog_title_matches']:,} of {results['goodbooks_books']:,} Goodbooks books
- Users with at least one liked training title recognized by the model: {matched_history:,} ({percent(matched_history / total)})
- Hidden test titles recognized by the model: {matched_hidden:,} ({percent(matched_hidden / total)})
- Users with both recognized history and a recognized hidden title: {fully_evaluable:,} ({percent(fully_evaluable / total)})

### Current personalized model — all test users

- Hit Rate@{RECOMMENDATION_COUNT}: {percent(overall['hit_rate'])}
- MRR@{RECOMMENDATION_COUNT}: {overall['mrr']:.4f}
- NDCG@{RECOMMENDATION_COUNT}: {overall['ndcg']:.4f}

### Current personalized model — fully evaluable users only

- Hit Rate@{RECOMMENDATION_COUNT}: {percent(evaluable['hit_rate'])}
- MRR@{RECOMMENDATION_COUNT}: {evaluable['mrr']:.4f}
- NDCG@{RECOMMENDATION_COUNT}: {evaluable['ndcg']:.4f}

The conditional result measures ranking quality when exact title matching
allows the model to operate. It must be shown beside the all-user result; on
its own it would hide catalog and input failures.

### Popularity baseline — all test users

- Hit Rate@{RECOMMENDATION_COUNT}: {percent(baseline['hit_rate'])}
- MRR@{RECOMMENDATION_COUNT}: {baseline['mrr']:.4f}
- NDCG@{RECOMMENDATION_COUNT}: {baseline['ndcg']:.4f}

The baseline ranks books by the number of 4-5 star ratings in the training
set and removes books already rated by that user.

## What the result means

The personalized model's all-user Hit Rate is {baseline_lift:.2f} times the
popularity baseline, so the saved similarities contain useful preference
signal. The model is doing more than recommending globally popular books.

The two clearest weaknesses are title matching and already-read results.
Exact matching prevents {percent(1 - matched_hidden / total)} of hidden test
books from being found, while the current recommender removes liked seed books
but can return books the user rated 1-3. Fixing those system behaviors is the
most direct next experiment before replacing the collaborative-filtering
algorithm.

## Additional behavior

- Average results returned when the model recognizes user history: {results['average_recommendations']:.2f}
- Recommendations that repeat a book already rated by the user: {percent(results['repeat_rate'])}
- Fraction of the saved model catalog ever recommended: {percent(results['recommended_catalog_coverage'])}

## Interpretation limits

The saved model was built from separate Goodreads scrape files referenced by
an absolute local path in `buildSimilarity.py`. Those source files and a
recorded training split are not in the repository, so the artifact cannot yet
be rebuilt or checked conclusively for overlap with Goodbooks-10k. Treat this
as a black-box evaluation of the current artifact, not a leakage-proof model
experiment.

Titles are matched exactly because that is what the deployed recommender does.
Different subtitles, series suffixes, capitalization, or editions are counted
as unmatched. This reveals the production behavior but also means title entity
resolution is part of the measured system quality.
"""


def main():
    args = parse_arguments()
    required_paths = (
        args.similarity,
        args.book_names,
        args.books,
        args.train,
        args.test,
    )
    missing_paths = [str(path) for path in required_paths if not path.exists()]
    if missing_paths:
        raise SystemExit("Missing required files: " + ", ".join(missing_paths))

    print("Loading model and evaluation data...")
    similarity = load_npz(args.similarity).tocsr()
    with args.book_names.open("rb") as file:
        model_names = pickle.load(file)
    books = pd.read_csv(args.books, usecols=["book_id", "title"])
    train = pd.read_csv(args.train, dtype={"rating": "int8"})
    test = pd.read_csv(args.test, dtype={"rating": "int8"})

    print("Evaluating current personalized model and popularity baseline...")
    results = evaluate(similarity, model_names, books, train, test)
    report = build_report(results)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(report, encoding="utf-8")

    print(report)
    print(f"Report saved to {args.report}")


if __name__ == "__main__":
    main()
