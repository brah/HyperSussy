"""FastAPI dependency factories for shared application state.

All dependencies read from ``app.state`` which is populated during the
lifespan context in ``server.py``.  Route handlers declare deps via
``Annotated[T, Depends(fn)]`` aliases defined at the bottom of this module.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from hypersussy.app.actions import DashboardActions
from hypersussy.app.db_reader import DashboardReader
from hypersussy.app.state import SharedState


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


ReaderDep = Annotated[DashboardReader, Depends(get_reader)]
ActionsDep = Annotated[DashboardActions, Depends(get_actions)]
StateDep = Annotated[SharedState, Depends(get_state)]
