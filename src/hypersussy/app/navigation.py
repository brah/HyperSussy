"""Navigation helpers for the API."""
from __future__ import annotations

def normalize_wallet_address(address: str) -> str | None:
    """Normalize a wallet address to a 42-char hex string."""
    if not address.startswith("0x"):
        return None
    address = address.lower()
    if len(address) != 42:
        return None
    if not all(c in "0123456789abcdef" for c in address[2:]):
        return None
    return address
