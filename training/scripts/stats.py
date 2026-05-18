#!/usr/bin/env python3
"""
Print statistics for any JSONL dataset file.
No dependencies — uses stdlib only.

Usage:
  python stats.py output/03_scored/whatever_scored.jsonl
  python stats.py seeds/seeds.jsonl
"""

import json
import sys
from pathlib import Path


def detect_language(text: str) -> str:
    """Simple heuristic to detect Spanish vs English."""
    spanish_markers = ["donde", "necesito", "está", "estoy", "quiero",
                       "como llego", "dónde", "ayuda", "doctor de los"]
    text_lower = text.lower()
    for marker in spanish_markers:
        if marker in text_lower:
            return "es"
    return "en"


def main():
    if len(sys.argv) < 2:
        print("Usage: python stats.py <file.jsonl>")
        sys.exit(1)

    input_path = Path(sys.argv[1])
    if not input_path.exists():
        print(f"ERROR: File not found: {input_path}")
        sys.exit(1)

    examples = []
    with open(input_path) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    examples.append(json.loads(line))
                except json.JSONDecodeError:
                    pass

    if not examples:
        print("No examples found.")
        sys.exit(0)

    print(f"\n{'='*50}")
    print(f"Dataset: {input_path.name}")
    print(f"{'='*50}")
    print(f"\nTotal examples: {len(examples)}")

    # --- Category distribution ---
    categories = {}
    for ex in examples:
        cat = ex.get("category", "untagged")
        categories[cat] = categories.get(cat, 0) + 1

    if categories and not (len(categories) == 1 and "untagged" in categories):
        print(f"\nCategories:")
        for cat, count in sorted(categories.items(), key=lambda x: -x[1]):
            pct = count / len(examples) * 100
            bar = "█" * int(pct / 2)
            print(f"  {cat:30s} {count:4d} ({pct:4.1f}%) {bar}")

    # --- Facility distribution ---
    facilities = {}
    for ex in examples:
        fac = ex.get("facility", "untagged")
        facilities[fac] = facilities.get(fac, 0) + 1

    if facilities and not (len(facilities) == 1 and "untagged" in facilities):
        print(f"\nFacilities:")
        for fac, count in sorted(facilities.items(), key=lambda x: -x[1]):
            pct = count / len(examples) * 100
            print(f"  {fac:30s} {count:4d} ({pct:4.1f}%)")

    # --- Language distribution ---
    languages = {"en": 0, "es": 0}
    for ex in examples:
        messages = ex.get("messages", [])
        user_msgs = [m for m in messages if m.get("role") == "user"]
        if user_msgs:
            lang = detect_language(user_msgs[0].get("content", ""))
            languages[lang] += 1

    if sum(languages.values()) > 0:
        print(f"\nLanguage:")
        for lang, count in sorted(languages.items(), key=lambda x: -x[1]):
            pct = count / len(examples) * 100
            label = "English" if lang == "en" else "Spanish"
            print(f"  {label:30s} {count:4d} ({pct:4.1f}%)")

    # --- Turn count ---
    turn_counts = []
    for ex in examples:
        messages = ex.get("messages", [])
        turns = len([m for m in messages if m.get("role") != "system"])
        turn_counts.append(turns)

    if turn_counts:
        avg_turns = sum(turn_counts) / len(turn_counts)
        print(f"\nTurns (non-system):")
        print(f"  Average: {avg_turns:.1f}")
        print(f"  Min: {min(turn_counts)}, Max: {max(turn_counts)}")

    # --- Score distribution (if present) ---
    # Check if examples have scores (from score.py output)
    scores = []
    for ex in examples:
        if "score" in ex:
            avg = ex["score"].get("average", 0)
            if avg > 0:
                scores.append(avg)
        elif "average" in ex:
            scores.append(ex["average"])

    if scores:
        print(f"\nScores:")
        print(f"  Mean:   {sum(scores) / len(scores):.2f}")
        print(f"  Median: {sorted(scores)[len(scores) // 2]:.2f}")
        print(f"  Min:    {min(scores):.1f}")
        print(f"  Max:    {max(scores):.1f}")

        # Histogram
        buckets = {}
        for s in scores:
            b = round(s, 0)
            buckets[b] = buckets.get(b, 0) + 1
        print(f"  Distribution:")
        for b in sorted(buckets.keys()):
            count = buckets[b]
            bar = "█" * count
            print(f"    {b:.0f}★: {count:3d} {bar}")

    print()


if __name__ == "__main__":
    main()
