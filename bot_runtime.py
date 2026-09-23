"""Keep user conversations separate and measure work without logging their data."""

import asyncio
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
import logging
from time import perf_counter
from uuid import uuid4


logger = logging.getLogger("whatdabook")
request_id = ContextVar("request_id", default="none")


def configure_logging():
    # Only enable our own INFO logs, not HTTP clients that can log token URLs.
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False


def error_fields(error):
    """Never include exception messages, which may contain URLs or user data."""
    if error is None:
        return "error=unknown"
    cause = error
    seen = set()
    while cause.__cause__ is not None and id(cause) not in seen:
        seen.add(id(cause))
        cause = cause.__cause__
    status = getattr(getattr(cause, "response", None), "status_code", None)
    fields = f"error={type(error).__name__} cause={type(cause).__name__}"
    if isinstance(status, int):
        fields += f" http_status={status}"
    return fields


@contextmanager
def timed_stage(stage):
    """Measure elapsed time; 'ok' means the function returned, not result quality."""
    started = perf_counter()
    outcome = "ok"
    details = ""
    logger.info("request=%s stage=%s event=started", request_id.get(), stage)
    try:
        yield
    except BaseException as error:
        outcome = "cancelled" if isinstance(error, asyncio.CancelledError) else "error"
        details = " " + error_fields(error)
        raise
    finally:
        logger.info(
            "request=%s stage=%s duration_ms=%.0f outcome=%s%s",
            request_id.get(), stage, (perf_counter() - started) * 1000,
            outcome, details,
        )


async def run_in_worker(stage, function, *args, **kwargs):
    # Timing includes waiting for a worker thread as well as the work itself.
    with timed_stage(stage):
        return await asyncio.to_thread(function, *args, **kwargs)


def guard_user_flow(handler):
    """One active handler per user, while other users can keep making progress."""
    @wraps(handler)
    async def guarded(update, context):
        if update.effective_user is None:
            return
        if context.user_data.get("_processing_update"):
            message = "I'm still working on your previous request. Please try again after it finishes."
            if update.callback_query:
                await update.callback_query.answer(message)
            elif update.effective_message:
                await update.effective_message.reply_text(message)
            return

        # No await between checking and setting: another handler cannot slip in.
        context.user_data["_processing_update"] = True
        token = request_id.set(uuid4().hex[:12])
        try:
            with timed_stage("request_total"):
                return await handler(update, context)
        finally:
            context.user_data.pop("_processing_update", None)
            request_id.reset(token)

    return guarded
