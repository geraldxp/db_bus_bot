"""
Main entry point — registers all handlers and starts watchers.
"""
import asyncio
import logging

from telegram.ext import ApplicationBuilder

from config import BOT_TOKEN
from db.bus import get_pool, close_pool

import bot.handlers.start as start_handler
import bot.handlers.services as services_handler
import bot.handlers.deposit as deposit_handler
import bot.handlers.wallet as wallet_handler
import bot.handlers.profile as profile_handler
import bot.handlers.support as support_handler
import admin.handlers as admin_handler

from watchers.payment_watcher import payment_watcher_loop
from watchers.deposit_watcher import deposit_watcher_loop

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


async def _apply_schema(pool):
    """
    Apply schema.sql safely on every boot.
    Tables/indexes use IF NOT EXISTS so they're always safe.
    ENUMs use a DO block pattern since CREATE TYPE has no IF NOT EXISTS.
    """
    from pathlib import Path
    schema_sql = Path("db/schema.sql").read_text()

    # Split on statement boundaries and run each one individually so a
    # DuplicateObjectError on an already-existing ENUM doesn't abort everything.
    import asyncpg
    async with pool.acquire() as con:
        for statement in schema_sql.split(";"):
            stmt = statement.strip()
            if not stmt:
                continue
            try:
                await con.execute(stmt)
            except asyncpg.DuplicateObjectError:
                pass  # type/index already exists — safe to skip
            except asyncpg.DuplicateTableError:
                pass  # table already exists — safe to skip (belt-and-suspenders)
    logger.info("Schema applied.")


async def post_init(app):
    pool = await get_pool()
    await _apply_schema(pool)
    bot = app.bot
    asyncio.create_task(payment_watcher_loop(bot))
    asyncio.create_task(deposit_watcher_loop(bot))
    logger.info("DB pool ready. Watchers started.")


async def post_shutdown(app):
    await close_pool()


def main():
    app = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    # Order matters — ConversationHandlers first
    admin_handler.register(app)
    support_handler.register(app)
    services_handler.register(app)
    deposit_handler.register(app)
    wallet_handler.register(app)
    profile_handler.register(app)
    start_handler.register(app)  # fallback nav last

    logger.info("Bot starting...")
    app.run_polling()


if __name__ == "__main__":
    main()
