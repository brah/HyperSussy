"""Tests for HIP-3 builder-deployed perpetual support in HyperLiquidReader."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from hypersussy.exchange.hyperliquid.client import HyperLiquidReader


def _make_dex_response() -> list[dict[str, str] | None]:
    """Build a fake perpDexs API response."""
    return [
        None,  # index 0 = validator dex
        {"name": "xyz", "fullName": "XYZ"},
        {"name": "flx", "fullName": "Felix Exchange"},
    ]


def _make_meta_response(
    prefix: str = "",
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Build a fake metaAndAssetCtxs response.

    Args:
        prefix: Dex prefix for coin names (e.g. "xyz:").

    Returns:
        Tuple of (meta, asset_ctxs).
    """
    return (
        {
            "universe": [
                {
                    "name": f"{prefix}BTC",
                    "szDecimals": 5,
                    "maxLeverage": 50,
                },
            ]
        },
        [
            {
                "dayNtlVlm": "1000000.0",
                "funding": "0.0001",
                "openInterest": "100.0",
                "oraclePx": "50001.0",
                "markPx": "50000.0",
                "midPx": "50000.5",
                "premium": "0.00005",
                "prevDayPx": "49500.0",
            },
        ],
    )


def _make_user_state(coin: str = "BTC") -> dict[str, Any]:
    """Build a fake user_state response.

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
                    "unrealizedPnl": "500.0",
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


class TestRefreshHip3Dexes:
    """Tests for HIP-3 dex discovery."""

    @pytest.mark.asyncio
    async def test_discovers_dexes(self) -> None:
        """Fetches and caches HIP-3 dex names."""
        reader = HyperLiquidReader(include_hip3=True)
        reader._info = MagicMock()
        reader._info.perp_dexs.return_value = _make_dex_response()

        names = await reader.refresh_hip3_dexes()

        assert names == ["xyz", "flx"]
        assert reader._hip3_dex_names == ["xyz", "flx"]

    @pytest.mark.asyncio
    async def test_respects_dex_filter(self) -> None:
        """Only includes dexes matching the filter."""
        reader = HyperLiquidReader(
            include_hip3=True, hip3_dex_filter=["xyz"]
        )
        reader._info = MagicMock()
        reader._info.perp_dexs.return_value = _make_dex_response()

        names = await reader.refresh_hip3_dexes()

        assert names == ["xyz"]

    @pytest.mark.asyncio
    async def test_skips_null_entries(self) -> None:
        """Null entries (validator dex) are skipped."""
        reader = HyperLiquidReader(include_hip3=True)
        reader._info = MagicMock()
        reader._info.perp_dexs.return_value = [None, None]

        names = await reader.refresh_hip3_dexes()

        assert names == []


class TestGetAssetSnapshotsHip3:
    """Tests for asset snapshot fetching with HIP-3."""

    @pytest.mark.asyncio
    async def test_includes_hip3_snapshots(self) -> None:
        """Snapshots include both native and HIP-3 assets."""
        reader = HyperLiquidReader(include_hip3=True)
        reader._info = MagicMock()
        reader._hip3_dex_names = ["xyz"]

        def fake_post(url: str, payload: dict[str, str]) -> Any:
            dex = payload.get("dex", "")
            if dex == "":
                return _make_meta_response("")
            return _make_meta_response(f"{dex}:")

        reader._info.post.side_effect = fake_post
        reader._info.meta_and_asset_ctxs.return_value = _make_meta_response("")

        snapshots = await reader.get_asset_snapshots()

        coins = {s.coin for s in snapshots}
        assert "BTC" in coins
        assert "xyz:BTC" in coins

    @pytest.mark.asyncio
    async def test_hip3_disabled(self) -> None:
        """Only native assets when HIP-3 is disabled."""
        reader = HyperLiquidReader(include_hip3=False)
        reader._info = MagicMock()

        def fake_post(url: str, payload: dict[str, str]) -> Any:
            return _make_meta_response("")

        reader._info.post.side_effect = fake_post

        snapshots = await reader.get_asset_snapshots()

        assert len(snapshots) == 1
        assert snapshots[0].coin == "BTC"

    @pytest.mark.asyncio
    async def test_dex_failure_doesnt_break_others(self) -> None:
        """A failing dex doesn't prevent other dex snapshots."""
        reader = HyperLiquidReader(include_hip3=True)
        reader._info = MagicMock()
        reader._hip3_dex_names = ["xyz", "broken"]

        def fake_post(url: str, payload: dict[str, str]) -> Any:
            dex = payload.get("dex", "")
            if dex == "broken":
                raise ConnectionError("API down")
            if dex == "":
                return _make_meta_response("")
            return _make_meta_response(f"{dex}:")

        reader._info.post.side_effect = fake_post

        snapshots = await reader.get_asset_snapshots()

        coins = {s.coin for s in snapshots}
        assert "BTC" in coins
        assert "xyz:BTC" in coins


class TestGetUserPositionsHip3:
    """Tests for user position fetching across dexes."""

    @pytest.mark.asyncio
    async def test_fetches_positions_across_dexes(self) -> None:
        """Positions are fetched from native and HIP-3 dexes."""
        reader = HyperLiquidReader(include_hip3=True)
        reader._info = MagicMock()
        reader._hip3_dex_names = ["xyz"]

        def fake_user_state(address: str, dex: str = "") -> Any:
            if dex == "xyz":
                return _make_user_state("xyz:GOLD")
            return _make_user_state("BTC")

        reader._info.user_state.side_effect = fake_user_state

        positions = await reader.get_user_positions("0xabc")

        coins = {p.coin for p in positions}
        assert "BTC" in coins
        assert "xyz:GOLD" in coins

    @pytest.mark.asyncio
    async def test_hip3_disabled_single_dex(self) -> None:
        """Only native positions when HIP-3 is disabled."""
        reader = HyperLiquidReader(include_hip3=False)
        reader._info = MagicMock()
        reader._info.user_state.return_value = _make_user_state("ETH")

        positions = await reader.get_user_positions("0xabc")

        assert len(positions) == 1
        assert positions[0].coin == "ETH"


class TestHip3ConfigDefaults:
    """Tests for HIP-3 configuration settings."""

    def test_include_hip3_default(self) -> None:
        """HIP-3 is enabled by default."""
        from hypersussy.config import HyperSussySettings

        settings = HyperSussySettings()
        assert settings.include_hip3 is True
        assert settings.hip3_dex_filter == []

    def test_reader_default_params(self) -> None:
        """Reader defaults match config defaults."""
        reader = HyperLiquidReader()
        assert reader._include_hip3 is True
        assert reader._hip3_dex_filter == set()
