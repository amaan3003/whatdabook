import pandas as pd
from summarizer import summarize
from sklearn.metrics.pairwise import cosine_similarity
import re
from summarizer import summarize

df = pd.read_csv(r"C:\Development\whatdabook\kaggle_book_ratings\popularityBasedDataset\Goodreads_books_with_genres.csv")

df = df.drop(columns =['isbn','isbn13','publisher','text_reviews_count'])
df = df.sort_values(by ='ratings_count',ascending=False).reset_index(drop=True)

df_head = df.head(1000)

genre_matrix = df_head['genres'].str.get_dummies(sep=';')



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
    
    