"""CLI entry point for the HyperSussy monitoring system."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import logging.handlers
import os
import signal
import sys
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from hypersussy.config import HyperSussySettings
    from hypersussy.engines.base import DetectionEngine
    from hypersussy.exchange.hyperliquid.client import HyperLiquidReader
    from hypersussy.exchange.hyperliquid.websocket import (
        HyperLiquidStream,
    )
    from hypersussy.rate_limiter import WeightRateLimiter
    from hypersussy.storage.sqlite import SqliteStorage

logger = logging.getLogger(__name__)


def _configure_logging(
    level: str,
    log_file: str | None = None,
    max_bytes: int = 50 * 1024 * 1024,
    backup_count: int = 5,
) -> None:
    """Set up structlog routed through stdlib logging with optional rotation.

    Both structlog events and stdlib ``logging`` calls are formatted by a
    single :class:`structlog.stdlib.ProcessorFormatter` attached to one
    root handler, so everything shares the same sink and the same rotation
    policy.

    Args:
        level: Log level string (e.g. "INFO", "DEBUG").
        log_file: Optional path to write logs to. If None, writes to stdout.
        max_bytes: Maximum bytes per log file before rotation kicks in.
            Only applies when ``log_file`` is set.
        backup_count: Number of rotated files to keep. Only applies when
            ``log_file`` is set.
    """
    level_no = getattr(logging, level, logging.INFO)

    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
    ]

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level_no),
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Colours only make sense on a TTY; force them off when writing to a
    # file so rotated logs stay clean of ANSI escape sequences.
    renderer = structlog.dev.ConsoleRenderer(colors=log_file is None)
    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler: logging.Handler
    if log_file is not None:
        handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
    else:
        handler = logging.StreamHandler()
    handler.setFormatter(formatter)

    root = logging.getLogger()
    # Clear any handlers from a prior basicConfig / reload so we don't
    # double-log or keep writing to a stale file descriptor.
    for existing in list(root.handlers):
        root.removeHandler(existing)
        with contextlib.suppress(Exception):
            existing.close()
    root.addHandler(handler)
    root.setLevel(level_no)


def _build_components(
    settings: HyperSussySettings,
) -> tuple[
    HyperLiquidReader,
    HyperLiquidStream,
    SqliteStorage,
    list[DetectionEngine],
    WeightRateLimiter,
]:
    """Import and instantiate all core components from settings.

    Args:
        settings: Application settings.

    Returns:
        Tuple of (reader, stream, storage, engines, rate_limiter).
    """
    from hypersussy.engines.funding_anomaly import FundingAnomalyEngine
    from hypersussy.engines.liquidation_risk import LiquidationRiskEngine
    from hypersussy.engines.oi_concentration import OiConcentrationEngine
    from hypersussy.engines.pre_move import PreMoveEngine
    from hypersussy.engines.whale_tracker import WhaleTrackerEngine
    from hypersussy.exchange.hyperliquid.client import HyperLiquidReader as _Reader
    from hypersussy.exchange.hyperliquid.websocket import (
        HyperLiquidStream as _Stream,
    )
    from hypersussy.exchange.hyperliquid.websocket import (
        WsThrottle,
    )
    from hypersussy.rate_limiter import WeightRateLimiter as _RateLimiter
    from hypersussy.storage.sqlite import SqliteStorage as _Storage

    rate_limiter = _RateLimiter(
        max_weight=settings.rate_limit_weight - settings.candle_rate_limit_weight,
        window_seconds=settings.rate_limit_window_s,
    )
    reader = _Reader(
        base_url=settings.hl_api_url,
        rate_limiter=rate_limiter,
        include_hip3=settings.include_hip3,
        hip3_dex_filter=settings.hip3_dex_filter,
    )
    throttle = WsThrottle(
        connect_delay_s=settings.ws_connect_delay_s,
        subscribe_delay_s=settings.ws_subscribe_delay_s,
    )
    stream = _Stream(ws_url=settings.hl_ws_url, throttle=throttle)
    storage = _Storage(db_path=settings.db_path)

    engines: list[DetectionEngine] = []
    if settings.engine_oi_concentration:
        engines.append(OiConcentrationEngine(storage=storage, settings=settings))
    if settings.engine_whale_tracker:
        engines.append(
            WhaleTrackerEngine(storage=storage, reader=reader, settings=settings)
        )
    if settings.engine_pre_move:
        engines.append(PreMoveEngine(settings=settings))
    if settings.engine_funding_anomaly:
        engines.append(FundingAnomalyEngine(settings=settings))
    if settings.engine_liquidation_risk:
        engines.append(
            LiquidationRiskEngine(storage=storage, reader=reader, settings=settings)
        )

    return reader, stream, storage, engines, rate_limiter


async def _run() -> None:
    """Wire up all components and start the orchestrator (headless mode)."""
    from hypersussy.alerts.base import AlertSink
    from hypersussy.alerts.manager import AlertManager
    from hypersussy.alerts.sinks.log_sink import LogSink
    from hypersussy.config import HyperSussySettings
    from hypersussy.orchestrator import Orchestrator

    settings = HyperSussySettings()
    _configure_logging(settings.log_level)

    log = structlog.get_logger("hypersussy.cli")
    log.info("Starting HyperSussy (headless)", log_level=settings.log_level)

    db_dir = os.path.dirname(settings.db_path)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)

    reader, stream, storage, engines, _ = _build_components(settings)
    await storage.init()

    sinks: list[AlertSink] = [LogSink()]
    alert_manager = AlertManager(storage=storage, sinks=sinks, settings=settings)
    orchestrator = Orchestrator(
        reader=reader,
        stream=stream,
        storage=storage,
        engines=engines,
        alert_manager=alert_manager,
        settings=settings,
    )

    loop = asyncio.get_running_loop()

    def _shutdown() -> None:
        log.info("Shutdown signal received")
        orchestrator.stop()

    if sys.platform != "win32":
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, _shutdown)

    try:
        await orchestrator.run()
    except KeyboardInterrupt:
        log.info("Interrupted by user")
    finally:
        await storage.close()
        log.info("HyperSussy stopped")


def _run_api() -> None:
    """Launch the FastAPI + uvicorn server.

    The FastAPI lifespan starts BackgroundRunner in a daemon thread so the
    orchestrator runs alongside uvicorn on the same process.  Blocks until
    the server is stopped.
    """
    import uvicorn

    from hypersussy.api.server import app
    from hypersussy.config import HyperSussySettings

    settings = HyperSussySettings()
    uvicorn.run(app, host=settings.api_host, port=settings.api_port)


def main() -> None:
    """Synchronous entry point for the CLI."""
    if "--api" in sys.argv:
        _run_api()
    else:
        asyncio.run(_run())


if __name__ == "__main__":
    main()
