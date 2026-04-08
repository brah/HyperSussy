"""FastAPI dependency factories for shared application state.

All dependencies read from ``app.state`` which is populated during the
lifespan context in ``server.py``.  Route handlers declare deps via
``Annotated[T, Depends(fn)]`` aliases defined at the bottom of this module.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from hypersussy.api.candle_service import CandleService
from hypersussy.api.pnl_service import PnlService
from hypersussy.api.spot_service import SpotService
from hypersussy.app.actions import DashboardActions
from hypersussy.app.db_reader import DashboardReader
from hypersussy.app.state import SharedState
from hypersussy.config import HyperSussySettings
from hypersussy.storage.sqlite import SqliteStorage


def get_reader(request: Request) -> DashboardReader:
    """Return the application-scoped read-only DB reader."""
    reader: DashboardReader = request.app.state.reader
    return reader


def get_actions(request: Request) -> DashboardActions:
    """Return the application-scoped writable DB actions."""
    actions: DashboardActions = request.app.state.actions
    return actions


def get_state(request: Request) -> SharedState:
    """Return the application-scoped shared live state."""
    state: SharedState = request.app.state.shared
    return state


def get_candle_service(request: Request) -> CandleService:
    """Return the application-scoped candle fetch-through service."""
    service: CandleService = request.app.state.candle_service
    return service


def get_pnl_service(request: Request) -> PnlService:
    """Return the application-scoped PnL service."""
    service: PnlService = request.app.state.pnl_service
    return service


def get_spot_service(request: Request) -> SpotService:
    """Return the application-scoped spot/account service."""
    service: SpotService = request.app.state.spot_service
    return service


def get_settings(request: Request) -> HyperSussySettings:
    """Return the application-scoped live settings instance.

    This is the same object the BackgroundRunner and downstream
    services hold, so in-place mutation via the config routes
    propagates to every consumer without re-wiring.
    """
    settings: HyperSussySettings = request.app.state.settings
    return settings


def get_config_storage(request: Request) -> SqliteStorage:
    """Return the API-scoped async storage handle for config writes.

    Separate from the BackgroundRunner's own storage so API request
    threads don't touch the runner's aiosqlite connection.
    """
    storage: SqliteStorage = request.app.state.config_storage
    return storage


ReaderDep = Annotated[DashboardReader, Depends(get_reader)]
ActionsDep = Annotated[DashboardActions, Depends(get_actions)]
StateDep = Annotated[SharedState, Depends(get_state)]
CandleServiceDep = Annotated[CandleService, Depends(get_candle_service)]
PnlServiceDep = Annotated[PnlService, Depends(get_pnl_service)]
SpotServiceDep = Annotated[SpotService, Depends(get_spot_service)]
SettingsDep = Annotated[HyperSussySettings, Depends(get_settings)]
ConfigStorageDep = Annotated[SqliteStorage, Depends(get_config_storage)]
