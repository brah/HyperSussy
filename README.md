# HyperSussy

Monitoring and alerting system for suspicious activity on HyperLiquid perpetual futures.

HyperSussy passively monitors all listed perps via REST polling and WebSocket trade streams, discovers whale addresses organically from trade flow, tracks their positions, and fires structured alerts when it detects patterns like OI concentration, large TWAPs, pre-move trading, funding anomalies, or liquidation risk.

## Features

- **All perps monitored** -- dynamically fetches the full asset list on startup and subscribes to trade streams for every listed perpetual
- **Passive whale discovery** -- no manual seed list required; addresses trading >$5M in a rolling hour are promoted to a tracked list from the trade stream
- **Streamlit dashboard** -- live overview, alert feed, charts, and whale tracker with per-address alert history
- **6 detection engines** running concurrently:

| Engine | What it detects |
| ------ | --------------- |
| **OI Concentration** | Rapid OI changes where a small number of addresses account for a disproportionate share of volume |
| **Whale Tracker** | Whale discovery, large positions (>20% of coin OI), significant position changes (>$1M); polls active TWAPs via HyperLiquid API |
| **TWAP Detector** | Evenly-spaced fill patterns indicative of algorithmic TWAP execution (disabled by default; API-based TWAP detection preferred) |
| **Pre-Move Correlation** | Addresses that traded heavily in a direction shortly before a large price move |
| **Funding Anomaly** | Extreme or unusual funding rates (z-score > 3 sigma or absolute rate breach) |
| **Liquidation Risk** | Tracked whales approaching liquidation with estimated market impact via L2 book depth |

- **Structured alert pipeline** with deduplication, cooldown, global throttling, and pluggable sinks
- **Multi-DEX extensible** -- protocol-based abstractions (`ExchangeReader`, `ExchangeStream`) allow adding Lighter, dYdX, etc. without touching engine code

## Architecture

```text
Orchestrator
  |-- REST polling (metaAndAssetCtxs every 10s)
  |-- WebSocket trade streams (per coin)
  |-- Engine tick loop
  |
  +-> Detection Engines (OI, Whale, TWAP, PreMove, Funding, Liquidation)
  |     |
  |     +-> Alerts
  |           |
  |           +-> AlertManager (dedup, throttle)
  |                 |
  |                 +-> Sinks (structured log)
  |
  +-> SQLite Storage (WAL mode, async via aiosqlite)
  |
  +-> Streamlit Dashboard (reads SQLite directly, live refresh)
```

## Quick Start

```bash
# Clone and install
git clone <repo-url> && cd HyperSussy
uv sync

# Configure (optional -- defaults work for monitoring all perps)
cp .env.example .env
# Edit .env to set thresholds, watched coins, etc.

# Run headless (logs to stdout)
uv run hypersussy

# Run Streamlit dashboard
uv sync --extra dashboard
uv run hypersussy --streamlit
```

## Configuration

All settings are configurable via environment variables with the `HYPERSUSSY_` prefix. See [.env.example](.env.example) for the full list.

Key settings:

| Variable | Default | Description |
| -------- | ------- | ----------- |
| `HYPERSUSSY_WATCHED_COINS` | `[]` (all) | Comma-separated list of coins to monitor, empty = all listed perps |
| `HYPERSUSSY_DB_PATH` | `data/hypersussy.db` | SQLite database path |
| `HYPERSUSSY_OI_CHANGE_PCT_THRESHOLD` | `0.10` | Minimum OI change % to trigger analysis |
| `HYPERSUSSY_WHALE_VOLUME_THRESHOLD_USD` | `5000000` | Volume threshold (USD) for whale promotion |
| `HYPERSUSSY_LARGE_POSITION_OI_PCT` | `0.20` | Position size as fraction of coin OI to trigger alert |
| `HYPERSUSSY_PRE_MOVE_THRESHOLD_PCT` | `0.02` | Minimum price move % for pre-move analysis |
| `HYPERSUSSY_ALERT_COOLDOWN_S` | `3600` | Alert deduplication cooldown in seconds |
| `HYPERSUSSY_LOG_LEVEL` | `INFO` | Log verbosity |

## Development

```bash
# Install with dev dependencies
uv sync --extra dev

# Run tests
uv run pytest tests/ -v

# Type checking
uv run mypy src/

# Lint and format
uv run ruff check src/ tests/
uv run ruff format src/ tests/
```

## Project Structure

```text
src/hypersussy/
    config.py                  # Pydantic-settings, all thresholds via env vars
    models.py                  # Frozen dataclasses: AssetSnapshot, Trade, Position, Alert, etc.
    orchestrator.py            # Main async loop: WS streams + poll loops + engine dispatch
    rate_limiter.py            # Async token-bucket for API weight (1200/min)
    cli.py                     # Entry point (--streamlit flag for dashboard mode)

    exchange/
        base.py                # Protocols: ExchangeReader, ExchangeStream
        hyperliquid/
            client.py          # HyperLiquidReader (wraps SDK + rate limiter)
            websocket.py       # Async WS manager (trades, allMids, L2 book)
            parsers.py         # Raw API dicts -> domain models

    storage/
        base.py                # StorageProtocol
        sqlite.py              # aiosqlite implementation (WAL mode)
        schema.sql             # DDL for all tables

    engines/
        base.py                # DetectionEngine protocol
        oi_concentration.py    # OI spike + address concentration
        whale_tracker.py       # Discover whales, poll positions, detect changes + active TWAPs
        twap_detector.py       # Statistical fill-pattern TWAP detection (disabled by default)
        pre_move.py            # Retroactive pre-move correlation
        funding_anomaly.py     # Extreme funding rate detection
        liquidation_risk.py    # Whales near liquidation with market impact

    alerts/
        base.py                # AlertSink protocol
        manager.py             # Dedup, throttle, route
        sinks/
            log_sink.py        # Structured JSON logging (default)

    dashboard/
        app.py                 # Streamlit entry point + page routing
        state.py               # SharedState (DataBus impl, in-process cache)
        sink.py                # StreamlitSink (AlertSink -> SharedState)
        db_reader.py           # Read-only SQLite queries for dashboard pages
        runner.py              # Background thread: runs Orchestrator alongside Streamlit
        _pages/
            overview.py        # Live market overview table
            alerts.py          # Alert feed with filters
            charts.py          # OI / funding / price charts
            whale_tracker.py   # Whale positions + per-address alert history

tests/                         # Tests covering all engines, storage, parsers, and dashboard
```

## Dependencies

- Python >= 3.13
- [hyperliquid-python-sdk](https://github.com/hyperliquid-dex/hyperliquid-python-sdk) -- REST API client
- [websockets](https://websockets.readthedocs.io/) -- async WebSocket streams
- [aiosqlite](https://github.com/omnilib/aiosqlite) -- async SQLite
- [pydantic-settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) -- env-based configuration
- [structlog](https://www.structlog.org/) -- structured logging
- [orjson](https://github.com/ijl/orjson) -- fast JSON
- [polars](https://pola.rs/) -- dataframe analysis (notebooks)

Optional (dashboard):

- [streamlit](https://streamlit.io/) -- dashboard UI
- [plotly](https://plotly.com/python/) -- interactive charts

## License

Private.
