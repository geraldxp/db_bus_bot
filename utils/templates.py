"""
HypeForge — all user-facing message strings.

Global message style:
    HEADER
    ──────────────
    clear explanation

    DETAILS

    NEXT ACTION
    ──────────────

Call esc() on any value sourced from user input or DB before embedding it.
All public functions return a ready-to-send Markdown string.
"""

_MD_ESCAPE = str.maketrans({c: f"\\{c}" for c in r"_*[]()~`>#+-=|{}.!"})
_DIV = "──────────────"


def esc(text: str) -> str:
    """Escape user-controlled text before embedding in Markdown messages."""
    return str(text).translate(_MD_ESCAPE)


def _fmt(header: str, body: str, footer: str = "") -> str:
    parts = [f"{header}\n{_DIV}", body.strip()]
    if footer:
        parts += [_DIV, footer.strip()]
    return "\n\n".join(parts)


# ─── ENTRY ───────────────────────────────────────────────────────────────────

def welcome(first_name: str) -> str:
    return _fmt(
        f"👋 Welcome to HypeForge, *{esc(first_name)}*",
        (
            "HypeForge helps crypto projects gain visibility through verified "
            "marketing services such as listings, trending placements, community "
            "promotion, and media exposure.\n\n"
            "From here you can:\n\n"
            "• Browse available services\n"
            "• Fund your account balance\n"
            "• Place and track orders\n"
            "• Contact support if you need help"
        ),
        "Use the menu below to begin.",
    )


def main_menu() -> str:
    return _fmt(
        "🏠 Main Menu",
        (
            "Choose an option below to continue.\n\n"
            "🛍 *Services*\nBrowse all available marketing services.\n\n"
            "💰 *Deposit*\nAdd SOL to your account balance.\n\n"
            "👛 *Wallet*\nConnect or manage your Solana wallet.\n\n"
            "📦 *My Orders*\nTrack your active and completed orders.\n\n"
            "🆘 *Support*\nContact our support team if you need assistance."
        ),
    )


# ─── SERVICES ────────────────────────────────────────────────────────────────

def services_list_header() -> str:
    return _fmt(
        "🛍 Available Services",
        "Select a service below to view details and pricing.",
    )


def service_info(service: dict) -> str:
    pricing = (
        f"*Standard*\n"
        f"`{service['price']} SOL`\n"
        f"Estimated Time: {esc(service['eta'])}"
    )
    if service.get("fast_track_price"):
        pricing += (
            f"\n\n*Fast Track*\n"
            f"`{service['fast_track_price']} SOL`\n"
            f"Estimated Time: {esc(service['fast_track_eta'] or '—')}"
        )
    body = (
        f"{esc(service.get('description') or '')}\n\n"
        f"*Pricing*\n\n{pricing}"
    )
    return _fmt(
        f"🛍 {esc(service['name'])}",
        body,
        (
            "After placing your order, you will be asked to provide the required "
            "information needed to process your request.\n\n"
            "Select *Order Now* to continue."
        ),
    )


def ask_input(label: str, type_: str = "text") -> str:
    hints = {
        "url":         "_Must start with http:// or https://_",
        "number":      "_Numbers only_",
        "sol_address": "_Solana wallet address_",
        "file":        "_Send a photo or file_",
    }
    hint = f"\n{hints[type_]}" if type_ in hints else ""
    return f"📝 *{esc(label)}*{hint}"


def input_invalid(error: str) -> str:
    return f"❌ {error}\n\nPlease try again:"


# ─── ORDERS ──────────────────────────────────────────────────────────────────

def order_created(order_id: int, service_name: str, priority: str, price: float, eta: str) -> str:
    priority_label = "⚡ Fast Track" if priority == "FAST_TRACK" else "🐢 Standard"
    return _fmt(
        "💳 Order Payment Required",
        (
            f"Your order has been created and is awaiting payment.\n\n"
            f"*Order ID*\n#{order_id}\n\n"
            f"*Service*\n{esc(service_name)}\n\n"
            f"*Priority*\n{priority_label}\n\n"
            f"*Amount*\n`{price} SOL`\n\n"
            f"*ETA*\n{esc(eta)}"
        ),
        "Choose a payment method below to continue.",
    )


