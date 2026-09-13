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
    recommendations = recommend_for_user_with_reasons(goodreads_data, n)
    return [recommendation["title"] for recommendation in recommendations]


def recommend_for_user_with_reasons(goodreads_data, n=5):
    """Return ranked titles and the liked books that produced each candidate."""
    books = goodreads_data['books']
    liked = [b['book_title'] for b in books if b['rating'] >= 4]
    all_recs = []
    recommendation_sources = {}
    for title in liked:
        for recommendation in recommend(title):
            all_recs.append(recommendation)
            recommendation_sources.setdefault(recommendation, []).append(title)

    liked_set = set(liked)
    all_recs = [b for b in all_recs if b not in liked_set]
    ranked_recommendations = Counter(all_recs).most_common(n)

    return [
        {
            "title": title,
            "based_on": list(dict.fromkeys(recommendation_sources[title]))[:2],
        }
        for title, _ in ranked_recommendations
    ]

