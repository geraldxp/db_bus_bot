"""
Generated Wallet flow — extend existing wallet system.

Generates a Solana keypair + BIP39 mnemonic for the user and stores it
encrypted in the database. One wallet per user maximum.

Encryption: Fernet symmetric encryption using WALLET_ENCRYPTION_KEY from .env.
Key generation: PyNaCl ed25519 SigningKey from BIP39 seed bytes.
Address encoding: base58 of the 32-byte verify (public) key.
Private key format: base58 of 64 bytes (signing_key_bytes + verify_key_bytes),
                    matching Phantom/Solflare import format.
"""
import logging
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes, CallbackQueryHandler, ConversationHandler, CommandHandler

import db.bus as bus
from utils.solana import get_sol_balance
from utils.templates import esc

logger = logging.getLogger(__name__)

# Conversation state
WAITING_DELETE_CONFIRM = 50


# ─── ENCRYPTION ───────────────────────────────────────────────────────────────

def _fernet():
    """Return a Fernet instance using WALLET_ENCRYPTION_KEY. Raises if not set."""
    from config import WALLET_ENCRYPTION_KEY
    if not WALLET_ENCRYPTION_KEY:
        raise RuntimeError(
            "WALLET_ENCRYPTION_KEY is not set. "
            "Generate one with: python3 -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        )
    from cryptography.fernet import Fernet
    return Fernet(WALLET_ENCRYPTION_KEY.encode())


def _encrypt(text: str) -> str:
    return _fernet().encrypt(text.encode()).decode()


def _decrypt(token: str) -> str:
    return _fernet().decrypt(token.encode()).decode()


# ─── KEYPAIR GENERATION ───────────────────────────────────────────────────────

def _generate_keypair() -> tuple[str, str, str]:
    """
    Generate a new Solana wallet.
    Returns (wallet_address, private_key_b58, seed_phrase).

    - BIP39 12-word mnemonic via `mnemonic` library
    - Seed bytes → ed25519 SigningKey via PyNaCl
    - Address = base58(verify_key bytes) — 32 bytes
    - Private key = base58(signing_key + verify_key) — 64 bytes (Phantom-compatible)
    """
    from mnemonic import Mnemonic
    import nacl.signing
    import base58 as _base58

    mnemo = Mnemonic("english")
    seed_phrase = mnemo.generate(strength=128)          # 12 words
    seed_bytes = mnemo.to_seed(seed_phrase)             # 64 bytes

    signing_key = nacl.signing.SigningKey(seed_bytes[:32])
    verify_key = signing_key.verify_key

    address = _base58.b58encode(bytes(verify_key)).decode()
    privkey = _base58.b58encode(bytes(signing_key) + bytes(verify_key)).decode()

    return address, privkey, seed_phrase


# ─── KEYBOARDS ────────────────────────────────────────────────────────────────

def generated_wallet_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 View Address",     callback_data="genw:view_address")],
        [InlineKeyboardButton("🔑 View Private Key", callback_data="genw:view_privkey"),
         InlineKeyboardButton("🌱 View Seed Phrase", callback_data="genw:view_seed")],
        [InlineKeyboardButton("💰 View Balance",     callback_data="genw:view_balance")],
        [InlineKeyboardButton("📥 Deposit Funds",    callback_data="genw:deposit")],
        [InlineKeyboardButton("🗑 Delete Wallet",    callback_data="genw:delete_start")],
        [InlineKeyboardButton("« Back",              callback_data="nav:main")],
    ])


