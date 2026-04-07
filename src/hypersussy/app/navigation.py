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


def short_wallet_label(address: str, chars: int = 4) -> str:
    """Return a compact label in prefix..suffix form (e.g. '0xab4f..ef35').

    Args:
        address: Full 0x wallet address.
        chars: Number of hex characters to show on each side of '..'.

    Returns:
        Shortened address string.
    """
    if len(address) <= 2 + chars * 2:
        return address
    return f"{address[: 2 + chars]}..{address[-chars:]}"
