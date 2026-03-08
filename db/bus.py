"""
DB Bus — single funnel for ALL database operations.
No raw SQL should exist outside this file.
"""
import json
from typing import Optional
from datetime import datetime, timezone

import asyncpg
from config import DATABASE_URL

_pool: Optional[asyncpg.Pool] = None


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=10)
    return _pool


async def close_pool():
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


# ─── USERS ───────────────────────────────────────────────────────────────────

async def upsert_user(telegram_id: int, username: str) -> asyncpg.Record:
    pool = await get_pool()
    return await pool.fetchrow(
        """
        INSERT INTO users (telegram_id, username)
        VALUES ($1, $2)
        ON CONFLICT (telegram_id) DO UPDATE SET username = EXCLUDED.username
        RETURNING *
        """,
        telegram_id, username,
    )


async def get_user_by_telegram_id(telegram_id: int) -> Optional[asyncpg.Record]:
    pool = await get_pool()
    return await pool.fetchrow("SELECT * FROM users WHERE telegram_id = $1", telegram_id)


# Alias used throughout
get_user = get_user_by_telegram_id


async def get_user_by_id(user_id: int) -> Optional[asyncpg.Record]:
    pool = await get_pool()
    return await pool.fetchrow("SELECT * FROM users WHERE id = $1", user_id)


async def get_telegram_id_by_user_id(user_id: int) -> Optional[int]:
    pool = await get_pool()
    row = await pool.fetchrow("SELECT telegram_id FROM users WHERE id = $1", user_id)
    return row["telegram_id"] if row else None


async def get_all_users() -> list:
    pool = await get_pool()
    return await pool.fetch("SELECT * FROM users WHERE is_blocked = FALSE")


async def update_user_balance(user_id: int, new_balance: float):
    pool = await get_pool()
    await pool.execute(
        "UPDATE users SET balance_sol = $1 WHERE id = $2", new_balance, user_id
    )


async def update_wallet_pubkey(user_id: int, pubkey: Optional[str]):
    pool = await get_pool()
    await pool.execute(
        "UPDATE users SET wallet_pubkey = $1 WHERE id = $2", pubkey, user_id
    )


async def set_user_blocked(user_id: int, blocked: bool):
    pool = await get_pool()
    await pool.execute(
        "UPDATE users SET is_blocked = $1 WHERE id = $2", blocked, user_id
    )


# ─── SERVICES ────────────────────────────────────────────────────────────────

async def get_active_services() -> list:
    pool = await get_pool()
    return await pool.fetch(
        "SELECT * FROM services WHERE is_active = TRUE ORDER BY id"
    )


async def get_all_services() -> list:
    pool = await get_pool()
    return await pool.fetch("SELECT * FROM services ORDER BY id")


async def get_service(service_id: int) -> Optional[asyncpg.Record]:
    pool = await get_pool()
    return await pool.fetchrow("SELECT * FROM services WHERE id = $1", service_id)


async def insert_service(
    name: str, description: str, price: float, eta: str,
    fast_track_price: Optional[float], fast_track_eta: Optional[str],
    required_inputs: list
) -> asyncpg.Record:
    pool = await get_pool()
    return await pool.fetchrow(
        """
        INSERT INTO services (name, description, price, eta, fast_track_price, fast_track_eta, required_inputs_json)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        RETURNING *
        """,
        name, description, price, eta, fast_track_price, fast_track_eta,
        json.dumps(required_inputs),
    )


async def update_service(service_id: int, **fields):
    pool = await get_pool()
    allowed = {"name", "description", "price", "eta", "fast_track_price",
               "fast_track_eta", "required_inputs_json", "is_active"}
    sets, vals = [], []
    for i, (k, v) in enumerate(fields.items(), 1):
        if k in allowed:
            sets.append(f"{k} = ${i}")
            vals.append(v)
    if not sets:
        return
    vals.append(service_id)
    await pool.execute(
        f"UPDATE services SET {', '.join(sets)}, updated_at = NOW() WHERE id = ${len(vals)}",
        *vals
    )


async def toggle_service(service_id: int, active: bool):
    pool = await get_pool()
    await pool.execute(
        "UPDATE services SET is_active = $1, updated_at = NOW() WHERE id = $2",
        active, service_id
    )


# ─── ORDERS ──────────────────────────────────────────────────────────────────

async def insert_order(
    user_id: int, service_id: int, priority: str,
    price: float, eta: str, user_details: dict, payment_expires_at
) -> asyncpg.Record:
    pool = await get_pool()
    return await pool.fetchrow(
        """
        INSERT INTO orders
            (user_id, service_id, priority, price, eta, user_details_json, payment_expires_at)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        RETURNING *
        """,
        user_id, service_id, priority, price, eta,
        json.dumps(user_details), payment_expires_at,
    )


