#!/usr/bin/env python3
"""
Generate synthetic training conversations using a teacher model.

Uses any OpenAI-compatible endpoint (llama-swap, Ollama, vLLM, Claude).
Configure via environment variables or config.py.

Usage:
  python generate.py                    # Generate with default settings
  python generate.py --batches 10       # Override total batches (for testing)
  python generate.py --category clean_resolution_en  # Generate one category only
"""

import argparse
import asyncio
import json
import random
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tqdm import tqdm as _tqdm
from tqdm.asyncio import tqdm_asyncio

from config import (
    BATCH_SIZE,
    CONCURRENCY,
    MODEL,
    TEMPERATURE,
    OUTPUT_DIR,
    REJECTED_DIR,
    build_context_block,
    ensure_dirs,
    get_client,
    load_categories,
    load_facilities,
    load_facilities_parsed,
    load_facility_topologies,
    load_generation_prompt,
    load_seeds,
    load_system_prompt,
)

PHRASES_FILE = Path(__file__).resolve().parent.parent / "data" / "real_data" / "mined" / "best_phrases.json"


def load_real_phrases() -> dict[str, list[str]]:
    """Load mined phrases from navigation datasets."""
    if not PHRASES_FILE.exists():
        return {}
    with open(PHRASES_FILE) as f:
        return json.load(f)


def sample_phrases(all_phrases: dict, phrase_buckets: list[str], n: int = 15) -> str:
    """Sample relevant phrases from the given mined-phrase buckets."""
    if not all_phrases:
        return "(no real phrases available)"

    pool = []
    for pc in phrase_buckets:
        pool.extend(all_phrases.get(pc, []))

    if not pool:
        return "(no real phrases available)"

    sampled = random.sample(pool, min(n, len(pool)))
    return "\n".join(f"- \"{p}\"" for p in sampled)


async def generate_batch(
    client,
    model: str,
    generation_prompt_template: str,
    system_prompt_template: str,
    facility_data: str,
    facility_parsed: dict,
    facility_name: str,
    category: str,
    category_cfg: dict,
    seeds: list[dict],
    batch_size: int,
    all_phrases: dict,
    topology: dict | None = None,
) -> list[dict]:
    """Generate one batch of training examples."""
    few_shot = random.sample(seeds, min(3, len(seeds)))
    # Strip system messages from few-shot to save tokens (they're huge with facility JSON)
    few_shot_compact = []
    for s in few_shot:
        compact = {
            "messages": [m for m in s["messages"] if m["role"] != "system"],
            "category": s.get("category", ""),
        }
        few_shot_compact.append(compact)

    few_shot_text = json.dumps(few_shot_compact, indent=2, ensure_ascii=False)
    real_phrases = sample_phrases(all_phrases, category_cfg["phrase_buckets"])

    prompt = generation_prompt_template.format(
        batch_size=batch_size,
        category=category,
        category_instructions=category_cfg["instructions"],
        facility_data=facility_data,
        few_shot_examples=few_shot_text,
        real_phrases=real_phrases,
    )

    response = await client.chat.completions.create(
        model=model,
        temperature=TEMPERATURE,
        max_tokens=8192,
        messages=[{"role": "user", "content": prompt}],
    )

    text = response.choices[0].message.content.strip()

    # Strip thinking tags if present (Qwen, DeepSeek, etc.)
    import re
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip()

    # Strip markdown fences if present
    if text.startswith("```"):
        text = text.split("\n", 1)[1]
        text = text.rsplit("```", 1)[0].strip()

    # strict=False allows raw \n and \t inside string values — some teacher
    # models (qwen, deepseek) emit unescaped newlines in long content fields.
    try:
        examples = json.loads(text, strict=False)
    except json.JSONDecodeError:
        # Fallback: extract the first top-level JSON array from surrounding prose.
        match = re.search(r'\[.*\]', text, flags=re.DOTALL)
        if not match:
            raise
        examples = json.loads(match.group(0), strict=False)

    # Build compact context block per example based on the department
    # in the first assistant response (instead of full facility dump)
    for ex in examples:
        if not isinstance(ex, dict) or "messages" not in ex:
            continue

        # Extract department from assistant's first response
        dept_name = None
        disambig_options = None
        for m in ex["messages"]:
            if m.get("role") != "assistant":
                continue
            try:
                blocks = json.loads(m["content"]) if isinstance(m["content"], str) else m["content"]
            except (json.JSONDecodeError, TypeError):
                break
            for block in (blocks if isinstance(blocks, list) else []):
                if isinstance(block, dict):
                    if block.get("type") == "destination":
                        dept_name = block.get("department")
                    elif block.get("type") == "disambig":
                        disambig_options = block.get("options", [])
            break

        if dept_name is None and not disambig_options:
            _tqdm.write(f"  WARNING: Generated example has no destination/disambig block, "
                        f"context will be facility-name-only [{category}/{facility_name}]")

        context = build_context_block(
            facility_parsed,
            department_name=dept_name,
            candidates=disambig_options,
            topology=topology,
        )

        # Align training shape with app inference (GemmaService.sendMessage):
        # - system message = static system_prompt.txt verbatim (cacheable)
        # - each user turn = "CONTEXT:\n<block>\n\nUSER: <raw user>"
        # Strip whatever system message the teacher emitted; we own that slot.
        non_system = [m for m in ex["messages"] if m.get("role") != "system"]
        rewrapped = [{"role": "system", "content": system_prompt_template}]
        for m in non_system:
            if m.get("role") == "user":
                rewrapped.append({
                    "role": "user",
                    "content": f"CONTEXT:\n{context}\n\nUSER: {m.get('content', '')}",
                })
            else:
                rewrapped.append(m)
        ex["messages"] = rewrapped

        ex["category"] = category
        ex["facility"] = facility_name

    return examples


