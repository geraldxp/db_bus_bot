"""
Solana wallet signature verification.
Uses PyNaCl for ed25519 signature verification.
"""
import base58
import base64

try:
    from nacl.signing import VerifyKey
    from nacl.exceptions import BadSignatureError
    NACL_AVAILABLE = True
except ImportError:
    NACL_AVAILABLE = False


def verify_signature(pubkey_b58: str, message: str, signature_b58: str) -> bool:
    """
    Verify a Solana wallet signature.
    
    Args:
        pubkey_b58: Base58-encoded public key
        message: The original message that was signed (nonce)
        signature_b58: Base58-encoded signature
    
    Returns:
        True if valid, False otherwise
    """
    if not NACL_AVAILABLE:
        import logging
        logging.error(
            "PyNaCl is not installed — wallet signature verification is disabled. "
            "Run: pip install PyNaCl. Rejecting signature as a safety measure."
        )
        return False  # Fail closed — never auto-accept without crypto

    try:
        pubkey_bytes = base58.b58decode(pubkey_b58)
        sig_bytes = base58.b58decode(signature_b58)
        msg_bytes = message.encode("utf-8")

        verify_key = VerifyKey(pubkey_bytes)
        verify_key.verify(msg_bytes, sig_bytes)
        return True
    except (BadSignatureError, Exception):
        return False


async def get_sol_balance(address: str) -> float:
    """
    Fetch the on-chain SOL balance for a wallet address via JSON-RPC.
    Returns balance in SOL (float), or -1.0 on error.
    """
    import aiohttp
    from config import SOLANA_RPC_URL

    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getBalance",
        "params": [address, {"commitment": "confirmed"}],
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                SOLANA_RPC_URL,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                data = await resp.json()
                lamports = data["result"]["value"]
                return lamports / 1_000_000_000
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("get_sol_balance failed for %s: %s", address, e)
        return -1.0
