#!/usr/bin/env python3
"""
Extract department-to-building mappings for a facility using an
OpenAI-compatible LLM endpoint (your llama-swap / Ollama / vLLM server).

Pairs with `fetch_osm_for_facility.py`:
  1. fetch_osm_for_facility.py    — bootstraps real building positions from OSM
  2. fetch_departments_for_facility.py  — fills in which dept is in which building

Usage:
  env/bin/python tools/fetch_departments_for_facility.py <slug> \\
      --url https://hospital.org/locations \\
      --url https://hospital.org/services \\
      [--model qwen3.5-122b] \\
      [--merge]

Configuration (read from training/.env, override via flags or env):
  OPENAI_BASE_URL  default: http://localhost:11434/v1
  OPENAI_MODEL     default: qwen3.5-122b
  OPENAI_API_KEY   default: not-needed

Workflow:
  1. Reads tools/bootstrap/<slug>/facility.json → closed list of building names.
  2. Fetches every --url and strips HTML to text.
  3. Sends one chat-completion call to the configured endpoint with a system
     prompt constraining buildings to the closed list.
  4. Validates each returned dept's building against the closed list.
  5. Prints to stdout (default) or merges into the bootstrap JSON (--merge).

Why no PDF support: hospital websites already publish department directories
as searchable HTML — the real source of truth. PDFs of campus maps are visual
documents; without a multimodal model, pdftotext gives jumbled label fragments
with no spatial context. URLs are simpler and produce better results.
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
TOOLS_DIR = ROOT / "tools"
ENV_FILE = ROOT / "training" / ".env"


# ---- Config ----------------------------------------------------------------

def load_env() -> dict[str, str]:
    """Load training/.env into a dict (without polluting os.environ)."""
    out = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def resolve_config(args) -> dict[str, str]:
    """Precedence: CLI flag > env var > training/.env > hardcoded default."""
    env_file = load_env()

    def pick(key: str, flag, default: str) -> str:
        if flag:
            return flag
        if os.environ.get(key):
            return os.environ[key]
        if env_file.get(key):
            return env_file[key]
        return default

    return {
        "base_url": pick("OPENAI_BASE_URL", args.base_url, "http://localhost:11434/v1"),
        "model":    pick("OPENAI_MODEL",    args.model,    "qwen3.5-122b"),
        "api_key":  pick("OPENAI_API_KEY",  None,          "not-needed"),
    }


# ---- Source loading --------------------------------------------------------

def html_to_text(html: str) -> str:
    """Crude HTML→text. Adequate for hospital directory pages; the model
    handles residual markup fine."""
    html = re.sub(r"<script\b[^<]*(?:(?!</script>)<[^<]*)*</script>", "", html, flags=re.I | re.S)
    html = re.sub(r"<style\b[^<]*(?:(?!</style>)<[^<]*)*</style>", "", html, flags=re.I | re.S)
    html = re.sub(r"<[^>]+>", " ", html)
    html = re.sub(r"&nbsp;", " ", html)
    html = re.sub(r"&amp;", "&", html)
    html = re.sub(r"&lt;", "<", html)
    html = re.sub(r"&gt;", ">", html)
    html = re.sub(r"&#?\w+;", " ", html)
    html = re.sub(r"\s+", " ", html)
    return html.strip()


def fetch_url(url: str, max_chars: int = 15_000) -> str:
    print(f"  fetching {url}", file=sys.stderr)
    r = requests.get(url, timeout=30, headers={
        "User-Agent": "HealthWayfinder/1.0 (department-extraction)"
    })
    r.raise_for_status()
    text = html_to_text(r.text)
    if len(text) > max_chars:
        text = text[:max_chars] + "\n...[truncated]"
    print(f"    → {len(text)} chars", file=sys.stderr)
    return text


# ---- Extraction prompt -----------------------------------------------------

SYSTEM_PROMPT = """\
You are extracting department-to-building mappings for a healthcare wayfinding app.

