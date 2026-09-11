"""Inspect the ratings data before training a recommendation model.

This script is intentionally separate from model training. It helps us learn
what is in the dataset and catch data-quality problems before they silently
affect an experiment.
"""

from argparse import ArgumentParser
from pathlib import Path

import pandas as pd


DEFAULT_DATA_DIRECTORY = Path("data/raw/goodbooks-10k")
REQUIRED_RATING_COLUMNS = {"user_id", "book_id", "rating"}


def parse_arguments():
    """Read optional file locations supplied on the command line."""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument(
        "--ratings",
        type=Path,
        default=DEFAULT_DATA_DIRECTORY / "ratings.csv",
        help="Path to ratings.csv",
    )
    parser.add_argument(
        "--books",
        type=Path,
        default=DEFAULT_DATA_DIRECTORY / "books.csv",
        help="Path to books.csv (metadata checks are skipped if it is absent)",
    )
    return parser.parse_args()


def load_ratings(path):
    """Load ratings and stop with a useful message if the file is missing."""
    if not path.exists():
        raise SystemExit(
            f"Ratings file not found: {path}\n"
            "Download Goodbooks-10k and follow data/README.md."
        )

    ratings = pd.read_csv(path)
    missing_columns = REQUIRED_RATING_COLUMNS - set(ratings.columns)
    if missing_columns:
        missing_list = ", ".join(sorted(missing_columns))
        raise SystemExit(f"ratings.csv is missing required columns: {missing_list}")

    return ratings


def print_count_summary(label, counts):
    """Print an easy-to-read summary of ratings per user or per book."""
    print(f"\n{label}")
    print(f"  Minimum: {counts.min():,.0f}")
    print(f"  Median:  {counts.median():,.1f}")
    print(f"  Mean:    {counts.mean():,.1f}")
    print(f"  Maximum: {counts.max():,.0f}")


def inspect_metadata(books_path, valid_ratings):
    """Check whether each rated book has a matching metadata row."""
    print("\nBOOK METADATA")
    if not books_path.exists():
        print(f"  Skipped: {books_path} was not found.")
        return

    books = pd.read_csv(books_path)
    if "book_id" not in books.columns:
        print("  Could not check coverage: books.csv has no book_id column.")
        return

    duplicate_book_ids = books.duplicated(subset=["book_id"]).sum()
    rated_book_ids = set(valid_ratings["book_id"])
    metadata_book_ids = set(books["book_id"].dropna())
    missing_metadata = rated_book_ids - metadata_book_ids

    print(f"  Metadata rows: {len(books):,}")
    print(f"  Duplicate book IDs: {duplicate_book_ids:,}")
    print(f"  Rated books missing metadata: {len(missing_metadata):,}")


def main():
    args = parse_arguments()
    ratings = load_ratings(args.ratings)

    # Convert the rating column explicitly so text or blank values can be found.
    numeric_ratings = pd.to_numeric(ratings["rating"], errors="coerce")
    invalid_rating_mask = numeric_ratings.isna() | ~numeric_ratings.isin(
        [1, 2, 3, 4, 5]
    )
    missing_id_mask = ratings[["user_id", "book_id"]].isna().any(axis=1)
    valid_mask = ~(invalid_rating_mask | missing_id_mask)
    valid_ratings = ratings.loc[valid_mask].copy()
    valid_ratings["rating"] = numeric_ratings.loc[valid_mask]

    duplicate_pairs = ratings.duplicated(subset=["user_id", "book_id"]).sum()
    user_count = valid_ratings["user_id"].nunique()
    book_count = valid_ratings["book_id"].nunique()
    possible_ratings = user_count * book_count
    density = len(valid_ratings) / possible_ratings if possible_ratings else 0

    print("GOODBOOKS RATINGS INSPECTION")
    print(f"  File: {args.ratings}")
    print(f"  Total rows: {len(ratings):,}")
    print(f"  Valid rows: {len(valid_ratings):,}")
    print(f"  Unique users: {user_count:,}")
    print(f"  Unique books: {book_count:,}")
    print(f"  Missing user or book IDs: {missing_id_mask.sum():,}")
    print(f"  Invalid ratings: {invalid_rating_mask.sum():,}")
    print(f"  Duplicate user-book pairs: {duplicate_pairs:,}")
    print(f"  Matrix density: {density:.4%}")
    print(f"  Matrix sparsity: {1 - density:.4%}")

    print("\nRATING DISTRIBUTION")
    rating_distribution = valid_ratings["rating"].value_counts().sort_index()
    for rating, count in rating_distribution.items():
        percentage = count / len(valid_ratings) if len(valid_ratings) else 0
        print(f"  {rating:.0f} stars: {count:>9,} ({percentage:>6.2%})")

    if not valid_ratings.empty:
        ratings_per_user = valid_ratings.groupby("user_id").size()
        ratings_per_book = valid_ratings.groupby("book_id").size()
        print_count_summary("RATINGS PER USER", ratings_per_user)
        print_count_summary("RATINGS PER BOOK", ratings_per_book)

    inspect_metadata(args.books, valid_ratings)


if __name__ == "__main__":
    main()
