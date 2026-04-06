"""Tests for pure dashboard navigation helpers."""

from __future__ import annotations

from hypersussy.app.navigation import normalize_wallet_address, short_wallet_label


def test_normalize_wallet_address_accepts_hex_and_lowercases() -> None:
    """Valid addresses are normalized to lowercase."""
    result = normalize_wallet_address("0xABCDEFabcdefABCDEFabcdefABCDEFabcdefABCD")
    assert result == "0xabcdefabcdefabcdefabcdefabcdefabcdefabcd"


def test_normalize_wallet_address_rejects_invalid_input() -> None:
    """Malformed addresses return None."""
    assert normalize_wallet_address("not-an-address") is None
    assert normalize_wallet_address("0x123") is None
    bad = "0xzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz"
    assert normalize_wallet_address(bad) is None


def test_short_wallet_label_uses_suffix() -> None:
    """Compact labels show only the suffix by default."""
    assert (
        short_wallet_label("0x1234567890abcdef1234567890abcdef12345678")
        == "...ef12345678"
    )