Given:
- A closed list of building names that exist on a hospital campus
- Source material from the hospital's public website / campus map

You must return a JSON array of department records.

CRITICAL RULES:
1. The "building" field MUST be one of the buildings in the provided list,
   character-for-character. Do NOT invent buildings. If you can't determine
   which building a department is in, omit that department entirely.
2. Don't hallucinate departments. If a department isn't clearly mentioned in
   the source material, don't include it.
3. Include English aliases (synonyms a patient might say) AND Spanish aliases
   for major patient-facing departments.
4. Set "confidence" to:
   - "high" — explicit statement (e.g. "located in the Wang Center")
   - "medium" — inferred from address or floor reference
   - "low" — guessed from indirect evidence
5. Cite which source URL/file in the "source" field.
6. Floor: when present in source ("Suite 460", "8th floor"), include verbatim.

OUTPUT FORMAT — pure JSON array, no prose, no markdown fences, no commentary:

[
  {
    "name": "Emergency Department",
    "building": "Lunder Building",
    "floor": "Ground floor",
    "hours": "24/7",
    "aliases": ["emergency", "ER", "emergency room", "urgencias", "emergencia"],
    "check_in": "Go directly to the emergency entrance",
    "directions": "Look for the Lunder Building's emergency entrance with red signage.",
    "confidence": "high",
    "source": "https://hospital.org/maps"
  }
]

