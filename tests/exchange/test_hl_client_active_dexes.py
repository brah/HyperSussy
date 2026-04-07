"""Tests for active_dexes filtering in HyperLiquidReader.get_user_positions."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from hyperliquid.utils.error import ClientError

from hypersussy.exchange.hyperliquid.client import (
    HyperLiquidReader,
    PositionFetchRateLimitError,
)


def _make_user_state(coin: str = "BTC") -> dict[str, Any]:
    """Build a minimal user_state response.

    Args:
        coin: Coin name for the position.

    Returns:
        Clearinghouse state dict.
    """
    return {
        "assetPositions": [
            {
                "position": {
                    "coin": coin,
                    "szi": "1.0",
                    "entryPx": "50000.0",
                    "positionValue": "50000.0",
                    "liquidationPx": "40000.0",
                    "unrealizedPnl": "0.0",
                    "marginUsed": "10000.0",
                    "leverage": {"type": "cross", "value": 5},
                },
                "type": "oneWay",
            }
        ],
        "marginSummary": {
            "accountValue": "10000.0",
            "totalMarginUsed": "5000.0",
            "totalNtlPos": "50000.0",
            "totalRawUsd": "10000.0",
        },
    }


def _make_reader(dex_names: list[str] | None = None) -> HyperLiquidReader:
    """Create a reader with a mock _info and pre-populated HIP-3 dex names.

    Args:
        dex_names: HIP-3 dex names to pre-populate. Defaults to [\"xyz\", \"flx\"].

    Returns:
        A configured HyperLiquidReader.
    """
    reader = HyperLiquidReader(include_hip3=True)
    reader._info = MagicMock()
    reader._hip3_dex_names = dex_names if dex_names is not None else ["xyz", "flx"]
    return reader


class TestActiveDexesNone:
    """active_dexes=None queries native + all known HIP-3 dexes."""

    @pytest.mark.asyncio
    async def test_queries_all_known_dexes(self) -> None:
        """When active_dexes is None, all 3 dexes are queried."""
        reader = _make_reader(["xyz"])

        def fake_user_state(address: str, dex: str = "") -> Any:
            coin = f"{dex}:BTC" if dex else "BTC"
            return _make_user_state(coin)

        reader._info.user_state.side_effect = fake_user_state

        positions = await reader.get_user_positions("0xabc", active_dexes=None)

        coins = {p.coin for p in positions}
        assert "BTC" in coins
        assert "xyz:BTC" in coins


class TestActiveDexesEmptySet:
    """active_dexes=set() restricts to native dex only."""

    @pytest.mark.asyncio
    async def test_queries_native_only(self) -> None:
        """An empty active_dexes set skips all HIP-3 dexes."""
        reader = _make_reader(["xyz", "flx"])
        reader._info.user_state.return_value = _make_user_state("BTC")

        positions = await reader.get_user_positions("0xabc", active_dexes=set())

        assert len(positions) == 1
        assert positions[0].coin == "BTC"
        # user_state called exactly once (native dex)
        assert reader._info.user_state.call_count == 1


class TestActiveDexesIntersection:
    """active_dexes intersects with known dexes to filter stale prefixes."""

    @pytest.mark.asyncio
    async def test_only_intersection_queried(self) -> None:
        """Only dexes present in both active_dexes and known dexes are queried."""
        reader = _make_reader(["xyz", "flx"])

        def fake_user_state(address: str, dex: str = "") -> Any:
            coin = f"{dex}:BTC" if dex else "BTC"
            return _make_user_state(coin)

        reader._info.user_state.side_effect = fake_user_state

        # "km" is unknown — should be filtered out
        positions = await reader.get_user_positions("0xabc", active_dexes={"xyz", "km"})

        coins = {p.coin for p in positions}
        assert "BTC" in coins
        assert "xyz:BTC" in coins
        assert not any("km" in c for c in coins)

    @pytest.mark.asyncio
    async def test_unrecognized_prefix_filtered(self) -> None:
        """A dex prefix not in known dexes is silently dropped."""
        reader = _make_reader(["xyz"])
        reader._info.user_state.return_value = _make_user_state("BTC")

        positions = await reader.get_user_positions(
            "0xabc", active_dexes={"unknown_dex"}
        )

        # Only native queried; unknown_dex filtered out
        assert all(p.coin == "BTC" for p in positions)
        assert reader._info.user_state.call_count == 1

    @pytest.mark.asyncio
    async def test_rate_limited_dex_returns_partial_results(self) -> None:
        """A 429 on one dex returns partial results from other dexes."""
        reader = _make_reader(["xyz"])

        def fake_user_state(address: str, dex: str = "") -> Any:
            if dex == "xyz":
                raise ClientError(429, None, "null", None, {})
            return _make_user_state("BTC")

        reader._info.user_state.side_effect = fake_user_state

        positions = await reader.get_user_positions("0xabc", active_dexes={"xyz"})

        # Native dex positions should be returned despite xyz 429
        assert len(positions) == 1
        assert positions[0].coin == "BTC"

    @pytest.mark.asyncio
    async def test_all_dexes_rate_limited_raises(self) -> None:
        """A 429 on every queried dex raises PositionFetchRateLimitError."""
        reader = _make_reader([])

        reader._info.user_state.side_effect = ClientError(429, None, "null", None, {})

        with pytest.raises(PositionFetchRateLimitError) as excinfo:
            await reader.get_user_positions("0xabc", active_dexes=set())

        assert excinfo.value.address == "0xabc"
        assert excinfo.value.dexes == ("native",)


class TestActiveDexesHip3Disabled:
    """When include_hip3=False, active_dexes param is ignored."""

    @pytest.mark.asyncio
    async def test_native_only_regardless_of_active_dexes(self) -> None:
        """HIP-3 disabled → always queries native only."""
        reader = HyperLiquidReader(include_hip3=False)
        reader._info = MagicMock()
        reader._info.user_state.return_value = _make_user_state("ETH")

        positions = await reader.get_user_positions(
            "0xabc", active_dexes={"xyz", "flx"}
        )

        assert len(positions) == 1
        assert positions[0].coin == "ETH"
        assert reader._info.user_state.call_count == 1
