"""
Payment Watcher — polls WAITING_PAYMENT orders, handles expiry and confirmation.

Solana RPC strategy: single address + unique memo per order.
Uses Helius enhanced transactions API for memo parsing.
Set HELIUS_API_KEY in .env to enable; without it, watcher logs a warning and skips confirmation checks.
"""
import asyncio
import logging
import os
from datetime import datetime, timezone

import db.bus as bus
from config import WATCHER_INTERVAL
from utils.notify import notify_user, notify_admin_new_order

logger = logging.getLogger(__name__)

HELIUS_API_KEY = os.environ.get("HELIUS_API_KEY", "")
HELIUS_BASE = "https://api.helius.xyz/v0"


async def _fetch_json(url: str) -> dict | list | None:
    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    return await resp.json()
                logger.warning("Helius %s returned %s", url, resp.status)
    except Exception as e:
        logger.error("Helius fetch error: %s", e)
    return None


async def check_payment_received(
    pay_address: str, memo: str, expected_amount: float
) -> tuple[bool, str | None]:
    """
    Check Solana chain for a payment matching address + memo + amount.
    Returns (confirmed, tx_signature).

    Strategy: query Helius enhanced transactions for pay_address,
    scan recent txns for one whose memo matches and SOL transfer >= expected_amount.

    Requires: pip install aiohttp
    Set HELIUS_API_KEY in your .env.
    """
    if not HELIUS_API_KEY:
        logger.debug("HELIUS_API_KEY not set — skipping on-chain payment check.")
        return False, None

    url = f"{HELIUS_BASE}/addresses/{pay_address}/transactions?api-key={HELIUS_API_KEY}&limit=20&type=TRANSFER"
    txns = await _fetch_json(url)
    if not txns or not isinstance(txns, list):
        return False, None

    for tx in txns:
        # Check memo field (Helius exposes it at top level for memo program txns)
        tx_memo = tx.get("memo") or ""
        if memo not in tx_memo:
            continue
        # Check native SOL transfers
        native_transfers = tx.get("nativeTransfers") or []
        received = sum(
            t.get("amount", 0) / 1e9  # lamports → SOL
            for t in native_transfers
            if t.get("toUserAccount") == pay_address
        )
        if received >= expected_amount * 0.999:  # 0.1% tolerance for rounding
            sig = tx.get("signature")
            logger.info("Payment confirmed: order memo=%s tx=%s amount=%.9f", memo, sig, received)
            return True, sig

    return False, None


async def payment_watcher_loop(bot):
    if not HELIUS_API_KEY:
        logger.warning(
            "HELIUS_API_KEY not configured — direct payment confirmation disabled. "
            "Set HELIUS_API_KEY in .env to enable on-chain checks."
        )
    logger.info("Payment watcher started.")
    while True:
        try:
            orders = await bus.get_pending_payment_orders()
            now = datetime.now(timezone.utc)

            for order in orders:
                expires_at = order["payment_expires_at"]

                # Handle expiry
                if expires_at and expires_at.replace(tzinfo=timezone.utc) < now:
                    await bus.update_order_status(order["id"], "CANCELLED")
                    tg_id = await bus.get_order_owner_telegram_id(order["id"])
                    if tg_id:
                        await notify_user(
                            bot, tg_id,
                            f"⏰ *Order \\#{order['id']}* payment expired and was cancelled\\."
                        )
                    continue

                if not order["pay_address"] or not order["pay_memo"]:
                    continue

                confirmed, tx_sig = await check_payment_received(
                    order["pay_address"],
                    order["pay_memo"],
                    float(order["price"]),
                )
                if confirmed:
                    # Dedup guard — skip if this tx was already applied
                    if tx_sig and await bus.is_tx_sig_used(tx_sig):
                        logger.warning("Skipping duplicate payment tx %s for order %s", tx_sig, order["id"])
                        continue
                    await bus.update_order_status(
                        order["id"], "PAID",
                        progress=5,
                        progress_stage="queued",
                        tx_sig=tx_sig,
                    )
                    tg_id = await bus.get_order_owner_telegram_id(order["id"])
                    if tg_id:
                        await notify_user(
                            bot, tg_id,
                            f"✅ *Payment confirmed\\!* Order \\#{order['id']} is queued\\.\n"
                            f"TX: `{tx_sig}`"
                        )
                    await notify_admin_new_order(bot, order["id"])

        except Exception as e:
            logger.error("Payment watcher error: %s", e, exc_info=True)

        await asyncio.sleep(WATCHER_INTERVAL)
