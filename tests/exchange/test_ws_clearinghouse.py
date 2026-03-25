"""Tests for HyperLiquidStream.stream_clearinghouse_states."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from hypersussy.exchange.hyperliquid.websocket import HyperLiquidStream, WsThrottle


class _FakeWS:
    """Minimal async-iterable fake WebSocket for testing.

    Args:
        messages: Pre-encoded string messages to yield in order.
    """

    def __init__(self, messages: list[str]) -> None:
        self._msgs = list(messages)
        self.send = AsyncMock()
        self.close = AsyncMock()

    def __aiter__(self) -> _FakeWS:
        return self

    async def __anext__(self) -> str:
        if not self._msgs:
            raise StopAsyncIteration
        return self._msgs.pop(0)


def _ch_msg(user: str, coin: str = "BTC", szi: str = "1.0") -> dict[str, Any]:
    """Build a fake clearinghouseState WS message.

    Args:
        user: Wallet address.
        coin: Position coin name.
        szi: Position size string.

    Returns:
        WS message dict.
    """
    return {
        "channel": "clearinghouseState",
        "subscription": {"type": "clearinghouseState", "user": user},
        "data": {
            "assetPositions": [
                {
                    "position": {
                        "coin": coin,
                        "szi": szi,
                        "entryPx": "50000.0",
                        "positionValue": "50000.0",
                        "liquidationPx": "40000.0",
                        "unrealizedPnl": "0.0",
                        "marginUsed": "5000.0",
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
        },
    }


def _make_stream() -> HyperLiquidStream:
    """Create a stream with a zero-delay throttle for testing."""
    throttle = WsThrottle(connect_delay_s=0.0, subscribe_delay_s=0.0)
    return HyperLiquidStream(throttle=throttle)


async def _collect(
    stream: HyperLiquidStream,
    users: list[str],
    messages: list[dict[str, Any]],
    n_expected: int = 1,
) -> list[tuple[str, list[Any]]]:
    """Collect n_expected yields from stream_clearinghouse_states.

    Breaks out of the async generator after receiving n_expected results,
    which cleanly terminates the generator without triggering the reconnect
    loop.

    Args:
        stream: The stream under test.
        users: Users to subscribe to.
        messages: Sequence of raw WS messages to inject.
        n_expected: Number of yielded results to collect before stopping.

    Returns:
        List of (address, positions) tuples yielded.
    """
    import orjson

    raw_msgs = [orjson.dumps(m).decode() for m in messages]
    fake_ws = _FakeWS(raw_msgs)

    with patch.object(stream, "_connect", return_value=fake_ws):
        results: list[tuple[str, list[Any]]] = []
        async for addr, positions in stream.stream_clearinghouse_states(users):
            results.append((addr, positions))
            if len(results) >= n_expected:
                break
        return results


class TestStreamClearinghouseStates:
    """Tests for stream_clearinghouse_states."""

    @pytest.mark.asyncio
    async def test_yields_parsed_positions(self) -> None:
        """A valid clearinghouseState message yields (address, positions)."""
        stream = _make_stream()
        msgs = [_ch_msg("0xwhale", "BTC", "2.5")]

        results = await _collect(stream, ["0xwhale"], msgs)

        assert len(results) == 1
        addr, positions = results[0]
        assert addr == "0xwhale"
        assert len(positions) == 1
        assert positions[0].coin == "BTC"
        assert positions[0].size == pytest.approx(2.5)

    @pytest.mark.asyncio
    async def test_skips_pong_messages(self) -> None:
        """pong and subscriptionResponse messages are not yielded."""
        stream = _make_stream()
        pong = {"channel": "pong"}
        sub_resp = {"channel": "subscriptionResponse", "data": {}}
        real = _ch_msg("0xwhale", "ETH")
        msgs = [pong, sub_resp, real]

        results = await _collect(stream, ["0xwhale"], msgs)

        assert len(results) == 1
        assert results[0][0] == "0xwhale"

    @pytest.mark.asyncio
    async def test_skips_unknown_channel(self) -> None:
        """Messages from unrelated channels are silently ignored."""
        stream = _make_stream()
        trade_msg = {
            "channel": "trades",
            "data": [{"coin": "BTC", "px": "50000", "sz": "1"}],
        }
        real = _ch_msg("0xwhale")
        msgs = [trade_msg, real]

        results = await _collect(stream, ["0xwhale"], msgs)

        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_skips_message_without_user(self) -> None:
        """A clearinghouseState message without subscription.user is skipped."""
        stream = _make_stream()
        no_user = {
            "channel": "clearinghouseState",
            "subscription": {},
            "data": {},
        }
        real = _ch_msg("0xwhale")
        msgs = [no_user, real]

        results = await _collect(stream, ["0xwhale"], msgs)

        assert len(results) == 1
        assert results[0][0] == "0xwhale"

    @pytest.mark.asyncio
    async def test_subscribes_per_user(self) -> None:
        """One subscribe message is sent per user in the list."""
        import orjson

        stream = _make_stream()
        users = ["0xalice", "0xbob", "0xcarol"]
        fake_ws = _FakeWS([])

        # First call returns fake_ws; second raises CancelledError to stop the
        # reconnect loop cleanly without running indefinitely.
        with patch.object(
            stream,
            "_connect",
            side_effect=[fake_ws, asyncio.CancelledError()],
        ):
            try:
                async for _ in stream.stream_clearinghouse_states(users):
                    pass  # pragma: no cover
            except asyncio.CancelledError:
                pass

        send_calls = fake_ws.send.call_args_list
        subs = [orjson.loads(call.args[0]) for call in send_calls]
        subscribed_users = [
            s["subscription"]["user"] for s in subs if s.get("method") == "subscribe"
        ]
        assert set(subscribed_users) == set(users)
