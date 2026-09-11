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

When publishing work based on this dataset, keep the source attribution above
and describe any cleaning or filtering performed by the project.
