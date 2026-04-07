# HyperSussy

HyperSussy is a monitoring and alerting system for suspicious activity on Hyperliquid perpetual futures.

It ingests market data from Hyperliquid REST and WebSocket APIs, stores snapshots and trades in SQLite, discovers high-signal wallets from flow, tracks positions, and exposes the results through a FastAPI backend plus a React dashboard.

## What It Does

- Monitors the live Hyperliquid perp universe, including HIP-3 builder-deployed markets when enabled
- Streams native perp trades and asset-context updates over WebSockets, while polling bulk snapshot data over REST
- Persists trades, asset snapshots, alerts, tracked addresses, positions, and cached candle data in SQLite
- Discovers whale wallets automatically from trade flow and lets you add or remove tracked wallets via the API/UI
- Runs multiple detection engines and routes structured alerts through a deduplicated alert pipeline
- Serves a REST API, a `/ws/live` push stream, and an optional built frontend from the same backend process

## Detection Engines

| Engine | Purpose |
| ------ | ------- |
| `OiConcentrationEngine` | Flags rapid OI changes where a concentrated set of addresses dominates flow |
| `WhaleTrackerEngine` | Coordinates whale discovery, position tracking, TWAP detection, and optional position census |
| `PreMoveEngine` | Looks for wallets trading aggressively before large price moves |
| `FundingAnomalyEngine` | Detects unusual funding behavior using z-score and absolute-rate thresholds |
| `LiquidationRiskEngine` | Flags tracked wallets nearing liquidation with estimated impact context |

## Architecture

