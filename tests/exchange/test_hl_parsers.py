"""Tests for HyperLiquid API response parsers."""

from __future__ import annotations

from hypersussy.exchange.hyperliquid.parsers import (
    parse_l2_snapshot,
    parse_meta_and_asset_ctxs,
    parse_user_fills,
    parse_user_state,
    parse_ws_all_mids,
    parse_ws_trades,
)


class TestParseMetaAndAssetCtxs:
    """Tests for meta_and_asset_ctxs parser."""

    def test_basic_parse(self) -> None:
        """Parses a two-asset response correctly."""
        raw = (
            {
                "universe": [
                    {
                        "name": "BTC",
                        "szDecimals": 5,
                        "maxLeverage": 50,
                        "onlyIsolated": False,
                    },
                    {
                        "name": "ETH",
                        "szDecimals": 4,
                        "maxLeverage": 50,
                        "onlyIsolated": False,
                    },
                ]
            },
            [
                {
                    "dayNtlVlm": "1000000.0",
                    "funding": "0.0001",
                    "openInterest": "100.5",
                    "oraclePx": "50001.0",
                    "markPx": "50000.0",
                    "midPx": "50000.5",
                    "premium": "0.00005",
                    "prevDayPx": "49500.0",
                },
                {
                    "dayNtlVlm": "500000.0",
                    "funding": "-0.0002",
                    "openInterest": "2000.0",
                    "oraclePx": "2001.0",
                    "markPx": "2000.0",
                    "midPx": None,
                    "premium": "0.0001",
                    "prevDayPx": "1980.0",
                },
            ],
        )

        snapshots = parse_meta_and_asset_ctxs(raw)
        assert len(snapshots) == 2

        btc = snapshots[0]
        assert btc.coin == "BTC"
        assert btc.open_interest == 100.5
        assert btc.mark_price == 50000.0
        assert btc.open_interest_usd == 100.5 * 50000.0
        assert btc.funding_rate == 0.0001
        assert btc.mid_price == 50000.5

        eth = snapshots[1]
        assert eth.coin == "ETH"
        assert eth.mid_price is None

    def test_hip3_prefixed_coin_names(self) -> None:
        """HIP-3 coins with dex:name format are parsed correctly."""
        raw = (
            {
                "universe": [
                    {
                        "name": "xyz:GOLD",
                        "szDecimals": 2,
                        "maxLeverage": 20,
                        "marginTableId": 0,
                    },
                ]
            },
            [
                {
                    "dayNtlVlm": "5000000.0",
                    "funding": "0.0003",
                    "openInterest": "500.0",
                    "oraclePx": "4500.0",
                    "markPx": "4500.0",
                    "midPx": "4500.5",
                    "premium": "0.0001",
                    "prevDayPx": "4400.0",
                },
            ],
        )

        snapshots = parse_meta_and_asset_ctxs(raw)
        assert len(snapshots) == 1
        assert snapshots[0].coin == "xyz:GOLD"
        assert snapshots[0].mark_price == 4500.0
        assert snapshots[0].open_interest_usd == 500.0 * 4500.0

    def test_empty_universe(self) -> None:
        """Empty universe returns empty list."""
        raw = ({"universe": []}, [])
        assert parse_meta_and_asset_ctxs(raw) == []


