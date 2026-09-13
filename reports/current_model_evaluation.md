# Current personalized model evaluation

This report evaluates the saved `similarity.npz` and `book_names.pkl`
artifacts against the deterministic Goodbooks-10k holdout split. For each
user, one book rated 4 or 5 is hidden. The model receives the remaining
positively rated books and succeeds when the hidden title appears in its top
10 recommendations.

## Results

- Test users: 53,406
- Exact catalog-title matches: 5,029 of 10,000 Goodbooks books
- Users with at least one liked training title recognized by the model: 53,378 (99.95%)
- Hidden test titles recognized by the model: 38,693 (72.45%)
- Users with both recognized history and a recognized hidden title: 38,684 (72.43%)

### Current personalized model — all test users

- Hit Rate@10: 3.96%
- MRR@10: 0.0135
- NDCG@10: 0.0195

### Current personalized model — fully evaluable users only

- Hit Rate@10: 5.47%
- MRR@10: 0.0187
- NDCG@10: 0.0270

The conditional result measures ranking quality when exact title matching
allows the model to operate. It must be shown beside the all-user result; on
its own it would hide catalog and input failures.

### Popularity baseline — all test users

- Hit Rate@10: 1.86%
- MRR@10: 0.0070
- NDCG@10: 0.0097

The baseline ranks books by the number of 4-5 star ratings in the training
set and removes books already rated by that user.

## What the result means

The personalized model's all-user Hit Rate is 2.13 times the
popularity baseline, so the saved similarities contain useful preference
signal. The model is doing more than recommending globally popular books.

The two clearest weaknesses are title matching and already-read results.
Exact matching prevents 27.55% of hidden test
books from being found, while the current recommender removes liked seed books
but can return books the user rated 1-3. Fixing those system behaviors is the
most direct next experiment before replacing the collaborative-filtering
algorithm.

## Additional behavior

- Average results returned when the model recognizes user history: 9.99
- Recommendations that repeat a book already rated by the user: 16.63%
- Fraction of the saved model catalog ever recommended: 44.86%

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
