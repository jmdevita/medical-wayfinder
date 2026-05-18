"""
Job runner: tracks long-running operations (OSM bootstrap, LLM extraction,
edge drafting, alias expansion) and streams their progress to clients.

Two backends:

  - **In-memory** (default): all state lives in a process-local dict. Single
    replica only; jobs vanish on restart. Fine for `make dev`.
  - **Redis-backed**: state lives in a Hash + Stream per job. Survives
    restarts; multiple backend replicas can serve any consumer. Selected by
    setting `ATLAS_REDIS_URL=redis://host:port/db`.

Both backends expose the same interface (`Job`, `JobStore`) and call sites
look identical.
"""

from __future__ import annotations

import abc
import os
import uuid
from enum import Enum
from typing import Any, AsyncIterator


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"


class Job(abc.ABC):
    """A single long-running operation. Created by the route that kicks it
    off; emits progress events as it runs."""

    id: str
    kind: str

    @abc.abstractmethod
    async def snapshot(self) -> dict[str, Any]:
        """Current state as a JSON-serialisable dict. Used by GET /jobs/{id}
        and as the first event yielded by `stream_events()`."""

    @abc.abstractmethod
    async def emit(self, stage: str, pct: float, msg: str = "") -> None:
        """Record progress. Status flips to RUNNING on first emit."""

    @abc.abstractmethod
    async def emit_complete(self, result: dict[str, Any]) -> None:
        """Final success event. Closes any open streams."""

    @abc.abstractmethod
    async def emit_failed(self, error: str) -> None:
        """Final failure event. Closes any open streams."""

    @abc.abstractmethod
    def stream_events(self) -> AsyncIterator[dict[str, Any]]:
        """
        Yield events for an SSE consumer. First event is always `snapshot`,
        followed by zero or more `progress`, ending in either `complete` or
        `failed`. Yields heartbeat dicts on long idles so the SSE generator
        can poll `request.is_disconnected()`.

        Late consumers (connecting after some progress already emitted) get
        the full history first via replay, then live updates.
        """


class JobStore(abc.ABC):
    """Process-wide registry. Modules import the singleton `jobs` from this
    file; the underlying implementation is selected by env at import time."""

    @abc.abstractmethod
    def create(self, kind: str) -> Job:
        """Allocate a fresh job. Sync — does not require a running event
        loop, so it works from `asyncio.create_task` callers."""

    @abc.abstractmethod
    async def get(self, job_id: str) -> Job | None: ...

    @abc.abstractmethod
    async def list_snapshots(self) -> list[dict[str, Any]]: ...


def _make_id() -> str:
    return f"j_{uuid.uuid4().hex[:12]}"


def _make_store() -> JobStore:
    """
    Pick a backend based on env. Imports are deferred so the unused module
    doesn't get pulled into local-dev startup.
    """
    redis_url = os.environ.get("ATLAS_REDIS_URL", "").strip()
    if redis_url:
        from app.jobs_redis import RedisJobStore
        return RedisJobStore(url=redis_url)
    from app.jobs_memory import InMemoryJobStore
    return InMemoryJobStore()


jobs: JobStore = _make_store()
