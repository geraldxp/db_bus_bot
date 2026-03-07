"""
Wallet connect flow.
Supports two modes:
  1. Telegram WebApp (Phantom mini-app) — if WEBAPP_URL is configured.
  2. Text-based challenge/response fallback — always available.

WebApp flow:
  Bot sends WebApp button → User opens mini-app → Phantom signs nonce
  → WebApp calls sendData({pubkey, signature_b64}) → Bot receives
  web_app_data update → verifies → saves pubkey.

Text flow:
  Bot shows nonce → User signs in Phantom (Sign Message) → User sends
  "<pubkey> <base58_sig>" back → Bot verifies → saves pubkey.
"""
import base64
import json
import logging
import secrets
import time
from telegram import Update
from telegram.ext import (
    ContextTypes, CallbackQueryHandler, MessageHandler,
    filters, ConversationHandler, CommandHandler,
)

import db.bus as bus
from bot.menus.keyboards import wallet_keyboard
from utils.templates import wallet_connect_prompt, wallet_webapp_prompt, wallet_connected, wallet_view as tmpl_wallet_view
from utils.solana import verify_signature
from config import WEBAPP_URL

logger = logging.getLogger(__name__)

WAITING_SIGNATURE = 1
NONCE_TTL_SECONDS = 300  # challenge expires after 5 minutes


async def wallet_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    db_user = await bus.get_user(update.effective_user.id)
    has_wallet = bool(db_user and db_user["wallet_pubkey"])
    await update.message.reply_text(
        "👛 *Wallet*", parse_mode="Markdown",
        reply_markup=wallet_keyboard(has_wallet, webapp_url=_webapp_url_for_user(ctx)),
    )


def _webapp_url_for_user(ctx: ContextTypes.DEFAULT_TYPE) -> str:
    """Return the full WebApp URL including the current nonce if already set."""
    if not WEBAPP_URL:
        return ""
    nonce = ctx.user_data.get("wallet_nonce", "")
    if nonce:
        return f"{WEBAPP_URL.rstrip('/')}?nonce={nonce}"
    return WEBAPP_URL


async def wallet_connect_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Text-based connect flow — generates nonce and asks user to sign."""
    query = update.callback_query
    await query.answer()
    nonce = secrets.token_hex(16)
    ctx.user_data["wallet_nonce"] = nonce
    ctx.user_data["wallet_nonce_ts"] = time.monotonic()
    await query.edit_message_text(
        wallet_connect_prompt(nonce), parse_mode="Markdown"
    )
    return WAITING_SIGNATURE


async def wallet_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data.pop("wallet_nonce", None)
    ctx.user_data.pop("wallet_nonce_ts", None)
    await update.message.reply_text("❌ Wallet connection cancelled.")
    return ConversationHandler.END


async def wallet_signature_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Receive '<pubkey> <base58_signature>' text reply and verify."""
    nonce_ts = ctx.user_data.get("wallet_nonce_ts", 0)
    if time.monotonic() - nonce_ts > NONCE_TTL_SECONDS:
        await update.message.reply_text(
            "⏰ Challenge expired. Please start the Connect flow again."
        )
        ctx.user_data.pop("wallet_nonce", None)
        ctx.user_data.pop("wallet_nonce_ts", None)
        return ConversationHandler.END

    parts = (update.message.text or "").strip().split()
    if len(parts) != 2:
        await update.message.reply_text(
            "❌ Please send: `<pubkey> <base58_signature>`", parse_mode="Markdown"
        )
        return WAITING_SIGNATURE

    pubkey, signature = parts
    nonce = ctx.user_data.get("wallet_nonce", "")

    if not verify_signature(pubkey, nonce, signature):
        logger.warning("Invalid wallet signature from user %s (pubkey=%s)", update.effective_user.id, pubkey[:8])
        await update.message.reply_text("❌ Invalid signature. Check that you signed the exact nonce and try again.")
        return WAITING_SIGNATURE

    await _save_wallet(update.effective_user.id, pubkey, ctx)
    await update.message.reply_text(
        wallet_connected(pubkey), parse_mode="Markdown",
        reply_markup=wallet_keyboard(True),
    )
    return ConversationHandler.END