async def update_order_pay_address(order_id: int, address: str, memo: str):
    pool = await get_pool()
    await pool.execute(
        "UPDATE orders SET pay_address=$1, pay_memo=$2, updated_at=NOW() WHERE id=$3",
        address, memo, order_id,
    )


async def update_order_payment_method(order_id: int, method: str):
    pool = await get_pool()
    await pool.execute(
        "UPDATE orders SET payment_method=$1, updated_at=NOW() WHERE id=$2",
        method, order_id,
    )


async def update_order_status(
    order_id: int, status: str,
    progress: int = None,
    progress_stage: str = None,
    tx_sig: str = None,
):
    pool = await get_pool()
    sets = ["status = $1", "updated_at = NOW()"]
    vals = [status]
    i = 2
    if progress is not None:
        sets.append(f"progress = ${i}"); vals.append(progress); i += 1
    if progress_stage is not None:
        sets.append(f"progress_stage = ${i}"); vals.append(progress_stage); i += 1
    if tx_sig is not None:
        sets.append(f"payment_tx_sig = ${i}"); vals.append(tx_sig); i += 1
    if status == "PAID":
        sets.append(f"paid_at = NOW()")
    vals.append(order_id)
    await pool.execute(
        f"UPDATE orders SET {', '.join(sets)} WHERE id = ${i}", *vals
    )


async def update_order_progress(order_id: int, progress: int, stage: str = None):
    pool = await get_pool()
    if stage:
        await pool.execute(
            "UPDATE orders SET progress=$1, progress_stage=$2, updated_at=NOW() WHERE id=$3",
            progress, stage, order_id,
        )
    else:
        await pool.execute(
            "UPDATE orders SET progress=$1, updated_at=NOW() WHERE id=$2",
            progress, order_id,
        )


async def update_order_proof(order_id: int, proof: dict):
    pool = await get_pool()
    await pool.execute(
        "UPDATE orders SET proof_json=$1, updated_at=NOW() WHERE id=$2",
        json.dumps(proof), order_id,
    )


async def update_order_admin_notes(order_id: int, notes: str):
    pool = await get_pool()
    await pool.execute(
        "UPDATE orders SET admin_notes=$1, updated_at=NOW() WHERE id=$2",
        notes, order_id,
    )


async def claim_order(order_id: int, admin_id: int):
    pool = await get_pool()
    # Use UPDATE ... WHERE claimed_by IS NULL to prevent race condition
    result = await pool.execute(
        """
        UPDATE orders
        SET status='CLAIMED', claimed_by=$1, claimed_at=NOW(), progress_stage='claimed', updated_at=NOW()
        WHERE id=$2 AND (status='PAID') AND claimed_by IS NULL
        """,
        admin_id, order_id,
    )
    return result == "UPDATE 1"


async def unclaim_order(order_id: int):
    pool = await get_pool()
    await pool.execute(
        """
        UPDATE orders
        SET status='PAID', claimed_by=NULL, claimed_at=NULL, progress_stage='queued', updated_at=NOW()
        WHERE id=$1
        """,
        order_id,
    )


async def get_order(order_id: int) -> Optional[asyncpg.Record]:
    pool = await get_pool()
    return await pool.fetchrow("SELECT * FROM orders WHERE id = $1", order_id)


async def get_order_with_service(order_id: int) -> Optional[asyncpg.Record]:
    pool = await get_pool()
    return await pool.fetchrow(
        """
        SELECT o.*, s.name AS service_name, s.description AS service_description
        FROM orders o
        JOIN services s ON s.id = o.service_id
        WHERE o.id = $1
        """,
        order_id,
    )


async def get_user_orders(user_id: int) -> list:
    pool = await get_pool()
    return await pool.fetch(
        """
        SELECT o.*, s.name AS service_name
        FROM orders o JOIN services s ON s.id = o.service_id
        WHERE o.user_id = $1
        ORDER BY o.created_at DESC
        """,
        user_id,
    )


async def get_orders_by_status(status: str) -> list:
    pool = await get_pool()
    return await pool.fetch(
        "SELECT * FROM orders WHERE status = $1 ORDER BY created_at", status
    )


async def get_unclaimed_orders() -> list:
    pool = await get_pool()
    return await pool.fetch(
        "SELECT * FROM orders WHERE status = 'PAID' ORDER BY created_at"
    )


