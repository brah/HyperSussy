"""Tests for BackgroundRunner lifecycle."""

from __future__ import annotations

import asyncio
import threading
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hypersussy.config import HyperSussySettings
from hypersussy.dashboard.runner import BackgroundRunner
from hypersussy.dashboard.state import SharedState


@pytest.fixture
def shared_state() -> SharedState:
    """Minimal SharedState for runner tests."""
    return SharedState()


@pytest.fixture
def settings() -> HyperSussySettings:
    """Default settings."""
    return HyperSussySettings()


def _make_runner(
    settings: HyperSussySettings,
    shared_state: SharedState,
) -> BackgroundRunner:
    """Construct a BackgroundRunner with a mocked async_main."""
    return BackgroundRunner(settings=settings, shared_state=shared_state)


def _patch_async_main(runner: BackgroundRunner) -> None:
    """Replace _async_main with a coroutine that sets running then returns."""

    async def _stub() -> None:
        runner._state.set_running(True)  # noqa: SLF001
        await asyncio.sleep(0.05)

    runner._async_main = _stub  # type: ignore[method-assign]


def test_start_sets_is_alive(
    settings: HyperSussySettings,
    shared_state: SharedState,
) -> None:
    """After start(), runner.is_alive is True."""
    runner = _make_runner(settings, shared_state)
    _patch_async_main(runner)
    runner.start()
    # give the thread a moment to spin up
    time.sleep(0.02)
    assert runner.is_alive
    runner.stop()


def test_start_is_idempotent(
    settings: HyperSussySettings,
    shared_state: SharedState,
) -> None:
    """Calling start() twice does not create a second thread."""
    runner = _make_runner(settings, shared_state)
    _patch_async_main(runner)
    runner.start()
    first_thread = runner._thread  # noqa: SLF001
    runner.start()
    assert runner._thread is first_thread  # noqa: SLF001
    runner.stop()


def test_stop_joins_thread(
    settings: HyperSussySettings,
    shared_state: SharedState,
) -> None:
    """After stop(), is_alive is False within 2 seconds."""

    async def _long_stub() -> None:
        runner._state.set_running(True)  # noqa: SLF001
        await asyncio.sleep(10)  # would run forever without stop

    runner = _make_runner(settings, shared_state)
    runner._async_main = _long_stub  # type: ignore[method-assign]
    runner.start()
    time.sleep(0.05)
    runner.stop()
    # join(5) inside stop(); check is_alive afterwards
    assert not runner.is_alive


def test_sets_shared_state_running(
    settings: HyperSussySettings,
    shared_state: SharedState,
) -> None:
    """shared_state.is_running becomes True once the loop begins."""
    runner = _make_runner(settings, shared_state)
    _patch_async_main(runner)
    runner.start()

    deadline = time.monotonic() + 2.0
    while not shared_state.is_running and time.monotonic() < deadline:
        time.sleep(0.01)

    assert shared_state.is_running
    runner.stop()


def test_running_flag_cleared_on_exit(
    settings: HyperSussySettings,
    shared_state: SharedState,
) -> None:
    """is_running is False after the orchestrator exits."""

    async def _quick_stub() -> None:
        runner._state.set_running(True)  # noqa: SLF001
        # returns immediately, simulating a clean shutdown

    runner = _make_runner(settings, shared_state)
    runner._async_main = _quick_stub  # type: ignore[method-assign]
    runner.start()

    deadline = time.monotonic() + 2.0
    while runner.is_alive and time.monotonic() < deadline:
        time.sleep(0.01)

    assert not shared_state.is_running
