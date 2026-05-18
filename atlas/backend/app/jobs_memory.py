"""
In-memory implementation of `Job` / `JobStore`.

Single-replica only: all state lives in a process-local dict. Jobs vanish on
restart. Used as the default backend when `ATLAS_REDIS_URL` is unset.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

from app.jobs import Job, JobStatus, JobStore, _make_id


@dataclass
class _LiveJob(Job):
    """Concrete in-memory Job. Carries state plus a list of consumer queues
    so progress events broadcast to every open SSE stream."""

    id: str = ""
    kind: str = ""
    status: JobStatus = JobStatus.PENDING
    stage: str = ""
    pct: float = 0.0
    msg: str = ""
    result: dict[str, Any] | None = None
    error: str | None = None
    created_at: float = field(default_factory=time.time)
    finished_at: float | None = None
    # Buffered event log so a consumer that connects mid-flight still gets
    # earlier progress lines.
    events: list[dict[str, Any]] = field(default_factory=list)
    _consumers: list[asyncio.Queue[dict[str, Any] | None]] = field(default_factory=list)

    # ---- internal helpers ----

    def _snapshot_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "status": self.status.value,
            "stage": self.stage,
            "pct": self.pct,
            "msg": self.msg,
            "result": self.result,
            "error": self.error,
            "created_at": self.created_at,
            "finished_at": self.finished_at,
        }

    def _broadcast(self, event: dict[str, Any]) -> None:
        self.events.append(event)
        for q in self._consumers:
            q.put_nowait(event)

    def _close_streams(self) -> None:
        for q in self._consumers:
            q.put_nowait(None)
        self._consumers.clear()

    def _attach_consumer(self) -> asyncio.Queue[dict[str, Any] | None]:
        q: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
        for past in self.events:
            q.put_nowait(past)
        if self.status in (JobStatus.COMPLETE, JobStatus.FAILED):
            q.put_nowait(None)
        else:
            self._consumers.append(q)
        return q

    def _detach_consumer(self, q: asyncio.Queue[dict[str, Any] | None]) -> None:
        try:
            self._consumers.remove(q)
        except ValueError:
            pass

    # ---- Job interface ----

    async def snapshot(self) -> dict[str, Any]:
        return self._snapshot_dict()

    async def emit(self, stage: str, pct: float, msg: str = "") -> None:
        self.status = JobStatus.RUNNING
        self.stage = stage
        self.pct = max(0.0, min(1.0, pct))
        self.msg = msg
        self._broadcast({"type": "progress", "stage": stage, "pct": self.pct, "msg": msg})

    async def emit_complete(self, result: dict[str, Any]) -> None:
        self.status = JobStatus.COMPLETE
        self.pct = 1.0
        self.result = result
        self.finished_at = time.time()
        self._broadcast({"type": "complete", "result": result})
        self._close_streams()

    async def emit_failed(self, error: str) -> None:
        self.status = JobStatus.FAILED
        self.error = error
        self.finished_at = time.time()
        self._broadcast({"type": "failed", "error": error})
        self._close_streams()

    async def stream_events(self) -> AsyncIterator[dict[str, Any]]:
        # First event is always a snapshot so consumers can render immediately.
        yield {"type": "snapshot", **self._snapshot_dict()}
        queue = self._attach_consumer()
        try:
            while True:
                # Periodic timeout lets the SSE caller poll is_disconnected().
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15.0)
                except asyncio.TimeoutError:
                    yield {"type": "heartbeat"}
                    continue
                if event is None:
                    return
                yield event
        finally:
            self._detach_consumer(queue)


class InMemoryJobStore(JobStore):
    def __init__(self) -> None:
        self._jobs: dict[str, _LiveJob] = {}

    def create(self, kind: str) -> Job:
        job = _LiveJob(id=_make_id(), kind=kind)
        self._jobs[job.id] = job
        return job

    async def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    async def list_snapshots(self) -> list[dict[str, Any]]:
        return [j._snapshot_dict() for j in self._jobs.values()]
