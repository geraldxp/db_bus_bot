from telegram import Update
from telegram.ext import ContextTypes, CallbackQueryHandler

import db.bus as bus
from bot.menus.keyboards import profile_keyboard, orders_list_keyboard, order_detail_keyboard
from utils.templates import order_detail as tmpl_order_detail


async def profile_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👤 *Profile*", parse_mode="Markdown", reply_markup=profile_keyboard()
    )


async def _send_profile_menu(query, ctx):
    await query.edit_message_text(
        "👤 *Profile*", parse_mode="Markdown", reply_markup=profile_keyboard()
    )


async def profile_balance(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    db_user = await bus.get_user(update.effective_user.id)
    ledger = await bus.get_user_ledger(db_user["id"])
    pending = await bus.get_user_pending_deposits(db_user["id"])
    pending_total = sum(float(d["expected_amount"]) for d in pending)

    lines = "\n".join(
        f"{'➕' if r['type'] == 'CREDIT' else '➖'} `{r['amount']} SOL` — {r['reason']}"
        for r in ledger[:5]
    ) or "_No transactions yet._"

    from bot.menus.keyboards import InlineKeyboardMarkup, InlineKeyboardButton
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("« Profile", callback_data="nav:profile")]])

    await query.edit_message_text(
        f"💰 *Balance*: `{db_user['balance_sol']} SOL`\n"
        f"⏳ Pending deposits: `{pending_total} SOL`\n\n"
        f"*Recent transactions:*\n{lines}",
        parse_mode="Markdown",
        reply_markup=kb,
    )


async def profile_orders(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    db_user = await bus.get_user(update.effective_user.id)
    orders = await bus.get_user_orders(db_user["id"])

    if not orders:
        from bot.menus.keyboards import InlineKeyboardMarkup, InlineKeyboardButton
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("« Profile", callback_data="nav:profile")]])
        await query.edit_message_text("You have no orders yet.", reply_markup=kb)
        return

    await query.edit_message_text(
        "📦 *Your Orders* — tap one for details:",
        parse_mode="Markdown",
        reply_markup=orders_list_keyboard(list(orders)),
    )


async def order_detail_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    order_id = int(query.data.split(":")[1])
    order = await bus.get_order_with_service(order_id)
    if not order:
        await query.edit_message_text("Order not found.")
        return
    has_proof = bool(order["proof_json"])
    await query.edit_message_text(
        tmpl_order_detail(dict(order)),
        parse_mode="Markdown",
        reply_markup=order_detail_keyboard(order_id, has_proof),
    )


async def order_proof_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    order_id = int(query.data.split(":")[1])
    order = await bus.get_order(order_id)
    if not order or not order["proof_json"]:
        await query.answer("No proof uploaded yet.", show_alert=True)
        return

    import json
    proof = order["proof_json"] if isinstance(order["proof_json"], dict) else json.loads(order["proof_json"])
    file_id = proof.get("file_id")
    caption = proof.get("caption", "Proof of work")
    if file_id:
        try:
            await update.effective_chat.send_document(document=file_id, caption=caption)
        except Exception:
            await update.effective_chat.send_photo(photo=file_id, caption=caption)


async def profile_wallet_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """profile:wallet → show wallet menu inline."""
    query = update.callback_query
    await query.answer()
    db_user = await bus.get_user(update.effective_user.id)
    has_phantom = bool(db_user and db_user["wallet_pubkey"])
    gw = await bus.get_generated_wallet(db_user["id"]) if db_user else None
    has_generated = gw is not None
    from bot.menus.keyboards import wallet_keyboard
    from utils.templates import wallet_view
    if has_phantom:
        text = wallet_view(db_user["wallet_pubkey"])
    else:
        text = "👛 *Wallet*\n\nNo linked wallet connected."
    await query.edit_message_text(
        text, parse_mode="Markdown",
        reply_markup=wallet_keyboard(has_phantom=has_phantom, has_generated=has_generated),
    )


def register(app):
    app.add_handler(CallbackQueryHandler(profile_balance, pattern=r"^profile:balance$"))
    app.add_handler(CallbackQueryHandler(profile_orders, pattern=r"^profile:orders$"))
    app.add_handler(CallbackQueryHandler(profile_wallet_cb, pattern=r"^profile:wallet$"))
    app.add_handler(CallbackQueryHandler(order_detail_cb, pattern=r"^order_detail:"))
    app.add_handler(CallbackQueryHandler(order_proof_cb, pattern=r"^order_proof:"))