def order_detail(order: dict) -> str:
    status_emoji = {
        "WAITING_PAYMENT": "⏳",
        "PAID":            "💳",
        "CLAIMED":         "✋",
        "IN_PROGRESS":     "⚙",
        "COMPLETED":       "🎉",
        "CANCELLED":       "❌",
    }.get(order["status"], "❓")

    payment_method = order.get("payment_method") or "—"
    notes = order.get("admin_notes") or ""

    details = ""
    if order.get("user_details_json"):
        import json
        d = (order["user_details_json"] if isinstance(order["user_details_json"], dict)
             else json.loads(order["user_details_json"]))
        if d:
            rows = []
            for k, v in d.items():
                if isinstance(v, dict) and v.get("type") == "file":
                    rows.append(f"• {esc(k)}: 📎 Attached")
                else:
                    rows.append(f"• {esc(k)}: {esc(str(v))}")
            details = "\n\n*Your Inputs*\n" + "\n".join(rows)

    proof_line = "\n\n📎 _Proof uploaded — tap View Proof below._" if order.get("proof_json") else ""
    notes_line = f"\n\n📝 *Note:* _{esc(notes)}_" if notes else ""

    return _fmt(
        "📦 Order Details",
        (
            f"*Order ID*\n#{order['id']}\n\n"
            f"*Service*\n{esc(order.get('service_name', str(order['service_id'])))}\n\n"
            f"*Status*\n{status_emoji} {order['status']}\n\n"
            f"*Priority*\n{order['priority']}\n\n"
            f"*Payment*\n{payment_method}\n\n"
            f"*Price*\n`{order['price']} SOL`\n\n"
            f"*ETA*\n{esc(order['eta'])}\n\n"
            f"*Progress*\n{order['progress']}% — _{esc(order['progress_stage'])}_"
            f"{details}{proof_line}{notes_line}"
        ),
    )


def order_processing(order_id: int, service_name: str, progress_stage: str) -> str:
    return _fmt(
        "⚙ Order Processing",
        (
            f"*Order ID*\n#{order_id}\n\n"
            f"*Service*\n{esc(service_name)}\n\n"
            f"*Status*\n{esc(progress_stage)}\n\n"
            "Our team is currently working on your request."
        ),
        "You will receive another notification once the order is completed.",
    )


def order_completed(order_id: int, service_name: str, proof_caption: str = "") -> str:
    proof_line = f"\n\n*Proof / Result*\n{esc(proof_caption)}" if proof_caption else ""
    return _fmt(
        "🎉 Order Completed",
        (
            f"*Order ID*\n#{order_id}\n\n"
            f"*Service*\n{esc(service_name)}\n\n"
            f"Your order has been successfully completed."
            f"{proof_line}"
        ),
        (
            "Thank you for using HypeForge.\n\n"
            "You can explore additional services anytime from the Services menu."
        ),
    )


def order_cancelled(order_id: int) -> str:
    return _fmt(
        "❌ Order Cancelled",
        (
            f"*Order ID*\n#{order_id}\n\n"
            "This order has been cancelled.\n\n"
            "If payment was expected but not received within the allowed time, "
            "the order may have expired."
        ),
        "You can create a new order anytime from the Services menu.",
    )


# ─── PAYMENTS ────────────────────────────────────────────────────────────────

def insufficient_balance(balance: float, price: float) -> str:
    return _fmt(
        "❌ Insufficient Balance",
        (
            f"*Your Balance*\n`{balance} SOL`\n\n"
            f"*Required*\n`{price} SOL`"
        ),
        "Use 💰 Deposit to top up your balance.",
    )


