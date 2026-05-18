#!/usr/bin/env python3
"""
Build seeds.jsonl from raw_seeds.json.
Embeds a compact CONTEXT block (not the full facility JSON) into each
seed's system prompt. Extracts the target department from the first
assistant response to determine which department to pre-retrieve.

Run once: python build_seeds.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import (
    FACILITIES_DIR,
    SEEDS_FILE,
    build_context_block,
    load_facilities_parsed,
    load_facility_topologies,
    load_system_prompt,
)

SYSTEM_PROMPT = load_system_prompt()

RAW_SEEDS = SEEDS_FILE.parent / "raw_seeds.json"


def wrap_user(content: str, context_block: str) -> str:
    """Wrap a raw user message with CONTEXT, matching the app's inference
    structure in `GemmaService.sendMessage`:
        CONTEXT:
        <block>

        USER: <raw user>
    The static system prompt stays cacheable; per-query state lives in
    user turns.
    """
    return f"CONTEXT:\n{context_block}\n\nUSER: {content}"


def extract_department_from_messages(messages: list[dict]) -> str | None:
    """Extract the target department name from the first assistant response."""
    for m in messages:
        if m["role"] != "assistant":
            continue
        content = m["content"]
        if isinstance(content, str):
            try:
                blocks = json.loads(content)
            except json.JSONDecodeError:
                continue
        elif isinstance(content, list):
            blocks = content
        else:
            continue

        for block in blocks:
            if isinstance(block, dict):
                if block.get("type") == "destination":
                    return block.get("department")
                if block.get("type") == "disambig":
                    # For disambig seeds, return None -- handled separately
                    return None
        break
    return None


def extract_disambig_options(messages: list[dict]) -> list[str] | None:
    """Extract disambiguation options from the first assistant response."""
    for m in messages:
        if m["role"] != "assistant":
            continue
        content = m["content"]
        if isinstance(content, str):
            try:
                blocks = json.loads(content)
            except json.JSONDecodeError:
                continue
        elif isinstance(content, list):
            blocks = content
        else:
            continue

        for block in blocks:
            if isinstance(block, dict) and block.get("type") == "disambig":
                return block.get("options", [])
        break
    return None


def main():
    with open(RAW_SEEDS) as f:
        raw = json.load(f)

    facilities = load_facilities_parsed()
    topologies = load_facility_topologies()

    SEEDS_FILE.parent.mkdir(parents=True, exist_ok=True)

    skipped = 0
    with open(SEEDS_FILE, "w") as out:
        for seed in raw:
            facility_name = seed["facility"]
            facility_data = facilities.get(facility_name)
            if facility_data is None:
                print(f"WARNING: facility '{facility_name}' not found, skipping seed")
                skipped += 1
                continue

            dept_name = extract_department_from_messages(seed["messages"])
            disambig_options = extract_disambig_options(seed["messages"])
            context_block = build_context_block(
                facility_data,
                department_name=dept_name,
                candidates=disambig_options,
                topology=topologies.get(facility_name),
            )

            # System prompt is static (matches app inference).
            # User turns carry the per-query CONTEXT block.
            messages = [{"role": "system", "content": SYSTEM_PROMPT}]
            for m in seed["messages"]:
                if m["role"] == "user":
                    messages.append({
                        "role": "user",
                        "content": wrap_user(m["content"], context_block),
                    })
                elif m["role"] == "assistant":
                    # Serialize list content to JSON string
                    messages.append({
                        "role": "assistant",
                        "content": json.dumps(m["content"], ensure_ascii=False),
                    })
                else:
                    messages.append(m)

            row = {
                "messages": messages,
                "category": seed["category"],
                "facility": seed["facility"],
            }
            out.write(json.dumps(row, ensure_ascii=False) + "\n")

    print(f"Wrote {len(raw) - skipped} seeds -> {SEEDS_FILE}")


if __name__ == "__main__":
    main()
