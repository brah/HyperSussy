"""Parse raw HyperLiquid API responses into domain models.

The HL API returns all numeric values as strings. These parsers
handle the string-to-float conversion and structural mapping.
"""

from __future__ import annotations

import time
from typing import Any

from hypersussy.models import (
    AssetSnapshot,
    CandleBar,
    FundingRate,
    L2Book,
    Position,
    Trade,
)


def _f(val: Any) -> float:
    """Safely parse a string or numeric value to float.

    Args:
        val: Value from API (typically a string like "1234.56").

    Returns:
        Parsed float value, or 0.0 if None/empty.
    """
    if val is None or val == "":
        return 0.0
    return float(val)


def parse_meta_and_asset_ctxs(
    raw: tuple[dict[str, Any], list[dict[str, Any]]],
) -> list[AssetSnapshot]:
    """Parse the response from ``info.meta_and_asset_ctxs()``.

    Args:
        raw: Tuple of (meta_dict, list_of_asset_ctx_dicts).

    Returns:
        One AssetSnapshot per listed perpetual asset.
    """
    meta, ctxs = raw
    universe = meta["universe"]
    now_ms = int(time.time() * 1000)
    snapshots: list[AssetSnapshot] = []

    for asset_info, ctx in zip(universe, ctxs, strict=True):
        # Skip delisted / inactive assets (no mark price from the exchange)
        if not ctx.get("markPx"):
            continue
        coin = asset_info["name"]
        mark = _f(ctx.get("markPx"))
        oi = _f(ctx.get("openInterest"))
        snapshots.append(
            AssetSnapshot(
                coin=coin,
                timestamp_ms=now_ms,
                open_interest=oi,
                open_interest_usd=oi * mark if mark else 0.0,
                mark_price=mark,
                oracle_price=_f(ctx.get("oraclePx")),
                funding_rate=_f(ctx.get("funding")),
                premium=_f(ctx.get("premium")),
                day_volume_usd=_f(ctx.get("dayNtlVlm")),
                mid_price=(_f(ctx["midPx"]) if ctx.get("midPx") else None),
            )
        )

    return snapshots


def parse_user_state(
    raw: dict[str, Any],
    address: str,
) -> list[Position]:
    """Parse the response from ``info.user_state(address)``.

    Args:
        raw: The clearinghouse state dict.
        address: The queried user address.

    Returns:
        List of open positions.
    """
    now_ms = int(time.time() * 1000)
    positions: list[Position] = []

    for ap in raw.get("assetPositions", []):
        pos = ap["position"]
        size = _f(pos.get("szi"))
        if size == 0.0:
            continue

        mark = _f(pos.get("positionValue")) / abs(size) if size else 0.0
        leverage = pos.get("leverage", {})
        liq_px = pos.get("liquidationPx")

        positions.append(
            Position(
                coin=pos["coin"],
                address=address,
                size=size,
                entry_price=_f(pos.get("entryPx")),
                mark_price=mark,
                liquidation_price=_f(liq_px) if liq_px else None,
                unrealized_pnl=_f(pos.get("unrealizedPnl")),
                margin_used=_f(pos.get("marginUsed")),
                leverage_value=int(leverage.get("value", 1)),
                leverage_type=leverage.get("type", "cross"),
                notional_usd=abs(_f(pos.get("positionValue"))),
                timestamp_ms=now_ms,
            )
        )

    return positions


def parse_l2_snapshot(raw: dict[str, Any]) -> L2Book:
    """Parse the response from ``info.l2_snapshot(coin)``.

    Args:
        raw: The L2 book dict with levels.

    Returns:
        Parsed L2Book model.
    """
    levels = raw.get("levels", [[], []])
    bids = tuple((_f(lvl["px"]), _f(lvl["sz"])) for lvl in levels[0])
    asks = tuple((_f(lvl["px"]), _f(lvl["sz"])) for lvl in levels[1])
    return L2Book(
        coin=raw.get("coin", ""),
        timestamp_ms=raw.get("time", int(time.time() * 1000)),
        bids=bids,
        asks=asks,
    )


def parse_candles(
    raw: list[dict[str, Any]],
    coin: str,
    interval: str,
) -> list[CandleBar]:
    """Parse the response from ``info.candles_snapshot()``.

    Args:
        raw: List of candle dicts.
        coin: Asset name.
        interval: Candle interval string.

    Returns:
        List of CandleBar models.
    """
    return [
        CandleBar(
            coin=coin,
            timestamp_ms=int(c["t"]),
            open=_f(c["o"]),
            high=_f(c["h"]),
            low=_f(c["l"]),
            close=_f(c["c"]),
            volume=_f(c["v"]),
            num_trades=int(c.get("n", 0)),
            interval=interval,
        )
        for c in raw
    ]


