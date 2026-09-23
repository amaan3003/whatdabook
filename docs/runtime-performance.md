# Concurrency and timing logs

Run the bot with `python main.py`. Importing `main` in a test does not start
polling, the web server, or database initialization.

## What changes for a user

The application can process up to eight Telegram updates concurrently. Slow
network calls run in worker threads so the event loop can serve other people.
Local recommendation calculations and activity recording also use workers.

Each user has one active conversation handler. During a photo scan, another
request from the same user gets a busy reply; it is not saved for later. This
also protects Goodreads imports, text entry, and callback buttons from changing
each other's state. Cancel exits link/title entry; it does not interrupt an
already-running API call.

Seven photo processing attempts are allowed per user in a rolling 60 seconds.
A failed attempt counts because work may already have cost money. Busy replies
do not consume the quota. The limit and busy flags are in memory and reset on
restart. They apply to one bot process, not multiple Azure instances. Keep one
polling process for this deployment.

Eight occupied slots can still cause a queue. Concurrency does not make an
individual LLM response faster or remove provider rate limits. Some smaller
database operations still run synchronously; measure before expanding the
design. Vision RPCs have a 20-second timeout without automatic retries. The
existing Requests timeouts are inactivity limits, not an end-to-end deadline.

## The matrix does not need another upload

`similarity.npz` is already tracked in Git and included by the deployment
workflow. It is approximately 62.5 MB on disk. Previously, startup expanded it
into a dense array requiring approximately 978 MiB, in addition to the sparse
copy. The code now retains the sparse arrays (approximately 91 MiB) and expands
only one requested book's row (approximately 88 KiB) for ranking. These are
matrix sizes, not total application RAM. The model and ranking rules are unchanged.

## Reading the logs

`bot_runtime.py` writes application logs to the console. Each accepted handler
gets a random request label, shared by its worker stages. Labels contain no
Telegram IDs. Activity tracking runs before the handler and uses `request=none`.

For example, these are illustrative values, not production measurements:

```text
request=a1b2c3d4e5f6 stage=ocr duration_ms=1200 outcome=ok
request=a1b2c3d4e5f6 stage=llm_summary duration_ms=8400 outcome=ok
request=a1b2c3d4e5f6 stage=request_total duration_ms=10300 outcome=ok
```

This request spent most of its measured time waiting for the summary. Other
stages include `photo_download`, `personalized_recommendations`, `book_metadata`,
`similar_local`, `llm_similar`, `goodreads_import`, and `activity_db`.

Each stage also emits `event=started`, useful if a process dies before it
finishes. Raised errors record their class and, when available, an HTTP status;
exception messages, keys, links, photos, titles, and Goodreads histories are
excluded from these logs. HTTP client debug logging is not enabled.

`outcome=ok` means the function returned normally. It can still have returned
an empty result or shown a fallback. `request_total` excludes Telegram polling,
the update queue, and activity tracking; worker durations include worker queue
time. Cancellation does not forcibly stop work already running in a thread.

After deployment, enable application logging if needed and open the App
Service's **Monitoring > Log stream** in Azure. See Microsoft's
[App Service logging guide](https://learn.microsoft.com/en-us/azure/app-service/troubleshoot-diagnostic-logs).
Inspect these timings alongside Azure memory/CPU metrics before deciding that
the LLM or the hosting plan is responsible. No Azure settings were changed to
add these local logs.

## Local checks

Run `python -m unittest discover -s tests -v`. Tests mock external API calls;
they check user isolation, busy replies, failure cleanup, photo limits, safe
timing output, OCR fallback, and unchanged sparse recommendation ordering.