# ─── WEBAPP DATA HANDLER ──────────────────────────────────────────────────────

async def wallet_webapp_data(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    Receives the signed wallet data from the Telegram WebApp mini-app.
    Expected payload (JSON string): {"pubkey": "...", "signature_b64": "..."}
    The signature is base64-encoded bytes of the ed25519 signature over the nonce.
    """
    if not update.effective_message.web_app_data:
        return

    nonce_ts = ctx.user_data.get("wallet_nonce_ts", 0)
    if time.monotonic() - nonce_ts > NONCE_TTL_SECONDS:
        await update.message.reply_text(
            "⏰ Wallet challenge expired. Please start again."
        )
        ctx.user_data.pop("wallet_nonce", None)
        ctx.user_data.pop("wallet_nonce_ts", None)
        return

    raw = update.effective_message.web_app_data.data
    try:
        payload = json.loads(raw)
        pubkey = payload["pubkey"]
        signature_b64 = payload["signature_b64"]

        if signature_b64.startswith("b58:"):
            # Manual fallback path: signature is already base58 from the user
            signature_b58 = signature_b64[4:]
        else:
            # Phantom extension path: signature is base64-encoded bytes
            sig_bytes = base64.b64decode(signature_b64)
            import base58 as _base58
            signature_b58 = _base58.b58encode(sig_bytes).decode()
    except Exception as e:
        logger.error("WebApp wallet data parse error: %s | raw=%r", e, raw)
        await update.message.reply_text("❌ Invalid wallet data from mini-app. Please try again.")
        return

    nonce = ctx.user_data.get("wallet_nonce", "")
    if not verify_signature(pubkey, nonce, signature_b58):
        logger.warning("Invalid WebApp wallet signature from user %s", update.effective_user.id)
        await update.message.reply_text("❌ Signature verification failed. Please try again.")
        return

    await _save_wallet(update.effective_user.id, pubkey, ctx)
    await update.message.reply_text(
        wallet_connected(pubkey), parse_mode="Markdown",
        reply_markup=wallet_keyboard(True),
    )


async def _save_wallet(telegram_id: int, pubkey: str, ctx: ContextTypes.DEFAULT_TYPE):
    db_user = await bus.get_user(telegram_id)
    await bus.update_wallet_pubkey(db_user["id"], pubkey)
    logger.info("Wallet connected for user %s: %s...", telegram_id, pubkey[:8])
    ctx.user_data.pop("wallet_nonce", None)
    ctx.user_data.pop("wallet_nonce_ts", None)


# ─── VIEW / DISCONNECT ────────────────────────────────────────────────────────

async def wallet_view_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    db_user = await bus.get_user(update.effective_user.id)
    if not db_user["wallet_pubkey"]:
        await query.edit_message_text("No wallet connected.", reply_markup=wallet_keyboard(False))
        return
    await query.edit_message_text(
        tmpl_wallet_view(db_user["wallet_pubkey"]),
        parse_mode="Markdown",
        reply_markup=wallet_keyboard(True),
    )


async def wallet_disconnect_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    db_user = await bus.get_user(update.effective_user.id)
    await bus.update_wallet_pubkey(db_user["id"], None)
    logger.info("User %s disconnected wallet", update.effective_user.id)
    await query.edit_message_text(
        "🔌 Wallet disconnected.", reply_markup=wallet_keyboard(False)
    )


def register(app):
    conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(wallet_connect_cb, pattern=r"^wallet:connect$")],
        states={
            WAITING_SIGNATURE: [MessageHandler(filters.TEXT & ~filters.COMMAND, wallet_signature_cb)]
        },
        fallbacks=[CommandHandler("cancel", wallet_cancel)],
    )
    app.add_handler(conv)
    # WebApp data — fires when mini-app calls sendData()
    app.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, wallet_webapp_data))
    app.add_handler(CallbackQueryHandler(wallet_view_cb, pattern=r"^wallet:view$"))
    app.add_handler(CallbackQueryHandler(wallet_disconnect_cb, pattern=r"^wallet:disconnect$"))
