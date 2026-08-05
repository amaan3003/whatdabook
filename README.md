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

**OCR** — reads the title off the cover image using EasyOCR.

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
| OCR | EasyOCR |
| Summarization | LLM API |
| Data / ML | pandas, scikit-learn (cosine similarity) |
| Storage | SQLite |
| Title matching | `difflib` (fuzzy string matching) |

---

## Using your Goodreads data (optional)

Collaborative filtering gets much sharper with your own ratings. Since Goodreads retired its public API, the bot uses your **library export** instead:

1. Go to Goodreads → *My Books* → *Import and Export* → *Export Library*.
2. Download the CSV.
3. Send it to the bot when prompted.

The bot parses the `Title` and `My Rating` columns, keeps only books you've actually rated, and feeds them into the recommender.

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
