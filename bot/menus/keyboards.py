from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, WebAppInfo


# ─── MAIN ─────────────────────────────────────────────────────────────────────

def main_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [["🛍 Services", "💰 Deposit"], ["👛 Wallet", "👤 Profile"], ["🎫 Support"]],
        resize_keyboard=True,
    )


def back_to_main() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("« Main Menu", callback_data="nav:main")]])


# ─── SERVICES ─────────────────────────────────────────────────────────────────

def services_keyboard(services: list) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(f"{s['name']} — {s['price']} SOL", callback_data=f"service:{s['id']}")]
        for s in services
    ]
    buttons.append([InlineKeyboardButton("« Back", callback_data="nav:main")])
    return InlineKeyboardMarkup(buttons)


def service_info_keyboard(service_id: int, has_fast_track: bool) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton("🐢 Standard", callback_data=f"priority:STANDARD:{service_id}")],
    ]
    if has_fast_track:
        buttons.append(
            [InlineKeyboardButton("⚡ Fast Track", callback_data=f"priority:FAST_TRACK:{service_id}")]
        )
    buttons.append([InlineKeyboardButton("« Services", callback_data="nav:services")])
    return InlineKeyboardMarkup(buttons)


def payment_method_keyboard(order_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💳 Pay from Balance", callback_data=f"pay:balance:{order_id}")],
        [InlineKeyboardButton("📤 Direct SOL Payment", callback_data=f"pay:direct:{order_id}")],
        [InlineKeyboardButton("❌ Cancel Order", callback_data=f"pay:cancel:{order_id}")],
    ])


# ─── DEPOSIT ──────────────────────────────────────────────────────────────────

def deposit_amount_keyboard() -> InlineKeyboardMarkup:
    presets = [0.1, 0.5, 1.0, 2.0]
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"{a} SOL", callback_data=f"deposit_amount:{a}") for a in presets[:2]],
        [InlineKeyboardButton(f"{a} SOL", callback_data=f"deposit_amount:{a}") for a in presets[2:]],
        [InlineKeyboardButton("✏️ Custom amount", callback_data="deposit_amount:custom")],
        [InlineKeyboardButton("« Back", callback_data="nav:main")],
    ])


# ─── WALLET ───────────────────────────────────────────────────────────────────

def wallet_keyboard(
    has_phantom: bool,
    has_generated: bool = False,
    webapp_url: str = "",
) -> InlineKeyboardMarkup:
    """
    Full wallet menu keyboard. Shows different options depending on what the user has:
    - has_phantom: Phantom/manual wallet connected (wallet_pubkey set)
    - has_generated: Bot-generated wallet exists in generated_wallets table
    """
    buttons = []

    # ── Generated wallet section ──
    if has_generated:
        buttons.append([InlineKeyboardButton("👛 My Generated Wallet", callback_data="genw:back_to_menu")])
    else:
        buttons.append([InlineKeyboardButton("✨ Generate SOL Wallet", callback_data="wallet:generate")])

    # ── Phantom / manual section ──
    if has_phantom:
        buttons.append([InlineKeyboardButton("👁 View Linked Wallet", callback_data="wallet:view")])
        buttons.append([InlineKeyboardButton("🔌 Disconnect Linked Wallet", callback_data="wallet:disconnect")])
    else:
        connect_row = []
        if webapp_url:
            connect_row.append(
                InlineKeyboardButton(
                    "🔗 Connect with Phantom",
                    web_app=WebAppInfo(url=webapp_url),
                )
            )
        connect_row.append(
            InlineKeyboardButton("🔗 Connect Wallet (manual)", callback_data="wallet:connect")
        )
        buttons.append(connect_row)

    buttons.append([InlineKeyboardButton("« Back", callback_data="nav:main")])
    return InlineKeyboardMarkup(buttons)


# ─── PROFILE ──────────────────────────────────────────────────────────────────

def profile_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💰 My Balance", callback_data="profile:balance")],
        [InlineKeyboardButton("📦 My Orders", callback_data="profile:orders")],
        [InlineKeyboardButton("👛 Wallet", callback_data="profile:wallet")],
        [InlineKeyboardButton("« Back", callback_data="nav:main")],
    ])


def orders_list_keyboard(orders: list) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(
            f"#{o['id']} {o.get('service_name','?')} — {o['status']}",
            callback_data=f"order_detail:{o['id']}"
        )]
        for o in orders[:10]
    ]
    buttons.append([InlineKeyboardButton("« Profile", callback_data="nav:profile")])
    return InlineKeyboardMarkup(buttons)


