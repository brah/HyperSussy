"""Streamlit entry point for the HyperSussy dashboard.

Run via:
    hypersussy --streamlit
    streamlit run src/hypersussy/dashboard/app.py
"""

from __future__ import annotations

import streamlit as st

from hypersussy.config import HyperSussySettings
from hypersussy.dashboard.actions import DashboardActions
from hypersussy.dashboard.components import apply_dashboard_theme
from hypersussy.dashboard.db_reader import DashboardReader
from hypersussy.dashboard.navigation import normalize_wallet_address
from hypersussy.dashboard.runner import BackgroundRunner
from hypersussy.dashboard.state import SharedState


@st.cache_resource
def _get_state() -> SharedState:
    """Instantiate SharedState exactly once per server process."""
    return SharedState()


@st.cache_resource
def _get_runner(_state: SharedState) -> BackgroundRunner:
    """Start the orchestrator in a background thread, once per process."""
    settings = HyperSussySettings()
    runner = BackgroundRunner(settings=settings, shared_state=_state)
    runner.start()
    return runner


@st.cache_resource
def _get_db_reader() -> DashboardReader:
    """Open the read-only SQLite connection once per process."""
    settings = HyperSussySettings()
    return DashboardReader(db_path=settings.db_path)


@st.cache_resource
def _get_db_actions() -> DashboardActions:
    """Open the writable dashboard actions interface once per process."""
    settings = HyperSussySettings()
    return DashboardActions(db_path=settings.db_path)


def main() -> None:
    """Streamlit application entry point."""
    st.set_page_config(
        page_title="HyperSussy",
        page_icon=":chart_with_upwards_trend:",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    apply_dashboard_theme()

    state = _get_state()
    _get_runner(state)  # idempotent start
    db_reader = _get_db_reader()
    db_actions = _get_db_actions()

    st.sidebar.title("HyperSussy")
    health = state.get_runtime_health()
    if health.is_running:
        st.sidebar.success("Monitor online")
    else:
        st.sidebar.warning("Monitor offline")

    def _clear_wallet_params() -> None:
        st.query_params.clear()

    page = st.sidebar.radio(
        "Page",
        options=["Overview", "Alerts", "Whale Tracker", "Charts", "Klines"],
        on_change=_clear_wallet_params,
    )
    refresh_s = int(
        st.sidebar.select_slider(
            "Auto-refresh (s)",
            options=[5, 10, 30, 60],
            value=10,
        )
    )

    with st.sidebar.expander("Go to wallet"):
        addr_input = st.text_input(
            "Wallet address (0x...)",
            key="sidebar_wallet_input",
            placeholder="0x...",
        )
        if st.button("Go", key="sidebar_wallet_go"):
            addr = normalize_wallet_address(addr_input)
            if addr is not None:
                st.query_params["page"] = "wallet"
                st.query_params["address"] = addr
                st.rerun()
            else:
                st.error("Invalid address. Use a 42-character 0x hex wallet.")

    if st.query_params.get("page") == "wallet":
        from hypersussy.dashboard._pages.wallet_detail import render_wallet_detail

        render_wallet_detail(db_reader, refresh_s)
    elif page == "Overview":
        from hypersussy.dashboard._pages.overview import render_overview

        render_overview(state, db_reader, refresh_s)
    elif page == "Alerts":
        from hypersussy.dashboard._pages.alerts import render_alerts

        render_alerts(db_reader, refresh_s)
    elif page == "Whale Tracker":
        from hypersussy.dashboard._pages.whale_tracker import render_whale_tracker

        render_whale_tracker(db_reader, db_actions, refresh_s)
    elif page == "Charts":
        from hypersussy.dashboard._pages.charts import render_charts

        render_charts(db_reader)
    elif page == "Klines":
        from hypersussy.dashboard._pages.klines import render_klines

        render_klines(db_reader, refresh_s)


if __name__ == "__main__":
    main()
