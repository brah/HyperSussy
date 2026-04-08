/** TypeScript types matching the FastAPI Pydantic schemas. */

export interface LiveSnapshot {
  coin: string;
  mark_price: number;
  open_interest_usd: number;
  funding_rate: number;
  premium: number;
  day_volume_usd: number;
  timestamp_ms: number;
}

export interface RuntimeIssueItem {
  source: string;
  message: string;
  timestamp_ms: number;
}

export interface HealthResponse {
  is_running: boolean;
  snapshot_count: number;
  last_snapshot_ms: number | null;
  last_alert_ms: number | null;
  engine_errors: RuntimeIssueItem[];
  runtime_errors: RuntimeIssueItem[];
}

export interface AlertItem {
  alert_id: string;
  alert_type: string;
  severity: string;
  coin: string;
  title: string;
  description: string;
  timestamp_ms: number;
  exchange: string;
  address: string | null;
}

export interface AlertSummaryItem {
  alert_type: string;
  severity: string;
  coin: string;
  title: string;
  timestamp_ms: number;
}

export interface OISnapshotItem {
  timestamp_ms: number;
  open_interest_usd: number;
  mark_price: number;
  funding_rate: number;
}

export interface FundingSnapshotItem {
  timestamp_ms: number;
  funding_rate: number;
  premium: number;
  mark_price: number;
  oracle_price: number;
}

export interface TopWhaleItem {
  address: string;
  volume_usd: number;
}

export interface TopHolderItem {
  address: string;
  volume_usd: number;
  total_volume: number;
}

export interface TradeFlowItem {
  bucket: number;
  side: string;
  volume_usd: number;
}

export interface TrackedAddressItem {
  address: string;
  label: string | null;
  total_volume_usd: number;
  last_active_ms: number | null;
  source: string;
}

export interface PositionItem {
  coin: string;
  size: number;
  notional_usd: number;
  unrealized_pnl: number;
  liquidation_price: number | null;
  mark_price: number;
  timestamp_ms: number;
}

export interface CoinPositionItem {
  address: string;
  coin: string;
  size: number;
  entry_price: number | null;
  notional_usd: number;
  unrealized_pnl: number;
  leverage_value: number | null;
  leverage_type: string | null;
  liquidation_price: number | null;
  mark_price: number;
  margin_used: number | null;
  timestamp_ms: number;
}

export interface CandleItem {
  timestamp_ms: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  num_trades: number;
}

export interface FillItem {
  coin: string;
  side: string;
  dir: string;
  px: number;
  sz: number;
  closed_pnl: number;
  start_position: number;
  oid: number;
  hash: string;
  time: number;
  crossed: boolean;
}

export interface FillPageResponse {
  fills: FillItem[];
  next_cursor: number | null;
}

export interface RealizedPnlResponse {
  pnl_7d: number;
  pnl_all_time: number;
  fills_7d: number;
  fills_all_time: number;
  is_complete_7d: boolean;
  is_complete_all_time: boolean;
}

export interface SpotAssetItem {
  coin: string;
  total: number;
  hold: number;
  entry_ntl: number;
}

export interface WalletAccountResponse {
  account_value: number;
  withdrawable: number;
  total_margin_used: number;
  total_ntl_pos: number;
  spot: SpotAssetItem[];
}

export interface ConfigFieldItem {
  key: string;
  section: string;
  label: string;
  description: string;
  type: "int" | "float" | "bool";
  value: number | boolean;
  default: number | boolean;
  overridden: boolean;
  minimum: number | null;
  maximum: number | null;
}

export interface ConfigResponse {
  fields: ConfigFieldItem[];
}

export interface StorageStatsResponse {
  db_size_bytes: number;
  asset_snapshots_rows: number;
  trades_rows: number;
  address_positions_rows: number;
  alerts_rows: number;
  candles_rows: number;
  tracked_addresses_rows: number;
  coins_covered: number;
  distinct_addresses_positioned: number;
  distinct_addresses_traded: number;
  perp_universe_count: number;
  perp_coverage_pct: number;
}

export type WsMessage =
  | { type: "snapshots"; data: Record<string, LiveSnapshot>; timestamp_ms: number }
  | { type: "alert"; data: AlertItem; timestamp_ms: number }
  | { type: "health"; data: HealthResponse; timestamp_ms: number };
