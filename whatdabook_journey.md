# WhatDaBook — Build Journey & Notes

A working reference of everything covered while building the book recommender and Telegram bot — from first genre matching to collaborative filtering, bot integration, and product planning.

---

## Part 1 — Content-Based Filtering (genre matching)

### The goal
Take an input book, look at its genres, and return the most similar books from a dataset — where books were already sorted by rating count (descending).

### Data shape
Both the dataset's `genres` column and the input book use **multiple genres separated by `;`**, e.g. `"Fantasy;Adventure;Young Adult"`.

### First approach — set overlap
Split each genre string into a set, then count how many genres overlap between the input and each book.

```python
def to_genre_set(genre_str):
    return set(g.strip().lower() for g in genre_str.split(';'))

def recommend_by_genre(df, input_genres, n=10):
    input_set = to_genre_set(input_genres)
    df = df.copy()
    df['overlap'] = df['genre'].apply(lambda x: len(input_set & to_genre_set(x)))
    matches = df[df['overlap'] > 0]
    matches = matches.sort_values(by=['overlap', 'rating_count'], ascending=[False, False])
    return matches.head(n)
```

Key idea: `set_a & set_b` gives shared genres; `len()` of that is the overlap score. Sort by overlap first, rating count as tiebreaker.

### The upgrade — one-hot encoding + cosine similarity

**One-hot encoding** turns the genre text into a table of 0/1 columns, one per unique genre:

```python
genre_matrix = df_head['genres'].str.get_dummies(sep=';')
```

`.str.get_dummies(sep=';')`:
1. splits every string on `;`
2. collects every distinct genre across all rows → these become column names
3. puts `1` where a book has that genre, `0` otherwise

**Critical bug learned:** `sep='; '` (with space) failed to split because the data used `;` with no space — every full genre string became its own column (964 junk columns). Fix: `sep=';'`. Always check `genre_matrix.columns.tolist()` after.

**Cosine similarity** = dot product, normalized by vector length. It fixes the flaw where a book tagged with 15 genres beats a book tagged with 3 just by having more surface area to overlap. Normalizing for length means direction matters, not magnitude.

```python
from sklearn.metrics.pairwise import cosine_similarity

def make_input_vector(input_genres, columns):
    input_set = set(g.strip() for g in input_genres.split(';'))
    return [1 if col in input_set else 0 for col in columns]

input_vec = make_input_vector("Fantasy;Adventure", genre_matrix.columns)
scores = cosine_similarity([input_vec], genre_matrix)[0]
```

- `[input_vec]` — wrapped in brackets because `cosine_similarity` needs 2D input.
- `[0]` — output is shape `(1, N)`; `[0]` extracts the flat array of N scores.
- Guard: if `sum(input_vec) == 0`, no genre matched — return early.

