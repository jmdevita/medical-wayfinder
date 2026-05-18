"""
Generic job endpoints: state snapshot + Server-Sent Events progress stream.

All long-running operations (OSM bootstrap, LLM extraction, edge drafting,
alias expansion) post here. The frontend opens an EventSource against the
stream URL and updates UI as events arrive.

The job runner backend (in-memory or Redis) is selected at import time in
`app/jobs.py` based on `ATLAS_REDIS_URL`.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from sse_starlette.sse import EventSourceResponse

from app.jobs import jobs

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("")
async def list_jobs() -> dict[str, list[dict[str, Any]]]:
    """All jobs the runner has seen. Useful for debugging."""
    return {"jobs": await jobs.list_snapshots()}


@router.get("/{job_id}")
async def get_job(job_id: str) -> dict[str, Any]:
    job = await jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")
    return await job.snapshot()


@router.get("/{job_id}/stream")
async def stream_job(job_id: str, request: Request) -> EventSourceResponse:
    """SSE stream of progress events. Replays history then tails live updates."""
    job = await jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")

    async def gen():
        try:
            async for event in job.stream_events():
                if await request.is_disconnected():
                    break
                # Heartbeats from the backend are filtered out client-side
                # by the SSE generator; we just keep the connection alive.
                yield {"event": event.get("type", "message"), "data": json.dumps(event)}
        except asyncio.CancelledError:
            # Client closed the connection; let the framework propagate.
            raise

    return EventSourceResponse(gen(), ping=15)
