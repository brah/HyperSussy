import type { AlertItem, AlertSummaryItem } from "../../api/types";
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

export function AlertFeed({ alerts, maxRows = 50 }: AlertFeedProps) {
  const displayed = alerts.slice(0, maxRows);
  if (displayed.length === 0) {
    return (
      <p className="text-[#4a4e69] text-sm py-4 text-center">No alerts yet.</p>
    );
  }
  return (
    <div className="divide-y divide-[#2a2d35]">
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
            <span className="text-[#4a4e69] text-xs">{alert.coin}</span>
            <span className="text-[#4a4e69] text-xs ml-auto">
              {fmtDatetime(alert.timestamp_ms)}
            </span>
          </div>
          <p className="text-[#fafafa] text-sm">{alert.title}</p>
          {isAlertItem(alert) && alert.description && (
            <p className="text-[#4a4e69] text-xs mt-0.5 line-clamp-2">
              {alert.description}
            </p>
          )}
        </div>
      ))}
    </div>
  );
}
