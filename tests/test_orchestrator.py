"""Regression tests for orchestrator stream supervision."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from hypersussy.alerts.manager import AlertManager
from hypersussy.config import HyperSussySettings
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
