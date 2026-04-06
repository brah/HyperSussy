"""Regression tests for orchestrator stream supervision."""

from __future__ import annotations

import asyncio
import sqlite3
from unittest.mock import AsyncMock, MagicMock

import pytest

from hypersussy.alerts.manager import AlertManager
from hypersussy.config import HyperSussySettings
from hypersussy.models import Trade
from hypersussy.orchestrator import Orchestrator


def _make_orchestrator(settings: HyperSussySettings) -> Orchestrator:
    """Build an orchestrator with mocked collaborators."""
    reader = MagicMock()
    stream = MagicMock()
    storage = MagicMock()
    alert_manager = MagicMock(spec=AlertManager)
    alert_manager.process_alert = AsyncMock()
    return Orchestrator(
        reader=reader,
        stream=stream,
        storage=storage,
        engines=[],
        alert_manager=alert_manager,
        settings=settings,
    )


@pytest.mark.asyncio
async def test_trade_stream_supervisor_refreshes_batches(
    settings: HyperSussySettings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Trade subscriptions are rebuilt when the tracked coin list changes."""
    monkeypatch.setattr("hypersussy.orchestrator._STREAM_RECONCILE_S", 0.01)
    orchestrator = _make_orchestrator(settings)
    orchestrator._running = True  # noqa: SLF001
    orchestrator._coins = ["BTC"]  # noqa: SLF001

    started: list[tuple[str, ...]] = []
    cancelled: list[tuple[str, ...]] = []
    first_started = asyncio.Event()
    second_started = asyncio.Event()

    async def _fake_trade_stream_batch(coins: list[str]) -> None:
        started.append(tuple(coins))
        if len(started) == 1:
            first_started.set()
        else:
            second_started.set()
        try:
            await asyncio.Future()
        except asyncio.CancelledError:
            cancelled.append(tuple(coins))
            raise

    orchestrator._trade_stream_batch = _fake_trade_stream_batch  # type: ignore[method-assign]

    task = asyncio.create_task(orchestrator._trade_stream_supervisor_loop())  # noqa: SLF001
    await asyncio.wait_for(first_started.wait(), timeout=1.0)

    orchestrator._coins = ["BTC", "ETH"]  # noqa: SLF001
    await asyncio.wait_for(second_started.wait(), timeout=1.0)

    orchestrator._running = False  # noqa: SLF001
    await asyncio.wait_for(task, timeout=1.0)

    assert started[0] == ("BTC",)
    assert ("ETH",) in started
    assert ("BTC",) in cancelled


@pytest.mark.asyncio
async def test_asset_ctx_supervisor_refreshes_native_coin_set(
    settings: HyperSussySettings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Native asset-context subscriptions are rebuilt after coin refreshes."""
    monkeypatch.setattr("hypersussy.orchestrator._STREAM_RECONCILE_S", 0.01)
    orchestrator = _make_orchestrator(settings)
    orchestrator._running = True  # noqa: SLF001
    orchestrator._native_coins = ["BTC"]  # noqa: SLF001

    started: list[tuple[str, ...]] = []
    cancelled: list[tuple[str, ...]] = []
    first_started = asyncio.Event()
    second_started = asyncio.Event()

    async def _fake_asset_ctx_stream_loop(coins: list[str]) -> None:
        started.append(tuple(coins))
        if len(started) == 1:
            first_started.set()
        else:
            second_started.set()
        try:
            await asyncio.Future()
        except asyncio.CancelledError:
            cancelled.append(tuple(coins))
            raise

    orchestrator._asset_ctx_stream_loop = _fake_asset_ctx_stream_loop  # type: ignore[method-assign]

    task = asyncio.create_task(
        orchestrator._asset_ctx_stream_supervisor_loop()  # noqa: SLF001
    )
    await asyncio.wait_for(first_started.wait(), timeout=1.0)

    orchestrator._native_coins = ["BTC", "ETH"]  # noqa: SLF001
    await asyncio.wait_for(second_started.wait(), timeout=1.0)

    orchestrator._running = False  # noqa: SLF001
    await asyncio.wait_for(task, timeout=1.0)

    assert started[0] == ("BTC",)
    assert ("BTC", "ETH") in started
    assert ("BTC",) in cancelled


@pytest.mark.asyncio
async def test_dispatch_trade_backs_off_after_locked_db(
    settings: HyperSussySettings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Persistent DB locks do not trigger a write attempt for every trade."""
    orchestrator = _make_orchestrator(settings)
    orchestrator._storage.insert_trades = AsyncMock(  # noqa: SLF001
        side_effect=sqlite3.OperationalError("database is locked")
    )
    log_mock = MagicMock()
    monkeypatch.setattr("hypersussy.orchestrator.logger.log", log_mock)

    trade = Trade(
        coin="BTC",
        price=1.0,
        size=1.0,
        side="B",
        timestamp_ms=1_000,
        buyer="0xabc",
        seller="0xdef",
        tx_hash="0xhash",
        tid=1,
    )

    await orchestrator._dispatch_trade(trade)  # noqa: SLF001
    await orchestrator._dispatch_trade(trade)  # noqa: SLF001

    assert orchestrator._storage.insert_trades.await_count == 1  # noqa: SLF001
    assert log_mock.call_count == 1
    # Both trades are buffered and waiting for recovery
    assert len(orchestrator._trade_buffer) == 2  # noqa: SLF001


@pytest.mark.asyncio
async def test_dispatch_trade_flushes_buffer_on_recovery(
    settings: HyperSussySettings,
) -> None:
    """Buffered trades are flushed once storage becomes available again."""
    orchestrator = _make_orchestrator(settings)
    call_count = 0

    async def _fail_then_succeed(trades: list[Trade]) -> None:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise sqlite3.OperationalError("database is locked")

    orchestrator._storage.insert_trades = AsyncMock(  # noqa: SLF001
        side_effect=_fail_then_succeed
    )

    trade1 = Trade(
        coin="BTC", price=1.0, size=1.0, side="B",
        timestamp_ms=1_000, buyer="0xabc", seller="0xdef",
        tx_hash="0xh1", tid=1,
    )
    trade2 = Trade(
        coin="ETH", price=2.0, size=1.0, side="B",
        timestamp_ms=2_000, buyer="0xabc", seller="0xdef",
        tx_hash="0xh2", tid=2,
    )

    # First dispatch: insert fails, enters backoff
    await orchestrator._dispatch_trade(trade1)  # noqa: SLF001
    assert len(orchestrator._trade_buffer) == 1  # noqa: SLF001

    # Second dispatch during backoff: buffered without write attempt
    await orchestrator._dispatch_trade(trade2)  # noqa: SLF001
    assert len(orchestrator._trade_buffer) == 2  # noqa: SLF001
    assert call_count == 1

    # Expire the backoff window
    orchestrator._trade_storage_backoff_until = 0.0  # noqa: SLF001

    # Third dispatch triggers flush of all 3 trades (2 buffered + 1 new)
    trade3 = Trade(
        coin="BTC", price=3.0, size=1.0, side="B",
        timestamp_ms=3_000, buyer="0xabc", seller="0xdef",
        tx_hash="0xh3", tid=3,
    )
    await orchestrator._dispatch_trade(trade3)  # noqa: SLF001

    assert call_count == 2
    # Buffer should be empty after successful flush
    assert len(orchestrator._trade_buffer) == 0  # noqa: SLF001
    # The flush should have included all 3 trades
    flushed_batch = orchestrator._storage.insert_trades.call_args_list[1][0][0]  # noqa: SLF001
    assert len(flushed_batch) == 3
