"""Create a simple per-user train/test split for recommender evaluation."""

from argparse import ArgumentParser
from pathlib import Path

import pandas as pd


DEFAULT_RAW_DIRECTORY = Path("data/raw/goodbooks-10k")
DEFAULT_PROCESSED_DIRECTORY = Path("data/processed/goodbooks-10k")
REQUIRED_COLUMNS = {"user_id", "book_id", "rating"}
POSITIVE_RATING_MINIMUM = 4


def parse_arguments():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument(
        "--ratings",
        type=Path,
        default=DEFAULT_RAW_DIRECTORY / "ratings.csv",
        help="Path to the source ratings.csv file",
    )
    parser.add_argument(
        "--output-directory",
        type=Path,
        default=DEFAULT_PROCESSED_DIRECTORY,
        help="Directory for train_ratings.csv and test_ratings.csv",
    )
    return parser.parse_args()


def validate_ratings(ratings):
    """Stop before splitting when the input would make the result unreliable."""
    missing_columns = REQUIRED_COLUMNS - set(ratings.columns)
    if missing_columns:
        missing_list = ", ".join(sorted(missing_columns))
        raise ValueError(f"Missing required columns: {missing_list}")

    if ratings.empty:
        raise ValueError("The ratings file is empty.")

    missing_ids = ratings[["user_id", "book_id"]].isna().any(axis=1).sum()
    if missing_ids:
        raise ValueError(f"Found {missing_ids:,} rows with a missing user or book ID.")

    numeric_ratings = pd.to_numeric(ratings["rating"], errors="coerce")
    invalid_ratings = numeric_ratings.isna() | ~numeric_ratings.isin([1, 2, 3, 4, 5])
    if invalid_ratings.any():
        raise ValueError(f"Found {invalid_ratings.sum():,} invalid ratings.")

    duplicate_pairs = ratings.duplicated(subset=["user_id", "book_id"]).sum()
    if duplicate_pairs:
        raise ValueError(f"Found {duplicate_pairs:,} duplicate user-book pairs.")

    validated = ratings.copy().reset_index(drop=True)
    validated["rating"] = numeric_ratings.to_numpy(dtype="int8")
    return validated


def split_ratings(ratings):
    """Hide the last positive rating for users who retain training history."""
    validated = validate_ratings(ratings)

    ratings_per_user = validated.groupby("user_id")["user_id"].transform("size")
    eligible_positive = (
        (validated["rating"] >= POSITIVE_RATING_MINIMUM)
        & (ratings_per_user >= 2)
    )

    test_indices = (
        validated.loc[eligible_positive]
        .groupby("user_id", sort=False)
        .tail(1)
        .index
    )

    test_ratings = validated.loc[test_indices].copy().reset_index(drop=True)
    train_ratings = validated.drop(index=test_indices).reset_index(drop=True)

    validate_split(validated, train_ratings, test_ratings)
    return train_ratings, test_ratings


def validate_split(original, train_ratings, test_ratings):
    """Check the main promises made by the splitting algorithm."""
    if len(train_ratings) + len(test_ratings) != len(original):
        raise RuntimeError("Train and test row counts do not match the source data.")

    if test_ratings["user_id"].duplicated().any():
        raise RuntimeError("A user appears more than once in the test set.")

    if not test_ratings.empty and (test_ratings["rating"] < POSITIVE_RATING_MINIMUM).any():
        raise RuntimeError("The test set contains a rating below 4.")

    train_users = set(train_ratings["user_id"])
    test_users = set(test_ratings["user_id"])
    if not test_users.issubset(train_users):
        raise RuntimeError("At least one test user has no remaining training history.")


def save_split(train_ratings, test_ratings, output_directory):
    output_directory.mkdir(parents=True, exist_ok=True)
    train_path = output_directory / "train_ratings.csv"
    test_path = output_directory / "test_ratings.csv"

    train_ratings.to_csv(train_path, index=False)
    test_ratings.to_csv(test_path, index=False)
    return train_path, test_path


def main():
    args = parse_arguments()
    if not args.ratings.exists():
        raise SystemExit(
            f"Ratings file not found: {args.ratings}\n"
            "Download Goodbooks-10k and follow data/README.md."
        )

    ratings = pd.read_csv(args.ratings)

    try:
        train_ratings, test_ratings = split_ratings(ratings)
    except (ValueError, RuntimeError) as error:
        raise SystemExit(f"Could not create evaluation split: {error}") from error

    train_path, test_path = save_split(
        train_ratings,
        test_ratings,
        args.output_directory,
    )

    all_users = ratings["user_id"].nunique()
    evaluated_users = test_ratings["user_id"].nunique()
    skipped_users = all_users - evaluated_users

    print("EVALUATION SPLIT CREATED")
    print(f"  Source rows: {len(ratings):,}")
    print(f"  Training rows: {len(train_ratings):,}")
    print(f"  Test rows: {len(test_ratings):,}")
    print(f"  Evaluated users: {evaluated_users:,}")
    print(f"  Users without an eligible test rating: {skipped_users:,}")
    print(f"  Training file: {train_path}")
    print(f"  Test file: {test_path}")


if __name__ == "__main__":
    main()
