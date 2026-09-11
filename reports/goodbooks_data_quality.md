# Goodbooks-10k data quality report

This report records the first reproducible inspection of the recommendation
data. It was produced with `inspect_ratings.py` using the Goodbooks-10k v1.0
release.

## Results

- Rating rows: 5,976,479
- Unique users: 53,424
- Unique books: 10,000
- Missing user or book IDs: 0
- Ratings outside the 1-5 range: 0
- Duplicate user-book pairs: 0
- Rated books missing metadata: 0
- User-book matrix density: 1.1187%
- User-book matrix sparsity: 98.8813%

Users have a median of 111 ratings, and books have a median of 248 ratings.
The least active user has 19 ratings, so each user has enough interactions for
a train/test split that keeps some history available for recommendations.

The rating distribution is positively skewed: 68.97% of ratings are four or
five stars. Evaluation should therefore include a simple popularity baseline
and ranking metrics instead of relying only on rating-prediction error.

## Modelling implications

- Store the interaction matrix as a sparse matrix. A dense 53,424 by 10,000
  matrix would allocate memory for more than 534 million possible interactions,
  even though almost 99% of them are absent.
- Split each user's ratings into training and test interactions. A random split
  across all rows can leak the preferences of test users into training and can
  produce an unrealistically easy result.
- Compare every model with a popularity recommender. The most-rated book has
  22,806 ratings while the median book has 248, so popularity is a strong bias
  in this dataset.

## Limitations

Goodbooks-10k contains the platform's 10,000 most popular books and is a static
2017-era snapshot. It is suitable for offline recommender experiments, but it
will underrepresent niche and newer books. WhatDaBook should eventually collect
consented feedback from its own users and use a current book metadata provider
for descriptions, covers, availability, and affiliate links.

## Reproduce the report

After following `data/README.md`, run:

```powershell
.\.venv\Scripts\python.exe inspect_ratings.py
```
