import pandas as pd
import pickle


df = pd.read_csv(r"C:\Development\whatdabook\kaggle_book_ratings\popularityBasedDataset\Goodreads_books_with_genres.csv")
df = df.drop(columns=['isbn','isbn13','publisher','text_reviews_count'])
df = df.sort_values(by='ratings_count', ascending=False).reset_index(drop=True)
df_head = df.head(1000)
genre_matrix = df_head['genres'].str.get_dummies(sep=';')


df_slim = df_head[['Title', 'ratings_count']].copy()

with open("genre_data.pkl", "wb") as f:
    pickle.dump({"genre_matrix": genre_matrix, "df_head": df_slim}, f)

print("Saved!")