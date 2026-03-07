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
