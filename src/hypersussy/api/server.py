"""FastAPI application factory and lifespan for the HyperSussy API.

Single-process design: uvicorn runs the main event loop; BackgroundRunner
starts the orchestrator in a daemon thread sharing SharedState in-memory.
Static files from ``frontend/dist/`` are mounted at ``/`` when the
production build exists.
"""

from __future__ import annotations

import logging
import os
import time
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from hypersussy.api.candle_service import CandleService
from hypersussy.api.pnl_service import PnlService
from hypersussy.api.routes import (
    alerts,
    candles,
    health,
    snapshots,
    stats,
    trades,
    whales,
)
from hypersussy.api.routes import (
    config as config_route,
)
from hypersussy.api.settings_service import apply_persisted_overrides
from hypersussy.api.spot_service import SpotService
from hypersussy.api.ws import router as ws_router
from hypersussy.app.actions import DashboardActions
from hypersussy.app.db_reader import DashboardReader
from hypersussy.app.runner import BackgroundRunner
from hypersussy.app.state import SharedState
from hypersussy.config import HyperSussySettings
from hypersussy.logging_utils import LogFloodGuard
from hypersussy.storage.sqlite import SqliteStorage

logger = logging.getLogger(__name__)

# Requests slower than this get logged at WARNING. Tune in one place.
SLOW_REQUEST_THRESHOLD_S = 0.25

