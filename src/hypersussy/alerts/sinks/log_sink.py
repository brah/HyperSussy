"""Structured logging alert sink."""

from __future__ import annotations

import structlog

from hypersussy.models import Alert

logger = structlog.get_logger("hypersussy.alerts")


class LogSink:
    """Alert sink that writes structured log entries.

    Uses structlog for JSON-formatted output suitable for
    log aggregation and piping to external tools.
    """

    async def send(self, alert: Alert) -> None:
        """Log the alert as a structured event.

        Args:
            alert: The alert to log.
        """
        logger.info(
            "alert_fired",
            alert_id=alert.alert_id,
            alert_type=alert.alert_type,
            severity=alert.severity,
            coin=alert.coin,
            title=alert.title,
            description=alert.description,
            exchange=alert.exchange,
            **{k: v for k, v in alert.metadata.items() if not isinstance(v, list)},
        )
