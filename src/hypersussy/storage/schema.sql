-- HyperSussy storage schema (SQLite)

CREATE TABLE IF NOT EXISTS asset_snapshots (
    coin            TEXT    NOT NULL,
    timestamp_ms    INTEGER NOT NULL,
    open_interest   REAL    NOT NULL,
    open_interest_usd REAL  NOT NULL,
    mark_price      REAL    NOT NULL,
    oracle_price    REAL    NOT NULL,
    funding_rate    REAL    NOT NULL,
    premium         REAL    NOT NULL,
    day_volume_usd  REAL    NOT NULL,
    mid_price       REAL,
    PRIMARY KEY (coin, timestamp_ms)
);

CREATE TABLE IF NOT EXISTS trades (
    tid             INTEGER PRIMARY KEY,
    coin            TEXT    NOT NULL,
    price           REAL    NOT NULL,
    size            REAL    NOT NULL,
    side            TEXT    NOT NULL,
    timestamp_ms    INTEGER NOT NULL,
    buyer           TEXT    NOT NULL DEFAULT '',
    seller          TEXT    NOT NULL DEFAULT '',
    tx_hash         TEXT    NOT NULL DEFAULT '',
    exchange        TEXT    NOT NULL DEFAULT 'hyperliquid'
);

CREATE INDEX IF NOT EXISTS idx_trades_coin_ts
    ON trades (coin, timestamp_ms);

-- Note: idx_trades_buyer_ts and idx_trades_seller_ts used to exist
-- here to serve /api/trades/by-address. That endpoint was removed
-- (wallet fills are served by PnlService via the HL API instead)
-- and the two indexes cost ~2 GB combined on a live 3 M-trades/day
-- database for zero read benefit. Existing DBs get these dropped on
-- startup by SqliteStorage.init().

CREATE TABLE IF NOT EXISTS tracked_addresses (
    address         TEXT    PRIMARY KEY,
    label           TEXT    NOT NULL DEFAULT '',
    source          TEXT    NOT NULL DEFAULT 'discovered',
    first_seen_ms   INTEGER NOT NULL,
    total_volume_usd REAL   NOT NULL DEFAULT 0.0,
    last_active_ms  INTEGER NOT NULL,
    is_manual       INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS address_positions (
    address         TEXT    NOT NULL,
    coin            TEXT    NOT NULL,
    timestamp_ms    INTEGER NOT NULL,
    size            REAL    NOT NULL,
    entry_price     REAL    NOT NULL,
    notional_usd    REAL    NOT NULL,
    unrealized_pnl  REAL    NOT NULL,
    leverage_value  INTEGER NOT NULL DEFAULT 1,
    leverage_type   TEXT    NOT NULL DEFAULT 'cross',
    liquidation_price REAL,
    mark_price      REAL    NOT NULL DEFAULT 0.0,
    margin_used     REAL    NOT NULL DEFAULT 0.0,
    PRIMARY KEY (address, coin, timestamp_ms)
);

-- The PRIMARY KEY leads with `address`, so it can't satisfy the
-- "latest position per address for one coin" query used by the
-- /api/whales/top/{coin} endpoint. Without this index that query
-- full-scans address_positions and is the dominant source of latency
-- on coin changes for tracked coins with many holders.
CREATE INDEX IF NOT EXISTS idx_address_positions_coin_ts
    ON address_positions (coin, timestamp_ms);

CREATE TABLE IF NOT EXISTS alerts (
    alert_id        TEXT    PRIMARY KEY,
    alert_type      TEXT    NOT NULL,
    severity        TEXT    NOT NULL,
    coin            TEXT    NOT NULL,
    title           TEXT    NOT NULL,
    description     TEXT    NOT NULL,
    timestamp_ms    INTEGER NOT NULL,
    metadata_json   BLOB,
    exchange        TEXT    NOT NULL DEFAULT 'hyperliquid',
    dispatched      INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_alerts_type_coin_ts
    ON alerts (alert_type, coin, timestamp_ms);

CREATE INDEX IF NOT EXISTS idx_alerts_metadata_address
    ON alerts (json_extract(metadata_json, '$.address'), timestamp_ms);

CREATE TABLE IF NOT EXISTS candles (
    coin            TEXT    NOT NULL,
    interval_str    TEXT    NOT NULL,
    timestamp_ms    INTEGER NOT NULL,
    open            REAL    NOT NULL,
    high            REAL    NOT NULL,
    low             REAL    NOT NULL,
    close           REAL    NOT NULL,
    volume          REAL    NOT NULL,
    num_trades      INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (coin, interval_str, timestamp_ms)
);

-- Persisted overrides layered on top of HyperSussySettings defaults
-- at application startup. Values are JSON-serialised so a single TEXT
-- column can hold ints, floats, and bools uniformly. Only fields in
-- the settings-service hot-field registry are accepted here; anything
-- else would be silently ignored on load.
CREATE TABLE IF NOT EXISTS settings_overrides (
    key         TEXT    PRIMARY KEY,
    value       TEXT    NOT NULL,
    updated_ms  INTEGER NOT NULL
);
