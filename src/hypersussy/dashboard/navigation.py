"""Pure navigation and validation helpers for dashboard pages."""

from __future__ import annotations


def normalize_wallet_address(value: str) -> str | None:
    """Return a normalized wallet address or ``None`` if invalid."""
    address = value.strip()
    if len(address) != 42 or not address.startswith("0x"):
        return None
    hex_part = address[2:]
    if not all(ch in "0123456789abcdefABCDEF" for ch in hex_part):
        return None
    return f"0x{hex_part.lower()}"


def short_wallet_label(address: str, width: int = 10) -> str:
    """Render a compact wallet label from a normalized address."""
    return f"...{address[-width:]}"