def order_detail_keyboard(order_id: int, has_proof: bool) -> InlineKeyboardMarkup:
    buttons = []
    if has_proof:
        buttons.append([InlineKeyboardButton("📎 View Proof", callback_data=f"order_proof:{order_id}")])
    buttons.append([InlineKeyboardButton("« My Orders", callback_data="profile:orders")])
    return InlineKeyboardMarkup(buttons)


# ─── SUPPORT ──────────────────────────────────────────────────────────────────

def support_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💬 DM Admin", callback_data="support:dm")],
        [InlineKeyboardButton("🎫 Open Ticket", callback_data="support:ticket")],
        [InlineKeyboardButton("« Back", callback_data="nav:main")],
    ])


# ─── ADMIN ────────────────────────────────────────────────────────────────────

def admin_workboard_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🆕 New (PAID)", callback_data="admin:orders:PAID"),
         InlineKeyboardButton("✋ Claimed", callback_data="admin:orders:CLAIMED")],
        [InlineKeyboardButton("🔧 In Progress", callback_data="admin:orders:IN_PROGRESS"),
         InlineKeyboardButton("✅ Completed", callback_data="admin:orders:COMPLETED")],
        [InlineKeyboardButton("🎫 Open Tickets", callback_data="admin:tickets")],
        [InlineKeyboardButton("📊 Ledger", callback_data="admin:ledger")],
        [InlineKeyboardButton("🛍 Services CRUD", callback_data="admin:services")],
        [InlineKeyboardButton("📢 Broadcast", callback_data="admin:broadcast")],
    ])


def order_action_keyboard(order_id: int, status: str) -> InlineKeyboardMarkup:
    buttons = []
    if status == "PAID":
        buttons.append([InlineKeyboardButton("✋ Claim", callback_data=f"admin:claim:{order_id}")])
    if status == "CLAIMED":
        buttons.append([InlineKeyboardButton("▶️ Set In Progress", callback_data=f"admin:inprogress:{order_id}")])
        buttons.append([InlineKeyboardButton("↩️ Unclaim", callback_data=f"admin:unclaim:{order_id}")])
    if status in ("CLAIMED", "IN_PROGRESS"):
        buttons.append([InlineKeyboardButton("📎 Upload Proof", callback_data=f"admin:proof:{order_id}")])
        buttons.append([InlineKeyboardButton("✅ Mark Completed", callback_data=f"admin:complete:{order_id}")])
        buttons.append([InlineKeyboardButton("📝 Add Note", callback_data=f"admin:note:{order_id}")])
    buttons.append([InlineKeyboardButton("« Workboard", callback_data="admin:workboard")])
    return InlineKeyboardMarkup(buttons)


def ticket_action_keyboard(ticket_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💬 Reply", callback_data=f"admin:ticket_reply:{ticket_id}")],
        [InlineKeyboardButton("✅ Close Ticket", callback_data=f"admin:ticket_close:{ticket_id}")],
        [InlineKeyboardButton("« Tickets", callback_data="admin:tickets")],
    ])


def admin_services_keyboard(services: list) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(
            f"{'✅' if s['is_active'] else '❌'} {s['name']}",
            callback_data=f"admin:service_edit:{s['id']}"
        )]
        for s in services
    ]
    buttons.append([InlineKeyboardButton("➕ New Service", callback_data="admin:service_new")])
    buttons.append([InlineKeyboardButton("« Workboard", callback_data="admin:workboard")])
    return InlineKeyboardMarkup(buttons)


def service_edit_keyboard(service_id: int, is_active: bool) -> InlineKeyboardMarkup:
    toggle_label = "🔴 Disable" if is_active else "🟢 Enable"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✏️ Edit Name", callback_data=f"admin:svc_edit_name:{service_id}"),
         InlineKeyboardButton("📝 Edit Desc", callback_data=f"admin:svc_edit_desc:{service_id}")],
        [InlineKeyboardButton("💰 Edit Price/ETA", callback_data=f"admin:service_price:{service_id}")],
        [InlineKeyboardButton("📋 Edit Template", callback_data=f"admin:service_template:{service_id}")],
        [InlineKeyboardButton(toggle_label, callback_data=f"admin:service_toggle:{service_id}")],
        [InlineKeyboardButton("« Services", callback_data="admin:services")],
    ])


def broadcast_confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Send Broadcast", callback_data="admin:broadcast_confirm")],
        [InlineKeyboardButton("❌ Cancel", callback_data="admin:broadcast_cancel")],
    ])