Aim for 8-15 departments — the major patient-facing ones. Use only ASCII apostrophes.
Reply with ONLY the JSON array. No explanation before or after.
"""


def call_llm(cfg: dict[str, str], buildings: list[str], sources: list[dict]) -> str:
    user_text = (
        "Buildings on this campus (use these EXACT names in the 'building' field):\n"
        + "\n".join(f"- {b}" for b in buildings)
        + "\n\nSource material follows. Extract a JSON departments array per the system rules.\n"
    )
    for src in sources:
        user_text += f"\n=== Source: {src['name']} ===\n{src['text']}\n"

    body = {
        "model": cfg["model"],
        "temperature": 0.1,
        "max_tokens": 8192,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_text},
        ],
        # Disable the model's reasoning track. Qwen3.x and similar
        # reasoning models emit a `reasoning_content` field that consumes
        # most of the token budget before any actual answer. We only want
        # the direct JSON answer — disable thinking so `content` is populated.
        "chat_template_kwargs": {"enable_thinking": False},
    }

    url = f"{cfg['base_url'].rstrip('/')}/chat/completions"
    print(f"\nCalling {url} (model={cfg['model']})…", file=sys.stderr)
    resp = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {cfg['api_key']}",
            "Content-Type": "application/json",
        },
        json=body,
        timeout=600,
    )
    if resp.status_code != 200:
        raise SystemExit(f"LLM endpoint {resp.status_code}: {resp.text[:600]}")
    data = resp.json()
    msg = data["choices"][0]["message"]
    content = msg.get("content") or ""
    usage = data.get("usage", {})
    print(
        f"  → {len(content)} chars · "
        f"in_tokens={usage.get('prompt_tokens')} "
        f"out_tokens={usage.get('completion_tokens')}",
        file=sys.stderr,
    )
    if not content:
        raise SystemExit(
            "Empty content. The server may not honor enable_thinking=False for this model. "
            "Try a non-reasoning model (gemma4-26b, gemma4-31b, gpt-oss-120b)."
        )
    return content


# ---- Output handling -------------------------------------------------------

def parse_departments(raw: str) -> list[dict]:
    raw = raw.strip()
    # Strip <think> blocks some reasoning models emit
    raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.S).strip()
    # Strip markdown fences
    raw = re.sub(r"^```(?:json)?\n?", "", raw)
    raw = re.sub(r"\n?```$", "", raw)
    if not raw.startswith("["):
        m = re.search(r"\[.*\]", raw, re.S)
        if m:
            raw = m.group(0)
    return json.loads(raw, strict=False)


def validate_and_clean(depts: list[dict], buildings: set[str]) -> tuple[list[dict], list[dict]]:
    kept, dropped = [], []
    for d in depts:
        if not isinstance(d, dict):
            continue
        if d.get("building") not in buildings:
            dropped.append(d)
            continue
        d.setdefault("aliases", [])
        d.setdefault("accessible", True)
        kept.append(d)
    return kept, dropped


def to_facility_schema(depts: list[dict]) -> list[dict]:
    """Strip review-only fields before writing into facility JSON."""
    return [{k: v for k, v in d.items() if k not in ("confidence", "source")}
            for d in depts]


# ---- Main ------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(
        description="Extract department-to-building mappings via LLM.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument("slug", help="Facility slug (matches tools/bootstrap/<slug>/facility.json)")
    ap.add_argument("--url", action="append", default=[],
                    help="Hospital page to extract from (repeatable)")
    ap.add_argument("--model", help="Override OPENAI_MODEL")
    ap.add_argument("--base-url", help="Override OPENAI_BASE_URL")
    ap.add_argument("--merge", action="store_true",
                    help="Write departments into the bootstrap facility JSON.")
    args = ap.parse_args()

    if not args.url:
        raise SystemExit("Provide at least one --url source.")

    cfg = resolve_config(args)
    print(f"Endpoint: {cfg['base_url']}", file=sys.stderr)
    print(f"Model:    {cfg['model']}", file=sys.stderr)

    bootstrap_path = TOOLS_DIR / "bootstrap" / args.slug / "facility.json"
    if not bootstrap_path.exists():
        raise SystemExit(
            f"Missing {bootstrap_path.relative_to(ROOT)}. "
            f"Run fetch_osm_for_facility.py first."
        )
    facility = json.loads(bootstrap_path.read_text())
    buildings = [b["name"] for b in facility.get("buildings", [])]
    if not buildings:
        raise SystemExit("Bootstrap facility has no buildings; can't constrain extraction.")
    print(f"\nSlug: {args.slug}", file=sys.stderr)
    print(f"Buildings ({len(buildings)}):", file=sys.stderr)
    for b in buildings:
        print(f"  · {b}", file=sys.stderr)

    sources = []
    for url in args.url:
        try:
            sources.append({"name": url, "text": fetch_url(url)})
        except Exception as e:
            print(f"  WARNING: {url} failed: {e}", file=sys.stderr)
    if not sources:
        raise SystemExit("No sources successfully loaded.")

    raw = call_llm(cfg, buildings, sources)

    try:
        depts = parse_departments(raw)
    except json.JSONDecodeError as e:
        print(f"\nFailed to parse model output:\n{raw[:1500]}", file=sys.stderr)
        raise SystemExit(f"JSON error: {e}")

    kept, dropped = validate_and_clean(depts, set(buildings))
    print(f"\nKept {len(kept)} departments · Dropped {len(dropped)} (invalid building):",
          file=sys.stderr)
    for d in kept:
        c = d.get("confidence", "?")
        print(f"  [{c:6}] {d['name']:<45} → {d['building']}"
              + (f"  ({d.get('floor')})" if d.get('floor') else ""),
              file=sys.stderr)
    for d in dropped:
        print(f"  [DROPPED] {d.get('name','?')} → {d.get('building','?')} "
              f"(not in closed list)", file=sys.stderr)

    if args.merge:
        facility["departments"] = to_facility_schema(kept)
        bootstrap_path.write_text(json.dumps(facility, indent=2, ensure_ascii=False) + "\n")
        print(f"\nMerged {len(kept)} departments into {bootstrap_path.relative_to(ROOT)}",
              file=sys.stderr)
        print("Review confidence levels above — verify any 'low' entries before promoting.",
              file=sys.stderr)
    else:
        print(json.dumps(kept, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
