"""Shared sliding-volume-window accumulator for engines.

Both :class:`WhaleDiscovery` and :class:`PositionCensus` used to
maintain their own per-address volume ring buffer with near-identical
add/prune/top-N code. This helper owns the common pieces:

* Rolling per-address notional total.
* Optional per-address-per-coin breakout for engines that need it
  (e.g. whale-discovery's OI-percentage promotion rule).
* Ring-of-trades so a prune at time ``t`` exactly subtracts the
  contributions that fell out of the window.

The lookback is passed to :meth:`prune` per-call rather than stored
at construction time — the orchestrator's tick callers read it from
the live settings instance so edits from the Config page take effect
without a restart.

Kept deliberately minimal — no alert generation, no storage writes.
Engines compose it; they own their own policy.
"""

from __future__ import annotations

from collections import deque


class SlidingVolumeWindow:
    """Per-address trading volume over a sliding time window.

    Args:
        track_coin_volume: When True, also maintain a per-(address,
            coin) breakdown. ``WhaleDiscovery`` needs this for its
            OI-ratio promotion; ``PositionCensus`` does not and pays
            less per trade when the flag is off.
    """

    __slots__ = (
        "_track_coin_volume",
        "_trades",
        "address_volume",
        "coin_address_volume",
    )

    def __init__(self, *, track_coin_volume: bool = False) -> None:
        self._track_coin_volume = track_coin_volume
        # (ts, buyer, seller, coin, notional). coin is empty when
        # ``track_coin_volume`` is False to avoid retaining the
        # reference for every trade.
        self._trades: deque[tuple[int, str, str, str, float]] = deque()
        self.address_volume: dict[str, float] = {}
        self.coin_address_volume: dict[tuple[str, str], float] = {}

    def add_trade(
        self,
        timestamp_ms: int,
        buyer: str,
        seller: str,
        coin: str,
        notional: float,
    ) -> None:
        """Accumulate one trade's notional on both sides of the book.

        Empty address strings are skipped — HL emits them for some
        synthetic flows. ``coin`` is retained verbatim only when the
        instance was built with ``track_coin_volume=True``.
        """
        stored_coin = coin if self._track_coin_volume else ""
        self._trades.append((timestamp_ms, buyer, seller, stored_coin, notional))
        for addr in (buyer, seller):
            if not addr:
                continue
            self.address_volume[addr] = self.address_volume.get(addr, 0.0) + notional
            if self._track_coin_volume:
                key = (addr, coin)
                self.coin_address_volume[key] = (
                    self.coin_address_volume.get(key, 0.0) + notional
                )

    def prune(self, timestamp_ms: int, lookback_ms: int) -> None:
        """Drop trades older than ``timestamp_ms - lookback_ms``.

        Each popped trade subtracts its contribution from the per-address
        totals (and per-coin totals when tracked), so the dicts stay in
        sync with the retained trades.

        Args:
            timestamp_ms: Reference timestamp (typically "now").
            lookback_ms: Window size in milliseconds. Read live from
                settings on every tick so edits via the Config page
                take effect without restarting the process.
        """
        cutoff = timestamp_ms - lookback_ms
        while self._trades and self._trades[0][0] < cutoff:
            _, buyer, seller, coin, notional = self._trades.popleft()
            for addr in (buyer, seller):
                if not addr:
                    continue
                vol = self.address_volume.get(addr, 0.0) - notional
                if vol <= 0:
                    self.address_volume.pop(addr, None)
                else:
                    self.address_volume[addr] = vol
                if self._track_coin_volume:
                    key = (addr, coin)
                    cvol = self.coin_address_volume.get(key, 0.0) - notional
                    if cvol <= 0:
                        self.coin_address_volume.pop(key, None)
                    else:
                        self.coin_address_volume[key] = cvol

    def cap_addresses(self, max_addresses: int) -> None:
        """Evict lowest-volume addresses if the dict exceeds ``max_addresses``.

        Used by :class:`PositionCensus` as a memory safety valve when
        the trade stream pushes thousands of unique addresses in a
        busy window. The per-coin map (if tracked) stays untouched —
        it keys on (addr, coin) pairs that still live in the
        underlying trade deque and will prune themselves naturally.
        """
        if len(self.address_volume) <= max_addresses:
            return
        # heapq.nlargest would be marginally cheaper but ``sorted`` is
        # fine at the typical scales (< 10 k addresses) and gives a
        # stable, easy-to-reason-about ordering.
        sorted_addrs = sorted(
            self.address_volume,
            key=self.address_volume.__getitem__,
            reverse=True,
        )
        keep = set(sorted_addrs[:max_addresses])
        self.address_volume = {
            a: v for a, v in self.address_volume.items() if a in keep
        }
