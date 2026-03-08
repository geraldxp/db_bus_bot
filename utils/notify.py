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
        logger.warning("Could not notify user %s: %s", telegram_id, e)


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
    from utils.templates import admin_new_order
    try:
        order = await bus.get_order_with_service(order_id)
        if not order:
            logger.warning("notify_admin_new_order: order %s not found", order_id)
            return
        user = await bus.get_user_by_id(order["user_id"])
        username = (user["username"] or str(user["telegram_id"])) if user else "unknown"
        text = admin_new_order(
            order_id=order_id,
            username=username,
            service_name=order.get("service_name") or str(order["service_id"]),
            priority=order["priority"],
            payment_method=order.get("payment_method") or "—",
        )
        await bot.send_message(ADMIN_CHANNEL_ID, text, parse_mode="Markdown")
    except Exception as e:
        logger.warning("Could not notify admin channel for order %s: %s", order_id, e)


async def notify_admin_deposit(bot, deposit_id: int, amount: float):
    """Post a deposit confirmed alert to the admin channel."""
    from utils.templates import admin_deposit_detected
    try:
        tg_id = await bus.get_deposit_owner_telegram_id(deposit_id)
        user = await bus.get_user(tg_id) if tg_id else None
        username = (user["username"] or str(tg_id)) if user else "unknown"
        text = admin_deposit_detected(username=username, amount=amount)
        await bot.send_message(ADMIN_CHANNEL_ID, text, parse_mode="Markdown")
    except Exception as e:
        logger.warning("Could not notify admin channel for deposit %s: %s", deposit_id, e)


async def notify_admin_new_ticket(bot, ticket_id: int):
    """Post a new ticket alert to the admin channel."""
    from utils.templates import admin_new_ticket
    from config import SUPPORT_GROUP_ID
    try:
        tg_id = await bus.get_ticket_owner_telegram_id(ticket_id)
        user = await bus.get_user(tg_id) if tg_id else None
        username = (user["username"] or str(tg_id)) if user else "unknown"
        text = admin_new_ticket(ticket_id=ticket_id, username=username)
        await bot.send_message(SUPPORT_GROUP_ID, text, parse_mode="Markdown")
    except Exception as e:
        logger.warning("Could not notify support group for ticket %s: %s", ticket_id, e)
