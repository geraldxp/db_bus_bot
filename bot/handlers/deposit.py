"""
Flow: Deposit Menu → Preset/Custom Amount → Create Intent → Show Instructions → Watcher confirms
"""
from datetime import datetime, timedelta, timezone

from telegram import Update
from telegram.ext import ContextTypes, CallbackQueryHandler, MessageHandler, filters, ConversationHandler

import db.bus as bus
from bot.menus.keyboards import deposit_amount_keyboard
from config import DEPOSIT_EXPIRY_MINUTES, DEPOSIT_ADDRESS

WAITING_CUSTOM_AMOUNT = 1


async def deposit_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "💰 *Deposit SOL*\n\nChoose an amount to top up your balance:",
        parse_mode="Markdown",
        reply_markup=deposit_amount_keyboard(),
    )


async def deposit_preset(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    amount_str = query.data.split(":")[1]

    if amount_str == "custom":
        await query.edit_message_text(
            "✏️ Enter a custom amount in SOL (e.g. `0.75`):", parse_mode="Markdown"
        )
        return WAITING_CUSTOM_AMOUNT

    await _create_deposit_intent(update, ctx, float(amount_str))
    return ConversationHandler.END


async def deposit_custom_amount(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        amount = float(update.message.text.strip())
        if amount <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Invalid amount. Please enter a positive number.")
        return WAITING_CUSTOM_AMOUNT

    await _create_deposit_intent(update, ctx, amount)
    return ConversationHandler.END


async def _create_deposit_intent(update, ctx, amount: float):
    tg_user = update.effective_user
    db_user = await bus.get_user(tg_user.id)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=DEPOSIT_EXPIRY_MINUTES)
    memo = f"deposit-{db_user['id']}-{int(datetime.now().timestamp())}"

    deposit = await bus.insert_deposit(
        user_id=db_user["id"],
        expected_amount=amount,
        address=DEPOSIT_ADDRESS,
        memo=memo,
        expires_at=expires_at,
    )

    msg = (
        f"📥 *Deposit Intent Created*\n\n"
        f"Amount: `{amount} SOL`\n"
        f"Send to: `{DEPOSIT_ADDRESS}`\n"
        f"Memo: `{memo}`\n\n"
        f"⏳ Expires in {DEPOSIT_EXPIRY_MINUTES} minutes.\n"
        f"Your balance will update automatically once confirmed."
    )
    reply = update.callback_query.edit_message_text if update.callback_query else update.message.reply_text
    await reply(msg, parse_mode="Markdown")


async def deposit_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Deposit cancelled.")
    return ConversationHandler.END


def register(app):
    from telegram.ext import CommandHandler
    conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(deposit_preset, pattern=r"^deposit_amount:"),
        ],
        states={
            WAITING_CUSTOM_AMOUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, deposit_custom_amount)
            ],
        },
        fallbacks=[CommandHandler("cancel", deposit_cancel)],
        per_message=False,
    )
    app.add_handler(conv)