def reveal_confirm_keyboard(action: str) -> InlineKeyboardMarkup:
    """Inline confirm button before showing sensitive data."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Yes, show me", callback_data=f"genw:reveal:{action}")],
        [InlineKeyboardButton("❌ Cancel",        callback_data="genw:back_to_menu")],
    ])


def delete_confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⚠️ Yes, delete permanently", callback_data="genw:delete_confirm")],
        [InlineKeyboardButton("❌ Cancel",                   callback_data="genw:back_to_menu")],
    ])


# ─── HELPERS ─────────────────────────────────────────────────────────────────

async def _get_gen_wallet(telegram_id: int):
    db_user = await bus.get_user(telegram_id)
    if not db_user:
        return None, None
    gw = await bus.get_generated_wallet(db_user["id"])
    return db_user, gw


async def _send_wallet_menu(query, telegram_id: int):
    """(Re)render the generated wallet menu."""
    _, gw = await _get_gen_wallet(telegram_id)
    if not gw:
        await query.edit_message_text(
            "⚠️ No generated wallet found. Tap *Generate SOL Wallet* to create one.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("« Back", callback_data="nav:main")]]),
        )
        return
    await query.edit_message_text(
        f"👛 *Generated Wallet*\n──────────────\n\n"
        f"*Address*\n`{gw['wallet_address']}`\n\n"
        f"_Use the buttons below to manage your wallet._",
        parse_mode="Markdown",
        reply_markup=generated_wallet_keyboard(),
    )


# ─── GENERATE ENTRY ──────────────────────────────────────────────────────────

async def genw_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Entry point — wallet:generate callback."""
    query = update.callback_query
    await query.answer()

    db_user, gw = await _get_gen_wallet(update.effective_user.id)
    if not db_user:
        await query.edit_message_text("❌ User not found. Try /start first.")
        return

    if gw:
        # Already has one — show existing wallet menu
        await query.edit_message_text(
            f"👛 *Generated Wallet*\n──────────────\n\n"
            f"*Address*\n`{gw['wallet_address']}`\n\n"
            f"_You already have a generated wallet. Delete it first to generate a new one._",
            parse_mode="Markdown",
            reply_markup=generated_wallet_keyboard(),
        )
        return

    # Check encryption key is configured before proceeding
    try:
        _fernet()
    except RuntimeError as e:
        logger.error("Wallet generation blocked: %s", e)
        await query.edit_message_text(
            "❌ *Wallet generation is not available*\n\n"
            "The server administrator needs to configure `WALLET_ENCRYPTION_KEY`.\n\n"
            "Please contact support.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("« Back", callback_data="nav:main")]]),
        )
        return

    # Generate
    try:
        address, privkey, seed_phrase = _generate_keypair()
    except Exception as e:
        logger.error("Keypair generation failed: %s", e, exc_info=True)
        await query.edit_message_text(
            "❌ Wallet generation failed. Please try again or contact support.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("« Back", callback_data="nav:main")]]),
        )
        return

    # Encrypt and store
    try:
        enc_privkey = _encrypt(privkey)
        enc_seed = _encrypt(seed_phrase)
        await bus.insert_generated_wallet(
            user_id=db_user["id"],
            wallet_address=address,
            encrypted_privkey=enc_privkey,
            encrypted_seed=enc_seed,
        )
        logger.info("Generated wallet for user %s: %s...", update.effective_user.id, address[:8])
    except Exception as e:
        logger.error("Failed to store generated wallet for user %s: %s", update.effective_user.id, e, exc_info=True)
        await query.edit_message_text(
            "❌ Failed to save wallet. Please try again.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("« Back", callback_data="nav:main")]]),
        )
        return

    # Show result — display full details once, then only on demand
    await query.edit_message_text(
        f"✅ *Wallet Generated Successfully*\n──────────────\n\n"
        f"*Wallet Address*\n`{address}`\n\n"
        f"*Private Key*\n`{privkey}`\n\n"
        f"*Seed Phrase*\n`{seed_phrase}`\n\n"
        f"──────────────\n"
        f"⚠️ *Save your private key and seed phrase securely.*\n"
        f"You can view them again anytime from the wallet menu, "
        f"but they are never shared with anyone else.\n\n"
        f"_Never share your private key or seed phrase with anyone, "
        f"including HypeForge support._",
        parse_mode="Markdown",
        reply_markup=generated_wallet_keyboard(),
    )


