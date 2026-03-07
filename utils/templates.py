"""
All user-facing message strings in one place.
Edit copy here — don't scatter strings throughout handlers.
"""
import html

_MD_ESCAPE = str.maketrans({c: f"\\{c}" for c in r"_*[]()~`>#+-=|{}.!"})


def esc(text: str) -> str:
    """Escape user-controlled text before embedding in MarkdownV2 messages.
    Use for any value that came from user input or DB fields set by users.
    """
    return str(text).translate(_MD_ESCAPE)


def welcome(first_name: str) -> str:
    return (
        f"👋 Welcome, *{esc(first_name)}*!\n\n"
        f"Use the menu below to browse services, top up your balance, or track your orders."
    )


def main_menu() -> str:
    return "🏠 *Main Menu* — what would you like to do?"


# ─── SERVICES ────────────────────────────────────────────────────────────────

def services_list_header() -> str:
    return "🛍 *Available Services*\n\nSelect a service to see details:"


def service_info(service: dict) -> str:
    text = (
        f"*{esc(service['name'])}*\n\n"
        f"{esc(service['description'] or '')}\n\n"
        f"💰 Price: `{service['price']} SOL`\n"
        f"⏱ ETA: {esc(service['eta'])}\n"
    )
    if service.get("fast_track_price"):
        text += (
            f"\n⚡ *Fast Track*: `{service['fast_track_price']} SOL`"
            f" ({esc(service['fast_track_eta'])})\n"
        )
    return text


def ask_input(label: str, type_: str = "text") -> str:
    hints = {
        "url": " _(must start with http:// or https://)_",
        "number": " _(numbers only)_",
        "sol_address": " _(Solana wallet address)_",
        "file": " _(send a photo or file)_",
    }
    return f"📝 Please provide: *{esc(label)}*{hints.get(type_, '')}"


def input_invalid(error: str) -> str:
    return f"❌ {error}\n\nPlease try again:"


def order_created(order_id: int, service_name: str, priority: str, price: float, eta: str) -> str:
    return (
        f"✅ *Order #{order_id} Created*\n\n"
        f"Service: {esc(service_name)}\n"
        f"Priority: {'⚡ Fast Track' if priority == 'FAST_TRACK' else '🐢 Standard'}\n"
        f"Price: `{price} SOL`\n"
        f"ETA: {esc(eta)}\n\n"
        f"How would you like to pay?"
    )


def order_detail(order: dict) -> str:
    status_emoji = {
        "WAITING_PAYMENT": "⏳", "PAID": "💳", "CLAIMED": "✋",
        "IN_PROGRESS": "🔧", "COMPLETED": "✅", "CANCELLED": "❌",
    }.get(order["status"], "❓")

    payment_method = order.get("payment_method") or "—"
    notes = order.get("admin_notes") or ""

    details = ""
    if order.get("user_details_json"):
        import json
        d = (order["user_details_json"] if isinstance(order["user_details_json"], dict)
             else json.loads(order["user_details_json"]))
        if d:
            # Show file fields as "📎 Attached" rather than raw file_id
            rows = []
            for k, v in d.items():
                if isinstance(v, dict) and v.get("type") == "file":
                    rows.append(f"• {esc(k)}: 📎 Attached")
                else:
                    rows.append(f"• {esc(k)}: {esc(str(v))}")
            details = "\n*Your inputs:*\n" + "\n".join(rows)

    proof_line = "\n📎 _Proof uploaded — tap View Proof below._" if order.get("proof_json") else ""
    notes_line = f"\n📝 _Note: {esc(notes)}_" if notes else ""

    return (
        f"📦 *Order #{order['id']}*\n\n"
        f"Service: {esc(order.get('service_name', str(order['service_id'])))}\n"
        f"Status: {status_emoji} {order['status']}\n"
        f"Priority: {order['priority']}\n"
        f"Payment: {payment_method}\n"
        f"Price: `{order['price']} SOL`\n"
        f"ETA: {esc(order['eta'])}\n"
        f"Progress: {order['progress']}% _{esc(order['progress_stage'])}_"
        f"{details}{proof_line}{notes_line}"
    )


# ─── PAYMENTS ────────────────────────────────────────────────────────────────

def insufficient_balance(balance: float, price: float) -> str:
    return (
        f"❌ *Insufficient balance.*\n\n"
        f"Your balance: `{balance} SOL`\n"
        f"Required: `{price} SOL`\n\n"
        f"Use 💰 Deposit to top up."
    )


def payment_success(order_id: int, new_balance: float) -> str:
    return (
        f"✅ *Payment successful!*\n\n"
        f"Order #{order_id} is now queued.\n"
        f"Remaining balance: `{new_balance:.9f} SOL`"
    )


def direct_payment_instructions(order_id: int, address: str, memo: str, amount: float, expiry_mins: int) -> str:
    return (
        f"📤 *Direct Payment*\n\n"
        f"Send exactly `{amount} SOL` to:\n\n"
        f"`{address}`\n\n"
        f"Memo / Reference: `{memo}`\n\n"
        f"⏳ Payment window: {expiry_mins} minutes.\n"
        f"We'll confirm automatically once received."
    )


def order_status_update(order_id: int, message: str) -> str:
    return f"📦 *Order #{order_id} Update*\n\n{message}"


# ─── DEPOSITS ────────────────────────────────────────────────────────────────

def deposit_instructions(amount: float, address: str, memo: str, expiry_mins: int) -> str:
    return (
        f"📥 *Deposit Instructions*\n\n"
        f"Amount: `{amount} SOL`\n"
        f"Address: `{address}`\n"
        f"Memo: `{memo}`\n\n"
        f"⏳ Expires in {expiry_mins} minutes.\n"
        f"Your balance updates automatically once confirmed."
    )


def deposit_confirmed(amount: float, new_balance: float) -> str:
    return (
        f"✅ *Deposit Confirmed!*\n\n"
        f"Amount: `{amount} SOL`\n"
        f"New balance: `{new_balance:.9f} SOL`"
    )


# ─── WALLET ──────────────────────────────────────────────────────────────────

def wallet_connect_prompt(nonce: str) -> str:
    return (
        f"🔗 *Connect Wallet* — Text Flow\n\n"
        f"Sign this challenge with your Solana wallet app:\n\n"
        f"`{nonce}`\n\n"
        f"Then reply with:\n`<pubkey> <base58_signature>`\n\n"
        f"_Challenge expires in 5 minutes. Send /cancel to abort._"
    )


def wallet_webapp_prompt(nonce: str) -> str:
    return (
        f"🔗 *Connect Wallet*\n\n"
        f"Tap the button below to connect your Phantom wallet securely.\n\n"
        f"_Challenge: `{nonce}`_\n"
        f"_Expires in 5 minutes._"
    )


def wallet_connected(pubkey: str) -> str:
    return f"✅ *Wallet connected!*\n\n`{pubkey}`"


def wallet_view(pubkey: str) -> str:
    return f"👛 *Linked Wallet*\n\n`{pubkey}`"


# ─── SUPPORT ─────────────────────────────────────────────────────────────────

def ticket_created(ticket_id: int) -> str:
    return (
        f"🎫 *Ticket #{ticket_id} created.*\n\n"
        f"Our team will reply soon. You'll receive a notification here."
    )


def ticket_reply(ticket_id: int, reply_text: str) -> str:
    return f"📩 *Reply to Ticket #{ticket_id}:*\n\n{esc(reply_text)}"


def ticket_closed(ticket_id: int) -> str:
    return f"✅ Ticket #{ticket_id} has been closed. Thanks for reaching out!"