class TestParseUserState:
    """Tests for user_state parser."""

    def test_parses_positions(self) -> None:
        """Parses open positions from user state."""
        raw = {
            "assetPositions": [
                {
                    "position": {
                        "coin": "BTC",
                        "szi": "0.5",
                        "entryPx": "48000.0",
                        "positionValue": "25000.0",
                        "liquidationPx": "35000.0",
                        "unrealizedPnl": "1000.0",
                        "marginUsed": "5000.0",
                        "leverage": {
                            "type": "cross",
                            "value": 5,
                        },
                    },
                    "type": "oneWay",
                }
            ],
            "marginSummary": {
                "accountValue": "10000.0",
                "totalMarginUsed": "5000.0",
                "totalNtlPos": "25000.0",
                "totalRawUsd": "10000.0",
            },
        }

        positions = parse_user_state(raw, "0xabc")
        assert len(positions) == 1
        pos = positions[0]
        assert pos.coin == "BTC"
        assert pos.address == "0xabc"
        assert pos.size == 0.5
        assert pos.entry_price == 48000.0
        assert pos.leverage_type == "cross"
        assert pos.leverage_value == 5
        assert pos.notional_usd == 25000.0

    def test_skips_zero_size(self) -> None:
        """Positions with zero size are skipped."""
        raw = {
            "assetPositions": [
                {
                    "position": {
                        "coin": "ETH",
                        "szi": "0",
                        "entryPx": "0",
                        "positionValue": "0",
                        "liquidationPx": None,
                        "unrealizedPnl": "0",
                        "marginUsed": "0",
                        "leverage": {"type": "cross", "value": 1},
                    },
                    "type": "oneWay",
                }
            ]
        }
        assert parse_user_state(raw, "0xabc") == []


class TestParseL2Snapshot:
    """Tests for l2_snapshot parser."""

    def test_parses_levels(self) -> None:
        """Parses bid/ask levels correctly."""
        raw = {
            "coin": "BTC",
            "levels": [
                [
                    {"px": "50000.0", "sz": "1.0", "n": 3},
                    {"px": "49999.0", "sz": "2.5", "n": 1},
                ],
                [
                    {"px": "50001.0", "sz": "0.5", "n": 2},
                ],
            ],
            "time": 1000000,
        }

        book = parse_l2_snapshot(raw)
        assert book.coin == "BTC"
        assert len(book.bids) == 2
        assert len(book.asks) == 1
        assert book.bids[0] == (50000.0, 1.0)
        assert book.asks[0] == (50001.0, 0.5)


class TestParseUserFills:
    """Tests for user_fills parser."""

    def test_parses_fills(self) -> None:
        """Parses a fill list with buyer/seller assignment."""
        raw = [
            {
                "coin": "ETH",
                "px": "2000.0",
                "sz": "10.0",
                "side": "B",
                "time": 5000,
                "hash": "0xhash1",
                "tid": 42,
            },
            {
                "coin": "ETH",
                "px": "2001.0",
                "sz": "5.0",
                "side": "A",
                "time": 5001,
                "hash": "0xhash2",
                "tid": 43,
            },
        ]

        trades = parse_user_fills(raw, "0xuser")
        assert len(trades) == 2
        assert trades[0].buyer == "0xuser"
        assert trades[0].seller == ""
        assert trades[1].buyer == ""
        assert trades[1].seller == "0xuser"


class TestParseWsTrades:
    """Tests for WebSocket trades parser."""

    def test_parses_with_users(self) -> None:
        """Extracts buyer and seller from WS users field."""
        raw = {
            "channel": "trades",
            "data": [
                {
                    "coin": "BTC",
                    "px": "50000.0",
                    "sz": "0.1",
                    "side": "B",
                    "time": 1000,
                    "hash": "0xh",
                    "tid": 99,
                    "users": ["0xbuyer", "0xseller"],
                }
            ],
        }

        trades = parse_ws_trades(raw)
        assert len(trades) == 1
        assert trades[0].buyer == "0xbuyer"
        assert trades[0].seller == "0xseller"
        assert trades[0].price == 50000.0


class TestParseWsAllMids:
    """Tests for WebSocket allMids parser."""

    def test_parses_mids(self) -> None:
        """Parses mid prices from WS message."""
        raw = {
            "channel": "allMids",
            "data": {
                "mids": {
                    "BTC": "50000.5",
                    "ETH": "2000.1",
                }
            },
        }

        mids = parse_ws_all_mids(raw)
        assert mids["BTC"] == 50000.5
        assert mids["ETH"] == 2000.1
