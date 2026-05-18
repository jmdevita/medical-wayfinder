"""
Redis-backed implementation of `Job` / `JobStore`.

Survives backend restarts and works across multiple replicas — the SSE GET
can land on a different pod from the kicker-off POST and still tail every
event in order.

Layout:

  jobs:index                 SET of all known job ids
  job:<id>:meta              HASH of {kind, status, stage, pct, msg, result?,
                              error?, created_at, finished_at?}
  job:<id>:stream            STREAM of events ({type, stage?, pct?, msg?,
                              result?, error?})

24-hour TTL is applied on terminal events (`emit_complete` / `emit_failed`)
to garbage-collect old jobs without manual cleanup.

Streams (XADD/XREAD) eliminate the late-consumer race: a connection at any
point reads from id `0-0` to replay the full history, then BLOCKs for tail.
No separate event log + pub/sub split.

The `result` and `error` fields can hold arbitrary JSON; the stream values
must be strings, so they're `json.dumps`'d on write and parsed on read.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any, AsyncIterator

import redis.asyncio as aioredis

from app.jobs import Job, JobStatus, JobStore, _make_id


# Keep this short enough that GC happens promptly, long enough that a user
# coming back from lunch can still see the result.
_JOB_TTL_SECONDS = 24 * 60 * 60


def _meta_key(job_id: str) -> str:   return f"job:{job_id}:meta"
def _stream_key(job_id: str) -> str: return f"job:{job_id}:stream"
_INDEX_KEY = "jobs:index"


def _encode_optional(v: Any) -> str:
    """Serialise an arbitrary value for stream/hash storage. None → ''."""
    if v is None:
        return ""
    if isinstance(v, str):
        return v
    return json.dumps(v, default=str)


def _decode_optional(s: str | None) -> Any:
    """Parse a hash/stream value. '' → None, JSON object → dict, else str."""
    if s is None or s == "":
        return None
    if s.startswith("{") or s.startswith("["):
        try:
            return json.loads(s)
        except json.JSONDecodeError:
            return s
    return s


class RedisJob(Job):
    def __init__(self, redis: aioredis.Redis, job_id: str, kind: str) -> None:
        self.redis = redis
        self.id = job_id
        self.kind = kind

    async def snapshot(self) -> dict[str, Any]:
        m = await self.redis.hgetall(_meta_key(self.id))
        if not m:
            return {
                "id": self.id, "kind": self.kind,
                "status": JobStatus.PENDING.value,
                "stage": "", "pct": 0.0, "msg": "",
                "result": None, "error": None,
                "created_at": 0.0, "finished_at": None,
            }
        return {
            "id": self.id,
            "kind": m.get("kind", self.kind),
            "status": m.get("status", JobStatus.PENDING.value),
            "stage": m.get("stage", ""),
            "pct": float(m.get("pct", 0.0) or 0.0),
            "msg": m.get("msg", ""),
            "result": _decode_optional(m.get("result")),
            "error":  _decode_optional(m.get("error")),
            "created_at":  float(m["created_at"])  if m.get("created_at")  else 0.0,
            "finished_at": float(m["finished_at"]) if m.get("finished_at") else None,
        }

    async def emit(self, stage: str, pct: float, msg: str = "") -> None:
        clamped = max(0.0, min(1.0, pct))
        meta_updates = {
            "status": JobStatus.RUNNING.value,
            "stage": stage,
            "pct": str(clamped),
            "msg": msg,
        }
        # Pipeline: hset + xadd in one round trip.
        async with self.redis.pipeline(transaction=False) as pipe:
            pipe.hset(_meta_key(self.id), mapping=meta_updates)
            pipe.xadd(
                _stream_key(self.id),
                {
                    "type": "progress",
                    "stage": stage,
                    "pct": str(clamped),
                    "msg": msg,
                },
            )
            await pipe.execute()

    async def emit_complete(self, result: dict[str, Any]) -> None:
        now = time.time()
        async with self.redis.pipeline(transaction=False) as pipe:
            pipe.hset(_meta_key(self.id), mapping={
                "status": JobStatus.COMPLETE.value,
                "pct": "1.0",
                "finished_at": str(now),
                "result": _encode_optional(result),
            })
            pipe.xadd(
                _stream_key(self.id),
                {"type": "complete", "result": _encode_optional(result)},
            )
            pipe.expire(_meta_key(self.id),   _JOB_TTL_SECONDS)
            pipe.expire(_stream_key(self.id), _JOB_TTL_SECONDS)
            await pipe.execute()

    async def emit_failed(self, error: str) -> None:
        now = time.time()
        async with self.redis.pipeline(transaction=False) as pipe:
            pipe.hset(_meta_key(self.id), mapping={
                "status": JobStatus.FAILED.value,
                "finished_at": str(now),
                "error": _encode_optional(error),
            })
            pipe.xadd(
                _stream_key(self.id),
                {"type": "failed", "error": _encode_optional(error)},
            )
            pipe.expire(_meta_key(self.id),   _JOB_TTL_SECONDS)
            pipe.expire(_stream_key(self.id), _JOB_TTL_SECONDS)
            await pipe.execute()

    async def stream_events(self) -> AsyncIterator[dict[str, Any]]:
        # First: the current snapshot — replays full state for a late client.
        snap = await self.snapshot()
        yield {"type": "snapshot", **snap}

        # Then tail the stream from the beginning. XREAD with id "0-0" returns
        # all history, then we use the last seen id to BLOCK for the next.
        last_id = "0"  # "0" means "read from start"; "$" would skip history
        terminal = JobStatus(snap["status"]) in (JobStatus.COMPLETE, JobStatus.FAILED)
        while True:
            # 15s block aligns with the SSE caller's heartbeat cadence so it
            # can poll request.is_disconnected() on a steady tick.
            try:
                resp = await self.redis.xread(
                    {_stream_key(self.id): last_id},
                    count=200,
                    block=15_000,
                )
            except asyncio.CancelledError:
                raise
            if not resp:
                # Idle window. If the job was already terminal at attach time
                # and no events arrived (i.e. stream TTL'd out before us), end
                # the loop instead of looping forever.
                if terminal:
                    return
                yield {"type": "heartbeat"}
                continue

            for _stream, entries in resp:
                for entry_id, fields in entries:
                    last_id = entry_id
                    event = _entry_to_event(fields)
                    yield event
                    if event["type"] in ("complete", "failed"):
                        return


def _entry_to_event(fields: dict[str, str]) -> dict[str, Any]:
    """Stream entries store every value as a string; reshape to the dict the
    SSE consumer expects."""
    out: dict[str, Any] = {"type": fields.get("type", "progress")}
    for k in ("stage", "msg"):
        if k in fields:
            out[k] = fields[k]
    if "pct" in fields:
        try:
            out["pct"] = float(fields["pct"])
        except ValueError:
            out["pct"] = 0.0
    if "result" in fields:
        out["result"] = _decode_optional(fields["result"])
    if "error" in fields:
        out["error"] = _decode_optional(fields["error"])
    return out


class RedisJobStore(JobStore):
    def __init__(self, *, url: str) -> None:
        # Single connection pool reused across all jobs.
        self.redis = aioredis.from_url(
            url,
            decode_responses=True,
            health_check_interval=30,
            socket_keepalive=True,
        )

    async def ping(self) -> None:
        """Used by the lifespan to fail fast if Redis is misconfigured."""
        await self.redis.ping()

    async def aclose(self) -> None:
        await self.redis.aclose()

    def create(self, kind: str) -> Job:
        """Allocate the id synchronously (no event loop required) and let the
        first emit*() actually populate Redis. Until then the job is in
        PENDING state — the snapshot reflects that."""
        job_id = _make_id()
        # Schedule the index/meta write so list_snapshots() sees the job
        # before the first emit. Fire-and-forget on a running loop.
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._initial_register(job_id, kind))
        except RuntimeError:
            # No loop yet (extremely unlikely from a request handler); the
            # initial state will appear on the first emit instead.
            pass
        return RedisJob(self.redis, job_id, kind)

    async def _initial_register(self, job_id: str, kind: str) -> None:
        async with self.redis.pipeline(transaction=False) as pipe:
            pipe.sadd(_INDEX_KEY, job_id)
            pipe.hset(_meta_key(job_id), mapping={
                "kind": kind,
                "status": JobStatus.PENDING.value,
                "stage": "",
                "pct": "0.0",
                "msg": "",
                "created_at": str(time.time()),
            })
            await pipe.execute()

    async def get(self, job_id: str) -> Job | None:
        kind = await self.redis.hget(_meta_key(job_id), "kind")
        if kind is None:
            # Either expired (TTL) or never existed.
            return None
        return RedisJob(self.redis, job_id, kind)

    async def list_snapshots(self) -> list[dict[str, Any]]:
        ids = await self.redis.smembers(_INDEX_KEY)
        out: list[dict[str, Any]] = []
        # Drop ids whose meta has expired (Sets aren't TTL'd alongside hashes).
        stale: list[str] = []
        for jid in sorted(ids):
            kind = await self.redis.hget(_meta_key(jid), "kind")
            if kind is None:
                stale.append(jid)
                continue
            job = RedisJob(self.redis, jid, kind)
            out.append(await job.snapshot())
        if stale:
            await self.redis.srem(_INDEX_KEY, *stale)
        return out
