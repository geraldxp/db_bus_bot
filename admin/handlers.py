"""
Admin Panel — full workboard, service CRUD, ticket inbox, ledger, broadcast.
All actions gated by admins table. All mutations logged to audit_log.
"""
import json
import logging
from telegram import Update
from telegram.ext import (
    ContextTypes, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ConversationHandler,
)

import db.bus as bus
from bot.menus.keyboards import (
    admin_workboard_keyboard, order_action_keyboard,
    ticket_action_keyboard, admin_services_keyboard, service_edit_keyboard,
    broadcast_confirm_keyboard,
)
from utils.notify import notify_order_owner
from utils.templates import esc
from config import SUPPORT_GROUP_ID

logger = logging.getLogger(__name__)

# ─── CONVERSATION STATES ──────────────────────────────────────────────────────
WAITING_BROADCAST      = 10
WAITING_PROOF          = 11
WAITING_PROGRESS       = 12
WAITING_NOTE           = 13
WAITING_SVC_NAME       = 20
WAITING_SVC_DESC       = 21
WAITING_SVC_PRICE      = 22
WAITING_SVC_ETA        = 23
WAITING_SVC_FT_PRICE   = 24
WAITING_SVC_FT_ETA     = 25
WAITING_SVC_TEMPLATE   = 26
WAITING_SVC_EDIT_PRICE    = 27
WAITING_SVC_EDIT_NAME     = 28
WAITING_SVC_EDIT_DESC     = 29
WAITING_SVC_EDIT_TEMPLATE = 30
WAITING_TICKET_REPLY      = 31


async def _require_admin(update: Update):
    admin = await bus.get_admin(update.effective_user.id)
    if not admin:
        if update.callback_query:
            await update.callback_query.answer("❌ Not authorised.", show_alert=True)
        elif update.message:
            await update.message.reply_text("❌ Not authorised.")
    return admin


# ─── PANEL ENTRY ─────────────────────────────────────────────────────────────

async def admin_panel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    admin = await _require_admin(update)
    if not admin:
        return
    await update.message.reply_text(
        f"🔴 *Admin Panel* — {admin['role']}", parse_mode="Markdown",
        reply_markup=admin_workboard_keyboard(),
    )


async def admin_workboard_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    admin = await _require_admin(update)
    if not admin:
        return
    await query.answer()
    await query.edit_message_text(
        "🔴 *Admin Panel*", parse_mode="Markdown",
        reply_markup=admin_workboard_keyboard(),
    )


# ─── WORKBOARD ORDERS ─────────────────────────────────────────────────────────

async def admin_orders_by_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    admin = await _require_admin(update)
    if not admin:
        return
    await query.answer()
    status = query.data.split(":")[2]

    if status == "PAID":
        orders = await bus.get_unclaimed_orders()
    else:
        orders = await bus.get_orders_by_status(status)

    if not orders:
        await query.edit_message_text(
            f"No orders with status *{status}*.", parse_mode="Markdown",
            reply_markup=admin_workboard_keyboard(),
        )
        return

    await query.edit_message_text(
        f"📋 *{status} Orders* ({len(orders)})\n\nShowing up to 5:",
        parse_mode="Markdown",
    )
    for order in list(orders)[:5]:
        await update.effective_chat.send_message(
            f"📦 *Order #{order['id']}*\n"
            f"Status: `{order['status']}` | Stage: _{esc(order['progress_stage'])}_\n"
            f"Price: `{order['price']} SOL` | ETA: {esc(order['eta'])}\n"
            f"Progress: {order['progress']}%"
            + (f"\n📝 _{esc(order['admin_notes'])}_" if order.get("admin_notes") else ""),
            parse_mode="Markdown",
            reply_markup=order_action_keyboard(order["id"], order["status"]),
        )
    logger.info("Admin %s viewed %s orders (status=%s)", admin['id'], min(len(orders), 5), status)


