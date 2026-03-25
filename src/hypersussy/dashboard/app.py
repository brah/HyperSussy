"""Streamlit entry point for the HyperSussy dashboard.

Run via:
    hypersussy --streamlit
    streamlit run src/hypersussy/dashboard/app.py
"""

from __future__ import annotations

import streamlit as st

from hypersussy.config import HyperSussySettings
from hypersussy.dashboard.db_reader import DashboardReader
from hypersussy.dashboard.runner import BackgroundRunner
from hypersussy.dashboard.state import SharedState


@st.cache_resource
def _get_state() -> SharedState:
    """Instantiate SharedState exactly once per server process."""
    return SharedState()


@st.cache_resource
def _get_runner(_state: SharedState) -> BackgroundRunner:
    """Start the orchestrator in a background thread, once per process.

    Args:
        _state: SharedState — passed as argument so the cache key includes it,
            ensuring the runner is bound to this state instance.

    Returns:
        A started BackgroundRunner.
    """
    settings = HyperSussySettings()
    runner = BackgroundRunner(settings=settings, shared_state=_state)
    runner.start()
    return runner


@st.cache_resource
def _get_db_reader() -> DashboardReader:
    """Open the read-only SQLite connection once per process."""
    settings = HyperSussySettings()
    return DashboardReader(db_path=settings.db_path)


def main() -> None:
    """Streamlit application entry point."""
    st.set_page_config(
        page_title="HyperSussy",
        page_icon=":chart_with_upwards_trend:",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    state = _get_state()
    _get_runner(state)  # idempotent start
    db_reader = _get_db_reader()

    # Sidebar navigation
    st.sidebar.title("HyperSussy")
    page = st.sidebar.radio(
        "Page",
        options=["Overview", "Alerts", "Whale Tracker", "Charts"],
    )
    refresh_s = int(
        st.sidebar.select_slider(
            "Auto-refresh (s)",
            options=[5, 10, 30, 60],
            value=10,
        )
    )

    if page == "Overview":
        from hypersussy.dashboard._pages.overview import render_overview

        render_overview(state, db_reader, refresh_s)
    elif page == "Alerts":
        from hypersussy.dashboard._pages.alerts import render_alerts

        render_alerts(db_reader, refresh_s)
    elif page == "Whale Tracker":
        from hypersussy.dashboard._pages.whale_tracker import render_whale_tracker

        render_whale_tracker(db_reader, refresh_s)
    elif page == "Charts":
        from hypersussy.dashboard._pages.charts import render_charts

        render_charts(db_reader)


if __name__ == "__main__":
    main()
