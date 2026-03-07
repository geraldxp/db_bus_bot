"""
Validates user-supplied values against service required_inputs_json field definitions.

Each field spec: {"field": "x", "label": "X", "type": "text|url|number|file", "required": true}
"""
import re
from typing import Optional

URL_RE = re.compile(
    r"^https?://"
    r"(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|"
    r"localhost|\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})"
    r"(?::\d+)?(?:/?|[/?]\S+)$",
    re.IGNORECASE,
)

SOL_ADDRESS_RE = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")

ALLOWED_FILE_MIME = {
    "image/jpeg", "image/png", "image/gif", "image/webp",
    "application/pdf",
    "video/mp4",
}
MAX_FILE_BYTES = 20 * 1024 * 1024  # 20 MB


def validate_text(value: str) -> Optional[str]:
    if not value or not value.strip():
        return "This field cannot be empty."
    if len(value) > 2000:
        return "Input too long (max 2000 chars)."
    return None


def validate_url(value: str) -> Optional[str]:
    err = validate_text(value)
    if err:
        return err
    if not URL_RE.match(value.strip()):
        return "Please send a valid URL starting with http:// or https://"
    return None


def validate_number(value: str) -> Optional[str]:
    try:
        float(value.strip())
        return None
    except ValueError:
        return "Please send a valid number (e.g. 1.5 or 100)."


def validate_sol_address(value: str) -> Optional[str]:
    if not SOL_ADDRESS_RE.match(value.strip()):
        return "Please send a valid Solana wallet address."
    return None


def validate_field(field_spec: dict, value: str) -> Optional[str]:
    """
    Returns an error message string if invalid, or None if valid.
    field_spec example: {"field": "wallet", "label": "Wallet Address", "type": "sol_address", "required": true}
    """
    field_type = field_spec.get("type", "text")
    required = field_spec.get("required", True)

    if not value or not value.strip():
        if required:
            return f"*{field_spec['label']}* is required."
        return None  # Optional field, empty is fine

    validators = {
        "text": validate_text,
        "url": validate_url,
        "number": validate_number,
        "sol_address": validate_sol_address,
    }

    validator = validators.get(field_type, validate_text)
    return validator(value)


def validate_file(
    mime_type: str, file_size: int, field_spec: dict
) -> Optional[str]:
    """Validate a file upload against allowed types and size."""
    if mime_type not in ALLOWED_FILE_MIME:
        allowed = ", ".join(ALLOWED_FILE_MIME)
        return f"File type not allowed. Accepted: {allowed}"
    if file_size > MAX_FILE_BYTES:
        return f"File too large (max {MAX_FILE_BYTES // (1024*1024)} MB)."
    return None