# ─── VIEW ADDRESS ─────────────────────────────────────────────────────────────

async def genw_view_address(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    db_user, gw = await _get_gen_wallet(update.effective_user.id)
    if not gw:
        await query.edit_message_text("No generated wallet found.")
        return
    await query.edit_message_text(
        f"📋 *Wallet Address*\n──────────────\n\n"
        f"`{gw['wallet_address']}`\n\n"
        f"_Copy this address to receive SOL._",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("« Wallet Menu", callback_data="genw:back_to_menu")]]),
    )


# ─── VIEW PRIVATE KEY (with confirm) ─────────────────────────────────────────

async def genw_view_privkey_prompt(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "🔑 *View Private Key*\n──────────────\n\n"
        "⚠️ Your private key grants full access to your wallet.\n\n"
        "• Never share it with anyone\n"
        "• HypeForge support will never ask for it\n"
        "• Make sure no one can see your screen\n\n"
        "Are you sure you want to reveal your private key?",
        parse_mode="Markdown",
        reply_markup=reveal_confirm_keyboard("privkey"),
    )


async def genw_view_seed_prompt(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "🌱 *View Seed Phrase*\n──────────────\n\n"
        "⚠️ Your seed phrase can be used to recover your entire wallet.\n\n"
        "• Never share it with anyone\n"
        "• HypeForge support will never ask for it\n"
        "• Make sure no one can see your screen\n\n"
        "Are you sure you want to reveal your seed phrase?",
        parse_mode="Markdown",
        reply_markup=reveal_confirm_keyboard("seed"),
    )


