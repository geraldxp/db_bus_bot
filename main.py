"""
Main entry point — registers all handlers and starts watchers.
"""
import asyncio
import logging
from pathlib import Path

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


async def post_init(app):
    await get_pool()  # warm up DB pool
    bot = app.bot
    asyncio.create_task(payment_watcher_loop(bot))
    asyncio.create_task(deposit_watcher_loop(bot))
    logger.info("DB pool ready. Watchers started.")

async def post_init(app):
    pool = await get_pool()
    schema_sql = Path("db/schema.sql").read_text()
    await pool.execute(schema_sql)          # safe — all tables use CREATE IF NOT EXISTS
    bot = app.bot
    asyncio.create_task(payment_watcher_loop(bot))
    asyncio.create_task(deposit_watcher_loop(bot))
    logger.info("DB ready. Watchers started.")


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