### Combining scores with the data
`scores` is just numbers; titles live in `df_head`. Attach scores back by **row position** (get_dummies doesn't reorder rows):

```python
result = df_head.copy()
result['score'] = scores
top = result.sort_values(by=['score', 'ratings_count'], ascending=[False, False]).head(10)
```

### Naming clarity
- **Popularity-based** = same list for everyone, no input (sort by rating count, take top N).
- **Content-based** = genre similarity for an input book. ← this is what the button does.
- Using `df.head(1000)` (top popular books) as the pool = a **popularity-filtered content-based** system. Both concepts working together.

---

## Part 2 — Extracting genres from the LLM (DeepSeek) output

DeepSeek returns a fixed-format book breakdown. Only the genre line is needed for similarity.

```python
import re

def get_genres(text):
    match = re.search(r'\*?Genre:\*?\s*(.+)', text)   # handles optional * markdown
    if not match:
        return []
    line = match.group(1).strip().strip('*').strip()
    return [g.strip() for g in line.split(',')]        # DeepSeek uses commas
```

Note the separator mismatch: **DeepSeek uses commas**, the **dataset uses semicolons**. Handled in two different places.

Known limitation: DeepSeek's genre vocabulary may not match the dataset's genre names, causing silent no-matches. Long-term fix is a cleaner dataset (planned).

---

## Part 3 — Telegram bot integration

### Adding a "Similar Books" button

```python
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

async def handle_photo(update, context):
    photo = update.message.photo[-1]
    file = await photo.get_file()
    await file.download_to_drive("incoming.jpg")

    summary = summarize(ocr("incoming.jpg"))
    context.user_data['genres'] = get_genres(summary)   # save for the button press

    keyboard = [[InlineKeyboardButton("📚 Similar Books", callback_data="similar")]]
    await update.message.reply_text(
        summary, parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
```

### Handling the button press

```python
from telegram.ext import CallbackQueryHandler

async def button_handler(update, context):
    query = update.callback_query
    await query.answer()                                # REQUIRED — stops the loading spinner
    if query.data == "similar":
        genres = context.user_data.get('genres', [])
        books = get_similar_books(genres, n=5)
        if not books:
            await query.message.reply_text("Koi similar book nahi mili.")
            return
        msg = "📚 *Similar Books:*\n\n" + "".join(f"• {t}\n" for t in books)
        await query.message.reply_text(msg, parse_mode="Markdown")
```

### Registering handlers — order matters
All `add_handler` calls come **before** `run_polling()`. Anything after `run_polling()` never runs.

```python
app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
app.add_handler(CommandHandler("start", start))
app.add_handler(CallbackQueryHandler(button_handler))
app.run_polling()   # LAST
```

### Bugs squashed
- `app` vs `application` — mismatched variable names; keep one name.
- `KeyError: 'title'` — the column was `Title` (capital T). Columns are case-sensitive.
- `context.user_data` disappears on restart — fine for a button in one session, but not persistent storage.

### How the bot talks via token
The token is **identity**, not communication. `run_polling()` does the communicating — it repeatedly asks Telegram's server "any new messages?" and shows the token each time to prove it's the right bot. (The alternative is a webhook, where Telegram pushes to you — better for production servers.)

---

## Part 4 — User-Based Collaborative Filtering

### The core difference
- Content-based asks: *"what books have similar genres?"*
- Collaborative asks: *"people who liked this book — what else did they like?"* Genre is irrelevant; only rating patterns matter.

Both share the same machinery: **turn each book into a vector, compare with cosine similarity.** Only the vector's source differs — genres vs user ratings.

### What it needs
Per-user ratings: `ID / Name / Rating` (one row = one user rating one book). Aggregate `ratings_count` is NOT enough.

### Step 1 — text ratings to numbers

```python
ratings_map = {
    'it was amazing': 5, 'really liked it': 4,
    'liked it': 3, 'it was ok': 2, 'did not like it': 1,
}
df['Rating Points'] = df['Rating'].map(ratings_map)
df = df.dropna(subset=['Rating Points'])   # drops unmapped labels like "no rating"
```

### Step 2 — pivot table (each book becomes a vector)

```python
pivot = df.pivot_table(index='Name', columns='ID', values='Rating Points').fillna(0)
```

- **rows = books** (because we want book-to-book similarity, and the thing being compared must be a row)
- **columns = users**
- **cells = ratings**, empty filled with 0

Insight: a book's row *is* its user-rating pattern. Comparing two rows = comparing two books' user patterns. (If we wanted user-to-user similarity, we'd flip it: users as rows.)

### Step 3 — filter out noise
Raw pivot was `24093 × 531` and ~99.6% empty — most books had a single rating.

```python
book_counts = (pivot > 0).sum(axis=1)
user_counts = (pivot > 0).sum(axis=0)
famous_books = book_counts[book_counts >= 5].index   # books rated by 5+ users
active_users = user_counts[user_counts >= 10].index  # users who rated 10+ books
filtered = pivot.loc[famous_books, active_users]      # → 1720 × 359
```

Sparsity is why filtering matters: without it, cosine similarity is meaningless and the matrix is huge.

### Step 4 — cosine similarity (all books vs all books)

```python
similarity = cosine_similarity(filtered)   # → 1720 × 1720 matrix
```

`cosine_similarity(filtered)` with one argument compares every row to every other row. The whole table is built once; lookups are cheap after.

### Step 5 — the recommend function

```python
book_names = filtered.index

def recommend(book_title, n=5):
    if book_title not in book_names:
        return []
    idx = book_names.get_loc(book_title)                 # name → row number
    scores = list(enumerate(similarity[idx]))            # attach positions to scores
    scores = sorted(scores, key=lambda x: x[1], reverse=True)
    scores = scores[1:n+1]                               # skip itself (score 1.0), take top n
    return [book_names[i] for i, _ in scores]            # row number → name
```

Flow: name → number → look up row → `enumerate` (keep positions) → sort by score → skip self → convert numbers back to names. `recommend()` does no math — all similarity is precomputed; it's just a sorted lookup.

---

## Part 5 — Personal Goodreads data

Goodreads killed its public API in 2020, so users **export their library CSV** instead.

```python
userInfo = pd.read_csv("goodreads_library_export.csv")   # it's a CSV, not JSON
my_books = userInfo[['Title', 'My Rating']]
my_books = my_books[my_books['My Rating'] > 0]           # 0 = not actually rated
```

### The matching problem
Goodreads titles are long (`"Atomic Habits: An Easy & Proven Way..."`) while training data has `"Atomic Habits"`. Exact match fails. Fix with fuzzy matching:

```python
import difflib

def find_match(my_title, book_names, cutoff=0.6):
    matches = difflib.get_close_matches(my_title, book_names, n=1, cutoff=cutoff)
    return matches[0] if matches else None
```

Caveat: fuzzy matching only helps if the same book exists (under any name) in the training data. Niche/regional books that aren't in the training set can't be matched at all.

### Personalized recommendations idea
For each highly-rated book, pull its similar books, pool them, drop already-read titles, and rank by how often each appears (a book similar to *many* of your favorites is a stronger match):

```python
from collections import Counter

def recommend_for_me(user_df, n=10):
    my_books = user_df[user_df['My Rating'] >= 4]['Title'].tolist()
    all_recs = []
    for book in my_books:
        all_recs.extend(recommend(book))
    my_titles = set(user_df['Title'])
    all_recs = [b for b in all_recs if b not in my_titles]
    return [book for book, _ in Counter(all_recs).most_common(n)]
```

---

## Part 6 — Product & Monetization Planning

### Database
`context.user_data` doesn't persist. Use **SQLite** (free, built into Python, just a file) for user profiles and Goodreads data.

### Free book databases
- **Open Library** — free, huge, API, no key. Best for metadata/content-based.
- **Google Books API** — free tier, rich metadata.
- Note: none provide per-user *ratings* at scale — collaborative filtering must rely on an existing ratings dataset or self-collected data over time.

### Amazon affiliate (US program, based in India)
- Possible: India is among the 52 countries supported for direct bank transfer from Amazon US.
- **Critical:** file a **W-8BEN** form claiming the India–US tax treaty benefit, or up to **30% is withheld**. Getting this right is the single biggest money-saver.
- Register on amazon.com (not amazon.in), declare as non-US resident.
- Must disclose affiliate links; new Associates accounts need 3 qualifying sales within 180 days or get terminated.
- Not legal/tax advice — verify current terms and consult a CA if earnings grow.

### Weighting the two recommenders
```python
final_score = w1 * content_score + w2 * collab_score   # w1 + w2 = 1
```
- Goodreads data present → weight collaborative higher.
- No Goodreads data → w2 = 0, content-based only.
- Must **normalize** both score sets to the same 0–1 scale before combining, or one model dominates.

### "Why you'll like this book"
Reuse the existing LLM. After picking a recommendation, feed it the user's liked books + the recommended book and ask for a 2-line personalized reason. No new model needed.

### Deployment
Currently `run_polling()` = only alive while the laptop runs. To go 24/7:
- **Railway / Render** — easiest, deploy from GitHub, free tier.
- **Fly.io** — more technical, good free tier.
- Polling works on a server; webhook is a later optimization.

---

## Recommended build order

1. **SQLite database** — foundation; nothing persists without it.
2. **`/start` + profile flow** — ask name, ask for Goodreads CSV, save to DB.
3. **Conditional recommendation** — if Goodreads data → both models; else → content-based only.
4. **Weighting** — combine the two models once both run together (normalize first).
5. **"Why you'll like it"** — LLM-generated personalized reason (polish).
6. **Deploy** — once everything works locally.

Do one brick at a time. The recurring risk is jumping between features before any one is finished.

---

## Key takeaways

- **One tool, different data:** cosine similarity powered both recommenders — genres in one, user ratings in the other. Same math, different inputs.
- **Pivot = vectorization:** it reshapes scattered rows so each book becomes a comparable vector.
- **Filtering before similarity:** sparse data makes similarity meaningless; cut low-signal rows/columns first.
- **Precompute, then look up:** the similarity matrix is built once; recommendations are just sorted lookups.
- **Real-world glue is the hard part:** genre-vocabulary mismatches and title matching (entity resolution) caused more trouble than the algorithms.
