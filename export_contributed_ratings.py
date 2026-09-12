"""Export opted-in ratings for offline model experiments."""

from argparse import ArgumentParser
import csv
from pathlib import Path

from db import get_collection_summary, get_contributed_ratings, init_db


DEFAULT_OUTPUT = Path("data/processed/user_contributions/ratings.csv")


def parse_arguments():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Location for the anonymised ratings CSV",
    )
    return parser.parse_args()


def anonymize_ratings(database_rows):
    """Replace Telegram IDs with temporary IDs for this complete export."""
    anonymous_users = {}
    exported_rows = []

    for telegram_id, book_title, rating in database_rows:
        if telegram_id not in anonymous_users:
            anonymous_users[telegram_id] = f"bot_user_{len(anonymous_users) + 1:06d}"

        exported_rows.append(
            {
                "user_id": anonymous_users[telegram_id],
                "book_title": book_title,
                "rating": rating,
                "source": "whatdabook_goodreads_opt_in",
            }
        )

    return exported_rows


def write_export(rows, output_path):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as output_file:
        writer = csv.DictWriter(
            output_file,
            fieldnames=["user_id", "book_title", "rating", "source"],
        )
        writer.writeheader()
        writer.writerows(rows)


def main():
    args = parse_arguments()
    init_db()

    exported_rows = anonymize_ratings(get_contributed_ratings())
    write_export(exported_rows, args.output)
    summary = get_collection_summary()

    print("USER CONTRIBUTION EXPORT")
    print(f"  Registered users: {summary['users']:,}")
    print(f"  Users with Goodreads data: {summary['goodreads_users']:,}")
    print(f"  Users contributing to training: {summary['contributing_users']:,}")
    print(f"  Exported ratings: {len(exported_rows):,}")
    print(f"  Output file: {args.output}")


if __name__ == "__main__":
    main()
