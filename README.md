# 📚 WhatDaBook

**Click a photo of any book's cover and get a full breakdown and personalized recommendations, right inside Telegram.**

Ever stood in a bookstore holding a book, with no idea if it's actually worth your time? WhatDaBook answers that in seconds. Point your camera at a cover and the bot tells you what the book is about, what readers loved, what they didn't, and whether *you'd* actually enjoy it — using your own reading taste.


## What it does

1. **📸 Cover → text** — OCR extracts the title from a photo of the book's cover.
2. **🧠 Structured summary** — an LLM generates a clean, formatted breakdown: description, summary, what people liked, what they disliked, and a final verdict.
3. **📊 Personalized recommendations** — two recommender systems work together to suggest what to read next.
4. **💾 User profiles** — your preferences and Goodreads data persist across sessions.

---

## How it works (the pipeline)

```
Photo → OCR → LLM summary → Recommenders → Telegram reply
                                ↑
                        User's Goodreads data
```

**OCR** — reads the title off the cover image using Google Vision API.

**LLM summary** — the extracted title is sent to an LLM, which returns a structured Telegram-formatted message (description, summary, likes, dislikes, verdict).

**Two recommenders:**

- **Content-based (popularity-filtered)** — each book is turned into a genre vector via one-hot encoding, then compared using cosine similarity. Candidates are drawn from a pool of the most-rated books, so recommendations are both genre-relevant *and* popular.
- **User-based collaborative filtering** — builds a book × user rating matrix (pivot table), filters out sparse rows/columns, and computes book-to-book cosine similarity. If you share your Goodreads library, the bot finds books that readers with similar taste rated highly — regardless of genre.

Both recommenders share the same core idea: **turn each book into a vector, measure how close they are.** The only difference is what the vector is built from — genres for one, user ratings for the other.

**Database** — user profiles and state are persisted so the bot remembers your taste between sessions.

---

## Tech stack

| Layer | Tool |
|---|---|
| Bot framework | `python-telegram-bot` |
| OCR | Google Vision API |
| Summarization | LLM API |
| Data / ML | pandas, scikit-learn (cosine similarity) |
| Storage | SQLite |
| Title matching | `difflib` (fuzzy string matching) |

---

## Using your Goodreads data (optional)

Use `/goodreads <public profile link>` to connect a public Goodreads read shelf through PirateReads. WhatDaBook stores the returned book history for that user's personalised summaries and recommendations.

After linking, the bot separately asks whether the user wants to contribute book titles and 1–5 star ratings to future model experiments. Training contribution is optional:

- Tapping **Help improve recommendations** saves validated ratings in a separate table.
- `/optout` revokes consent and immediately removes those contributed rows.
- Personal summaries continue working after training opt-out.
- Offline training exports replace Telegram IDs with temporary anonymous user IDs and never include names.

Run `python export_contributed_ratings.py` to create the ignored local snapshot at `data/processed/user_contributions/ratings.csv`. This snapshot is an input for future evaluation and retraining; it does not update the production model automatically.

---

## Engineering challenges

Building this surfaced a lot of real problems worth documenting:

- **Fusing two recommenders** — combining collaborative and content-based signals into one coherent ranking rather than two separate lists.
- **Latency** — keeping the full OCR → LLM → recommendation chain fast enough for a chat interface.
- **Local vs cloud LLM** — the tradeoff between privacy/cost/control (local) and quality/speed/no-infra (cloud). And also finding the most cost effective llm model for this task!
- **Data sparsity** — the raw ratings matrix was ~99% empty; most books had a single rating. Aggressive filtering (minimum ratings per book, minimum books per user) was needed before similarity became meaningful.
- **Entity resolution** — *"Atomic Habits: An Easy & Proven Way to Build Good Habits"* in one dataset is just *"Atomic Habits"* in another, and the model treats them as different items. Solved with fuzzy string matching.
- **End-to-end architecture** — building this as a connected system rather than disconnected scripts.

---


## Running locally

### Admin statistics

Send `/myid` to the bot in a private chat, then set `ADMIN_TELEGRAM_ID` to that
numeric ID in Azure App Service environment variables. `/stats` only responds
with analytics to that ID in private chat; an unset ID grants nobody access.

Stats include total saved users, new users today, distinct active users today
and over the last seven UTC calendar days, photo scan requests, and recommendation
requests (including similar-book requests). Activity counts start when this
version is deployed and include unsuccessful requests. Opening the bot without
interacting is not counted. Existing migrated user creation dates may reflect
the earlier database migration rather than the original signup date.

On Azure App Service, SQLite defaults to `/home/whatdabook/users.db` so it survives
code deployments. An existing working-directory `users.db` is copied on first
startup if the destination does not exist. `DATABASE_PATH` can override this path;
its directory must be writable and persistent. Keep App Service `/home` storage
enabled and run a single bot instance for Telegram polling and SQLite.

```bash
git clone https://github.com/amaan3003/whatdabook
cd whatdabook
pip install -r requirements.txt
```

Create a `.env` file with your credentials:

```
TELEGRAM_BOT_TOKEN=your_token_here
LLM_API_KEY=your_api_key_here
```

Then run:

```bash
python main.py
```

---

## Contributing & feedback

This is being built in public as a learning project. Suggestions, advice, and PRs are all welcome — especially around recommendation systems and handling messy, mismatched data.

**Repo:** https://github.com/amaan3003/whatdabook
