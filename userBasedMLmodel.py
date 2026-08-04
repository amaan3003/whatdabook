from scipy.sparse import load_npz
import pickle
from collections import Counter

# load sparse similarity + book names
sparse_sim = load_npz("similarity.npz")
similarity = sparse_sim.toarray()             # back to normal array for recommend()

with open("book_names.pkl", "rb") as f:
    book_names = pickle.load(f)


def recommend(book_title, n=5):
    if book_title not in book_names:
        return []
    idx = book_names.get_loc(book_title)
    scores = list(enumerate(similarity[idx]))
    scores = sorted(scores, key=lambda x: x[1], reverse=True)
    scores = scores[1:n+1]
    return [book_names[i] for i, _ in scores]


def recommend_for_user(goodreads_data, n=5):
    books = goodreads_data['books']
    liked = [b['book_title'] for b in books if b['rating'] >= 4]
    all_recs = []
    for title in liked:
        all_recs.extend(recommend(title))
    liked_set = set(liked)
    all_recs = [b for b in all_recs if b not in liked_set]
    return [book for book, _ in Counter(all_recs).most_common(n)]

