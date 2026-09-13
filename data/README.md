# Recommendation data

This folder is the local home for the datasets used to train and evaluate the
WhatDaBook recommender. Large data files are deliberately excluded from Git.

## First dataset: Goodbooks-10k

Source: [Goodbooks-10k](https://github.com/zygmuntz/goodbooks-10k)

License: [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/)

The dataset contains about six million ratings from 53,424 users across 10,000
books. It is useful for building and evaluating a first collaborative-filtering
model. Book descriptions, current cover images, and Amazon links should come
from a separate live metadata source because those fields change over time.

Download the `goodbooks-10k` release archive from the source repository and
extract these files into `data/raw/goodbooks-10k/`:

```text
data/raw/goodbooks-10k/
|-- ratings.csv
|-- books.csv
|-- book_tags.csv
|-- tags.csv
`-- to_read.csv
```

The first two files are enough for the initial inspection. Once Python 3.11 and
the project's dependencies are installed, run:

```powershell
py -3.11 inspect_ratings.py
```

The inspection is read-only: it reports the dataset's shape and common quality
issues without changing the CSV files.

To create the training and test files used for recommendation evaluation, run:

```powershell
.\.venv\Scripts\python.exe prepare_evaluation_data.py
```

This keeps one positive rating hidden for each eligible user. Generated files
are written to `data/processed/goodbooks-10k/` and are excluded from Git.

To evaluate the currently saved personalized model on that split, run:

```powershell
.\.venv\Scripts\python.exe evaluate_current_model.py
```

The script reports ranking quality, exact-title coverage, repeated-read
recommendations, and a popularity baseline. It keeps the saved similarity
matrix sparse and writes the results to
`reports/current_model_evaluation.md`.

## Opted-in WhatDaBook ratings

Users who connect Goodreads can separately choose to contribute their validated
book titles and ratings to future model experiments. To create an anonymised
snapshot of only those opted-in rows, run:

```powershell
.\.venv\Scripts\python.exe export_contributed_ratings.py
```

The snapshot is written to `data/processed/user_contributions/ratings.csv`.
It contains temporary user IDs, book titles, ratings, and a source label. It
does not contain Telegram IDs or names. Run a complete export each time rather
than appending snapshots because the temporary IDs are created per export.

When publishing work based on this dataset, keep the source attribution above
and describe any cleaning or filtering performed by the project.
