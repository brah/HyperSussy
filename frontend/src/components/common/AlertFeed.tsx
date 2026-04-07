import { memo } from "react";
import { Link } from "react-router-dom";
import type { AlertItem, AlertSummaryItem } from "../../api/types";
import { AddressLink } from "./AddressLink";
import { severityColor } from "../../theme/colors";
import { fmtDatetime } from "../../utils/time";

type AnyAlert = AlertItem | AlertSummaryItem;

interface AlertFeedProps {
  alerts: AnyAlert[];
  maxRows?: number;
}

function isAlertItem(a: AnyAlert): a is AlertItem {
  return "alert_id" in a;
}

export const AlertFeed = memo(function AlertFeed({ alerts, maxRows = 50 }: Readonly<AlertFeedProps>) {
  const displayed = alerts.slice(0, maxRows);
  if (displayed.length === 0) {
    return (
      <p className="py-4 text-center text-sm text-hs-grey">No alerts yet.</p>
    );
  }
  return (
    <div className="divide-y divide-hs-grid">
      {displayed.map((alert, idx) => (
        <div key={isAlertItem(alert) ? alert.alert_id : idx} className="py-2">
          <div className="flex items-center gap-2 mb-0.5">
            <span
              className="text-xs font-semibold uppercase px-1.5 py-0.5 rounded"
              style={{
                color: severityColor(alert.severity),
                border: `1px solid ${severityColor(alert.severity)}`,
              }}
            >
              {alert.severity}
            </span>
            <Link
              to={`/?coin=${alert.coin}`}
              className="text-xs font-medium text-hs-teal hover:underline"
            >
              {alert.coin}
            </Link>
            <span className="ml-auto text-xs text-hs-grey">
              {fmtDatetime(alert.timestamp_ms)}
            </span>
          </div>
          <p className="text-sm text-hs-text">{alert.title}</p>
          {isAlertItem(alert) && alert.description && (
            <p className="mt-0.5 line-clamp-2 text-xs text-hs-grey">
              {alert.description}
            </p>
          )}
          {isAlertItem(alert) && alert.address && (
            <div className="mt-0.5">
              <AddressLink address={alert.address} />
            </div>
          )}
        </div>
      ))}
    </div>
  );
});
