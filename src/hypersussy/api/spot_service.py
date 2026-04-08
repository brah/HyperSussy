"""Account summary and spot balance fetching from Hyperliquid.

Fetches ``marginSummary`` from ``user_state`` and spot token balances from
``spot_user_state`` concurrently.  Results are cached per address with a
short TTL to avoid redundant upstream calls.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from hypersussy.api._address_cache import TtlAddressCache
from hypersussy.exchange.hyperliquid.client import HyperLiquidReader
from hypersussy.rate_limiter import WeightRateLimiter

_CACHE_TTL_S = 60.0
# Hard cap on distinct addresses retained in the per-process cache.
# 512 × (one AccountSnapshot ~ a few KB) ≈ well under 10 MB even in the
# worst case. Combined with TtlAddressCache's TTL eviction, this bounds
# memory growth even when many wallets are searched over a long session.
_CACHE_MAX_ENTRIES = 512


@dataclass(frozen=True, slots=True)
class MarginSummary:
    """Margin / equity summary for a wallet.

    Args:
        account_value: Total equity in USD (perp margin + unrealised PnL).
        withdrawable: Amount available to withdraw.
        total_margin_used: Margin locked in open positions.
        total_ntl_pos: Sum of absolute position values.
    """

    account_value: float
    withdrawable: float
    total_margin_used: float
    total_ntl_pos: float


@dataclass(frozen=True, slots=True)
class SpotBalance:
    """A single spot token holding.

    Args:
        coin: Token ticker (e.g. "USDC", "ETH").
        total: Total balance (held + available).
        hold: Amount locked in open spot orders.
        entry_ntl: USD notional at average entry price.
    """

    coin: str
    total: float
    hold: float
    entry_ntl: float


@dataclass(frozen=True, slots=True)
class AccountSnapshot:
    """Combined account state for a wallet.

    Args:
        margin: Margin / equity summary from the perp clearing house.
        spot: List of non-zero spot token balances.
    """

    margin: MarginSummary
    spot: list[SpotBalance]


def _f(val: object) -> float:
    """Safely coerce a string-or-numeric API value to float."""
    if val is None or val == "":
        return 0.0
    return float(val)  # type: ignore[arg-type]


class SpotService:
    """Fetches account summary and spot balances for a wallet address.

    Both the perp margin summary and spot balances are fetched concurrently
    in a single ``get_account`` call.  Results are cached per address for
    ``_CACHE_TTL_S`` seconds to avoid hitting the HL API on every render.

    Args:
        base_url: Hyperliquid API base URL.
    """

    def __init__(self, base_url: str = "https://api.hyperliquid.xyz") -> None:
        self._reader = HyperLiquidReader(
            base_url=base_url,
            rate_limiter=WeightRateLimiter(max_weight=200, window_seconds=60),
            include_hip3=False,
        )
        self._cache: TtlAddressCache[AccountSnapshot] = TtlAddressCache(
            ttl_seconds=_CACHE_TTL_S,
            max_entries=_CACHE_MAX_ENTRIES,
        )

    async def get_account(self, address: str) -> AccountSnapshot:
        """Fetch margin summary and spot balances for an address.

        Args:
            address: The 0x wallet address.

        Returns:
            AccountSnapshot with margin equity and spot holdings.
        """
        cached = self._cache.get(address)
        if cached is not None:
            return cached

        margin_raw, spot_raw = await asyncio.gather(
            self._fetch_user_state(address),
            self._fetch_spot_user_state(address),
        )

        ms = margin_raw.get("marginSummary", {})
        margin = MarginSummary(
            account_value=_f(ms.get("accountValue")),
            withdrawable=_f(margin_raw.get("withdrawable")),
            total_margin_used=_f(ms.get("totalMarginUsed")),
            total_ntl_pos=_f(ms.get("totalNtlPos")),
        )

        spot = [
            SpotBalance(
                coin=b["coin"],
                total=_f(b.get("total")),
                hold=_f(b.get("hold")),
                entry_ntl=_f(b.get("entryNtl")),
            )
            for b in spot_raw.get("balances", [])
            if _f(b.get("total")) > 0
        ]

        snapshot = AccountSnapshot(margin=margin, spot=spot)
        self._cache.put(address, snapshot)
        return snapshot

    async def _fetch_user_state(self, address: str) -> dict[str, Any]:
        """Call HL user_state to retrieve margin summary.

        Args:
            address: The 0x wallet address.

        Returns:
            Raw clearinghouse state dict.
        """
        raw = await self._reader._call_info(
            "user_state",
            lambda: self._reader._info_client.user_state(address),
            weight=2,
            context=f"spot_svc:address={address}",
        )
        return dict(raw) if raw else {}

    async def _fetch_spot_user_state(self, address: str) -> dict[str, Any]:
        """Call HL spot_user_state to retrieve spot balances.

        Args:
            address: The 0x wallet address.

        Returns:
            Raw spot user state dict.
        """
        raw = await self._reader._call_info(
            "spot_user_state",
            lambda: self._reader._info_client.spot_user_state(address),
            weight=2,
            context=f"spot_svc:address={address}",
        )
        return dict(raw) if raw else {}
