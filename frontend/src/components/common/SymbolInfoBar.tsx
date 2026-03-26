import { useWsStore } from "../../api/websocket";
import { formatPrice, formatUSD, formatFundingRate } from "../../utils/format";
import { colors } from "../../theme/colors";

/** Live symbol stats bar sourced from the WebSocket snapshot store. */
export function SymbolInfoBar({ coin }: Readonly<{ coin: string }>) {
  const snapshot = useWsStore((s) => s.snapshots[coin]);
  if (!snapshot) return null;

  const fundingColor =
    snapshot.funding_rate >= 0 ? colors.teal : colors.red;
  const premiumColor = snapshot.premium >= 0 ? colors.teal : colors.red;

  const items: { label: string; value: string; color?: string }[] = [
    { label: "Mark", value: formatPrice(snapshot.mark_price) },
    { label: "24h Vol", value: formatUSD(snapshot.day_volume_usd) },
    { label: "OI", value: formatUSD(snapshot.open_interest_usd) },
    { label: "Funding", value: formatFundingRate(snapshot.funding_rate), color: fundingColor },
    { label: "Premium", value: formatFundingRate(snapshot.premium), color: premiumColor },
  ];

  return (
    <div className="flex flex-wrap items-center gap-x-5 gap-y-1 px-1 py-2 text-sm">
      <span className="text-hs-text font-semibold text-base">{coin}</span>
      {items.map((it) => (
        <span key={it.label} className="flex items-center gap-1">
          <span className="text-hs-grey">{it.label}</span>
          <span
            className="tabular-nums font-medium"
            style={{ color: it.color ?? colors.text }}
          >
            {it.value}
          </span>
        </span>
      ))}
    </div>
  );
}