# One slow-request WARNING per endpoint per minute — without this a
# flaky downstream at the wrong moment can bury the log in thousands
# of identical lines, drowning any useful signal alongside them.
_slow_request_guard = LogFloodGuard(window_s=60.0)


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Start BackgroundRunner on startup; stop and close on shutdown."""
    settings = HyperSussySettings()

    db_dir = os.path.dirname(settings.db_path)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)

    state = SharedState()

    # Open the async storage handle *first* so its ``init()`` creates
    # the file + schema before the read-only DashboardReader tries to
    # connect (read-only mode fails on a missing file). An earlier
    # version of this block ran schema creation three times — once
    # synchronously via a helper, then again here via aiosqlite, then
    # a third time inside the background runner. The runner's init
    # is idempotent so that third call is cheap; trimming this down
    # to two runs (one sync path via aiosqlite here, one runner-side
    # for the runner's own connection).
    config_storage = SqliteStorage(db_path=settings.db_path)
    await config_storage.init()

    reader = DashboardReader(db_path=settings.db_path)
    actions = DashboardActions(db_path=settings.db_path)

    # Apply any persisted config overrides on top of env/defaults
    # before anything downstream reads from the settings instance.
    # BackgroundRunner, CandleService, PnlService, SpotService all
    # receive the same mutable instance, so a subsequent PUT to
    # /api/config/{key} propagates without re-wiring.
    apply_persisted_overrides(settings, reader.get_settings_overrides())
    candle_service = CandleService(
        base_url=settings.hl_api_url,
        db_path=settings.db_path,
        rate_limit_weight=settings.candle_rate_limit_weight,
        window_seconds=settings.rate_limit_window_s,
    )
    await candle_service.init()
    pnl_service = PnlService(base_url=settings.hl_api_url)
    spot_service = SpotService(base_url=settings.hl_api_url)
    runner = BackgroundRunner(settings=settings, shared_state=state)

    app.state.shared = state
    app.state.settings = settings
    app.state.reader = reader
    app.state.actions = actions
    app.state.runner = runner
    app.state.candle_service = candle_service
    app.state.pnl_service = pnl_service
    app.state.spot_service = spot_service
    app.state.config_storage = config_storage
    runner.start()

    yield

    runner.stop()
    await candle_service.close()
    await config_storage.close()
    reader.close()
    actions.close()


async def _static_cache_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    """Add long-lived cache headers to content-hashed static assets.

    Vite writes all JS/CSS/font chunks under ``/assets/`` with a content hash
    in the filename (e.g. ``vendor-react-_O6PI0e7.js``).  Because the hash
    changes whenever the content changes, these files are safe to cache
    forever.  ``index.html`` is intentionally excluded — it must stay fresh so
    that browsers pick up new chunk filenames after a deploy.
    """
    response = await call_next(request)
    if request.url.path.startswith("/assets/"):
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    elif request.url.path in ("/", "/index.html"):
        response.headers["Cache-Control"] = "no-cache, must-revalidate"
    return response


async def _timing_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    """Always-on per-request timing log.

    Logs every request at DEBUG with its wall time, and emits a WARNING
    for anything slower than ``SLOW_REQUEST_THRESHOLD_S``. WebSocket
    upgrades and the static SPA are excluded — they don't go through this
    middleware path anyway, but the path-prefix check keeps the log noise
    on real API traffic only.
    """
    is_api = request.url.path.startswith("/api/")
    if not is_api:
        return await call_next(request)

    started = time.perf_counter()
    response = await call_next(request)
    elapsed = time.perf_counter() - started

    if elapsed >= SLOW_REQUEST_THRESHOLD_S:
        _slow_request_guard.log(
            logger,
            logging.WARNING,
            f"slow_request:{request.method}:{request.url.path}",
            "slow_request method=%s path=%s status=%d duration_ms=%d",
            request.method,
            request.url.path,
            response.status_code,
            int(elapsed * 1000),
        )
    else:
        logger.debug(
            "request method=%s path=%s status=%d duration_ms=%d",
            request.method,
            request.url.path,
            response.status_code,
            int(elapsed * 1000),
        )
    return response


async def _profile_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    """Opt-in pyinstrument profiler.

    Append ``?profile=1`` to any API URL to get an interactive HTML flame
    graph back instead of the JSON response. Pyinstrument is a sampling
    profiler so the overhead when this branch is not taken is zero — the
    middleware short-circuits on the missing query param.

    Example:
        curl 'http://localhost:8000/api/whales/top/BTC?hours=24&profile=1' \\
            -o profile.html && start profile.html
    """
    if request.query_params.get("profile") != "1":
        return await call_next(request)

    try:
        from pyinstrument import Profiler
    except ImportError:
        logger.warning("pyinstrument not installed; ?profile=1 ignored")
        return await call_next(request)

    profiler = Profiler(async_mode="enabled")
    profiler.start()
    try:
        await call_next(request)
    finally:
        profiler.stop()

    return Response(
        content=profiler.output_html(),
        media_type="text/html",
    )


def create_app() -> FastAPI:
    """Construct and configure the FastAPI application.

    Returns:
        Configured FastAPI instance with all routes and middleware.
    """
    app = FastAPI(
        title="HyperSussy API",
        description="REST + WebSocket API for the HyperSussy monitoring dashboard",
        version="0.1.0",
        lifespan=_lifespan,
    )

    # Middleware execution order is last-registered = outermost.
    # _static_cache_middleware is outermost: it runs on every response and
    # adds Cache-Control headers before anything else sees the response.
    # _timing_middleware is next: times only /api/ requests.
    # _profile_middleware is innermost: opt-in ?profile=1 profiler.
    app.middleware("http")(_static_cache_middleware)
    app.middleware("http")(_timing_middleware)
    app.middleware("http")(_profile_middleware)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router, prefix="/api")
    app.include_router(snapshots.router, prefix="/api")
    app.include_router(alerts.router, prefix="/api")
    app.include_router(trades.router, prefix="/api")
    app.include_router(whales.router, prefix="/api")
    app.include_router(candles.router, prefix="/api")
    app.include_router(stats.router, prefix="/api")
    app.include_router(config_route.router, prefix="/api")
    app.include_router(ws_router)

    # Serve SPA in production when frontend/dist is present
    _frontend_dist = os.path.join(
        os.path.dirname(__file__), "..", "..", "..", "frontend", "dist"
    )
    _frontend_dist = os.path.normpath(_frontend_dist)
    if os.path.isdir(_frontend_dist):
        app.mount(
            "/",
            StaticFiles(directory=_frontend_dist, html=True),
            name="static",
        )

    return app


app = create_app()