def parse_funding_history(
    raw: list[dict[str, Any]],
    coin: str,
) -> list[FundingRate]:
    """Parse the response from ``info.funding_history()``.

    Args:
        raw: List of funding rate dicts.
        coin: Asset name.

    Returns:
        List of FundingRate models.
    """
    return [
        FundingRate(
            coin=coin,
            timestamp_ms=int(entry["time"]),
            funding_rate=_f(entry.get("fundingRate")),
            premium=_f(entry.get("premium")),
        )
        for entry in raw
    ]


def parse_user_fills(
    raw: list[dict[str, Any]],
    address: str,
) -> list[Trade]:
    """Parse the response from ``info.user_fills(address)``.

    Args:
        raw: List of fill dicts.
        address: The queried user address.

    Returns:
        List of Trade models.

    Note:
        user_fills doesn't include counterparty address.
        buyer/seller are set based on side relative to the user.
    """
    trades: list[Trade] = []
    for fill in raw:
        side = fill.get("side", "B")
        is_buyer = side == "B"
        trades.append(
            Trade(
                coin=fill["coin"],
                price=_f(fill.get("px")),
                size=_f(fill.get("sz")),
                side=side,
                timestamp_ms=int(fill.get("time", 0)),
                buyer=address if is_buyer else "",
                seller=address if not is_buyer else "",
                tx_hash=fill.get("hash", ""),
                tid=int(fill.get("tid", 0)),
            )
        )
    return trades


def parse_ws_trades(
    raw: dict[str, Any],
) -> list[Trade]:
    """Parse a WebSocket ``trades`` channel message.

    The WS trades message includes a ``data`` list where each trade
    has ``coin``, ``px``, ``sz``, ``side``, ``time``, ``hash``,
    ``tid``, and crucially ``users`` which gives [buyer, seller].

    Args:
        raw: The full WS message dict.

    Returns:
        List of Trade models with buyer/seller addresses.
    """
    trades: list[Trade] = []
    for t in raw.get("data", []):
        users = t.get("users", ["", ""])
        buyer = users[0] if len(users) > 0 else ""
        seller = users[1] if len(users) > 1 else ""
        trades.append(
            Trade(
                coin=t.get("coin", ""),
                price=_f(t.get("px")),
                size=_f(t.get("sz")),
                side=t.get("side", "B"),
                timestamp_ms=int(t.get("time", 0)),
                buyer=buyer,
                seller=seller,
                tx_hash=t.get("hash", ""),
                tid=int(t.get("tid", 0)),
            )
        )
    return trades


def parse_ws_active_asset_ctx(msg: dict[str, Any]) -> AssetSnapshot | None:
    """Parse a WebSocket ``activeAssetCtx`` channel message.

    The WS ``activeAssetCtx`` message delivers real-time asset context
    updates (funding, OI, prices) for a single native perpetual coin.
    HL sends an initial snapshot on subscribe and push updates thereafter.
    All numeric values in ``ctx`` are strings — parsed via ``_f()``.

    Args:
        msg: The full WS message dict with ``channel`` and ``data`` keys.

    Returns:
        An AssetSnapshot, or None if the asset is inactive (no markPx).
    """
    data: dict[str, Any] = msg.get("data", {})
    coin: str = data.get("coin", "")
    ctx: dict[str, Any] = data.get("ctx", {})
    if not coin or not ctx.get("markPx"):
        return None
    mark = _f(ctx["markPx"])
    oi = _f(ctx.get("openInterest"))
    return AssetSnapshot(
        coin=coin,
        timestamp_ms=int(time.time() * 1000),
        open_interest=oi,
        open_interest_usd=oi * mark,
        mark_price=mark,
        oracle_price=_f(ctx.get("oraclePx")),
        funding_rate=_f(ctx.get("funding")),
        premium=_f(ctx.get("premium")),
        day_volume_usd=_f(ctx.get("dayNtlVlm")),
        mid_price=_f(ctx["midPx"]) if ctx.get("midPx") else None,
    )


def parse_ws_all_mids(
    raw: dict[str, Any],
) -> dict[str, float]:
    """Parse a WebSocket ``allMids`` channel message.

    Args:
        raw: The full WS message dict.

    Returns:
        Dict mapping coin name to mid price.
    """
    mids = raw.get("data", {}).get("mids", {})
    return {coin: _f(price) for coin, price in mids.items()}
