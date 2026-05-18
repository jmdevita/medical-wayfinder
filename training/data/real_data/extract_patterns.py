#!/usr/bin/env python3
"""
Extract natural language navigation patterns from CVDN, RxR, and Talk the Walk.

Categorizes extracted text into:
  - asking_directions: how people ask for help ("where is...", "how do I get to...")
  - giving_directions: step-by-step instruction language ("turn left", "walk past")
  - landmarks: how people describe what they see ("I see a red building")
  - confusion: lost/confused language ("I can't find", "I think I'm near")
  - clarification: follow-up questions ("should I go left or right?")

Output: real_data/mined/patterns.json (organized by category)
"""

import json
import re
from pathlib import Path

RAW_DIR = Path(__file__).parent / "raw"
OUTPUT_DIR = Path(__file__).parent / "mined"
OUTPUT_DIR.mkdir(exist_ok=True)

# Pattern matchers for categorization
ASKING_PATTERNS = [
    r"where (?:is|are|do|can|should)",
    r"how do I (?:get|find|go)",
    r"how to get",
    r"which way",
    r"can you (?:tell|show|help|direct)",
    r"I need to (?:find|get to|go to)",
    r"I'm looking for",
    r"where's the",
    r"do you know where",
    r"point me to",
    r"I have (?:an? )?appointment",
    r"take me to",
]

GIVING_PATTERNS = [
    r"turn (?:left|right|around)",
    r"go (?:straight|forward|through|past|toward|down|up|left|right|to the)",
    r"walk (?:straight|forward|through|past|toward|down|to the|between|along)",
    r"head (?:toward|to|down|straight)",
    r"follow the",
    r"take the (?:elevator|stairs|hallway|door|first|second)",
    r"you(?:'ll| will) (?:see|find|reach|pass|come to|arrive)",
    r"on your (?:left|right)",
    r"continue (?:straight|down|past|through)",
    r"enter (?:through|the)",
    r"exit (?:through|the)",
    r"cross the",
    r"stay on",
]

LANDMARK_PATTERNS = [
    r"I (?:see|can see|notice|spot)",
    r"there(?:'s| is) (?:a|an|the)",
    r"(?:next to|beside|near|across from|in front of|behind|diagonal from)",
    r"on the corner",
    r"(?:red|blue|white|glass|brick|metal|wooden) (?:building|door|sign|wall)",
    r"(?:sign|signs) (?:that says|saying|for|reading)",
    r"looks like (?:a|an|the)",
    r"I(?:'m| am) (?:at|by|near|next to|in front of|standing)",
]

CONFUSION_PATTERNS = [
    r"I(?:'m| am) lost",
    r"I can(?:'t| not) find",
    r"I don(?:'t| not) (?:know|see|understand)",
    r"I(?:'m| am) (?:confused|not sure|unsure)",
    r"(?:hard|difficult|tough) to (?:tell|see|read|find)",
    r"I think I(?:'m| am) (?:near|at|by|in)",
    r"I(?:'ve| have) been (?:walking|looking|wandering)",
    r"is (?:this|that) (?:the right|the correct|where)",
    r"am I (?:in|at|near|going|on) the (?:right|correct|wrong)",
    r"I(?:'m| am) not sure (?:where|which|if|what)",
    r"did I (?:pass|miss|go)",
]

CLARIFICATION_PATTERNS = [
    r"should I (?:go|turn|take|stay|keep|head)",
    r"(?:left|right|straight|up|down)\??$",
    r"do (?:I|you) (?:mean|want me to)",
    r"which (?:way|direction|door|hallway|floor|building|one)",
    r"can you (?:be more specific|clarify|repeat|explain)",
    r"what (?:do you mean|should I|does)",
    r"is it (?:the|on the|to the)",
    r"you said",
]


def categorize(text: str) -> list[str]:
    """Return which categories a text snippet matches."""
    text_lower = text.lower().strip()
    cats = []
    for name, patterns in [
        ("asking_directions", ASKING_PATTERNS),
        ("giving_directions", GIVING_PATTERNS),
        ("landmarks", LANDMARK_PATTERNS),
        ("confusion", CONFUSION_PATTERNS),
        ("clarification", CLARIFICATION_PATTERNS),
    ]:
        for pat in patterns:
            if re.search(pat, text_lower):
                cats.append(name)
                break
    return cats


def extract_cvdn() -> list[dict]:
    """Extract dialog turns from CVDN."""
    path = RAW_DIR / "cvdn" / "tasks" / "CVDN" / "data" / "train.json"
    with open(path) as f:
        data = json.load(f)

    results = []
    for dialog in data:
        for turn in dialog.get("dialog_history", []):
            msg = turn["message"].strip()
            if len(msg) < 5:
                continue
            cats = categorize(msg)
            if cats:
                results.append({
                    "text": msg,
                    "role": turn["role"],  # navigator or oracle
                    "categories": cats,
                    "source": "cvdn",
                })
    return results