async def get_admin_claimed_orders(admin_id: int) -> list:
    pool = await get_pool()
    return await pool.fetch(
        "SELECT * FROM orders WHERE claimed_by=$1 AND status NOT IN ('COMPLETED','CANCELLED') ORDER BY claimed_at",
        admin_id,
    )


async def get_pending_payment_orders() -> list:
    """All WAITING_PAYMENT orders without a confirmed tx — watcher evaluates expiry itself."""
    pool = await get_pool()
    return await pool.fetch(
        "SELECT * FROM orders WHERE status = 'WAITING_PAYMENT' AND payment_tx_sig IS NULL"
    )


async def is_tx_sig_used(tx_sig: str) -> bool:
    """Check whether a tx signature has already been applied (dedup guard)."""
    pool = await get_pool()
    row = await pool.fetchrow(
        "SELECT id FROM orders WHERE payment_tx_sig = $1 LIMIT 1", tx_sig
    )
    return row is not None


async def get_order_owner_telegram_id(order_id: int) -> Optional[int]:
    pool = await get_pool()
    row = await pool.fetchrow(
        "SELECT u.telegram_id FROM orders o JOIN users u ON u.id = o.user_id WHERE o.id = $1",
        order_id,
    )
    return row["telegram_id"] if row else None


# ─── DEPOSITS ────────────────────────────────────────────────────────────────

async def insert_deposit(
    user_id: int, expected_amount: float, address: str, memo: str, expires_at
) -> asyncpg.Record:
    pool = await get_pool()
    return await pool.fetchrow(
        """
        INSERT INTO deposits (user_id, expected_amount, address, memo, expires_at)
        VALUES ($1, $2, $3, $4, $5)
        RETURNING *
        """,
        user_id, expected_amount, address, memo, expires_at,
    )


async def update_deposit_status(deposit_id: int, status: str, confirmed_tx: str = None):
    pool = await get_pool()
    if status == "CONFIRMED":
        await pool.execute(
            "UPDATE deposits SET status=$1, confirmed_tx=$2, confirmed_at=NOW() WHERE id=$3",
            status, confirmed_tx, deposit_id,
        )
    else:
        await pool.execute(
            "UPDATE deposits SET status=$1 WHERE id=$2", status, deposit_id
        )


async def get_all_pending_deposits() -> list:
    """All WAITING_DEPOSIT deposits without a confirmed tx — watcher evaluates expiry itself."""
    pool = await get_pool()
    return await pool.fetch(
        "SELECT * FROM deposits WHERE status = 'WAITING_DEPOSIT' AND confirmed_tx IS NULL"
    )


async def is_deposit_tx_used(tx_sig: str) -> bool:
    """Check whether a tx signature has already been used for a deposit (dedup guard)."""
    pool = await get_pool()
    row = await pool.fetchrow(
        "SELECT id FROM deposits WHERE confirmed_tx = $1 LIMIT 1", tx_sig
    )
    return row is not None


async def get_user_pending_deposits(user_id: int) -> list:
    pool = await get_pool()
    return await pool.fetch(
        "SELECT * FROM deposits WHERE user_id=$1 AND status='WAITING_DEPOSIT'", user_id
    )


async def get_deposit_owner_telegram_id(deposit_id: int) -> Optional[int]:
    pool = await get_pool()
    row = await pool.fetchrow(
        "SELECT u.telegram_id FROM deposits d JOIN users u ON u.id = d.user_id WHERE d.id = $1",
        deposit_id,
    )
    return row["telegram_id"] if row else None


# ─── LEDGER ──────────────────────────────────────────────────────────────────

async def insert_ledger(user_id: int, type_: str, amount: float, reason: str, ref_id: str = None):
    pool = await get_pool()
    await pool.execute(
        "INSERT INTO ledger (user_id, type, amount, reason, ref_id) VALUES ($1,$2,$3,$4,$5)",
        user_id, type_, amount, reason, ref_id,
    )


async def get_user_ledger(user_id: int, limit: int = 20) -> list:
    pool = await get_pool()
    return await pool.fetch(
        "SELECT * FROM ledger WHERE user_id=$1 ORDER BY created_at DESC LIMIT $2",
        user_id, limit,
    )


async def get_recent_ledger(limit: int = 50) -> list:
    pool = await get_pool()
    return await pool.fetch(
        """
        SELECT l.*, u.username, u.telegram_id
        FROM ledger l JOIN users u ON u.id = l.user_id
        ORDER BY l.created_at DESC LIMIT $1
        """,
        limit,
    )