def payment_success(order_id: int, new_balance: float) -> str:
    return _fmt(
        "✅ Payment Confirmed",
        (
            "Your payment has been successfully detected and verified.\n\n"
            f"*Order ID*\n#{order_id}"
        ),
        (
            "Your request is now queued for processing.\n\n"
            "You can track progress anytime in *My Orders*."
        ),
    )


def direct_payment_instructions(order_id: int, address: str, memo: str, amount: float, expiry_mins: int) -> str:
    return _fmt(
        "💳 Order Payment Required",
        (
            f"Your order has been created and is awaiting payment.\n\n"
            f"*Order ID*\n#{order_id}\n\n"
            f"*Amount*\n`{amount} SOL`\n\n"
            f"*Payment Address*\n`{address}`\n\n"
            f"*Reference Memo*\n`{memo}`\n\n"
            f"*Important*\n\n"
            f"• Send the exact amount\n"
            f"• Include the memo when possible\n"
            f"• Payments without the correct memo may not be matched"
        ),
        (
            f"Your order will automatically move to processing once payment is confirmed.\n"
            f"Payment window: *{expiry_mins} minutes*."
        ),
    )


def order_status_update(order_id: int, message: str) -> str:
    return _fmt(f"⚙ Order Update — #{order_id}", message)


# ─── DEPOSITS ────────────────────────────────────────────────────────────────

def deposit_instructions(amount: float, address: str, memo: str, expiry_mins: int) -> str:
    return _fmt(
        "💰 Deposit SOL",
        (
            f"To fund your account balance, send the requested amount to the address below.\n\n"
            f"*Amount*\n`{amount} SOL`\n\n"
            f"*Deposit Address*\n`{address}`\n\n"
            f"*Reference Memo*\n`{memo}`\n\n"
            f"*Important*\n\n"
            f"• Send the exact amount requested\n"
            f"• Include the memo if your wallet supports it\n"
            f"• Deposits are automatically detected once confirmed on-chain"
        ),
        (
            f"Your balance will update automatically after confirmation.\n"
            f"This request expires in *{expiry_mins} minutes*."
        ),
    )


def deposit_confirmed(amount: float, new_balance: float) -> str:
    return _fmt(
        "💰 Deposit Confirmed",
        (
            f"*Amount*\n`{amount} SOL`\n\n"
            "Your balance has been updated successfully."
        ),
        "You can now place orders using your available balance.",
    )


def deposit_expired(amount: float) -> str:
    return _fmt(
        "⏰ Deposit Request Expired",
        f"Your deposit request for `{amount} SOL` has expired.",
        "If you still wish to add funds, please create a new deposit request from the Deposit menu.",
    )


# ─── WALLET ──────────────────────────────────────────────────────────────────

def wallet_connect_prompt(nonce: str) -> str:
    return _fmt(
        "👛 Connect Wallet",
        (
            "Sign the challenge below with your Solana wallet to prove ownership.\n\n"
            f"*Challenge*\n`{nonce}`\n\n"
            "Open your wallet app → Sign Message → paste the challenge above.\n\n"
            "Then reply here with:\n`<pubkey> <base58_signature>`"
        ),
        "_Challenge expires in 5 minutes. Send /cancel to abort._",
    )


def wallet_webapp_prompt(nonce: str) -> str:
    return _fmt(
        "👛 Connect Wallet",
        (
            "Tap the button below to connect your Phantom wallet securely.\n\n"
            f"*Challenge*\n`{nonce}`"
        ),
        "_Expires in 5 minutes._",
    )


def wallet_connected(pubkey: str) -> str:
    return _fmt(
        "👛 Wallet Connected",
        (
            "Your Solana wallet has been successfully linked.\n\n"
            f"*Wallet Address*\n`{pubkey}`\n\n"
            "You can now verify ownership and use wallet-based features."
        ),
    )


