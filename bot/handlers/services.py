"""
Services → Order → Payment flow.
Handles input validation per field type (text/url/number/file/sol_address).
"""
import json
from datetime import datetime, timedelta, timezone

from telegram import Update
from telegram.ext import (
    ContextTypes, CallbackQueryHandler, MessageHandler,
    filters, ConversationHandler, CommandHandler,
)

import db.bus as bus
from bot.menus.keyboards import (
    services_keyboard, service_info_keyboard, payment_method_keyboard
)
from utils.templates import (
    services_list_header, service_info as tmpl_service_info,
    order_created, ask_input, input_invalid,
    insufficient_balance, payment_success, direct_payment_instructions,
)
from utils.validators import validate_field, validate_file
from utils.rate_limit import rate_limit
from utils.notify import notify_admin_new_order
from config import PAYMENT_EXPIRY_MINUTES, DEPOSIT_ADDRESS

COLLECTING_INPUTS = 1

_MD_ESCAPE = str.maketrans({c: f"\\{c}" for c in r"_*[]()~`>#+-=|{}.!"})


def _esc(text: str) -> str:
    """Escape user-controlled text before embedding in Markdown messages."""
    return text.translate(_MD_ESCAPE)


async def services_list(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    services = await bus.get_active_services()
    if not services:
        await update.message.reply_text("No services available right now.")
        return
    await update.message.reply_text(
        services_list_header(),
        parse_mode="Markdown",
        reply_markup=services_keyboard(services),
    )


async def _send_services_list(query, ctx):
    services = await bus.get_active_services()
    await query.edit_message_text(
        services_list_header(),
        parse_mode="Markdown",
        reply_markup=services_keyboard(services),
    )


async def service_info_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    service_id = int(query.data.split(":")[1])
    service = await bus.get_service(service_id)
    if not service:
        await query.edit_message_text("Service not found.")
        return
    ctx.user_data["service_id"] = service_id
    await query.edit_message_text(
        tmpl_service_info(dict(service)),
        parse_mode="Markdown",
        reply_markup=service_info_keyboard(service_id, bool(service["fast_track_price"])),
    )


async def choose_priority(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, priority, service_id = query.data.split(":")
    service_id = int(service_id)
    service = await bus.get_service(service_id)

    ctx.user_data.update({
        "priority": priority,
        "service_id": service_id,
        "collected_inputs": {},
        "input_index": 0,
    })

    required_inputs = json.loads(service["required_inputs_json"] or "[]")
    ctx.user_data["required_inputs"] = required_inputs

    if not required_inputs:
        await _create_order_and_prompt_payment(query, ctx, service, {})
        return ConversationHandler.END

    field = required_inputs[0]
    await query.edit_message_text(
        ask_input(field["label"], field.get("type", "text")),
        parse_mode="Markdown",
    )
    return COLLECTING_INPUTS


async def collect_input(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    required_inputs = ctx.user_data["required_inputs"]
    collected = ctx.user_data["collected_inputs"]
    idx = ctx.user_data["input_index"]
    field_spec = required_inputs[idx]
    field_type = field_spec.get("type", "text")

    # Handle file field
    if field_type == "file":
        file_ref = None
        mime = None
        size = 0
        if update.message.photo:
            photo = update.message.photo[-1]
            file_ref = photo.file_id
            mime = "image/jpeg"
            size = photo.file_size or 0
        elif update.message.document:
            doc = update.message.document
            file_ref = doc.file_id
            mime = doc.mime_type or ""
            size = doc.file_size or 0
        else:
            await update.message.reply_text(
                input_invalid("Please send a photo or file."), parse_mode="Markdown"
            )
            return COLLECTING_INPUTS

        err = validate_file(mime, size, field_spec)
        if err:
            await update.message.reply_text(input_invalid(err), parse_mode="Markdown")
            return COLLECTING_INPUTS
        # Store as structured dict so downstream code can reliably parse it
        collected[field_spec["field"]] = {"type": "file", "file_id": file_ref, "mime": mime}
    else:
        err = validate_field(field_spec, update.message.text or "")
        if err:
            await update.message.reply_text(input_invalid(err), parse_mode="Markdown")
            return COLLECTING_INPUTS
        collected[field_spec["field"]] = _esc(update.message.text.strip())

    idx += 1
    ctx.user_data["input_index"] = idx

    if idx < len(required_inputs):
        next_field = required_inputs[idx]
        await update.message.reply_text(
            ask_input(next_field["label"], next_field.get("type", "text")),
            parse_mode="Markdown",
        )
        return COLLECTING_INPUTS

    # All inputs collected
    service = await bus.get_service(ctx.user_data["service_id"])
    await _create_order_and_prompt_payment(update, ctx, service, collected)
    return ConversationHandler.END


async def _create_order_and_prompt_payment(source, ctx, service, user_details: dict):
    priority = ctx.user_data.get("priority", "STANDARD")
    if priority == "FAST_TRACK" and service["fast_track_price"]:
        price = float(service["fast_track_price"])
        eta = service["fast_track_eta"]
    else:
        price = float(service["price"])
        eta = service["eta"]

    tg_user = source.effective_user if hasattr(source, "effective_user") else source.from_user
    db_user = await bus.get_user(tg_user.id)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=PAYMENT_EXPIRY_MINUTES)

    order = await bus.insert_order(
        user_id=db_user["id"],
        service_id=service["id"],
        priority=priority,
        price=price,
        eta=eta,
        user_details=user_details,
        payment_expires_at=expires_at,
    )
    ctx.user_data["current_order_id"] = order["id"]

    text = order_created(order["id"], service["name"], priority, price, eta)
    kb = payment_method_keyboard(order["id"])

    if hasattr(source, "edit_message_text"):
        await source.edit_message_text(text, parse_mode="Markdown", reply_markup=kb)
    else:
        await source.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)


async def pay_balance(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    order_id = int(query.data.split(":")[2])
    order = await bus.get_order(order_id)
    db_user = await bus.get_user(update.effective_user.id)

    if float(db_user["balance_sol"]) < float(order["price"]):
        await query.edit_message_text(
            insufficient_balance(float(db_user["balance_sol"]), float(order["price"])),
            parse_mode="Markdown",
        )
        return

    new_balance = float(db_user["balance_sol"]) - float(order["price"])
    await bus.update_user_balance(db_user["id"], new_balance)
    await bus.insert_ledger(db_user["id"], "DEBIT", float(order["price"]), "Order payment", str(order_id))
    await bus.update_order_payment_method(order_id, "BALANCE")
    await bus.update_order_status(order_id, "PAID", progress=5, progress_stage="queued")

    await query.edit_message_text(
        payment_success(order_id, new_balance), parse_mode="Markdown"
    )
    await notify_admin_new_order(ctx.bot, order_id)


async def pay_direct(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    order_id = int(query.data.split(":")[2])
    order = await bus.get_order(order_id)
    memo = f"order-{order_id}"
    await bus.update_order_pay_address(order_id, DEPOSIT_ADDRESS, memo)
    await bus.update_order_payment_method(order_id, "DIRECT")

    await query.edit_message_text(
        direct_payment_instructions(
            order_id, DEPOSIT_ADDRESS, memo, float(order["price"]), PAYMENT_EXPIRY_MINUTES
        ),
        parse_mode="Markdown",
    )


async def pay_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    order_id = int(query.data.split(":")[2])
    await bus.update_order_status(order_id, "CANCELLED")
    await query.edit_message_text(f"❌ Order #{order_id} cancelled.")


async def conv_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data.pop("required_inputs", None)
    ctx.user_data.pop("collected_inputs", None)
    ctx.user_data.pop("input_index", None)
    await update.message.reply_text("❌ Order cancelled.")
    return ConversationHandler.END


def register(app):
    conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(choose_priority, pattern=r"^priority:")],
        states={
            COLLECTING_INPUTS: [
                MessageHandler(
                    (filters.TEXT | filters.PHOTO | filters.Document.ALL) & ~filters.COMMAND,
                    collect_input,
                )
            ],
        },
        fallbacks=[CommandHandler("cancel", conv_cancel)],
        per_user=True,
        per_chat=True,
        per_message=False,
    )
    app.add_handler(CallbackQueryHandler(service_info_cb, pattern=r"^service:\d+$"))
    app.add_handler(conv)
    app.add_handler(CallbackQueryHandler(pay_balance, pattern=r"^pay:balance:"))
    app.add_handler(CallbackQueryHandler(pay_direct, pattern=r"^pay:direct:"))
    app.add_handler(CallbackQueryHandler(pay_cancel, pattern=r"^pay:cancel:"))