async def main():
    parser = argparse.ArgumentParser(description="Generate synthetic training data")
    parser.add_argument("--batches", type=int, help="Override total batches per category")
    parser.add_argument("--category", type=str, help="Generate only this category")
    parser.add_argument("--model", type=str, default="gemma4-31b", help="Teacher model")
    parser.add_argument("--endpoint", type=str, default="http://localhost:11434/v1", help="Teacher endpoint")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate configs/seeds/facilities and print the generation plan; do not call the teacher.",
    )
    args = parser.parse_args()

    ensure_dirs()

    categories_cfg = load_categories()

    seeds = load_seeds()
    if not seeds:
        print("ERROR: No seeds found. Run `python build_seeds.py` first.")
        sys.exit(1)

    facilities = load_facilities()
    facilities_parsed = load_facilities_parsed()
    topologies = load_facility_topologies()
    if not facilities:
        print("ERROR: No facility JSON files found in facilities/")
        sys.exit(1)

    system_prompt_template = load_system_prompt()
    generation_prompt_template = load_generation_prompt()
    client = get_client(base_url=args.endpoint)
    all_phrases = load_real_phrases()
    if all_phrases:
        total_phrases = sum(len(v) for v in all_phrases.values())
        print(f"Real phrases loaded: {total_phrases} across {len(all_phrases)} categories")
    else:
        print("No real phrases found (run real_data/extract_patterns.py first)")

    # Build task list
    selected = categories_cfg
    if args.category:
        if args.category not in categories_cfg:
            print(f"ERROR: Unknown category '{args.category}'")
            print(f"Available: {', '.join(categories_cfg.keys())}")
            sys.exit(1)
        selected = {args.category: categories_cfg[args.category]}

    tasks = []
    for category, cfg in selected.items():
        count = args.batches if args.batches else cfg.get("batches", 5)
        for _ in range(count):
            facility_name = random.choice(list(facilities.keys()))
            facility_data = facilities[facility_name]
            facility_parsed = facilities_parsed[facility_name]
            topology = topologies.get(facility_name)
            tasks.append((category, cfg, facility_name, facility_data, facility_parsed, topology))

    model = args.model
    total_expected = len(tasks) * BATCH_SIZE
    print(f"Generating {total_expected} examples ({len(tasks)} batches × {BATCH_SIZE})")
    print(f"Teacher: {model} @ {args.endpoint}")
    print(f"Categories: {len(selected)}")
    print(f"Facilities: {', '.join(facilities.keys())}")
    print()

    if args.dry_run:
        print("Dry run: configs/seeds/facilities loaded OK, plan above. Exiting before teacher calls.")
        return

    # Stream each successful batch to disk as soon as it finishes so a
    # crashed teacher endpoint (or Ctrl-C) costs you the in-flight batches,
    # not the whole run.
    timestamp = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
    output_file = OUTPUT_DIR / "01_raw" / f"raw_{timestamp}.jsonl"
    out_f = open(output_file, "a", encoding="utf-8")
    file_lock = asyncio.Lock()

    all_examples = []
    errors = []
    semaphore = asyncio.Semaphore(CONCURRENCY)
    import time

    batch_counter = {"n": 0}

    async def run_batch(category, category_cfg, facility_name, facility_data, facility_parsed, topology):
        async with semaphore:
            batch_counter["n"] += 1
            batch_id = batch_counter["n"]
            start = time.time()
            _tqdm.write(f"  → start  #{batch_id:<3} [{category}/{facility_name}]")
            try:
                result = await generate_batch(
                    client,
                    model,
                    generation_prompt_template,
                    system_prompt_template,
                    facility_data,
                    facility_parsed,
                    facility_name,
                    category,
                    category_cfg,
                    seeds,
                    BATCH_SIZE,
                    all_phrases,
                    topology=topology,
                )
                _tqdm.write(f"  ✓ done   #{batch_id:<3} [{category}/{facility_name}] {time.time()-start:.0f}s → {len(result)} examples")
                async with file_lock:
                    for ex in result:
                        out_f.write(json.dumps(ex, ensure_ascii=False) + "\n")
                    out_f.flush()
                return result
            except Exception as e:
                _tqdm.write(f"  ✗ err1   #{batch_id:<3} [{category}/{facility_name}] {time.time()-start:.0f}s → {type(e).__name__}: {str(e)[:80]}")
                errors.append({
                    "category": category,
                    "facility": facility_name,
                    "error": str(e),
                    "attempt": 1,
                })
                # Retry once after delay
                await asyncio.sleep(2)
                retry_start = time.time()
                try:
                    result = await generate_batch(
                        client,
                        model,
                        generation_prompt_template,
                        system_prompt_template,
                        facility_data,
                        facility_parsed,
                        facility_name,
                        category,
                        category_cfg,
                        seeds,
                        BATCH_SIZE,
                        all_phrases,
                        topology=topology,
                    )
                    _tqdm.write(f"  ✓ retry  #{batch_id:<3} [{category}/{facility_name}] {time.time()-retry_start:.0f}s → {len(result)} examples")
                    async with file_lock:
                        for ex in result:
                            out_f.write(json.dumps(ex, ensure_ascii=False) + "\n")
                        out_f.flush()
                    return result
                except Exception as e2:
                    _tqdm.write(f"  ✗ err2   #{batch_id:<3} [{category}/{facility_name}] {time.time()-retry_start:.0f}s → {type(e2).__name__}: {str(e2)[:80]}")
                    errors.append({
                        "category": category,
                        "facility": facility_name,
                        "error": f"Retry failed: {e2}",
                        "attempt": 2,
                    })
                    return []

    # Run all batches with progress bar (each batch streams itself to disk
    # via run_batch -> file_lock above; we just collect for the in-memory
    # summary below).
    coroutines = [run_batch(cat, cfg, fn, fd, fp, topo) for cat, cfg, fn, fd, fp, topo in tasks]
    try:
        results = await tqdm_asyncio.gather(*coroutines, desc="Generating")
    finally:
        out_f.close()

    for batch in results:
        if isinstance(batch, list):
            all_examples.extend(batch)

    # Save errors if any
    if errors:
        error_file = REJECTED_DIR / f"generation_errors_{timestamp}.jsonl"
        with open(error_file, "w") as f:
            for err in errors:
                f.write(json.dumps(err) + "\n")
        print(f"\n⚠ {len(errors)} errors → {error_file}")

    # Summary
    print(f"\n✓ Generated {len(all_examples)} examples → {output_file}")

    # Category breakdown
    cat_counts = {}
    for ex in all_examples:
        cat = ex.get("category", "unknown")
        cat_counts[cat] = cat_counts.get(cat, 0) + 1
    print("\nCategory distribution:")
    for cat, count in sorted(cat_counts.items()):
        print(f"  {cat}: {count}")


if __name__ == "__main__":
    asyncio.run(main())