def wallet_view(pubkey: str) -> str:
    return _fmt(
        "👛 Linked Wallet",
        f"*Wallet Address*\n`{pubkey}`",
    )


def wallet_disconnected() -> str:
    return _fmt(
        "🔌 Wallet Disconnected",
        "Your wallet has been removed from this account.",
        "You can reconnect a wallet anytime from the Wallet menu.",
    )


# ─── SUPPORT ─────────────────────────────────────────────────────────────────

def ticket_created(ticket_id: int) -> str:
    return _fmt(
        "🆘 Support Request Received",
        (
            f"*Ticket ID*\n#{ticket_id}\n\n"
            "Your message has been forwarded to our support team.\n\n"
            "A team member will review your request and respond as soon as possible."
        ),
        "Replies will appear here automatically.",
    )


def ticket_reply(ticket_id: int, reply_text: str) -> str:
    return _fmt(
        "💬 Support Reply",
        (
            f"*Ticket ID*\n#{ticket_id}\n\n"
            f"*Message from Support*\n\n"
            f"{esc(reply_text)}"
        ),
        "If you need further assistance, simply reply to continue the conversation.",
    )


def ticket_closed(ticket_id: int) -> str:
    return _fmt(
        "✅ Ticket Closed",
        f"*Ticket ID*\n#{ticket_id}\n\nThis support ticket has been closed.",
        "Thank you for reaching out to HypeForge.",
    )


# ─── ADMIN NOTIFICATIONS ─────────────────────────────────────────────────────

def admin_new_order(order_id: int, username: str, service_name: str, priority: str, payment_method: str) -> str:
    priority_label = "⚡ Fast Track" if priority == "FAST_TRACK" else "🐢 Standard"
    return _fmt(
        "📥 New Order Received",
        (
            f"*Order ID*\n#{order_id}\n\n"
            f"*User*\n@{esc(username)}\n\n"
            f"*Service*\n{esc(service_name)}\n\n"
            f"*Priority*\n{priority_label}\n\n"
            f"*Payment Method*\n{payment_method or '—'}"
        ),
        "The order is ready for assignment. Use /admin to manage.",
    )


def admin_deposit_detected(username: str, amount: float) -> str:
    return _fmt(
        "💰 Deposit Detected",
        (
            f"*User*\n@{esc(username)}\n\n"
            f"*Amount*\n`{amount} SOL`\n\n"
            "The user balance has been updated."
        ),
    )


def admin_new_ticket(ticket_id: int, username: str) -> str:
    return _fmt(
        "🆘 New Support Ticket",
        (
            f"*Ticket ID*\n#{ticket_id}\n\n"
            f"*User*\n@{esc(username)}\n\n"
            "A new support request has been submitted and is awaiting response."
        ),
        "Use /admin → Open Tickets to respond.",
    )


def broadcast_message(text: str) -> str:
    return _fmt(
        "📢 HypeForge Announcement",
        esc(text),
        "Stay updated with the latest services, campaigns, and opportunities available on HypeForge.",
    )


# ─── TEMPLATE REGISTRY ───────────────────────────────────────────────────────
# Useful for referencing keys programmatically or future i18n.

TEMPLATES = {
    "welcome":              welcome,
    "main_menu":            main_menu,
    "service_info":         service_info,
    "deposit_instructions": deposit_instructions,
    "payment_request":      direct_payment_instructions,
    "payment_confirmed":    payment_success,
    "order_processing":     order_processing,
    "order_completed":      order_completed,
    "order_cancelled":      order_cancelled,
    "support_created":      ticket_created,
    "support_reply":        ticket_reply,
    "deposit_confirmed":    deposit_confirmed,
    "deposit_expired":      deposit_expired,
    "wallet_connected":     wallet_connected,
    "wallet_disconnected":  wallet_disconnected,
    "admin_order":          admin_new_order,
    "admin_deposit":        admin_deposit_detected,
    "admin_ticket":         admin_new_ticket,
    "broadcast":            broadcast_message,
}
