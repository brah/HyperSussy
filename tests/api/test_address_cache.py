"""Tests for the shared TTL+LRU address cache."""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi", reason="fastapi not installed")

from hypersussy.api._address_cache import TtlAddressCache


def test_get_returns_none_on_miss() -> None:
    cache: TtlAddressCache[int] = TtlAddressCache(ttl_seconds=60.0, max_entries=10)
    assert cache.get("0xabc") is None


def test_put_then_get_returns_value() -> None:
    cache: TtlAddressCache[int] = TtlAddressCache(ttl_seconds=60.0, max_entries=10)
    cache.put("0xabc", 42)
    assert cache.get("0xabc") == 42


def test_expired_entry_returns_none() -> None:
    cache: TtlAddressCache[int] = TtlAddressCache(ttl_seconds=60.0, max_entries=10)
    cache.put("0xabc", 42)
    # Manually expire the entry by reaching into the OrderedDict.
    cache._cache["0xabc"].expires_at = 0.0
    assert cache.get("0xabc") is None


def test_lru_eviction_drops_oldest() -> None:
    cache: TtlAddressCache[int] = TtlAddressCache(ttl_seconds=60.0, max_entries=2)
    cache.put("a", 1)
    cache.put("b", 2)
    cache.put("c", 3)
    # "a" was the LRU and should have been evicted on the third put.
    assert cache.get("a") is None
    assert cache.get("b") == 2
    assert cache.get("c") == 3
    assert len(cache) == 2


def test_get_promotes_to_mru() -> None:
    cache: TtlAddressCache[int] = TtlAddressCache(ttl_seconds=60.0, max_entries=2)
    cache.put("a", 1)
    cache.put("b", 2)
    # Touch "a" so it becomes MRU; "b" is now LRU.
    assert cache.get("a") == 1
    cache.put("c", 3)
    # "b" should be evicted, not "a".
    assert cache.get("a") == 1
    assert cache.get("b") is None
    assert cache.get("c") == 3
