import pandas as pd
from sklearn.metrics.pairwise import cosine_similarity
import re
import pickle

# load precomputed genre data (no CSV, no hardcoded path)
with open("genre_data.pkl", "rb") as f:
    saved = pickle.load(f)

genre_matrix = saved["genre_matrix"]
df_head = saved["df_head"]


def get_genres(text):
    match = re.search(r'\*?Genre:\*?\s*(.+)', text)
    if not match:
        return []
    line = match.group(1).strip().strip('*').strip()
    return [g.strip() for g in line.split(',')]


def get_similar_books(genres, n=5):
    input_set = set(genres)
    input_vec = [1 if col in input_set else 0 for col in genre_matrix.columns]

    if sum(input_vec) == 0:
        return []

    scores = cosine_similarity([input_vec], genre_matrix)[0]
    result = df_head.copy()
    result['score'] = scores
    top = result.sort_values(by=['score', 'ratings_count'], ascending=[False, False]).head(n)

    return top['Title'].tolist()