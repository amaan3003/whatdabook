import pandas as pd
from sklearn.metrics.pairwise import cosine_similarity
from difflib import get_close_matches
import re
import pickle

# load precomputed genre data (no CSV, no hardcoded path)
with open("genre_data.pkl", "rb") as f:
    saved = pickle.load(f)

saved_genre_matrix = saved["genre_matrix"]
df_head = saved["df_head"]


GENRE_ALIASES = {
    "sci fi": "science fiction",
    "scifi": "science fiction",
    "non fiction": "nonfiction",
    "ya": "young adult",
}


def _normalize_genre(genre):
    normalized = " ".join(re.findall(r"[a-z0-9]+", genre.casefold()))
    return GENRE_ALIASES.get(normalized, normalized)


def _split_genres(value):
    value = re.sub(r"\s+&\s+", ",", value)
    return [
        normalized
        for part in re.split(r"[,;/|]", value)
        if (normalized := _normalize_genre(part))
    ]


def _expand_compound_genres(matrix):
    """Convert stored compound labels into consistent atomic genre columns."""
    expanded = {}
    for column in matrix.columns:
        for genre in _split_genres(column):
            if genre in expanded:
                expanded[genre] = expanded[genre] | matrix[column].astype(bool)
            else:
                expanded[genre] = matrix[column].astype(bool)
    return pd.DataFrame(expanded, index=matrix.index, dtype="int8")


genre_matrix = _expand_compound_genres(saved_genre_matrix)


def get_genres(text):
    match = re.search(r"Genres?\s*:\s*\**\s*([^\n]+)", text, re.IGNORECASE)
    if not match:
        return []
    line = match.group(1).strip().strip("*[]_ ")
    return list(dict.fromkeys(_split_genres(line)))


def get_similar_books(genres, n=5):
    available_genres = set(genre_matrix.columns)
    input_set = set()
    for genre in genres:
        normalized = _normalize_genre(genre)
        if normalized in available_genres:
            input_set.add(normalized)
            continue

        close_match = get_close_matches(
            normalized,
            genre_matrix.columns,
            n=1,
            cutoff=0.82,
        )
        if close_match:
            input_set.add(close_match[0])

    input_vec = [1 if col in input_set else 0 for col in genre_matrix.columns]

    if sum(input_vec) == 0:
        return []

    scores = cosine_similarity([input_vec], genre_matrix)[0]
    result = df_head.copy()
    result['score'] = scores
    top = result.sort_values(by=['score', 'ratings_count'], ascending=[False, False]).head(n)

    return top['Title'].tolist()