# ─── TICKETS ─────────────────────────────────────────────────────────────────

async def get_open_ticket_for_user(user_id: int) -> Optional[asyncpg.Record]:
    pool = await get_pool()
    return await pool.fetchrow(
        "SELECT * FROM tickets WHERE user_id=$1 AND status='OPEN' ORDER BY created_at DESC LIMIT 1",
        user_id,
    )


async def insert_ticket(user_id: int, order_id: int = None) -> asyncpg.Record:
    pool = await get_pool()
    return await pool.fetchrow(
        "INSERT INTO tickets (user_id, order_id) VALUES ($1,$2) RETURNING *",
        user_id, order_id,
    )


async def insert_ticket_message(
    ticket_id: int, from_role: str, text: str = None, file_ref: str = None
):
    pool = await get_pool()
    await pool.execute(
        "INSERT INTO ticket_messages (ticket_id, from_role, text, file_ref) VALUES ($1,$2,$3,$4)",
        ticket_id, from_role, text, file_ref,
    )


async def update_ticket_status(ticket_id: int, status: str):
    pool = await get_pool()
    if status == "CLOSED":
        await pool.execute(
            "UPDATE tickets SET status=$1, closed_at=NOW() WHERE id=$2", status, ticket_id
        )
    else:
        await pool.execute(
            "UPDATE tickets SET status=$1, closed_at=NULL WHERE id=$2", status, ticket_id
        )


async def get_open_tickets() -> list:
    pool = await get_pool()
    return await pool.fetch(
        """
        SELECT t.*, u.username, u.telegram_id
        FROM tickets t JOIN users u ON u.id = t.user_id
        WHERE t.status = 'OPEN' ORDER BY t.created_at
        """
    )


async def get_ticket(ticket_id: int) -> Optional[asyncpg.Record]:
    pool = await get_pool()
    return await pool.fetchrow("SELECT * FROM tickets WHERE id=$1", ticket_id)


async def get_ticket_messages(ticket_id: int) -> list:
    pool = await get_pool()
    return await pool.fetch(
        "SELECT * FROM ticket_messages WHERE ticket_id=$1 ORDER BY created_at",
        ticket_id,
    )


async def get_ticket_owner_telegram_id(ticket_id: int) -> Optional[int]:
    pool = await get_pool()
    row = await pool.fetchrow(
        "SELECT u.telegram_id FROM tickets t JOIN users u ON u.id = t.user_id WHERE t.id=$1",
        ticket_id,
    )
    return row["telegram_id"] if row else None


# ─── GENERATED WALLETS ───────────────────────────────────────────────────────

async def get_generated_wallet(user_id: int) -> Optional[asyncpg.Record]:
    pool = await get_pool()
    return await pool.fetchrow(
        "SELECT * FROM generated_wallets WHERE user_id = $1", user_id
    )


async def insert_generated_wallet(
    user_id: int, wallet_address: str,
    encrypted_privkey: str, encrypted_seed: str,
) -> asyncpg.Record:
    pool = await get_pool()
    return await pool.fetchrow(
        """
        INSERT INTO generated_wallets
            (user_id, wallet_address, encrypted_privkey, encrypted_seed)
        VALUES ($1, $2, $3, $4)
        RETURNING *
        """,
        user_id, wallet_address, encrypted_privkey, encrypted_seed,
    )


async def delete_generated_wallet(user_id: int):
    pool = await get_pool()
    await pool.execute(
        "DELETE FROM generated_wallets WHERE user_id = $1", user_id
    )


# ─── ADMINS ──────────────────────────────────────────────────────────────────

async def get_admin(telegram_id: int) -> Optional[asyncpg.Record]:
    pool = await get_pool()
    return await pool.fetchrow("SELECT * FROM admins WHERE telegram_id=$1", telegram_id)


async def get_admin_by_id(admin_id: int) -> Optional[asyncpg.Record]:
    pool = await get_pool()
    return await pool.fetchrow("SELECT * FROM admins WHERE id=$1", admin_id)


async def get_all_admins() -> list:
    pool = await get_pool()
    return await pool.fetch("SELECT * FROM admins")


# ─── AUDIT LOG ───────────────────────────────────────────────────────────────

async def insert_audit_log(
    admin_id: int, action: str, entity: str,
    entity_id: int = None, detail: dict = None
):
    pool = await get_pool()
    await pool.execute(
        "INSERT INTO audit_logs (admin_id, action, entity, entity_id, detail) VALUES ($1,$2,$3,$4,$5)",
        admin_id, action, entity, entity_id,
        json.dumps(detail) if detail else None,
    )
