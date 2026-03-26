"""Shared Streamlit UI components for the dashboard."""

from __future__ import annotations

import time
from collections.abc import Sequence

import polars as pl
import streamlit as st

from hypersussy.dashboard.state import RuntimeHealth
from hypersussy.dashboard.view_models import AlertFeedItem, MetricCardData

_SEVERITY_ICONS = {
    "critical": "CRITICAL",
    "high": "HIGH",
    "medium": "MEDIUM",
    "low": "LOW",
}


def apply_dashboard_theme() -> None:
    """Inject the dashboard's shared CSS chrome."""
    st.markdown(
        """
        <style>
        .block-container {
            padding-top: 1.4rem;
            padding-bottom: 2rem;
        }
        div[data-testid="stMetric"] {
            background: linear-gradient(180deg, rgba(14,17,23,0.96), rgba(20,26,34,0.96));
            border: 1px solid rgba(0, 212, 170, 0.18);
            border-radius: 16px;
            padding: 0.65rem 0.85rem;
        }
        div[data-testid="stMetricLabel"] {
            letter-spacing: 0.02em;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_page_header(title: str, subtitle: str) -> None:
    """Render a consistent page title and supporting copy."""
    st.title(title)
    st.caption(subtitle)


def render_metric_cards(metrics: Sequence[MetricCardData]) -> None:
    """Render top-line metric cards."""
    columns = st.columns(len(metrics))
    for column, metric in zip(columns, metrics, strict=True):
        column.metric(metric.label, metric.value, help=metric.help_text)


def render_status_banner(
    health: RuntimeHealth,
    freshness_message: str,
) -> None:
    """Render the high-level runner/data health banner."""
    if not health.is_running:
        st.warning("Background orchestrator is not running.")
    elif health.last_snapshot_ms is None:
        st.info("Background orchestrator is running. Waiting for first data.")
    elif health.runtime_errors or health.engine_errors:
        st.warning(f"Monitoring is live with issues. {freshness_message}")
    else:
        st.success(f"Monitoring is live. {freshness_message}")


def render_runtime_issues(health: RuntimeHealth) -> None:
    """Render runtime and engine issues when present."""
    if not health.runtime_errors and not health.engine_errors:
        return

    with st.expander("Runtime health", expanded=False):
        if health.runtime_errors:
            st.markdown("**Runtime issues**")
            for issue in health.runtime_errors:
                ts = time.strftime("%H:%M:%S", time.localtime(issue.timestamp_ms / 1000))
                st.error(f"{issue.source} at {ts}: {issue.message}")
        if health.engine_errors:
            st.markdown("**Engine issues**")
            for issue in health.engine_errors:
                ts = time.strftime("%H:%M:%S", time.localtime(issue.timestamp_ms / 1000))
                st.error(f"{issue.source} at {ts}: {issue.message}")


def render_section_header(title: str, caption: str | None = None) -> None:
    """Render a section heading with optional caption."""
    st.subheader(title)
    if caption:
        st.caption(caption)


def render_empty_state(message: str) -> None:
    """Render a consistent empty-state message."""
    st.info(message)


def render_alert_feed(
    alerts: Sequence[AlertFeedItem],
    empty_message: str,
) -> None:
    """Render the alert feed using native Streamlit containers."""
    if not alerts:
        render_empty_state(empty_message)
        return

    for alert in alerts:
        with st.container(border=True):
            headline = f"{_SEVERITY_ICONS.get(alert.severity, alert.severity.upper())} | {alert.coin}"
            if alert.alert_type:
                headline = f"{headline} | {alert.alert_type}"
            st.markdown(f"**{headline}**")
            st.write(alert.title)
            footer_parts = [
                time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(alert.timestamp_ms / 1000))
            ]
            if alert.address:
                footer_parts.append(alert.address)
            st.caption(" | ".join(footer_parts))


def render_positions_table(dataframe: pl.DataFrame) -> None:
    """Render the standard positions dataframe with shared formatting."""
    st.dataframe(
        dataframe,
        width="stretch",
        hide_index=True,
        column_config={
            "Notional (USD)": st.column_config.NumberColumn(format="$%,.0f"),
            "Unr. PnL": st.column_config.NumberColumn(format="$%+,.0f"),
        },
    )
