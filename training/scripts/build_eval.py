#!/usr/bin/env python3
"""
Build the eval suite from raw_eval.json.
Embeds a compact CONTEXT block into each example's system prompt,
matching the pre-retrieval orchestration architecture.

Run once: python build_eval.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import (
    EVAL_DIR,
    build_context_block,
    load_facilities_parsed,
    load_facility_topologies,
    load_system_prompt,
)

SYSTEM_PROMPT = load_system_prompt()

RAW_EVAL = EVAL_DIR / "raw_eval.json"


def build_context_for_example(facility_data: dict, expected: str,
                              topology: dict | None = None) -> str:
    """Resolve the eval case to a CONTEXT block.

    Looks for a department named in the `expected` field; falls back to a
    facility-name-only block (still valid input for the model).
    """
    dept_name = None
    for dept in facility_data.get("departments", []):
        if dept["name"].lower() in expected.lower():
            dept_name = dept["name"]
            break

    return build_context_block(
        facility_data,
        department_name=dept_name,
        candidates=None,
        topology=topology,
    )


def main():
    with open(RAW_EVAL) as f:
        examples = json.load(f)

    facilities = load_facilities_parsed()
    topologies = load_facility_topologies()
    output_file = EVAL_DIR / "eval_suite.jsonl"

    for ex in examples:
        facility_data = facilities.get(ex["facility"])
        if facility_data is None:
            print(f"WARNING: facility '{ex['facility']}' not found, skipping")
            continue
        # Match app inference (GemmaService.sendMessage) and training data:
        # system stays static, CONTEXT travels in the user turn.
        context = build_context_for_example(
            facility_data, ex.get("expected", ""),
            topology=topologies.get(ex["facility"]),
        )
        ex["system_prompt"] = SYSTEM_PROMPT
        ex["context_block"] = context
        ex["wrapped_user_message"] = (
            f"CONTEXT:\n{context}\n\nUSER: {ex['user_message']}"
        )

    with open(output_file, "w") as f:
        for ex in examples:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")

    # Summary
    categories = {}
    for ex in examples:
        cat = ex["category"]
        categories[cat] = categories.get(cat, 0) + 1

    print(f"Wrote {len(examples)} eval examples -> {output_file}")
    print(f"\nCategory distribution:")
    for cat, count in sorted(categories.items()):
        print(f"  {cat}: {count}")


if __name__ == "__main__":
    main()
