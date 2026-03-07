"""
Notification helpers — all use DB Bus, no raw SQL.
"""
import logging
import db.bus as bus
from config import ADMIN_CHANNEL_ID

logger = logging.getLogger(__name__)


async def notify_user(bot, telegram_id: int, text: str, parse_mode: str = "Markdown"):
    """Send a message to a user by their Telegram ID."""
    try:
        await bot.send_message(telegram_id, text, parse_mode=parse_mode)
    except Exception as e:
        logger.warning(f"Could not notify user {telegram_id}: {e}")


async def notify_user_by_user_id(bot, user_id: int, text: str):
    """Send a message to a user by their internal DB user_id."""
    tg_id = await bus.get_telegram_id_by_user_id(user_id)
    if tg_id:
        await notify_user(bot, tg_id, text)


async def notify_order_owner(bot, order_id: int, text: str):
    """Notify the user who owns an order."""
    tg_id = await bus.get_order_owner_telegram_id(order_id)
    if tg_id:
        await notify_user(bot, tg_id, text)


async def notify_admin_new_order(bot, order_id: int):
    """Post a new paid order alert to the admin channel."""
    try:
        order = await bus.get_order(order_id)
        await bot.send_message(
            ADMIN_CHANNEL_ID,
            f"🆕 *New Order #{order_id}*\n"
            f"Status: `{order['status']}`\n"
            f"Price: `{order['price']} SOL`\n"
            f"ETA: {order['eta']}\n\n"
            f"Use /admin to manage.",
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.warning(f"Could not notify admin channel for order {order_id}: {e}")
