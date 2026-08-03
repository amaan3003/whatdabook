import pandas as pd
from sklearn.metrics.pairwise import cosine_similarity
from collections import Counter
import glob

# saari user_rating CSV files dhoondo
files = glob.glob(r"C:\Development\whatdabook\kaggle_book_ratings\18\user_rating_*.csv")

# har file padho, sab ek list mein
dfs = [pd.read_csv(f) for f in files]

# sabko ek ke neeche ek jodo
df = pd.concat(dfs, ignore_index=True)





ratings_map = {
    'it was amazing' : 5,
    'really liked it' : 4,
    'liked it':3,
    'it was ok':2,
    'did not like it':1,
}

df['Rating Points'] = df['Rating'].map(ratings_map)
df = df.dropna(subset=['Rating Points'])

pivot = df.pivot_table(index='Name', columns='ID', values='Rating Points').fillna(0)

book_counts = (pivot > 0).sum(axis=1)
user_counts = (pivot > 0).sum(axis=0)

famous_books = book_counts[book_counts >= 5].index
active_users = user_counts[user_counts >= 10].index

# pivot ko in dono se chhaanto
filtered = pivot.loc[famous_books, active_users]

similarity = cosine_similarity(filtered)
book_names = filtered.index   

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
        all_recs.extend(recommend(title))              # purana recommend() reuse


    liked_set = set(liked)
    all_recs = [b for b in all_recs if b not in liked_set]

    return [book for book, _ in Counter(all_recs).most_common(n)]

