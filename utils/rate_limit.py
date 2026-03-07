"""
Simple in-memory per-user rate limiter.
Use as a decorator or call check_rate_limit() directly.
"""
import time
from collections import defaultdict
from functools import wraps
from telegram import Update
from telegram.ext import ContextTypes

# {telegram_id: [timestamps]}
_buckets: dict[int, list[float]] = defaultdict(list)

# Default: max 10 actions per 60 seconds per user
DEFAULT_MAX = 10
DEFAULT_WINDOW = 60


def is_rate_limited(telegram_id: int, max_calls: int = DEFAULT_MAX, window: int = DEFAULT_WINDOW) -> bool:
    now = time.monotonic()
    bucket = _buckets[telegram_id]
    # Drop old entries
    _buckets[telegram_id] = [t for t in bucket if now - t < window]
    if len(_buckets[telegram_id]) >= max_calls:
        return True
    _buckets[telegram_id].append(now)
    return False


def rate_limit(max_calls: int = DEFAULT_MAX, window: int = DEFAULT_WINDOW):
    """Decorator for PTB handler functions."""
    def decorator(func):
        @wraps(func)
        async def wrapper(update: Update, ctx: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
            uid = update.effective_user.id if update.effective_user else 0
            if is_rate_limited(uid, max_calls, window):
                if update.message:
                    await update.message.reply_text("⚠️ Slow down! You're sending too many requests.")
                elif update.callback_query:
                    await update.callback_query.answer("Too many requests, slow down.", show_alert=True)
                return
            return await func(update, ctx, *args, **kwargs)
        return wrapper
    return decorator
