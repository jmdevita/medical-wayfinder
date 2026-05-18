"""
Pessimistic per-facility editing lock with a 5-minute idle TTL.

Holding a lock signals to the rest of the workspace "this user is editing
this facility right now." Other editors get a clear "Maya is editing this
facility (last update 30s ago)" rather than a silent last-write-wins clobber.

Storage is in-memory: this works only with a single backend replica. When the
deploy needs more than one replica, swap this for Redis.

The lock auto-expires if not heartbeated within 5 minutes — so a user that
closes a tab without releasing doesn't permanently block the facility.

Mutations call `assert_writable(slug, user)`:
  - if no lock, allowed (no implicit acquire)
  - if held by `user`, allowed + heartbeat
  - if held by someone else (and not expired), 423 Locked

The frontend is expected to call `acquire` when the editor opens, heartbeat
on activity, and `release` on navigate-away.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass

from fastapi import HTTPException, status


# 5 minutes of idle = lock auto-expires.
LOCK_TTL_SECONDS = 5 * 60


@dataclass
class LockState:
    user: str
    acquired_at: float
    last_heartbeat: float


class LockStore:
    """Thread-safe enough for asyncio + a couple of background threads. Keys
    are slugs. We don't bound size — workspaces have at most a few hundred."""

    def __init__(self) -> None:
        self._locks: dict[str, LockState] = {}
        self._mu = threading.Lock()

    def status(self, slug: str) -> LockState | None:
        with self._mu:
            lock = self._locks.get(slug)
            if not lock:
                return None
            if _is_expired(lock):
                del self._locks[slug]
                return None
            return lock

    def acquire_or_heartbeat(self, slug: str, user: str) -> LockState:
        """Idempotent: re-acquiring as the same user just heartbeats. If
        another user holds an unexpired lock, raises 423."""
        now = time.time()
        with self._mu:
            existing = self._locks.get(slug)
            if existing and not _is_expired(existing) and existing.user != user:
                raise _locked_exception(slug, existing)
            if existing and existing.user == user:
                existing.last_heartbeat = now
                return existing
            state = LockState(user=user, acquired_at=now, last_heartbeat=now)
            self._locks[slug] = state
            return state

    def release(self, slug: str, user: str) -> bool:
        """Release a lock you hold. Releasing a lock you don't hold is a no-op
        (returns False) — that's the right call when a tab closes after the
        TTL has already lapsed and someone else has the lock now."""
        with self._mu:
            existing = self._locks.get(slug)
            if not existing:
                return False
            if existing.user != user:
                return False
            del self._locks[slug]
            return True

    def assert_writable(self, slug: str, user: str, *, enforce: bool = True) -> None:
        """Used by mutation routes. Allows writes when:
          - `enforce=False` (auth disabled — local dev bypass)
          - the slug has no lock (or it has expired)
          - the slug's lock is held by `user` (heartbeated)
        """
        if not enforce:
            return
        with self._mu:
            existing = self._locks.get(slug)
            if not existing or _is_expired(existing):
                return
            if existing.user == user:
                # Refresh on a write — counts as activity.
                existing.last_heartbeat = time.time()
                return
            raise _locked_exception(slug, existing)


def _is_expired(lock: LockState) -> bool:
    return (time.time() - lock.last_heartbeat) > LOCK_TTL_SECONDS


def _locked_exception(slug: str, lock: LockState) -> HTTPException:
    age = int(time.time() - lock.last_heartbeat)
    return HTTPException(
        status_code=status.HTTP_423_LOCKED,
        detail={
            "message": f"'{slug}' is locked by another editor.",
            "held_by": lock.user,
            "idle_seconds": age,
            "ttl_seconds": LOCK_TTL_SECONDS,
        },
    )


# Module singleton. Lifespan is the process lifespan.
locks = LockStore()