def extract_rxr() -> list[dict]:
    """Extract navigation instructions from RxR."""
    path = RAW_DIR / "rxr" / "rxr_en_train.jsonl"
    results = []

    with open(path) as f:
        for line in f:
            d = json.loads(line)
            if not d.get("language", "").startswith("en"):
                continue
            instruction = d["instruction"].strip()
            if len(instruction) < 10:
                continue

            # Split into sentences for finer-grained categorization
            sentences = re.split(r'[.!]\s+', instruction)
            for sent in sentences:
                sent = sent.strip()
                if len(sent) < 10:
                    continue
                cats = categorize(sent)
                if cats:
                    results.append({
                        "text": sent,
                        "categories": cats,
                        "source": "rxr",
                    })

    return results


def extract_ttw() -> list[dict]:
    """Extract dialog turns from Talk the Walk."""
    path = RAW_DIR / "talk_the_walk" / "data" / "talkthewalk.train.json"
    with open(path) as f:
        data = json.load(f)

    results = []
    for dialog in data:
        for turn in dialog.get("dialog", []):
            if not isinstance(turn, dict):
                continue
            text = turn.get("text", "").strip()
            # Skip action commands
            if text.startswith("ACTION:") or text.startswith("EVALUATE_"):
                continue
            if len(text) < 5:
                continue
            cats = categorize(text)
            if cats:
                results.append({
                    "text": text,
                    "role": turn.get("id", "unknown").lower(),
                    "categories": cats,
                    "source": "talk_the_walk",
                })
    return results


def main():
    print("Extracting navigation patterns...\n")

    all_patterns = []

    # CVDN
    print("  CVDN...", end=" ", flush=True)
    cvdn = extract_cvdn()
    all_patterns.extend(cvdn)
    print(f"{len(cvdn)} patterns")

    # RxR
    print("  RxR...", end=" ", flush=True)
    rxr = extract_rxr()
    all_patterns.extend(rxr)
    print(f"{len(rxr)} patterns")

    # Talk the Walk
    print("  Talk the Walk...", end=" ", flush=True)
    ttw = extract_ttw()
    all_patterns.extend(ttw)
    print(f"{len(ttw)} patterns")

    # Organize by category
    by_category = {}
    for p in all_patterns:
        for cat in p["categories"]:
            by_category.setdefault(cat, []).append(p)

    # Deduplicate within each category (by lowercased text)
    for cat in by_category:
        seen = set()
        deduped = []
        for p in by_category[cat]:
            key = p["text"].lower().strip()
            if key not in seen:
                seen.add(key)
                deduped.append(p)
        by_category[cat] = deduped

    # Save full patterns
    output_file = OUTPUT_DIR / "patterns.json"
    with open(output_file, "w") as f:
        json.dump(by_category, f, indent=2, ensure_ascii=False)

    # Save a curated "best of" — natural-length phrases (not too short, not too long)
    best_of = {}
    for cat, patterns in by_category.items():
        # Filter: at least 30 chars, at most 200, and at least 5 words
        filtered = [p for p in patterns
                    if 30 <= len(p["text"]) <= 200
                    and len(p["text"].split()) >= 5]
        # Sort by length (prefer concise but complete phrases)
        filtered.sort(key=lambda p: len(p["text"]))
        # Take top 200 per category
        best_of[cat] = [p["text"] for p in filtered[:200]]

    best_file = OUTPUT_DIR / "best_phrases.json"
    with open(best_file, "w") as f:
        json.dump(best_of, f, indent=2, ensure_ascii=False)

    # Report
    print(f"\n{'='*60}")
    print(f"EXTRACTION RESULTS")
    print(f"{'='*60}")
    print(f"Total patterns: {len(all_patterns)}")
    print(f"\nBy category:")
    for cat in sorted(by_category.keys()):
        print(f"  {cat}: {len(by_category[cat])}")

    print(f"\nBy source:")
    source_counts = {}
    for p in all_patterns:
        source_counts[p["source"]] = source_counts.get(p["source"], 0) + 1
    for src, count in sorted(source_counts.items()):
        print(f"  {src}: {count}")

    # Show samples from each category
    print(f"\n{'='*60}")
    print(f"SAMPLE PHRASES")
    print(f"{'='*60}")
    for cat in sorted(by_category.keys()):
        print(f"\n  --- {cat} ---")
        samples = by_category[cat][:8]
        for s in samples:
            text = s["text"][:100]
            print(f"    \"{text}\"")

    print(f"\nFull output: {output_file}")
    print(f"Best phrases: {best_file}")


if __name__ == "__main__":
    main()
