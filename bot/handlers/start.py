from telegram import Update
from telegram.ext import ContextTypes, CommandHandler, MessageHandler, CallbackQueryHandler, filters

import db.bus as bus
from bot.menus.keyboards import main_menu_keyboard
from utils.templates import welcome
from utils.rate_limit import rate_limit

_STALE_KEYS = (
    "new_svc", "edit_svc_id", "progress_order_id", "proof_order_id",
    "note_order_id", "reply_ticket_id", "open_ticket_id",
    "current_order_id", "service_id", "priority",
    "required_inputs", "collected_inputs", "input_index",
    "wallet_nonce", "wallet_nonce_ts",
    "broadcast_msg",
)


def _clear_stale_state(ctx: ContextTypes.DEFAULT_TYPE):
    """Wipe any in-progress conversation data so /start always recovers cleanly."""
    for key in _STALE_KEYS:
        ctx.user_data.pop(key, None)


@rate_limit(max_calls=5, window=30)
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    _clear_stale_state(ctx)
    user = update.effective_user
    db_user = await bus.upsert_user(user.id, user.username or "")
    if db_user["is_blocked"]:
        await update.message.reply_text("You have been blocked from using this bot.")
        return
    await update.message.reply_text(
        welcome(user.first_name),
        parse_mode="Markdown",
        reply_markup=main_menu_keyboard(),
    )


async def cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Universal /cancel — aborts any active conversation and returns to menu."""
    _clear_stale_state(ctx)
    await update.message.reply_text(
        "❌ Cancelled. Use the menu to continue.",
        reply_markup=main_menu_keyboard(),
    )
    from telegram.ext import ConversationHandler
    return ConversationHandler.END


async def handle_menu_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    db_user = await bus.get_user(update.effective_user.id)
    if db_user and db_user["is_blocked"]:
        return

    text = update.message.text
    if text == "🛍 Services":
        from bot.handlers.services import services_list
        await services_list(update, ctx)
    elif text == "💰 Deposit":
        from bot.handlers.deposit import deposit_menu
        await deposit_menu(update, ctx)
    elif text == "👛 Wallet":
        from bot.handlers.wallet import wallet_menu
        await wallet_menu(update, ctx)
    elif text == "👤 Profile":
        from bot.handlers.profile import profile_menu
        await profile_menu(update, ctx)
    elif text == "🎫 Support":
        from bot.handlers.support import support_menu
        await support_menu(update, ctx)


async def nav_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Central back-navigation — edits existing message, no duplicate sends."""
    query = update.callback_query
    await query.answer()
    dest = query.data.split(":")[1]

    if dest == "main":
        # Edit the existing inline message to a clean state — no second message
        await query.edit_message_text(
            "🏠 Use the menu below to continue.",
            reply_markup=None,
        )
    elif dest == "services":
        from bot.handlers.services import _send_services_list
        await _send_services_list(query, ctx)
    elif dest == "profile":
        from bot.handlers.profile import _send_profile_menu
        await _send_profile_menu(query, ctx)


def register(app):
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(
        MessageHandler(
            filters.TEXT & filters.Regex(
                r"^(🛍 Services|💰 Deposit|👛 Wallet|👤 Profile|🎫 Support)$"
            ),
            handle_menu_text,
        )
    )
    app.add_handler(CallbackQueryHandler(nav_callback, pattern=r"^nav:"))
