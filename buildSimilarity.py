import pandas as pd
from sklearn.metrics.pairwise import cosine_similarity
from scipy.sparse import csr_matrix, save_npz
import glob
import pickle

# load, pivot, filter, cosine
files = glob.glob(r"C:\Development\whatdabook - Copy\kaggle_book_ratings\18\user_rating_*.csv")
df = pd.concat([pd.read_csv(f) for f in files], ignore_index=True)

ratings_map = {'it was amazing':5, 'really liked it':4, 'liked it':3, 'it was ok':2, 'did not like it':1}
df['Rating Points'] = df['Rating'].map(ratings_map)
df = df.dropna(subset=['Rating Points'])

pivot = df.pivot_table(index='Name', columns='ID', values='Rating Points').fillna(0)
book_counts = (pivot > 0).sum(axis=1)
user_counts = (pivot > 0).sum(axis=0)
famous_books = book_counts[book_counts >= 5].index
active_users = user_counts[user_counts >= 10].index
filtered = pivot.loc[famous_books, active_users]

similarity = cosine_similarity(filtered)
book_names = filtered.index

# make sparse - drop tiny scores, store only non-zeros
similarity[similarity < 0.1] = 0
sparse_sim = csr_matrix(similarity)

# save sparse matrix + book names separately
save_npz("similarity.npz", sparse_sim)
with open("book_names.pkl", "wb") as f:
    pickle.dump(book_names, f)

print("Saved!")