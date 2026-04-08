"""LRU+TTL cache keyed by wallet address.

Used by both :class:`hypersussy.api.pnl_service.PnlService` and
:class:`hypersussy.api.spot_service.SpotService` to bound the
per-process address cache so long-running sessions that search many
distinct wallets cannot leak memory.

The cache is intentionally synchronous and *not* thread-safe — it is
expected to be touched only from a single asyncio event loop.
"""

from __future__ import annotations

import time
from collections import OrderedDict
from dataclasses import dataclass


@dataclass(slots=True)
class _Entry[T]:
    value: T
    expires_at: float


class TtlAddressCache[T]:
    """OrderedDict-backed LRU cache with per-entry TTL and a hard cap.

    Both :class:`PnlService` and :class:`SpotService` previously
    duplicated this exact pattern. Hoisting it here removes ~50 lines
    of byte-identical code and gives a single place to evolve the
    eviction policy.

    Args:
        ttl_seconds: How long an entry stays valid after it is put.
            Compared against ``time.monotonic()``.
        max_entries: Hard cap on retained entries. When exceeded, the
            least-recently-used entry is evicted.
    """

    __slots__ = ("_cache", "_max_entries", "_ttl_seconds")

    def __init__(self, ttl_seconds: float, max_entries: int) -> None:
        self._ttl_seconds = ttl_seconds
        self._max_entries = max_entries
        self._cache: OrderedDict[str, _Entry[T]] = OrderedDict()

    def get(self, address: str) -> T | None:
        """Return a fresh cached value for ``address`` or ``None``.

        A cache hit moves the entry to the most-recently-used position.
        Stale entries are not eagerly deleted on read — they are
        cleaned up by :meth:`put` on the next insert.

        Args:
            address: Wallet address key.

        Returns:
            The cached value, or ``None`` on miss or stale entry.
        """
        entry = self._cache.get(address)
        if entry is None:
            return None
        if time.monotonic() >= entry.expires_at:
            return None
        self._cache.move_to_end(address)
        return entry.value

    def put(self, address: str, value: T) -> None:
        """Insert or refresh ``value`` and run eviction.

        Args:
            address: Wallet address key.
            value: Value to cache.
        """
        now = time.monotonic()
        self._cache[address] = _Entry(value=value, expires_at=now + self._ttl_seconds)
        self._cache.move_to_end(address)
        self._evict(now)

    def _evict(self, now: float) -> None:
        """Drop expired entries, then LRU-evict until under the hard cap.

        Amortised O(1) per :meth:`put` because the expired sweep
        usually finds nothing on hot-path workloads.

        Args:
            now: Current monotonic time, threaded through to avoid a
                second ``time.monotonic()`` call.
        """
        expired = [
            key for key, entry in self._cache.items() if entry.expires_at <= now
        ]
        for key in expired:
            del self._cache[key]
        while len(self._cache) > self._max_entries:
            self._cache.popitem(last=False)

    def __len__(self) -> int:
        return len(self._cache)
