#!/usr/bin/env python3
"""
Expand department aliases for a facility using an OpenAI-compatible LLM.

The dept-extractor (fetch_departments_for_facility.py) typically emits 2-3
aliases per department. For real patient matching we want 6-10: colloquial
English, Spanish, common misspellings, abbreviations.

Pairs with the rest of the bootstrap pipeline:
  fetch_osm_for_facility.py  -> fetch_departments_for_facility.py
  -> topology_editor.html    -> fetch_aliases_for_facility.py (this)

Usage:
  env/bin/python tools/fetch_aliases_for_facility.py <slug> [--merge]

  <slug> is the filename in health_wayfinder/assets/facilities/<slug>.json
  (not the bootstrap one - run this AFTER promoting the file).

  Without --merge: prints the proposed aliases JSON to stdout for review.
  With --merge:    writes back into the facility JSON, deduping with existing.

Configuration (training/.env, same as the other tools):
  OPENAI_BASE_URL  default: http://localhost:11434/v1
  OPENAI_MODEL     default: qwen3.5-122b
  OPENAI_API_KEY   default: not-needed
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT / "training" / ".env"
ASSETS_DIR = ROOT / "health_wayfinder" / "assets" / "facilities"


def load_env() -> dict[str, str]:
    out = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def resolve_config(args) -> dict[str, str]:
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


SYSTEM_PROMPT = """\
You expand department aliases for a healthcare wayfinding app. Patients ask
in many ways - colloquial English, Spanish, abbreviations, misspellings - and
the app matches their query against an aliases list.

Given a list of departments (each with name + existing aliases), return an
expanded aliases array per department. Aim for 6-10 aliases each, covering:

- Colloquial English ("blood draw", "MRI", "x-ray")
- Common Spanish equivalents ("laboratorio", "rayos x", "resonancia")
- Abbreviations and full forms ("ER" + "emergency room")
- What patients actually say, not clinical jargon

RULES:
1. Preserve all existing aliases - only add, never remove.
2. Match the department exactly by its "name" field.
3. Lowercase everything except acronyms (ER, MRI, CT, PET).
4. ASCII apostrophes only.
5. No duplicates within a department's aliases.
6. Don't invent department types - only expand aliases for what's given.

OUTPUT FORMAT - pure JSON array, no prose, no markdown fences:

[
  {
    "name": "Emergency Department",
    "aliases": ["emergency", "ER", "emergency room", "urgent care", "urgencias", "emergencia", "sala de emergencia", "ED"]
  },
  ...
]

Reply with ONLY the JSON array.
"""


def call_llm(cfg: dict[str, str], departments: list[dict]) -> str:
    payload = [
        {"name": d["name"], "aliases": d.get("aliases", [])}
        for d in departments
    ]
    user_text = (
        "Expand aliases for these departments. Return one entry per department, "
        "matched by name.\n\n"
        + json.dumps(payload, indent=2, ensure_ascii=False)
    )

    body = {
        "model": cfg["model"],
        "temperature": 0.2,
        "max_tokens": 4096,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_text},
        ],
        "chat_template_kwargs": {"enable_thinking": False},
    }

    url = f"{cfg['base_url'].rstrip('/')}/chat/completions"
    print(f"\nCalling {url} (model={cfg['model']})...", file=sys.stderr)
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
        f"  -> {len(content)} chars, "
        f"in_tokens={usage.get('prompt_tokens')} "
        f"out_tokens={usage.get('completion_tokens')}",
        file=sys.stderr,
    )
    if not content:
        raise SystemExit(
            "Empty content. Server may not honor enable_thinking=False; "
            "try gemma4-26b, gemma4-31b, gpt-oss-120b."
        )
    return content


def parse_aliases(raw: str) -> list[dict]:
    raw = raw.strip()
    raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.S).strip()
    raw = re.sub(r"^```(?:json)?\n?", "", raw)
    raw = re.sub(r"\n?```$", "", raw)
    if not raw.startswith("["):
        m = re.search(r"\[.*\]", raw, re.S)
        if m:
            raw = m.group(0)
    return json.loads(raw, strict=False)


def merge_aliases(existing: list[str], proposed: list[str]) -> list[str]:
    """Union-preserving order: existing first, then new ones in order."""
    seen = {a.lower(): a for a in existing}
    out = list(existing)
    for a in proposed:
        if not isinstance(a, str):
            continue
        a = a.strip()
        if not a or a.lower() in seen:
            continue
        seen[a.lower()] = a
        out.append(a)
    return out


def main():
    ap = argparse.ArgumentParser(
        description="Expand department aliases via LLM.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument("slug",
                    help="Facility filename (e.g. massachusetts_general)")
    ap.add_argument("--model", help="Override OPENAI_MODEL")
    ap.add_argument("--base-url", help="Override OPENAI_BASE_URL")
    ap.add_argument("--merge", action="store_true",
                    help="Write expanded aliases back into the facility JSON.")
    args = ap.parse_args()

    cfg = resolve_config(args)
    print(f"Endpoint: {cfg['base_url']}", file=sys.stderr)
    print(f"Model:    {cfg['model']}", file=sys.stderr)

    facility_path = ASSETS_DIR / f"{args.slug}.json"
    if not facility_path.exists():
        raise SystemExit(f"Missing {facility_path.relative_to(ROOT)}")
    facility = json.loads(facility_path.read_text())

    departments = facility.get("departments", [])
    if not departments:
        raise SystemExit("Facility has no departments to expand.")

    print(f"\nSlug: {args.slug}", file=sys.stderr)
    print(f"Departments ({len(departments)}):", file=sys.stderr)
    for d in departments:
        print(f"  - {d['name']:<45} ({len(d.get('aliases', []))} aliases)",
              file=sys.stderr)

    raw = call_llm(cfg, departments)

    try:
        proposed = parse_aliases(raw)
    except json.JSONDecodeError as e:
        print(f"\nFailed to parse:\n{raw[:1500]}", file=sys.stderr)
        raise SystemExit(f"JSON error: {e}")

    by_name = {p["name"]: p.get("aliases", []) for p in proposed if isinstance(p, dict)}

    expanded = []
    for d in departments:
        existing = d.get("aliases", [])
        new = by_name.get(d["name"], [])
        merged = merge_aliases(existing, new)
        added = len(merged) - len(existing)
        print(f"  [{added:+d}] {d['name']:<45} -> {len(merged)} total",
              file=sys.stderr)
        expanded.append({"name": d["name"], "aliases": merged})

    if args.merge:
        for d in departments:
            d["aliases"] = next(
                (e["aliases"] for e in expanded if e["name"] == d["name"]),
                d.get("aliases", []),
            )
        facility_path.write_text(
            json.dumps(facility, indent=2, ensure_ascii=False) + "\n"
        )
        print(f"\nMerged into {facility_path.relative_to(ROOT)}",
              file=sys.stderr)
    else:
        print(json.dumps(expanded, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