```text
CLI
  |- `hypersussy`        -> headless monitor
  |- `hypersussy --api`  -> FastAPI server + background orchestrator
  |
  +-> Orchestrator
        |- REST polling loops
        |- WebSocket supervisors
        |- Engine dispatch
        |- Alert pipeline
        |
        +-> SQLite storage
        +-> SharedState for live UI/API updates
        +-> Detection engines
              |- OI concentration
              |- Whale tracker
              |- Pre-move
              |- Funding anomaly
              |- Liquidation risk

FastAPI
  |- `/api/*` REST endpoints
  |- `/ws/live` WebSocket stream
  `- Serves `frontend/dist/` when present

React frontend
  |- Market dashboard
  `- Wallet tracking views
```

## Quick Start

### 1. Install Python dependencies

```bash
git clone <repo-url>
cd HyperSussy
uv sync --extra dev
```

> **Heads up:** the API backend (`fastapi`, `uvicorn`) lives in the `api`
> and `dev` *extras* (PEP 621 `[project.optional-dependencies]`), not the
> base dependency set. **Always pass an extra to `uv sync`** — a bare
> `uv sync` will *prune* anything that isn't in the base set, silently
> removing `uvicorn` and `fastapi` from the venv. Recommended commands:
>
> - `uv sync --extra dev` — full dev environment (tests, mypy, ruff, api)
> - `uv sync --extra api` — minimal install for running `hypersussy --api`
>
> uv has no `default-extras` setting and no `UV_EXTRA` environment
> variable, so there is no project-level config that makes a bare
> `uv sync` keep extras installed. The only "set and forget" options are:
>
> - A shell alias: `alias uvs='uv sync --extra dev'` (or a Makefile target)
> - **Or** migrate `dev` from `[project.optional-dependencies]` to
>   PEP 735 `[dependency-groups]`. uv's `[tool.uv] default-groups = ["dev"]`
>   *does* apply to dependency groups, so a bare `uv sync` would then keep
>   dev tooling installed. Leave `api` as an extra — it's a real
>   distribution install option (`pip install hypersussy[api]`), which
>   dependency groups deliberately can't express.

### 2. Configure environment

```bash
cp .env.example .env
```

All settings use the `HYPERSUSSY_` prefix. The authoritative reference is [`src/hypersussy/config.py`](src/hypersussy/config.py).

### 3. Run headless monitoring

```bash
uv run hypersussy
```

This starts the orchestrator, writes to the configured SQLite database, and logs to stdout. Headless mode does **not** require the `api` extra.

### 4. Run the API backend

```bash
uv sync --extra api   # only if you skipped --extra dev in step 1
uv run hypersussy --api
```

The API listens on `http://localhost:8000` and starts the monitoring orchestrator in a background thread.

### 5. Run the React frontend in development

In a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Vite serves the UI on `http://localhost:5173` and proxies `/api` requests to the backend.

### 6. Serve the built frontend from FastAPI

```bash
cd frontend
npm run build
cd ..
uv run hypersussy --api
```

When `frontend/dist/` exists, FastAPI mounts it at `/`.

## API Surface

Main routes exposed by the backend:

- `/api/health`, `/api/health/logs`
- `/api/alerts`, `/api/alerts/counts`, `/api/alerts/by-address/{address}`
- `/api/snapshots/coins`, `/api/snapshots/oi/{coin}`, `/api/snapshots/funding/{coin}`, `/api/snapshots/latest-oi`
- `/api/trades/top-whales/{coin}`, `/api/trades/by-address/{address}`, `/api/trades/top-holders/{coin}`, `/api/trades/flow/{coin}`
- `/api/whales`, `/api/whales/count`, `/api/whales/positions/{address}`, `/api/whales/top/{coin}`
- `/api/whales/pnl/{address}` — realised PnL (7d + all-time, with completeness flags)
- `/api/whales/fills/{address}` — paginated Hyperliquid fill history (cursor-based)
- `/api/candles/{coin}`
- `/ws/live`

## Configuration Notes

Selected settings from [`src/hypersussy/config.py`](src/hypersussy/config.py):

| Variable | Default | Description |
| -------- | ------- | ----------- |
| `HYPERSUSSY_DB_PATH` | `data/hypersussy.db` | SQLite database path |
| `HYPERSUSSY_WATCHED_COINS` | `[]` | Empty means monitor all listed perps |
| `HYPERSUSSY_INCLUDE_HIP3` | `true` | Include HIP-3 builder-deployed perpetuals |
| `HYPERSUSSY_HIP3_DEX_FILTER` | `[]` | Restrict HIP-3 markets to selected DEX prefixes |
| `HYPERSUSSY_ENGINE_OI_CONCENTRATION` | `true` | Enable OI concentration engine |
| `HYPERSUSSY_ENGINE_WHALE_TRACKER` | `true` | Enable whale discovery and position tracking |
| `HYPERSUSSY_ENGINE_PRE_MOVE` | `true` | Enable pre-move correlation engine |
| `HYPERSUSSY_ENGINE_FUNDING_ANOMALY` | `true` | Enable funding anomaly engine |
| `HYPERSUSSY_ENGINE_LIQUIDATION_RISK` | `true` | Enable liquidation risk engine |
| `HYPERSUSSY_WHALE_VOLUME_THRESHOLD_USD` | `25000000` | Rolling notional threshold for whale promotion |
| `HYPERSUSSY_WHALE_DISCOVERY_OI_PCT` | `0.15` | Promote addresses trading a large share of coin OI |
| `HYPERSUSSY_CENSUS_ENABLED` | `true` | Enable non-whale position census polling |
| `HYPERSUSSY_POSITION_POLL_INTERVAL_S` | `150.0` | Whale position polling interval |
| `HYPERSUSSY_ALERT_COOLDOWN_S` | `3600` | Alert deduplication cooldown |
| `HYPERSUSSY_ALERT_MAX_PER_MINUTE` | `10` | Global alert throttle |

## Development

### Python

```bash
uv sync --extra dev
uv run pytest -v
uv run mypy src
uv run ruff check src tests
uv run ruff format src tests
```

### Frontend

```bash
cd frontend
npm install
npm run lint
npm run typecheck
npm run build
```

The frontend uses Vite 8 (Rolldown) + React 19 + TanStack Query + Zustand + Tailwind 4. Production builds split vendor bundles (recharts, lightweight-charts, react, query) so app-only deploys re-download ~18 KB gzip instead of the full bundle.

## CI / CD

GitHub Actions workflows live in [`.github/workflows/`](.github/workflows/):

| Workflow | Trigger | What it does |
| -------- | ------- | ------------ |
| `ci.yml` | PRs and pushes to `main` | Runs ruff lint + format check, mypy strict, pytest, plus the frontend lint/typecheck/build |
| `audit.yml` | Weekly Monday cron, lockfile changes, manual dispatch | `pip-audit` against the synced uv environment, `npm audit --omit=dev --audit-level=high` for the frontend |
| `claude-code-review.yml` | PRs (skips Dependabot) | Auto code review by Claude using the official `code-review` plugin |
| `claude.yml` | `@claude` mentions on issues / PR review threads | Interactive Claude assistant, scoped via OAuth subscription |

Dependency updates are managed by [`.github/dependabot.yml`](.github/dependabot.yml) — weekly grouped PRs for `uv` (Python), `npm` (frontend), and `github-actions`. React major-version bumps are pinned for manual review.

The two Claude workflows authenticate via `CLAUDE_CODE_OAUTH_TOKEN`, generated by running `/install-github-app` inside a Claude Code session. Usage bills against a Claude Pro/Max subscription, not the Anthropic API console.

## Project Structure

```text
src/hypersussy/
    __main__.py
    cli.py
    config.py
    orchestrator.py
    models.py
    rate_limiter.py

    alerts/
        manager.py
        sinks/log_sink.py

    api/
        server.py
        ws.py
        candle_service.py
        routes/

    app/
        runner.py
        state.py
        db_reader.py
        actions.py
        navigation.py
        sink.py

    engines/
        oi_concentration.py
        whale_tracker.py
        whale_discovery.py
        position_tracker.py
        position_census.py
        twap_detector.py
        pre_move.py
        funding_anomaly.py
        liquidation_risk.py

    exchange/
        hyperliquid/
            client.py
            websocket.py
            parsers.py

    storage/
        sqlite.py
        schema.sql

frontend/
    src/
        components/
        pages/
        api/
        stores/

tests/
```

## License

Private.
