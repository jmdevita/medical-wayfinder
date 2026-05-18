"""
Async wrapper around `tools/fetch_aliases_for_facility.py`.

For each department, asks the configured LLM to expand `aliases[]` from the
existing 3-or-so seed phrases to ~10 entries spanning English and Spanish
patient phrasings. Merges back into the facility JSON.
"""

from __future__ import annotations

import asyncio

from app.jobs import Job
from app.services._io import ensure_tools_on_path, read_json, write_json_atomic
from app.services.locate import resolve_paths


async def run_expand_aliases(
    job: Job,
    *,
    slug: str,
    model: str | None = None,
    base_url: str | None = None,
) -> None:
    try:
        await job.emit("starting", 0.05, f"Expanding aliases for '{slug}'")
        ensure_tools_on_path()
        import fetch_aliases_for_facility as fa  # type: ignore

        facility_path, _topology_path, _source = resolve_paths(slug)
        if not facility_path.exists():
            raise FileNotFoundError(f"No facility for slug '{slug}'.")
        facility = read_json(facility_path)
        departments = facility.get("departments", [])
        if not departments:
            raise ValueError("Facility has no departments to expand.")

        cfg = _resolve_cfg(model=model, base_url=base_url)
        await job.emit(
            "config_ready",
            0.10,
            f"{len(departments)} departments via {cfg['model']}",
        )

        await job.emit("calling_llm", 0.25, f"Asking {cfg['model']} for aliases…")
        raw = await asyncio.to_thread(fa.call_llm, cfg, departments)

        await job.emit("parsing", 0.80, "Parsing JSON response…")
        proposed = await asyncio.to_thread(fa.parse_aliases, raw)
        by_name = {p["name"]: p.get("aliases", []) for p in proposed if isinstance(p, dict)}

        await job.emit("merging", 0.92, "Merging aliases into facility")
        added_total = 0
        for d in departments:
            existing = d.get("aliases", [])
            merged = await asyncio.to_thread(fa.merge_aliases, existing, by_name.get(d["name"], []))
            added_total += len(merged) - len(existing)
            d["aliases"] = merged
        facility["departments"] = departments
        write_json_atomic(facility_path, facility)

        await job.emit_complete({
            "slug": slug,
            "aliases_added": added_total,
            "departments_processed": len(departments),
            "facility_path": str(facility_path),
        })
    except Exception as exc:  # noqa: BLE001
        await job.emit_failed(f"{type(exc).__name__}: {exc}")


def _resolve_cfg(*, model: str | None, base_url: str | None) -> dict[str, str]:
    ensure_tools_on_path()
    import fetch_aliases_for_facility as fa  # type: ignore
    env = fa.load_env()
    return {
        "base_url": base_url or env.get("OPENAI_BASE_URL", "http://localhost:11434/v1"),
        "api_key":  env.get("OPENAI_API_KEY", "sk-NONE"),
        "model":    model or env.get("OPENAI_MODEL", "gemma4-31b"),
    }
