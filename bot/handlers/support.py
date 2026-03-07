"""
Support flow — reuses open ticket per user, admin auth for /reply, close/reopen.
"""
import logging
from telegram import Update
from telegram.ext import (
    ContextTypes, CallbackQueryHandler, MessageHandler,
    filters, ConversationHandler, CommandHandler,
)

import db.bus as bus
from bot.menus.keyboards import support_keyboard, ticket_action_keyboard
from utils.templates import ticket_created, ticket_reply, ticket_closed
from utils.rate_limit import rate_limit
from config import ADMIN_USERNAME, SUPPORT_GROUP_ID

logger = logging.getLogger(__name__)

WAITING_TICKET_MSG = 1
WAITING_TICKET_REPLY = 2


async def support_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎫 *Support*\n\nHow can we help?",
        parse_mode="Markdown",
        reply_markup=support_keyboard(),
    )


async def support_dm(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        f"💬 Contact admin directly: [@{ADMIN_USERNAME}](tg://resolve?domain={ADMIN_USERNAME})",
        parse_mode="Markdown",
    )


@rate_limit(max_calls=3, window=60)
async def support_ticket_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "🎫 *New Ticket*\n\nDescribe your issue:",
        parse_mode="Markdown",
    )
    return WAITING_TICKET_MSG


