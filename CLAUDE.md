# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Build & Run Commands

### Python Backend

```bash
uv sync                      # Install core deps
uv sync --extra dev          # Install dev deps (pytest, mypy, ruff, fastapi, uvicorn)
uv sync --extra api          # Install API deps only
uv run hypersussy            # Headless monitoring
uv run hypersussy --api      # FastAPI server + background orchestrator (port 8000)
```

### Frontend (React)

```bash
cd frontend
npm install
npm run dev                  # Vite dev server on :5173, proxies /api to :8000
npm run build                # tsc -b && vite build → frontend/dist/
npm run typecheck            # tsc --noEmit
npm run lint                 # eslint src
```

When `frontend/dist/` exists, the FastAPI server serves it at `/`.

### Testing & Quality

```bash
uv run pytest -v                                          # All tests
uv run pytest tests/engines/test_oi_concentration.py -v   # Single file
uv run pytest tests/alerts/test_manager.py::test_name     # Single test
uv run mypy src                                           # Type check (strict mode)
uv run ruff check src tests                               # Lint
uv run ruff format src tests                              # Format
```

Pytest uses `asyncio_mode = "auto"` — async test functions are detected automatically.

## Architecture

### Data Flow

```text
Hyperliquid API (REST + WebSocket)
    → Orchestrator (event loop)
        → Storage (SQLite via aiosqlite)
        → Detection Engines (5 engines, each implements DetectionEngine protocol)
            → AlertManager (dedup → throttle → persist → dispatch to sinks)
        → SharedState (thread-safe in-memory bus for live UI data)
    → FastAPI (/api/* REST + /ws/live WebSocket)
    → React Dashboard (TanStack Query + Zustand WS store)
```

### Orchestrator (`orchestrator.py`)

Runs concurrent async loops: REST polling, WebSocket streams (asset context + trades + positions), periodic engine ticks, and dynamic coin universe refresh. Engines are instantiated in `cli.py:_build_components()` based on settings toggles and passed as a list to the Orchestrator constructor.

**DetectionEngine protocol**: engines implement `tick()`, `on_trade()`, and `on_asset_update()`, each returning `list[Alert]`. The orchestrator dispatches alerts through the AlertManager.

### Alert Pipeline (`alerts/manager.py`)

Alerts go through: fingerprint-based dedup (cooldown window per alert_type+coin+address) → global rate limit (max N per minute) → SQLite persist → async dispatch to all sinks. Fingerprint keys include `alert_type`, `coin`, and optional metadata fields (`address`, `twap_id`, `direction`).

### Single-Process API Mode

`hypersussy --api` starts FastAPI with a lifespan that launches a `BackgroundRunner` (daemon thread running the Orchestrator). All components share a `SharedState` instance attached to `app.state`. The WebSocket endpoint (`/ws/live`) polls SharedState every 2s and pushes snapshots, alerts, and health.

### Frontend State

- **Zustand store** (`api/websocket.ts`): holds live snapshots, alerts, health from WebSocket. Auto-reconnects with exponential backoff.
- **TanStack React Query** (`api/queries.ts`): manages all REST data fetching with stale times (5s–30s) and refetch intervals.
- **Panel visibility** (`stores/panelStore.ts`): persisted to localStorage, each panel subscribes independently.

### Configuration (`config.py`)

`HyperSussySettings` extends Pydantic `BaseSettings` with env prefix `HYPERSUSSY_`. All 60+ settings are overridable via environment variables (e.g., `HYPERSUSSY_DB_PATH`, `HYPERSUSSY_ENGINE_WHALE_TRACKER=false`).

### Frontend Design System

The dashboard uses a Wise-inspired light theme defined in `DESIGN.md`. Key conventions:

- **Color tokens** defined in `index.css` `@theme` block and mirrored in `theme/colors.ts`
- **Brand accent** (`hs-green` / `#9fe870`): buttons, active nav, toggles only — never as text on white (fails WCAG)
- **Semantic positive** (`hs-teal` / `#054d28`): long positions, +PnL, +funding rate
- **Semantic negative** (`hs-red` / `#d03238`): short positions, -PnL, danger
- Pill-shaped buttons (`rounded-full`) with `wise-interactive` class for scale(1.05) hover
- Cards use `rounded-2xl` (16px) with `border-hs-grid`
- LogModal is the sole dark-themed component (hardcoded terminal colors)

## Code Conventions

### Python

- Python >=3.13, line length 88 (ruff)
- All models are frozen dataclasses with `slots=True`
- Use `orjson` for JSON, `structlog` for logging, `logger.error()` not `print()`
- Type hints on all signatures; `mypy --strict`
- Docstrings (Google-style Args/Returns/Raises) on all public functions
- No emoji or unicode emoji-equivalents in code
- No mutable default arguments; use `field(default_factory=...)`
- Tests use pytest with in-memory SQLite fixtures from `conftest.py`
- Never delete test output files; ensure test output dirs are in `.gitignore`

### Frontend

- React 19, TypeScript 5.7, Tailwind CSS 4, Vite 6
- Use design tokens (`hs-*` classes) — never hardcode hex values in components (exception: LogModal terminal)
- Memoize with `memo()` and `useMemo()` for chart/table components
- Zustand selectors subscribe to specific state slices to prevent unnecessary re-renders
