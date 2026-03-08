"""
Deposit Watcher — polls WAITING_DEPOSIT intents, handles expiry and confirmation.
Uses Helius enhanced transactions API: single address + unique memo per deposit.
Set HELIUS_API_KEY in .env to enable on-chain checks.
"""
import asyncio
import logging
import os
from datetime import datetime, timezone

import db.bus as bus
from config import WATCHER_INTERVAL
from utils.notify import notify_user

logger = logging.getLogger(__name__)

HELIUS_API_KEY = os.environ.get("HELIUS_API_KEY", "")
HELIUS_BASE = "https://api.helius.xyz/v0"


async def _fetch_json(url: str):
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


async def check_deposit_received(
    address: str, memo: str, expected_amount: float
) -> tuple[bool, str | None]:
    """
    Check Solana chain for a deposit matching address + memo + amount.
    Returns (confirmed, tx_signature).

    Strategy: Helius enhanced-transactions endpoint, scan for memo match + SOL received.
    Requires: pip install aiohttp  |  set HELIUS_API_KEY in .env
    """
    if not HELIUS_API_KEY:
        logger.debug("HELIUS_API_KEY not set — skipping on-chain deposit check.")
        return False, None

    url = (
        f"{HELIUS_BASE}/addresses/{address}/transactions"
        f"?api-key={HELIUS_API_KEY}&limit=20&type=TRANSFER"
    )
    txns = await _fetch_json(url)
    if not txns or not isinstance(txns, list):
        return False, None

    for tx in txns:
        tx_memo = tx.get("memo") or ""
        if memo not in tx_memo:
            continue
        native_transfers = tx.get("nativeTransfers") or []
        received = sum(
            t.get("amount", 0) / 1e9  # lamports → SOL
            for t in native_transfers
            if t.get("toUserAccount") == address
        )
        if received >= expected_amount * 0.999:  # 0.1% rounding tolerance
            sig = tx.get("signature")
            logger.info("Deposit confirmed: memo=%s tx=%s amount=%.9f", memo, sig, received)
            return True, sig

    return False, None


async def deposit_watcher_loop(bot):
    if not HELIUS_API_KEY:
        logger.warning(
            "HELIUS_API_KEY not configured — deposit confirmation disabled. "
            "Set HELIUS_API_KEY in .env to enable on-chain checks."
        )
    logger.info("Deposit watcher started.")
    while True:
        try:
            deposits = await bus.get_all_pending_deposits()
            now = datetime.now(timezone.utc)

            for deposit in deposits:
                expires_at = deposit["expires_at"]

                if expires_at.replace(tzinfo=timezone.utc) < now:
                    await bus.update_deposit_status(deposit["id"], "EXPIRED")
                    tg_id = await bus.get_deposit_owner_telegram_id(deposit["id"])
                    if tg_id:
                        from utils.templates import deposit_expired
                        await notify_user(bot, tg_id, deposit_expired(float(deposit["expected_amount"])))
                    continue

                confirmed, tx_sig = await check_deposit_received(
                    deposit["address"],
                    deposit["memo"] or "",
                    float(deposit["expected_amount"]),
                )
                if confirmed:
                    # Dedup guard — skip if this tx was already applied
                    if tx_sig and await bus.is_deposit_tx_used(tx_sig):
                        logger.warning("Skipping duplicate deposit tx %s for deposit %s", tx_sig, deposit["id"])
                        continue
                    await bus.update_deposit_status(deposit["id"], "CONFIRMED", confirmed_tx=tx_sig)

                    user = await bus.get_user_by_id(deposit["user_id"])
                    new_balance = float(user["balance_sol"]) + float(deposit["expected_amount"])
                    await bus.update_user_balance(deposit["user_id"], new_balance)
                    await bus.insert_ledger(
                        deposit["user_id"], "CREDIT",
                        float(deposit["expected_amount"]),
                        "Deposit confirmed",
                        str(deposit["id"]),
                    )

                    tg_id = await bus.get_deposit_owner_telegram_id(deposit["id"])
                    if tg_id:
                        from utils.templates import deposit_confirmed as tmpl_deposit_confirmed
                        await notify_user(
                            bot, tg_id,
                            tmpl_deposit_confirmed(float(deposit["expected_amount"]), new_balance)
                        )
                    from utils.notify import notify_admin_deposit
                    await notify_admin_deposit(bot, deposit["id"], float(deposit["expected_amount"]))

        except Exception as e:
            logger.error("Deposit watcher error: %s", e, exc_info=True)

        await asyncio.sleep(WATCHER_INTERVAL)