async def admin_claim(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    admin = await _require_admin(update)
    if not admin:
        return
    await query.answer()
    order_id = int(query.data.split(":")[2])
    claimed = await bus.claim_order(order_id, admin["id"])
    if claimed:
        logger.info("Admin %s claimed order %s", admin['id'], order_id)
        await query.edit_message_text(f"✋ Order #{order_id} claimed by you.")
        await notify_order_owner(ctx.bot, order_id, f"✋ Your order #{order_id} has been picked up by our team.")
        await bus.insert_audit_log(admin["id"], "claim", "order", order_id)
    else:
        logger.warning("Admin %s failed to claim order %s (race or wrong status)", admin['id'], order_id)
        await query.edit_message_text(
            f"⚠️ Could not claim order #{order_id} — already claimed or not in PAID status."
        )


async def admin_unclaim(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    admin = await _require_admin(update)
    if not admin:
        return
    await query.answer()
    order_id = int(query.data.split(":")[2])
    await bus.unclaim_order(order_id)
    logger.info("Admin %s unclaimed order %s", admin['id'], order_id)
    await query.edit_message_text(f"↩️ Order #{order_id} unclaimed and returned to PAID queue.")
    await bus.insert_audit_log(admin["id"], "unclaim", "order", order_id)


async def admin_inprogress(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    admin = await _require_admin(update)
    if not admin:
        return
    await query.answer()
    order_id = int(query.data.split(":")[2])
    ctx.user_data["progress_order_id"] = order_id
    await query.edit_message_text(f"Enter progress % for Order #{order_id} (0–100):")
    return WAITING_PROGRESS


async def admin_set_progress(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    admin = await _require_admin(update)
    if not admin:
        return ConversationHandler.END
    try:
        progress = int(update.message.text.strip())
        if not 0 <= progress <= 100:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Enter a number between 0 and 100.")
        return WAITING_PROGRESS

    order_id = ctx.user_data.pop("progress_order_id", None)
    if not order_id:
        await update.message.reply_text("❌ Session lost. Start over.")
        return ConversationHandler.END

    await bus.update_order_status(order_id, "IN_PROGRESS", progress=progress, progress_stage="working")
    await notify_order_owner(ctx.bot, order_id, f"🔧 Order #{order_id} is in progress — {progress}% done.")
    logger.info("Admin %s set order %s progress to %s%%", admin['id'], order_id, progress)
    await update.message.reply_text(f"✅ Order #{order_id} → IN_PROGRESS {progress}%.")
    await bus.insert_audit_log(admin["id"], "set_progress", "order", order_id, {"progress": progress})
    return ConversationHandler.END


async def admin_proof_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    admin = await _require_admin(update)
    if not admin:
        return
    await query.answer()
    order_id = int(query.data.split(":")[2])
    ctx.user_data["proof_order_id"] = order_id
    await query.edit_message_text(f"📎 Send photo/file as proof for Order #{order_id}:")
    return WAITING_PROOF


async def admin_receive_proof(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    admin = await _require_admin(update)
    if not admin:
        return ConversationHandler.END
    order_id = ctx.user_data.pop("proof_order_id", None)
    if not order_id:
        await update.message.reply_text("❌ Session lost. Start over.")
        return ConversationHandler.END

    file_id = None
    if update.message.photo:
        file_id = update.message.photo[-1].file_id
    elif update.message.document:
        file_id = update.message.document.file_id

    if not file_id:
        await update.message.reply_text("❌ Send a photo or file.")
        return WAITING_PROOF

    proof = {"file_id": file_id, "caption": update.message.caption or ""}
    await bus.update_order_proof(order_id, proof)
    # Also mark as completed if currently IN_PROGRESS
    order = await bus.get_order(order_id)
    if order and order["status"] == "IN_PROGRESS":
        await bus.update_order_status(order_id, "COMPLETED", progress=100, progress_stage="completed")
        await notify_order_owner(ctx.bot, order_id, f"🎉 Your order #{order_id} is complete! Proof has been uploaded.")
        await update.message.reply_text(f"✅ Proof saved and Order #{order_id} marked COMPLETED.")
    else:
        await update.message.reply_text(f"✅ Proof saved for Order #{order_id}.")
    await bus.insert_audit_log(admin["id"], "upload_proof", "order", order_id)
    return ConversationHandler.END


async def admin_complete(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    admin = await _require_admin(update)
    if not admin:
        return
    await query.answer()
    order_id = int(query.data.split(":")[2])
    await bus.update_order_status(order_id, "COMPLETED", progress=100, progress_stage="completed")
    await notify_order_owner(ctx.bot, order_id, f"🎉 Your order #{order_id} is complete!")
    logger.info("Admin %s completed order %s", admin['id'], order_id)
    await query.edit_message_text(f"✅ Order #{order_id} marked COMPLETED.")
    await bus.insert_audit_log(admin["id"], "complete", "order", order_id)


async def admin_note_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    admin = await _require_admin(update)
    if not admin:
        return
    await query.answer()
    order_id = int(query.data.split(":")[2])
    ctx.user_data["note_order_id"] = order_id
    await query.edit_message_text(f"📝 Enter internal note for Order #{order_id}:")
    return WAITING_NOTE


async def admin_save_note(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    admin = await _require_admin(update)
    if not admin:
        return ConversationHandler.END
    order_id = ctx.user_data.pop("note_order_id", None)
    if not order_id:
        await update.message.reply_text("❌ Session lost. Start over.")
        return ConversationHandler.END
    await bus.update_order_admin_notes(order_id, update.message.text)
    await update.message.reply_text(f"✅ Note saved for Order #{order_id}.")
    await bus.insert_audit_log(admin["id"], "add_note", "order", order_id)
    return ConversationHandler.END


# ─── TICKETS INBOX ────────────────────────────────────────────────────────────

async def admin_tickets(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    admin = await _require_admin(update)
    if not admin:
        return
    await query.answer()
    tickets = await bus.get_open_tickets()

    if not tickets:
        await query.edit_message_text(
            "No open tickets.", reply_markup=admin_workboard_keyboard()
        )
        return

    await query.edit_message_text(
        f"🎫 *Open Tickets* ({len(tickets)}):", parse_mode="Markdown"
    )
    for t in list(tickets)[:10]:
        msgs = await bus.get_ticket_messages(t["id"])
        # Build a short transcript of the last 3 messages
        transcript_lines = []
        for m in msgs[-3:]:
            role = "👤" if m["from_role"] == "USER" else "🔴"
            text_snip = (m["text"] or "[file]")[:80]
            transcript_lines.append(f"{role} {esc(text_snip)}")
        transcript = "\n".join(transcript_lines) if transcript_lines else "_No messages_"
        username = t.get("username") or str(t["telegram_id"])
        await update.effective_chat.send_message(
            f"🎫 *Ticket #{t['id']}*\n"
            f"User: @{esc(username)}\n\n"
            f"*Last messages:*\n{transcript}",
            parse_mode="Markdown",
            reply_markup=ticket_action_keyboard(t["id"]),
        )


# ─── LEDGER VIEW ─────────────────────────────────────────────────────────────

async def admin_ledger(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    admin = await _require_admin(update)
    if not admin:
        return
    await query.answer()
    rows = await bus.get_recent_ledger(30)

    lines = "\n".join(
        f"{'➕' if r['type'] == 'CREDIT' else '➖'} `{r['amount']} SOL` "
        f"@{esc(r.get('username') or str(r['telegram_id']))} — {esc(r['reason'])}"
        for r in rows[:15]
    ) or "_No transactions._"

    from bot.menus.keyboards import InlineKeyboardMarkup, InlineKeyboardButton
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("« Workboard", callback_data="admin:workboard")]])
    await query.edit_message_text(
        f"📊 *Recent Ledger* (last 15):\n\n{lines}",
        parse_mode="Markdown",
        reply_markup=kb,
    )


# ─── SERVICE CRUD ─────────────────────────────────────────────────────────────

async def admin_services(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    admin = await _require_admin(update)
    if not admin:
        return
    await query.answer()
    services = await bus.get_all_services()
    await query.edit_message_text(
        "🛍 *Services*", parse_mode="Markdown",
        reply_markup=admin_services_keyboard(list(services)),
    )


async def admin_service_edit(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    admin = await _require_admin(update)
    if not admin:
        return
    await query.answer()
    service_id = int(query.data.split(":")[2])
    svc = await bus.get_service(service_id)
    if not svc:
        await query.edit_message_text("Service not found.")
        return
    text = (
        f"🛍 *{esc(svc['name'])}*\n"
        f"Desc: {esc(svc['description'] or '—')}\n"
        f"Price: `{svc['price']} SOL` | ETA: {esc(svc['eta'])}\n"
        f"Fast Track: `{svc['fast_track_price'] or '—'}` | {esc(svc['fast_track_eta'] or '—')}\n"
        f"Active: {'✅' if svc['is_active'] else '❌'}\n\n"
        f"Template fields: `{len(json.loads(svc['required_inputs_json'] or '[]'))}` defined"
    )
    await query.edit_message_text(
        text, parse_mode="Markdown",
        reply_markup=service_edit_keyboard(service_id, svc["is_active"]),
    )


async def admin_service_toggle(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    admin = await _require_admin(update)
    if not admin:
        return
    await query.answer()
    service_id = int(query.data.split(":")[2])
    svc = await bus.get_service(service_id)
    new_state = not svc["is_active"]
    await bus.toggle_service(service_id, new_state)
    label = "enabled" if new_state else "disabled"
    logger.info("Admin %s %s service %s", admin['id'], label, service_id)
    await query.edit_message_text(f"✅ Service #{service_id} {label}.")
    await bus.insert_audit_log(admin["id"], f"service_{label}", "service", service_id)


# ─── SERVICE CREATE ───────────────────────────────────────────────────────────

async def admin_service_new_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    admin = await _require_admin(update)
    if not admin:
        return
    await query.answer()
    ctx.user_data["new_svc"] = {}
    await query.edit_message_text("🆕 *New Service*\n\nEnter service name:", parse_mode="Markdown")
    return WAITING_SVC_NAME


async def admin_svc_name(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["new_svc"]["name"] = update.message.text.strip()
    await update.message.reply_text("Enter description (or 'skip'):")
    return WAITING_SVC_DESC


async def admin_svc_desc(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    val = update.message.text.strip()
    ctx.user_data["new_svc"]["description"] = "" if val.lower() == "skip" else val
    await update.message.reply_text("Enter standard price in SOL (e.g. 0.5):")
    return WAITING_SVC_PRICE


async def admin_svc_price(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        ctx.user_data["new_svc"]["price"] = float(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("❌ Enter a valid number.")
        return WAITING_SVC_PRICE
    await update.message.reply_text("Enter ETA (e.g. '2-4 hours'):")
    return WAITING_SVC_ETA


async def admin_svc_eta(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["new_svc"]["eta"] = update.message.text.strip()
    await update.message.reply_text("Fast track price in SOL (or 'skip'):")
    return WAITING_SVC_FT_PRICE


async def admin_svc_ft_price(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    val = update.message.text.strip()
    if val.lower() == "skip":
        ctx.user_data["new_svc"]["fast_track_price"] = None
        ctx.user_data["new_svc"]["fast_track_eta"] = None
        # Always proceed to template step even when skipping fast track
        await update.message.reply_text(
            "Enter required inputs JSON template, or 'skip' for none.\n\n"
            "Example:\n`[{\"field\":\"wallet\",\"label\":\"Wallet Address\",\"type\":\"sol_address\",\"required\":true}]`",
            parse_mode="Markdown",
        )
        return WAITING_SVC_TEMPLATE
    try:
        ctx.user_data["new_svc"]["fast_track_price"] = float(val)
    except ValueError:
        await update.message.reply_text("❌ Enter a number or 'skip'.")
        return WAITING_SVC_FT_PRICE
    await update.message.reply_text("Fast track ETA (e.g. '30 min'):")
    return WAITING_SVC_FT_ETA


async def admin_svc_ft_eta(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["new_svc"]["fast_track_eta"] = update.message.text.strip()
    await update.message.reply_text(
        "Enter required inputs JSON template, or 'skip' for none.\n\n"
        "Example:\n`[{\"field\":\"wallet\",\"label\":\"Wallet Address\",\"type\":\"sol_address\",\"required\":true}]`",
        parse_mode="Markdown",
    )
    return WAITING_SVC_TEMPLATE


_VALID_FIELD_TYPES = {"text", "url", "number", "sol_address", "file"}


def _validate_template(raw) -> str | None:
    """Validate template JSON structure, types, required bool, and field uniqueness."""
    if not isinstance(raw, list):
        return "Template must be a JSON array."
    seen_fields = set()
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            return f"Item {i} must be an object."
        for key in ("field", "label", "type"):
            if key not in item or not isinstance(item[key], str) or not item[key].strip():
                return f"Item {i} missing valid '{key}' key."
        ft = item.get("type", "text")
        if ft not in _VALID_FIELD_TYPES:
            return f"Item {i} has invalid type '{ft}'. Allowed: {', '.join(sorted(_VALID_FIELD_TYPES))}"
        if "required" not in item or not isinstance(item["required"], bool):
            return f"Item {i} 'required' must be true or false (boolean)."
        field_key = item["field"].strip()
        if field_key in seen_fields:
            return f"Duplicate field key '{field_key}' at item {i}."
        seen_fields.add(field_key)
    return None


async def admin_svc_template(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    val = update.message.text.strip()
    if val.lower() == "skip":
        ctx.user_data["new_svc"]["required_inputs"] = []
    else:
        try:
            parsed = json.loads(val)
        except json.JSONDecodeError:
            await update.message.reply_text("❌ Invalid JSON. Try again or send 'skip'.")
            return WAITING_SVC_TEMPLATE
        err = _validate_template(parsed)
        if err:
            await update.message.reply_text(f"❌ Template error: {err}\n\nFix it and try again, or send 'skip'.")
            return WAITING_SVC_TEMPLATE
        ctx.user_data["new_svc"]["required_inputs"] = parsed
    await _save_new_service(update, ctx)
    return ConversationHandler.END


async def _save_new_service(update, ctx):
    admin = await bus.get_admin(update.effective_user.id)
    d = ctx.user_data.get("new_svc", {})
    svc = await bus.insert_service(
        name=d["name"], description=d.get("description", ""),
        price=d["price"], eta=d["eta"],
        fast_track_price=d.get("fast_track_price"),
        fast_track_eta=d.get("fast_track_eta"),
        required_inputs=d.get("required_inputs", []),
    )
    logger.info("Admin %s created service '%s' (id=%s)", admin['id'] if admin else '?', svc['name'], svc['id'])
    await update.message.reply_text(
        f"✅ Service *{esc(svc['name'])}* created (ID: {svc['id']}).\n\n"
        f"Returning to services list...",
        parse_mode="Markdown",
    )
    if admin:
        await bus.insert_audit_log(admin["id"], "create_service", "service", svc["id"])
    # Clear creation state
    ctx.user_data.pop("new_svc", None)
    # Send services menu
    services = await bus.get_all_services()
    from bot.menus.keyboards import admin_services_keyboard
    await update.message.reply_text(
        "🛍 *Services*", parse_mode="Markdown",
        reply_markup=admin_services_keyboard(list(services)),
    )


# ─── SERVICE EDIT — PRICE/ETA ─────────────────────────────────────────────────

async def admin_service_edit_price(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    admin = await _require_admin(update)
    if not admin:
        return
    await query.answer()
    service_id = int(query.data.split(":")[2])
    ctx.user_data["edit_svc_id"] = service_id
    await query.edit_message_text(
        "Enter new values as:\n`price, eta, fast_track_price, fast_track_eta`\n\n"
        "Use `-` to clear fast track fields. Example:\n`0.5, 2-4 hours, 1.0, 30 min`\n"
        "or `0.5, 2-4 hours, -, -` to remove fast track.\n\n"
        "_Send /cancel to abort._",
        parse_mode="Markdown",
    )
    return WAITING_SVC_EDIT_PRICE


async def admin_service_save_price(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    admin = await _require_admin(update)
    if not admin:
        return ConversationHandler.END
    parts = [p.strip() for p in update.message.text.split(",")]
    if len(parts) < 2:
        await update.message.reply_text("❌ Format: `price, eta` (optional: `, ft_price, ft_eta`)", parse_mode="Markdown")
        return WAITING_SVC_EDIT_PRICE
    try:
        price = float(parts[0])
        eta = parts[1]
    except ValueError:
        await update.message.reply_text("❌ Invalid price.")
        return WAITING_SVC_EDIT_PRICE

    update_kwargs: dict = {"price": price, "eta": eta}
    if len(parts) >= 4:
        ft_price_raw, ft_eta_raw = parts[2], parts[3]
        update_kwargs["fast_track_price"] = None if ft_price_raw == "-" else float(ft_price_raw)
        update_kwargs["fast_track_eta"] = None if ft_eta_raw == "-" else ft_eta_raw

    svc_id = ctx.user_data.pop("edit_svc_id", None)
    if not svc_id:
        await update.message.reply_text("❌ Session lost. Start over.")
        return ConversationHandler.END
    await bus.update_service(svc_id, **update_kwargs)
    logger.info("Admin %s updated service %s price/ETA", admin['id'], svc_id)
    await update.message.reply_text(
        f"✅ Service #{svc_id} updated: `{price} SOL`, ETA: {esc(eta)}.", parse_mode="Markdown"
    )
    await bus.insert_audit_log(admin["id"], "update_service", "service", svc_id, update_kwargs)
    return ConversationHandler.END


# ─── SERVICE EDIT — NAME ─────────────────────────────────────────────────────

async def admin_service_edit_name_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    admin = await _require_admin(update)
    if not admin:
        return
    await query.answer()
    service_id = int(query.data.split(":")[2])
    ctx.user_data["edit_svc_id"] = service_id
    svc = await bus.get_service(service_id)
    await query.edit_message_text(
        f"Current name: *{esc(svc['name'])}*\n\nEnter new name (or /cancel):",
        parse_mode="Markdown",
    )
    return WAITING_SVC_EDIT_NAME


async def admin_service_save_name(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    admin = await _require_admin(update)
    if not admin:
        return ConversationHandler.END
    svc_id = ctx.user_data.pop("edit_svc_id", None)
    if not svc_id:
        await update.message.reply_text("❌ Session lost.")
        return ConversationHandler.END
    new_name = update.message.text.strip()
    if not new_name:
        await update.message.reply_text("❌ Name cannot be empty.")
        return WAITING_SVC_EDIT_NAME
    await bus.update_service(svc_id, name=new_name)
    logger.info("Admin %s renamed service %s to '%s'", admin['id'], svc_id, new_name)
    await update.message.reply_text(f"✅ Service #{svc_id} name updated to: *{esc(new_name)}*", parse_mode="Markdown")
    await bus.insert_audit_log(admin["id"], "update_service_name", "service", svc_id, {"name": new_name})
    return ConversationHandler.END


# ─── SERVICE EDIT — DESCRIPTION ──────────────────────────────────────────────

async def admin_service_edit_desc_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    admin = await _require_admin(update)
    if not admin:
        return
    await query.answer()
    service_id = int(query.data.split(":")[2])
    ctx.user_data["edit_svc_id"] = service_id
    svc = await bus.get_service(service_id)
    await query.edit_message_text(
        f"Current description:\n_{esc(svc['description'] or 'none')}_\n\n"
        f"Enter new description (or /cancel):",
        parse_mode="Markdown",
    )
    return WAITING_SVC_EDIT_DESC


async def admin_service_save_desc(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    admin = await _require_admin(update)
    if not admin:
        return ConversationHandler.END
    svc_id = ctx.user_data.pop("edit_svc_id", None)
    if not svc_id:
        await update.message.reply_text("❌ Session lost.")
        return ConversationHandler.END
    new_desc = update.message.text.strip()
    await bus.update_service(svc_id, description=new_desc)
    await update.message.reply_text(f"✅ Service #{svc_id} description updated.")
    await bus.insert_audit_log(admin["id"], "update_service_desc", "service", svc_id)
    return ConversationHandler.END


# ─── SERVICE EDIT — TEMPLATE ─────────────────────────────────────────────────

async def admin_service_edit_template_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    admin = await _require_admin(update)
    if not admin:
        return
    await query.answer()
    service_id = int(query.data.split(":")[2])
    ctx.user_data["edit_svc_id"] = service_id
    svc = await bus.get_service(service_id)
    current = svc["required_inputs_json"] or "[]"
    await query.edit_message_text(
        f"Current template:\n`{current}`\n\n"
        f"Send new JSON template, or 'clear' to remove all fields.\n\n"
        f"Example:\n`[{{\"field\":\"wallet\",\"label\":\"Wallet Address\",\"type\":\"sol_address\",\"required\":true}}]`\n\n"
        f"_Send /cancel to abort._",
        parse_mode="Markdown",
    )
    return WAITING_SVC_EDIT_TEMPLATE


async def admin_service_save_template(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    admin = await _require_admin(update)
    if not admin:
        return ConversationHandler.END
    svc_id = ctx.user_data.pop("edit_svc_id", None)
    if not svc_id:
        await update.message.reply_text("❌ Session lost.")
        return ConversationHandler.END

    val = update.message.text.strip()
    if val.lower() == "clear":
        new_template = []
    else:
        try:
            new_template = json.loads(val)
        except json.JSONDecodeError:
            await update.message.reply_text("❌ Invalid JSON. Try again or /cancel.")
            return WAITING_SVC_EDIT_TEMPLATE
        err = _validate_template(new_template)
        if err:
            await update.message.reply_text(f"❌ Template error: {err}\n\nFix and try again or /cancel.")
            return WAITING_SVC_EDIT_TEMPLATE

    await bus.update_service(svc_id, required_inputs_json=json.dumps(new_template))
    logger.info("Admin %s updated template for service %s (%d fields)", admin['id'], svc_id, len(new_template))
    await update.message.reply_text(
        f"✅ Service #{svc_id} template updated ({len(new_template)} field(s))."
    )
    await bus.insert_audit_log(admin["id"], "update_service_template", "service", svc_id, {"fields": len(new_template)})
    return ConversationHandler.END


# ─── BROADCAST ────────────────────────────────────────────────────────────────

async def admin_broadcast_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    admin = await _require_admin(update)
    if not admin:
        return
    await query.answer()
    await query.edit_message_text(
        "📢 *Broadcast*\n\nType your message. You'll see a preview before it's sent.\n\n"
        "_Send /cancel to abort._",
        parse_mode="Markdown",
    )
    return WAITING_BROADCAST


async def admin_broadcast_preview(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Receive broadcast text → show preview with confirm/cancel buttons."""
    admin = await _require_admin(update)
    if not admin:
        return ConversationHandler.END
    msg = update.message.text
    ctx.user_data["broadcast_msg"] = msg
    users = await bus.get_all_users()
    await update.message.reply_text(
        f"📢 *Broadcast Preview*\n\n"
        f"━━━━━━━━━━━━━━━\n{esc(msg)}\n━━━━━━━━━━━━━━━\n\n"
        f"This will be sent to *{len(users)} user(s)*.\n"
        f"Confirm or cancel below.",
        parse_mode="Markdown",
        reply_markup=broadcast_confirm_keyboard(),
    )
    return ConversationHandler.END


async def admin_broadcast_confirm_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    admin = await _require_admin(update)
    if not admin:
        return
    await query.answer()
    msg = ctx.user_data.pop("broadcast_msg", None)
    if not msg:
        await query.edit_message_text("❌ No broadcast message found. Start over.")
        return

    from utils.templates import broadcast_message as tmpl_broadcast
    users = await bus.get_all_users()
    sent, failed = 0, 0
    for user in users:
        try:
            await query.get_bot().send_message(
                user["telegram_id"],
                tmpl_broadcast(msg),
                parse_mode="Markdown",
            )
            sent += 1
        except Exception as e:
            logger.debug("Broadcast failed for user %s: %s", user["telegram_id"], e)
            failed += 1

    logger.info("Admin %s sent broadcast: %d sent, %d failed", admin['id'], sent, failed)
    await query.edit_message_text(f"📢 Broadcast done. ✅ {sent} sent, ❌ {failed} failed.")
    await bus.insert_audit_log(admin["id"], "broadcast", "broadcast", None, {"sent": sent, "failed": failed})


async def admin_broadcast_cancel_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    ctx.user_data.pop("broadcast_msg", None)
    await query.edit_message_text("❌ Broadcast cancelled.")


# ─── ADMIN CANCEL ─────────────────────────────────────────────────────────────

async def admin_conv_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Universal /cancel for all admin conversations."""
    ctx.user_data.pop("new_svc", None)
    ctx.user_data.pop("edit_svc_id", None)
    ctx.user_data.pop("progress_order_id", None)
    ctx.user_data.pop("proof_order_id", None)
    ctx.user_data.pop("note_order_id", None)
    ctx.user_data.pop("broadcast_msg", None)
    await update.message.reply_text("❌ Admin action cancelled. Use /admin to return to the panel.")
    return ConversationHandler.END


# ─── REGISTER ─────────────────────────────────────────────────────────────────

def register(app):
    _cancel = CommandHandler("cancel", admin_conv_cancel)

    conv_broadcast = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_broadcast_start, pattern=r"^admin:broadcast$")],
        states={WAITING_BROADCAST: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_broadcast_preview)]},
        fallbacks=[_cancel],
        per_message=False,
    )
    conv_proof = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_proof_start, pattern=r"^admin:proof:")],
        states={WAITING_PROOF: [MessageHandler(filters.PHOTO | filters.Document.ALL, admin_receive_proof)]},
        fallbacks=[_cancel],
        per_message=False,
    )
    conv_progress = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_inprogress, pattern=r"^admin:inprogress:")],
        states={WAITING_PROGRESS: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_set_progress)]},
        fallbacks=[_cancel],
        per_message=False,
    )
    conv_note = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_note_start, pattern=r"^admin:note:")],
        states={WAITING_NOTE: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_save_note)]},
        fallbacks=[_cancel],
        per_message=False,
    )
    conv_new_svc = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_service_new_start, pattern=r"^admin:service_new$")],
        states={
            WAITING_SVC_NAME:     [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_svc_name)],
            WAITING_SVC_DESC:     [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_svc_desc)],
            WAITING_SVC_PRICE:    [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_svc_price)],
            WAITING_SVC_ETA:      [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_svc_eta)],
            WAITING_SVC_FT_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_svc_ft_price)],
            WAITING_SVC_FT_ETA:   [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_svc_ft_eta)],
            WAITING_SVC_TEMPLATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_svc_template)],
        },
        fallbacks=[_cancel],
        per_message=False,
    )
    conv_edit_price = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_service_edit_price, pattern=r"^admin:service_price:")],
        states={WAITING_SVC_EDIT_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_service_save_price)]},
        fallbacks=[_cancel],
        per_message=False,
    )
    conv_edit_name = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_service_edit_name_start, pattern=r"^admin:svc_edit_name:")],
        states={WAITING_SVC_EDIT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_service_save_name)]},
        fallbacks=[_cancel],
        per_message=False,
    )
    conv_edit_desc = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_service_edit_desc_start, pattern=r"^admin:svc_edit_desc:")],
        states={WAITING_SVC_EDIT_DESC: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_service_save_desc)]},
        fallbacks=[_cancel],
        per_message=False,
    )
    conv_edit_template = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_service_edit_template_start, pattern=r"^admin:service_template:")],
        states={WAITING_SVC_EDIT_TEMPLATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_service_save_template)]},
        fallbacks=[_cancel],
        per_message=False,
    )

    # ConversationHandlers must be registered before plain CallbackQueryHandlers
    app.add_handler(conv_broadcast)
    app.add_handler(conv_proof)
    app.add_handler(conv_progress)
    app.add_handler(conv_note)
    app.add_handler(conv_new_svc)
    app.add_handler(conv_edit_price)
    app.add_handler(conv_edit_name)
    app.add_handler(conv_edit_desc)
    app.add_handler(conv_edit_template)

    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_handler(CallbackQueryHandler(admin_workboard_cb,       pattern=r"^admin:workboard$"))
    app.add_handler(CallbackQueryHandler(admin_orders_by_status,   pattern=r"^admin:orders:"))
    app.add_handler(CallbackQueryHandler(admin_claim,              pattern=r"^admin:claim:"))
    app.add_handler(CallbackQueryHandler(admin_unclaim,            pattern=r"^admin:unclaim:"))
    app.add_handler(CallbackQueryHandler(admin_complete,           pattern=r"^admin:complete:"))
    app.add_handler(CallbackQueryHandler(admin_tickets,            pattern=r"^admin:tickets$"))
    app.add_handler(CallbackQueryHandler(admin_ledger,             pattern=r"^admin:ledger$"))
    app.add_handler(CallbackQueryHandler(admin_services,           pattern=r"^admin:services$"))
    app.add_handler(CallbackQueryHandler(admin_service_edit,       pattern=r"^admin:service_edit:"))
    app.add_handler(CallbackQueryHandler(admin_service_toggle,     pattern=r"^admin:service_toggle:"))
    app.add_handler(CallbackQueryHandler(admin_broadcast_confirm_cb, pattern=r"^admin:broadcast_confirm$"))
    app.add_handler(CallbackQueryHandler(admin_broadcast_cancel_cb,  pattern=r"^admin:broadcast_cancel$"))
