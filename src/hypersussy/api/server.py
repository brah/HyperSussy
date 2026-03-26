"""FastAPI application factory and lifespan for the HyperSussy API.

Single-process design: uvicorn runs the main event loop; BackgroundRunner
starts the orchestrator in a daemon thread sharing SharedState in-memory.
Static files from ``frontend/dist/`` are mounted at ``/`` when the
production build exists.
"""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from hypersussy.api.routes import alerts, candles, health, snapshots, trades, whales
from hypersussy.api.ws import router as ws_router
from hypersussy.config import HyperSussySettings
from hypersussy.app.actions import DashboardActions
from hypersussy.app.db_reader import DashboardReader
from hypersussy.app.runner import BackgroundRunner
from hypersussy.app.state import SharedState


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Start BackgroundRunner on startup; stop and close on shutdown."""
    settings = HyperSussySettings()

    db_dir = os.path.dirname(settings.db_path)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)

    state = SharedState()
    runner = BackgroundRunner(settings=settings, shared_state=state)
    runner.start()

    reader = DashboardReader(db_path=settings.db_path)
    actions = DashboardActions(db_path=settings.db_path)

    app.state.shared = state
    app.state.reader = reader
    app.state.actions = actions
    app.state.runner = runner

    yield

    runner.stop()
    reader.close()
    actions.close()


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
    app.include_router(ws_router)

    # Serve SPA in production when frontend/dist is present
    _frontend_dist = os.path.join(
        os.path.dirname(__file__), "..", "..", "..", "..", "frontend", "dist"
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
