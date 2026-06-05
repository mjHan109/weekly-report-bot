"""Slack event deduplicator — prevents double-processing of retried events.

Slack may retry events when your server doesn't respond within 3 seconds.
This module keeps a bounded in-memory cache of recently seen event IDs.
If the same event_id arrives again within the TTL window, it is dropped.

Notes
-----
- Cache is in-memory; a server restart clears it (acceptable — retries that
  arrive after restart are legitimate and should be processed).
- Uses a simple dict with insertion-order eviction when over capacity.
- TTL default is 300 seconds (Slack's maximum retry window is ~3 minutes).
"""

from __future__ import annotations

import time
from collections import OrderedDict

_DEFAULT_TTL_SECS = 300
_DEFAULT_MAX_SIZE = 2_000  # ~2 k events per 5-minute window is more than enough


class EventDeduplicator:
    """Thread-safe (GIL-protected) seen-event cache."""

    def __init__(self, ttl_secs: int = _DEFAULT_TTL_SECS, max_size: int = _DEFAULT_MAX_SIZE) -> None:
        self._ttl = ttl_secs
        self._max = max_size
        self._seen: OrderedDict[str, float] = OrderedDict()  # event_id → seen_at

    def is_duplicate(self, event_id: str) -> bool:
        """Return True if event_id was already seen within the TTL window.

        Side effect: records event_id as seen if this is the first occurrence.
        """
        now = time.monotonic()
        self._evict_expired(now)

        if event_id in self._seen:
            return True  # duplicate — do not process

        # Evict oldest entry when at capacity
        if len(self._seen) >= self._max:
            self._seen.popitem(last=False)

        self._seen[event_id] = now
        return False

    def _evict_expired(self, now: float) -> None:
        cutoff = now - self._ttl
        # OrderedDict is insertion-ordered; oldest entries are at the front
        while self._seen:
            oldest_id, oldest_ts = next(iter(self._seen.items()))
            if oldest_ts < cutoff:
                del self._seen[oldest_id]
            else:
                break


# Module-level singleton — shared across all Slack event handlers
_deduplicator = EventDeduplicator()


def is_duplicate_event(event_id: str | None) -> bool:
    """Return True if this event should be skipped (already processed).

    Pass event.get("event_id") or body.get("event_id").
    Returns False (not a duplicate) when event_id is None so that
    events without an ID are always processed.
    """
    if not event_id:
        return False
    return _deduplicator.is_duplicate(event_id)