async def genw_reveal(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle genw:reveal:privkey and genw:reveal:seed."""
    query = update.callback_query
    await query.answer()
    action = query.data.split(":")[2]  # privkey or seed

    db_user, gw = await _get_gen_wallet(update.effective_user.id)
    if not gw:
        await query.edit_message_text("No generated wallet found.")
        return

    try:
        if action == "privkey":
            value = _decrypt(gw["encrypted_privkey"])
            label = "🔑 *Private Key*"
            note = "_Import this into Phantom or any Solana wallet app._"
        else:
            value = _decrypt(gw["encrypted_seed"])
            label = "🌱 *Seed Phrase*"
            note = "_Use these 12 words to recover your wallet._"
    except Exception as e:
        logger.error("Decryption failed for user %s: %s", update.effective_user.id, e)
        await query.edit_message_text(
            "❌ Could not decrypt wallet data. Contact support if this persists.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("« Back", callback_data="genw:back_to_menu")]]),
        )
        return

    await query.edit_message_text(
        f"{label}\n──────────────\n\n"
        f"`{value}`\n\n"
        f"──────────────\n"
        f"⚠️ _Delete this message after saving._\n{note}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("« Wallet Menu", callback_data="genw:back_to_menu")]]),
    )


# ─── VIEW BALANCE ─────────────────────────────────────────────────────────────

async def genw_view_balance(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("Checking balance…")
    db_user, gw = await _get_gen_wallet(update.effective_user.id)
    if not gw:
        await query.edit_message_text("No generated wallet found.")
        return

    balance = await get_sol_balance(gw["wallet_address"])
    if balance < 0:
        balance_text = "_Could not fetch balance. Check your connection._"
    else:
        balance_text = f"`{balance:.9f} SOL`"

    await query.edit_message_text(
        f"💰 *Wallet Balance*\n──────────────\n\n"
        f"*Address*\n`{gw['wallet_address']}`\n\n"
        f"*On-chain Balance*\n{balance_text}\n\n"
        f"_Balance reflects confirmed on-chain SOL._",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Refresh", callback_data="genw:view_balance")],
            [InlineKeyboardButton("« Wallet Menu", callback_data="genw:back_to_menu")],
        ]),
    )


# ─── DEPOSIT ─────────────────────────────────────────────────────────────────

async def genw_deposit(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    db_user, gw = await _get_gen_wallet(update.effective_user.id)
    if not gw:
        await query.edit_message_text("No generated wallet found.")
        return

    await query.edit_message_text(
        f"📥 *Deposit Funds*\n──────────────\n\n"
        f"Send SOL directly to your generated wallet address.\n\n"
        f"*Your Wallet Address*\n`{gw['wallet_address']}`\n\n"
        f"*Important*\n\n"
        f"• Send only SOL (Solana native token)\n"
        f"• No minimum amount required\n"
        f"• No memo needed — this is your personal wallet\n"
        f"• Balance updates automatically once confirmed on-chain\n\n"
        f"_Tap View Balance to check your updated balance after sending._",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("💰 View Balance", callback_data="genw:view_balance")],
            [InlineKeyboardButton("« Wallet Menu",  callback_data="genw:back_to_menu")],
        ]),
    )


# ─── DELETE ──────────────────────────────────────────────────────────────────

async def genw_delete_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    db_user, gw = await _get_gen_wallet(update.effective_user.id)
    if not gw:
        await query.edit_message_text("No generated wallet found.")
        return

    await query.edit_message_text(
        f"🗑 *Delete Generated Wallet*\n──────────────\n\n"
        f"*Address*\n`{gw['wallet_address']}`\n\n"
        f"⚠️ *This action is permanent.*\n\n"
        f"• Your private key and seed phrase will be deleted from our servers\n"
        f"• Any SOL remaining in this wallet will NOT be recovered automatically\n"
        f"• Make sure you have saved your private key or seed phrase first\n\n"
        f"Are you sure you want to permanently delete this wallet?",
        parse_mode="Markdown",
        reply_markup=delete_confirm_keyboard(),
    )


async def genw_delete_confirm(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    db_user, gw = await _get_gen_wallet(update.effective_user.id)
    if not gw:
        await query.edit_message_text("No wallet to delete.")
        return

    address_snip = gw["wallet_address"][:12] + "…"
    await bus.delete_generated_wallet(db_user["id"])
    logger.info("User %s deleted generated wallet %s", update.effective_user.id, gw["wallet_address"][:8])

    await query.edit_message_text(
        f"✅ *Wallet Deleted*\n──────────────\n\n"
        f"Generated wallet `{address_snip}` has been permanently removed.\n\n"
        f"You can generate a new wallet anytime from the Wallet menu.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("« Back", callback_data="nav:main")]]),
    )


# ─── BACK TO MENU ─────────────────────────────────────────────────────────────

async def genw_back_to_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await _send_wallet_menu(query, update.effective_user.id)


# ─── REGISTER ─────────────────────────────────────────────────────────────────

def register(app):
    app.add_handler(CallbackQueryHandler(genw_start,            pattern=r"^wallet:generate$"))
    app.add_handler(CallbackQueryHandler(genw_view_address,     pattern=r"^genw:view_address$"))
    app.add_handler(CallbackQueryHandler(genw_view_privkey_prompt, pattern=r"^genw:view_privkey$"))
    app.add_handler(CallbackQueryHandler(genw_view_seed_prompt, pattern=r"^genw:view_seed$"))
    app.add_handler(CallbackQueryHandler(genw_reveal,           pattern=r"^genw:reveal:"))
    app.add_handler(CallbackQueryHandler(genw_view_balance,     pattern=r"^genw:view_balance$"))
    app.add_handler(CallbackQueryHandler(genw_deposit,          pattern=r"^genw:deposit$"))
    app.add_handler(CallbackQueryHandler(genw_delete_start,     pattern=r"^genw:delete_start$"))
    app.add_handler(CallbackQueryHandler(genw_delete_confirm,   pattern=r"^genw:delete_confirm$"))
    app.add_handler(CallbackQueryHandler(genw_back_to_menu,     pattern=r"^genw:back_to_menu$"))
