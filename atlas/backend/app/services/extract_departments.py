"""
Async wrapper around `tools/fetch_departments_for_facility.py`.

Given a slug (must already exist as a bootstrap or published facility) and a
list of hospital website URLs, fetches each, sends to the configured LLM,
and merges the resulting `departments[]` into the facility JSON.
"""

from __future__ import annotations

import asyncio
from typing import Any

from app.jobs import Job
from app.services._io import ensure_tools_on_path, read_json, write_json_atomic
from app.services.locate import resolve_paths


async def run_extract(
    job: Job,
    *,
    slug: str,
    urls: list[str],
    model: str | None = None,
    base_url: str | None = None,
) -> None:
    try:
        if not urls:
            raise ValueError("Provide at least one URL.")
        await job.emit("starting", 0.05, f"Extracting departments for '{slug}' from {len(urls)} URL(s)")
        ensure_tools_on_path()
        import fetch_departments_for_facility as fd  # type: ignore

        facility_path, _topology_path, _source = resolve_paths(slug)
        if not facility_path.exists():
            raise FileNotFoundError(f"No facility for slug '{slug}'. Bootstrap first.")
        facility = read_json(facility_path)
        buildings = [b["name"] for b in facility.get("buildings", [])]
        if not buildings:
            raise ValueError("Facility has no buildings; can't constrain extraction.")

        # Build the LLM config the same way the CLI does — env vars + overrides.
        cfg = _resolve_cfg(model=model, base_url=base_url)
        await job.emit("config_ready", 0.10, f"Endpoint {cfg['base_url']}, model {cfg['model']}")

        # Fetch each URL sequentially (polite + simple).
        sources: list[dict[str, Any]] = []
        for i, url in enumerate(urls):
            pct = 0.10 + (0.30 - 0.10) * ((i + 1) / max(len(urls), 1))
            await job.emit("fetching", pct, f"Fetching {url[:80]}")
            try:
                text = await asyncio.to_thread(fd.fetch_url, url)
                sources.append({"name": url, "text": text})
            except Exception as exc:  # noqa: BLE001
                await job.emit("fetch_warning", pct, f"{url}: {exc}")
        if not sources:
            raise RuntimeError("No URLs could be fetched.")

        await job.emit("calling_llm", 0.40, f"Asking {cfg['model']} for departments…")
        raw = await asyncio.to_thread(fd.call_llm, cfg, buildings, sources)

        await job.emit("parsing", 0.80, "Parsing JSON response…")
        depts_raw = await asyncio.to_thread(fd.parse_departments, raw)
        kept, dropped = await asyncio.to_thread(fd.validate_and_clean, depts_raw, set(buildings))
        depts = await asyncio.to_thread(fd.to_facility_schema, kept)

        # The LLM occasionally returns the same department name twice (often
        # when a service appears on multiple source pages). The save endpoint
        # rejects duplicates, so dedupe here — keep the first occurrence.
        deduped: list[dict[str, Any]] = []
        seen_names: set[str] = set()
        for d in depts:
            n = d.get("name") if isinstance(d, dict) else None
            if not isinstance(n, str) or n in seen_names:
                continue
            seen_names.add(n)
            deduped.append(d)
        depts = deduped

        await job.emit("merging", 0.92, f"Merging {len(depts)} departments")
        facility["departments"] = depts
        write_json_atomic(facility_path, facility)

        await job.emit_complete({
            "slug": slug,
            "departments_added": len(depts),
            "departments_dropped": len(dropped),
            "facility_path": str(facility_path),
        })
    except Exception as exc:  # noqa: BLE001
        await job.emit_failed(f"{type(exc).__name__}: {exc}")


def _resolve_cfg(*, model: str | None, base_url: str | None) -> dict[str, str]:
    """
    Mirrors fetch_departments_for_facility.resolve_config but without argparse.
    Reads training/.env via load_env (lives in the tools/ script), then layers
    explicit overrides on top.
    """
    ensure_tools_on_path()
    import fetch_departments_for_facility as fd  # type: ignore
    env = fd.load_env()
    return {
        "base_url": base_url or env.get("OPENAI_BASE_URL", "http://localhost:11434/v1"),
        "api_key":  env.get("OPENAI_API_KEY", "sk-NONE"),
        "model":    model or env.get("OPENAI_MODEL", "gemma4-31b"),
    }
