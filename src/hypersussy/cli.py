"""CLI entry point for the HyperSussy monitoring system."""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys

import structlog


def _configure_logging(level: str) -> None:
    """Set up structlog with JSON output.

    Args:
        level: Log level string (e.g. "INFO", "DEBUG").
    """
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelName(level)
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(message)s",
    )


async def _run() -> None:
    """Wire up all components and start the orchestrator."""
    from hypersussy.alerts.manager import AlertManager
    from hypersussy.alerts.sinks.log_sink import LogSink
    from hypersussy.config import HyperSussySettings
    from hypersussy.engines.base import DetectionEngine
    from hypersussy.engines.funding_anomaly import (
        FundingAnomalyEngine,
    )
    from hypersussy.engines.liquidation_risk import (
        LiquidationRiskEngine,
    )
    from hypersussy.engines.oi_concentration import (
        OiConcentrationEngine,
    )
    from hypersussy.engines.pre_move import PreMoveEngine
    from hypersussy.engines.twap_detector import TwapDetectorEngine
    from hypersussy.engines.whale_tracker import WhaleTrackerEngine
    from hypersussy.exchange.hyperliquid.client import (
        HyperLiquidReader,
    )
    from hypersussy.exchange.hyperliquid.websocket import (
        HyperLiquidStream,
    )
    from hypersussy.orchestrator import Orchestrator
    from hypersussy.rate_limiter import WeightRateLimiter
    from hypersussy.storage.sqlite import SqliteStorage

    settings = HyperSussySettings()
    _configure_logging(settings.log_level)

    log = structlog.get_logger("hypersussy.cli")
    log.info("Starting HyperSussy", log_level=settings.log_level)

    # Ensure data directory exists
    db_dir = os.path.dirname(settings.db_path)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)

    # Initialize components
    rate_limiter = WeightRateLimiter(
        max_weight=settings.rate_limit_weight,
        window_seconds=settings.rate_limit_window_s,
    )
    reader = HyperLiquidReader(
        base_url=settings.hl_api_url,
        rate_limiter=rate_limiter,
    )
    stream = HyperLiquidStream(ws_url=settings.hl_ws_url)
    storage = SqliteStorage(db_path=settings.db_path)
    await storage.init()

    # Engines
    engines: list[DetectionEngine] = [
        OiConcentrationEngine(storage=storage, settings=settings),
        WhaleTrackerEngine(storage=storage, reader=reader, settings=settings),
        TwapDetectorEngine(settings=settings),
        PreMoveEngine(settings=settings),
        FundingAnomalyEngine(settings=settings),
        LiquidationRiskEngine(storage=storage, reader=reader, settings=settings),
    ]

    # Alert system
    sinks = [LogSink()]
    alert_manager = AlertManager(storage=storage, sinks=sinks, settings=settings)

    # Orchestrator
    orchestrator = Orchestrator(
        reader=reader,
        stream=stream,
        storage=storage,
        engines=engines,
        alert_manager=alert_manager,
        settings=settings,
    )

    # Graceful shutdown on SIGINT/SIGTERM
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


def main() -> None:
    """Synchronous entry point for the CLI."""
    asyncio.run(_run())


if __name__ == "__main__":
    main()
