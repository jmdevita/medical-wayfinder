#!/usr/bin/env python3
"""
Mine downloaded CallCenterEN transcripts for healthcare navigation phrases.

Reads raw JSON transcript files, filters for healthcare + navigation keywords,
and extracts relevant calls.

Usage:
  python mine_callcenter.py                          # Mine all downloaded folders
  python mine_callcenter.py --folder medicare_inbound  # Mine specific folder
"""

import argparse
import json
from pathlib import Path
from tqdm import tqdm

RAW_DIR = Path(__file__).parent / "raw"
OUTPUT_DIR = Path(__file__).parent / "mined"
OUTPUT_DIR.mkdir(exist_ok=True)

# Keywords that suggest healthcare/medical context
HEALTHCARE_KEYWORDS = [
    "doctor", "hospital", "clinic", "medical", "health", "patient",
    "appointment", "prescription", "pharmacy", "lab", "laboratory",
    "nurse", "emergency", "urgent care", "check-in", "check in",
    "insurance", "medicare", "medicaid", "copay", "referral",
    "specialist", "primary care", "pediatric", "cardiology",
    "radiology", "x-ray", "xray", "mri", "ultrasound",
    "blood draw", "blood test", "blood work", "phlebotomy",
    "vaccination", "vaccine", "immunization",
    "dental", "dentist", "optometry", "ophthalmology", "eye doctor",
    "physical therapy", "therapy", "counselor", "behavioral health",
    "ob/gyn", "obgyn", "gynecology", "maternity", "prenatal",
    "dermatology", "dermatologist", "allergy", "allergist",
    "surgery", "surgeon", "oncology", "cancer",
]

# Keywords that suggest navigation/wayfinding/scheduling
NAVIGATION_KEYWORDS = [
    "where", "direction", "how do i get", "how to get", "find",
    "located", "location", "floor", "building", "room",
    "parking", "entrance", "lobby", "elevator", "stairs",
    "check in", "check-in", "front desk", "reception",
    "waiting room", "waiting area",
    "which way", "lost", "can't find", "looking for",
    "schedule", "appointment", "book", "reschedule", "cancel",
    "what time", "hours", "open", "close",
    "walk-in", "walk in", "address",
]


def has_keywords(text: str, keywords: list[str]) -> list[str]:
    text_lower = text.lower()
    return [kw for kw in keywords if kw in text_lower]


def mine_folder(folder: Path) -> tuple[list[dict], list[dict]]:
    """Mine a single folder of JSON transcripts. Returns (gold, silver)."""
    gold = []
    silver = []
    json_files = list(folder.glob("*.json"))

    for f in tqdm(json_files, desc=f"  {folder.name}"):
        try:
            with open(f) as fh:
                data = json.load(fh)
            text = data.get("text", "")
            if not text:
                continue
        except (json.JSONDecodeError, KeyError):
            continue

        health_matches = has_keywords(text, HEALTHCARE_KEYWORDS)
        nav_matches = has_keywords(text, NAVIGATION_KEYWORDS)

        record = {
            "file": f.name,
            "folder": folder.name,
            "text": text,
            "confidence": data.get("confidence", 0),
            "duration_s": data.get("audio_duration", 0),
        }

        if health_matches and nav_matches:
            record["healthcare_keywords"] = health_matches
            record["navigation_keywords"] = nav_matches
            record["tier"] = "gold"
            gold.append(record)
        elif health_matches:
            record["healthcare_keywords"] = health_matches
            record["tier"] = "silver"
            silver.append(record)

    return gold, silver


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--folder", type=str, help="Mine only this subfolder")
    args = parser.parse_args()

    # Find all unzipped transcript folders
    if args.folder:
        folders = [RAW_DIR / args.folder]
    else:
        folders = [d for d in RAW_DIR.iterdir() if d.is_dir()]

    if not folders:
        print("No transcript folders found in real_data/raw/")
        print("Download and unzip datasets first.")
        return

    print(f"Mining {len(folders)} folder(s)...")

    all_gold = []
    all_silver = []

    for folder in sorted(folders):
        gold, silver = mine_folder(folder)
        all_gold.extend(gold)
        all_silver.extend(silver)
        print(f"    → {len(gold)} gold, {len(silver)} silver")

    # Save results
    gold_file = OUTPUT_DIR / "callcenter_gold_navigation.jsonl"
    with open(gold_file, "w") as f:
        for call in all_gold:
            f.write(json.dumps(call, ensure_ascii=False) + "\n")

    silver_file = OUTPUT_DIR / "callcenter_silver_healthcare.jsonl"
    with open(silver_file, "w") as f:
        for call in all_silver:
            f.write(json.dumps(call, ensure_ascii=False) + "\n")

    # Summary
    print(f"\n{'='*60}")
    print(f"MINING RESULTS")
    print(f"{'='*60}")
    print(f"Healthcare + Navigation (gold): {len(all_gold)}")
    print(f"Healthcare only (silver):       {len(all_silver)}")
    print(f"\nGold → {gold_file}")
    print(f"Silver → {silver_file}")

    # Top keywords
    if all_gold:
        nav_kw = {}
        health_kw = {}
        for call in all_gold:
            for kw in call.get("navigation_keywords", []):
                nav_kw[kw] = nav_kw.get(kw, 0) + 1
            for kw in call.get("healthcare_keywords", []):
                health_kw[kw] = health_kw.get(kw, 0) + 1

        print(f"\nTop navigation keywords (gold):")
        for kw, count in sorted(nav_kw.items(), key=lambda x: -x[1])[:15]:
            print(f"  {kw}: {count}")

        print(f"\nTop healthcare keywords (gold):")
        for kw, count in sorted(health_kw.items(), key=lambda x: -x[1])[:15]:
            print(f"  {kw}: {count}")


if __name__ == "__main__":
    main()