async def support_ticket_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    db_user = await bus.get_user(update.effective_user.id)

    # Reuse open ticket if exists, otherwise create new
    ticket = await bus.get_open_ticket_for_user(db_user["id"])
    if not ticket:
        ticket = await bus.insert_ticket(db_user["id"])

    await bus.insert_ticket_message(ticket["id"], "USER", text=update.message.text)

    # Forward to support group
    forwarded = True
    try:
        await update.get_bot().send_message(
            SUPPORT_GROUP_ID,
            f"🎫 *Ticket \\#{ticket['id']}*\n"
            f"From: @{update.effective_user.username or update.effective_user.id}\n\n"
            f"{update.message.text}\n\n"
            f"Reply: `/reply {ticket['id']} <message>`\n"
            f"Close: `/close_ticket {ticket['id']}`",
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.error(
            "Failed to forward ticket #%s to support group %s: %s",
            ticket["id"], SUPPORT_GROUP_ID, e, exc_info=True,
        )
        forwarded = False

    reply = ticket_created(ticket["id"])
    if not forwarded:
        reply += "\n\n⚠️ There was an issue alerting our team. Please also contact us via DM."
    await update.message.reply_text(reply)
    ctx.user_data["open_ticket_id"] = ticket["id"]
    return ConversationHandler.END


async def admin_reply_command(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Admin /reply <ticket_id> <message> — only valid from support group + verified admin."""
    if update.effective_chat.id != SUPPORT_GROUP_ID:
        return

    # Verify admin from DB
    admin = await bus.get_admin(update.effective_user.id)
    if not admin:
        await update.message.reply_text("❌ Not authorised.")
        return

    args = ctx.args
    if not args or len(args) < 2:
        await update.message.reply_text("Usage: /reply <ticket_id> <message>")
        return

    try:
        ticket_id = int(args[0])
    except ValueError:
        await update.message.reply_text("Invalid ticket ID.")
        return

    reply_text = " ".join(args[1:])
    ticket = await bus.get_ticket(ticket_id)
    if not ticket:
        await update.message.reply_text("Ticket not found.")
        return
    if ticket["status"] == "CLOSED":
        await update.message.reply_text("Ticket is already closed.")
        return

    await bus.insert_ticket_message(ticket_id, "ADMIN", text=reply_text)

    tg_id = await bus.get_ticket_owner_telegram_id(ticket_id)
    if tg_id:
        try:
            await update.get_bot().send_message(
                tg_id, ticket_reply(ticket_id, reply_text), parse_mode="Markdown"
            )
            await update.message.reply_text(f"✅ Reply sent.")
        except Exception as e:
            await update.message.reply_text(f"Could not reach user: {e}")

    await bus.insert_audit_log(admin["id"], "ticket_reply", "ticket", ticket_id, {"text": reply_text[:200]})


async def close_ticket_command(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """/close_ticket <ticket_id>"""
    admin = await bus.get_admin(update.effective_user.id)
    if not admin:
        return

    if not ctx.args:
        await update.message.reply_text("Usage: /close_ticket <ticket_id>")
        return

    ticket_id = int(ctx.args[0])
    await bus.update_ticket_status(ticket_id, "CLOSED")

    tg_id = await bus.get_ticket_owner_telegram_id(ticket_id)
    if tg_id:
        await update.get_bot().send_message(tg_id, ticket_closed(ticket_id), parse_mode="Markdown")

    await update.message.reply_text(f"✅ Ticket #{ticket_id} closed.")
    await bus.insert_audit_log(admin["id"], "ticket_close", "ticket", ticket_id)


# ─── Admin ticket inbox (callback-based) ─────────────────────────────────────

async def admin_ticket_reply_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    admin = await bus.get_admin(update.effective_user.id)
    if not admin:
        await query.answer("Not authorised.", show_alert=True)
        return
    await query.answer()
    ticket_id = int(query.data.split(":")[2])
    ctx.user_data["reply_ticket_id"] = ticket_id
    await query.edit_message_text(
        f"✏️ Type your reply for Ticket #{ticket_id}:",
    )
    return WAITING_TICKET_REPLY


async def admin_ticket_reply_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ticket_id = ctx.user_data.get("reply_ticket_id")
    if not ticket_id:
        return ConversationHandler.END
    admin = await bus.get_admin(update.effective_user.id)
    reply_text = update.message.text

    await bus.insert_ticket_message(ticket_id, "ADMIN", text=reply_text)
    tg_id = await bus.get_ticket_owner_telegram_id(ticket_id)
    if tg_id:
        await update.get_bot().send_message(tg_id, ticket_reply(ticket_id, reply_text), parse_mode="Markdown")

    await update.message.reply_text(f"✅ Reply sent to ticket #{ticket_id}.")
    if admin:
        await bus.insert_audit_log(admin["id"], "ticket_reply", "ticket", ticket_id)
    return ConversationHandler.END


async def admin_ticket_close_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    admin = await bus.get_admin(update.effective_user.id)
    if not admin:
        await query.answer("Not authorised.", show_alert=True)
        return
    await query.answer()
    ticket_id = int(query.data.split(":")[2])
    await bus.update_ticket_status(ticket_id, "CLOSED")

    tg_id = await bus.get_ticket_owner_telegram_id(ticket_id)
    if tg_id:
        await update.get_bot().send_message(tg_id, ticket_closed(ticket_id), parse_mode="Markdown")

    await query.edit_message_text(f"✅ Ticket #{ticket_id} closed.")
    await bus.insert_audit_log(admin["id"], "ticket_close", "ticket", ticket_id)


async def ticket_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Ticket cancelled.")
    return ConversationHandler.END


def register(app):
    conv_ticket = ConversationHandler(
        entry_points=[CallbackQueryHandler(support_ticket_start, pattern=r"^support:ticket$")],
        states={
            WAITING_TICKET_MSG: [MessageHandler(filters.TEXT & ~filters.COMMAND, support_ticket_message)]
        },
        fallbacks=[CommandHandler("cancel", ticket_cancel)],
    )
    conv_admin_reply = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_ticket_reply_cb, pattern=r"^admin:ticket_reply:")],
        states={
            WAITING_TICKET_REPLY: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_ticket_reply_text)]
        },
        fallbacks=[CommandHandler("cancel", ticket_cancel)],
    )
    app.add_handler(conv_ticket)
    app.add_handler(conv_admin_reply)
    app.add_handler(CallbackQueryHandler(support_dm, pattern=r"^support:dm$"))
    app.add_handler(CallbackQueryHandler(admin_ticket_close_cb, pattern=r"^admin:ticket_close:"))
    app.add_handler(CommandHandler("reply", admin_reply_command))
    app.add_handler(CommandHandler("close_ticket", close_ticket_command))
