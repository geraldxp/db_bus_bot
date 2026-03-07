# DB Bus Bot — Telegram Service Bot

A Telegram bot for selling services with Solana wallet integration, balance top-up, order tracking, admin workboard, support ticketing, and a full audit log.

## Stack
- Python 3.11+
- python-telegram-bot v20+
- PostgreSQL 14+
- asyncpg

## Project Structure
```
db_bus_bot/
├── bot/
│   ├── handlers/
│   │   ├── start.py        # /start, menu routing, back navigation
│   │   ├── services.py     # Browse → order → input collection → payment
│   │   ├── deposit.py      # Deposit intent creation
│   │   ├── wallet.py       # Solana wallet connect/view/disconnect
│   │   ├── profile.py      # Balance, orders list, order detail
│   │   └── support.py      # Ticket creation, admin reply routing
│   └── menus/
│       └── keyboards.py    # All InlineKeyboardMarkup builders
├── db/
│   ├── bus.py              # DB Bus — ALL queries funnel here
│   └── schema.sql          # PostgreSQL schema (run once)
├── watchers/
│   ├── payment_watcher.py  # Polls WAITING_PAYMENT orders, handles expiry
│   └── deposit_watcher.py  # Polls WAITING_DEPOSIT intents, handles expiry
├── admin/
│   └── handlers.py         # Full workboard, service CRUD, tickets, broadcast
├── utils/
│   ├── solana.py           # Ed25519 signature verification
│   ├── notify.py           # Notification helpers (no raw SQL)
│   ├── templates.py        # All user-facing message strings
│   ├── validators.py       # Input validation per field type
│   └── rate_limit.py       # Per-user rate limiting decorator
├── config.py
├── main.py
└── requirements.txt
```

## Setup

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Create `.env` from `.env.example`
```
BOT_TOKEN=your_telegram_bot_token
DATABASE_URL=postgresql://user:password@localhost:5432/dbbus
ADMIN_CHANNEL_ID=-100xxxxxxxxx
SUPPORT_GROUP_ID=-100xxxxxxxxx
ADMIN_USERNAME=youradmin_handle
DEPOSIT_ADDRESS=YourSolanaWalletAddressHere
```

### 3. Run schema
```bash
psql $DATABASE_URL -f db/schema.sql
```

### 4. Seed an admin
```sql
INSERT INTO admins (telegram_id, username, role) VALUES (123456789, 'yourusername', 'superadmin');
```

### 5. Start the bot
```bash
python main.py
```

## Admin Commands
| Command | Description |
|---|---|
| `/admin` | Open admin workboard |
| `/reply <ticket_id> <msg>` | Reply to a support ticket (support group only) |
| `/close_ticket <ticket_id>` | Close a ticket |

## TODO: Solana RPC Integration
Both `watchers/payment_watcher.py` and `watchers/deposit_watcher.py` have a `check_payment_received()` / `check_deposit_received()` stub. Implement these with your RPC provider (Helius, QuickNode, etc.) to enable automatic payment confirmation.

## Service Input Field Types
When creating a service, `required_inputs_json` supports these field types:
- `text` — free text
- `url` — validated URL
- `number` — numeric value
- `sol_address` — Solana public key
- `file` — photo or document upload

Example template:
```json
[
  {"field": "wallet", "label": "Your Solana Wallet", "type": "sol_address", "required": true},
  {"field": "quantity", "label": "Quantity", "type": "number", "required": true},
  {"field": "notes", "label": "Special Notes", "type": "text", "required": false}
]
```

## Color Legend (from blueprint)
- 🔵 Blue — Bot logic
- 🟣 Purple — Menu/UI
- 🟢 Green — DB layer (bus.py)
- 🟠 Orange — Watchers
- 🔴 Red — Admin
