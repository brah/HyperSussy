"""GET /api/stats/* — local storage and Hyperliquid coverage metrics."""

from __future__ import annotations

import os

from fastapi import APIRouter

from hypersussy.api.deps import ReaderDep, StateDep
from hypersussy.api.schemas import StorageStatsResponse
from hypersussy.config import HyperSussySettings

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("/storage")
def get_storage_stats(
    reader: ReaderDep,
    state: StateDep,
) -> StorageStatsResponse:
    """Return SQLite row counts, file size, and HL perp coverage.

    The reader query is cached in-process for 60 seconds; the SQLite
    file-size lookup and the in-memory snapshot count are cheap and
    re-evaluated on every call.

    Args:
        reader: Injected DashboardReader.
        state: Injected SharedState.

    Returns:
        StorageStatsResponse with row counts, file size, and coverage.
    """
    settings = HyperSussySettings()
    stats = reader.get_storage_stats()

    db_size = (
        os.path.getsize(settings.db_path)
        if os.path.exists(settings.db_path)
        else 0
    )

    # Coverage is the intersection of "coins HL currently lists" (live
    # snapshots in SharedState) and "coins we have historical data
    # for" (distinct_coins from the DB). Computing from the
    # intersection bounds the ratio at 100% regardless of delisted
    # coins lingering in the historical table or a just-started runner
    # that hasn't fully repopulated its live set yet.
    live_coins = frozenset(state.get_snapshots().keys())
    universe = len(live_coins)
    covered = len(stats.distinct_coins & live_coins)
    coverage = (covered / universe * 100.0) if universe > 0 else 0.0

    return StorageStatsResponse(
        db_size_bytes=db_size,
        asset_snapshots_rows=stats.asset_snapshots_rows,
        trades_rows=stats.trades_rows,
        address_positions_rows=stats.address_positions_rows,
        alerts_rows=stats.alerts_rows,
        candles_rows=stats.candles_rows,
        tracked_addresses_rows=stats.tracked_addresses_rows,
        coins_covered=covered,
        distinct_addresses_positioned=stats.distinct_addresses_positioned,
        distinct_addresses_traded=stats.distinct_addresses_traded,
        perp_universe_count=universe,
        perp_coverage_pct=coverage,
    )
