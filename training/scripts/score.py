#!/usr/bin/env python3
"""
LLM-as-Judge quality scoring for validated training examples.
Calls the teacher model to score each example on 6 criteria.

Uses the same OpenAI-compatible endpoint as generate.py.

Usage:
  python score.py output/02_validated/raw_2026-04-15_validated.jsonl
  python score.py output/02_validated/raw_2026-04-15_validated.jsonl --threshold 4.0
"""

import argparse
import asyncio
import hashlib
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tqdm import tqdm as _tqdm
from tqdm.asyncio import tqdm_asyncio

from config import (
    CONCURRENCY,
    MODEL,
    OUTPUT_DIR,
    REJECTED_DIR,
    SCORE_THRESHOLD,
    build_criteria_schema,
    ensure_dirs,
    get_client,
    load_criteria,
    load_scoring_rubric,
    render_rubric,
)


CRITERIA_CFG = load_criteria()
SCORING_RUBRIC = render_rubric(load_scoring_rubric(), CRITERIA_CFG)
SCORING_SCHEMA = build_criteria_schema(CRITERIA_CFG)
CRITERIA = [c["key"] for c in CRITERIA_CFG["criteria"]]
NOTES_FIELD = CRITERIA_CFG["notes_field"]


# Retry policy: AWS-style "full jitter" exponential backoff. Ported from
# eval_runner.py. Critical here because score.py runs against the same flaky
# judge endpoints — without retry, a single transient timeout silently
# zero-scores an example and drops it to rejected/.
#   https://aws.amazon.com/blogs/architecture/exponential-backoff-and-jitter/
RETRY_BACKOFF_BASE_S = 2.0
RETRY_BACKOFF_CAP_S = 30.0
RETRY_MAX_ATTEMPTS = 10


def _retry_sleep_seconds(attempt: int) -> float:
    ceiling = min(RETRY_BACKOFF_CAP_S, RETRY_BACKOFF_BASE_S * (2 ** attempt))
    return random.uniform(0, ceiling)


def _example_key(example: dict) -> str:
    """Stable identity for a training example, used to dedup on --resume.

    Examples here don't have explicit ids (unlike eval_suite.jsonl), so we
    hash category + first user-turn content. Stable across runs because the
    teacher's output is the input to scoring — same input bytes, same key.
    """
    first_user = ""
    for m in example.get("messages", []):
        if m.get("role") == "user":
            first_user = m.get("content", "")
            break
    h = hashlib.sha1(
        f"{example.get('category','')}::{first_user}".encode("utf-8")
    ).hexdigest()[:16]
    return h


async def score_example(client, model: str, example: dict) -> dict:
    """Score a single example using LLM-as-Judge, with bounded retries."""
    # Build conversation text (skip system message to save tokens).
    # Use .get() so a malformed message (missing 'role') doesn't crash the
    # whole run — validate.py is supposed to catch these but has a known
    # loophole when the teacher emits {"assistant": "assistant", "content": ...}
    # instead of {"role": "assistant", ...}. Treat unknown-role messages as
    # non-system so they still go to the judge for evaluation.
    conv_messages = [m for m in example["messages"] if m.get("role") != "system"]
    conversation_text = json.dumps(conv_messages, indent=2, ensure_ascii=False)

    prompt = SCORING_RUBRIC.format(conversation=conversation_text)

    for attempt in range(RETRY_MAX_ATTEMPTS):
        try:
            response = await client.chat.completions.create(
                model=model,
                temperature=0,
                max_tokens=16000,
                messages=[{"role": "user", "content": prompt}],
                response_format=SCORING_SCHEMA,
                extra_body={"chat_template_kwargs": {"enable_thinking": False}},
            )
            raw = json.loads(response.choices[0].message.content)
            scores_list = [raw[c] for c in CRITERIA]
            avg = sum(scores_list) / len(scores_list)
            return {
                "scores": scores_list,
                "average": round(avg, 2),
                NOTES_FIELD: raw.get(NOTES_FIELD, ""),
            }
        except Exception as e:
            if attempt < RETRY_MAX_ATTEMPTS - 1:
                wait = _retry_sleep_seconds(attempt)
                _tqdm.write(
                    f"  Judge error (attempt {attempt+1}/{RETRY_MAX_ATTEMPTS}): "
                    f"{e} — retrying in {wait:.1f}s..."
                )
                await asyncio.sleep(wait)
            else:
                return {
                    "scores": [],
                    "average": 0,
                    NOTES_FIELD: f"Judge error after {RETRY_MAX_ATTEMPTS} attempts: {e}",
                }
    return {"scores": [], "average": 0, NOTES_FIELD: "Judge: unreachable"}


async def main():
    parser = argparse.ArgumentParser(description="Score training examples with LLM-as-Judge")
    parser.add_argument("input_file", help="Validated JSONL file to score")
    parser.add_argument("--threshold", type=float, default=SCORE_THRESHOLD,
                       help=f"Minimum average score to keep (default: {SCORE_THRESHOLD})")
    parser.add_argument("--model", type=str, default="gemma4-31b", help="Judge model")
    parser.add_argument("--endpoint", type=str, default="http://localhost:11434/v1", help="Judge endpoint")
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Skip examples already present in the existing _scores.jsonl for this input.",
    )
    args = parser.parse_args()

    input_path = Path(args.input_file)
    if not input_path.exists():
        print(f"ERROR: File not found: {input_path}")
        sys.exit(1)

    ensure_dirs()
    client = get_client(base_url=args.endpoint)

    examples = []
    with open(input_path) as f:
        for line in f:
            line = line.strip()
            if line:
                examples.append(json.loads(line))

    model = args.model

    # Output paths. Stream each example to all three files as it completes,
    # so an interrupted run can be inspected (and resumed via --resume).
    stem = input_path.stem
    scored_file = OUTPUT_DIR / "03_scored" / f"{stem}_scored.jsonl"
    scores_file = OUTPUT_DIR / "03_scored" / f"{stem}_scores.jsonl"
    rejected_file = REJECTED_DIR / f"{stem}_low_score.jsonl"

    # --resume: skip examples whose keys appear in the existing scores file.
    completed_keys: set[str] = set()
    if args.resume and scores_file.exists():
        with open(scores_file) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if "key" in row:
                    completed_keys.add(row["key"])
        print(f"Resume: {len(completed_keys)} already scored in {scores_file.name}")

    pending = [ex for ex in examples if _example_key(ex) not in completed_keys]

    print(f"Scoring {len(pending)} of {len(examples)} with {model} @ {args.endpoint}")
    print(f"Threshold: {args.threshold}/5.0")
    print()

    semaphore = asyncio.Semaphore(CONCURRENCY)
    file_lock = asyncio.Lock()

    # Append mode: resume appends to existing files; fresh runs create them.
    # The summary at the end reads the scores file back, so resume produces
    # an aggregate view across both runs.
    mode = "a" if args.resume else "w"
    out_f = open(scored_file, mode, encoding="utf-8")
    sf_f = open(scores_file, mode, encoding="utf-8")
    rej_f = open(rejected_file, mode, encoding="utf-8")

    async def score_with_limit(ex):
        async with semaphore:
            score = await score_example(client, model, ex)

        avg = score.get("average", 0)
        preview = ""
        if len(ex.get("messages", [])) > 1:
            preview = ex["messages"][1].get("content", "")[:80]
        key = _example_key(ex)

        async with file_lock:
            sf_f.write(json.dumps({
                "key": key,
                "score": score,
                "category": ex.get("category", ""),
                "preview": preview,
            }, ensure_ascii=False) + "\n")
            sf_f.flush()
            if avg >= args.threshold:
                out_f.write(json.dumps(ex, ensure_ascii=False) + "\n")
                out_f.flush()
            else:
                rej_f.write(json.dumps({
                    "score": score,
                    "category": ex.get("category", ""),
                    "preview": preview,
                    "example": ex,
                }, ensure_ascii=False) + "\n")
                rej_f.flush()
        return (ex, score)

    try:
        coroutines = [score_with_limit(ex) for ex in pending]
        if coroutines:
            await tqdm_asyncio.gather(*coroutines, desc="Scoring")
    finally:
        out_f.close()
        sf_f.close()
        rej_f.close()

    # Read the full scores file back so the summary reflects everything
    # (including any prior run merged in via --resume), not just this slice.
    scored_rows: list[dict] = []
    with open(scores_file) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                scored_rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    kept = sum(1 for r in scored_rows if r["score"].get("average", 0) >= args.threshold)
    dropped = len(scored_rows) - kept
    all_averages = [r["score"].get("average", 0) for r in scored_rows]
    # For the per-category breakdown below.
    results = [({"category": r.get("category", "")}, r["score"]) for r in scored_rows]

    # Summary
    print(f"\n✓ Scoring complete")
    print(f"  Total:    {len(results)}")
    print(f"  Kept:     {kept} (avg ≥ {args.threshold})")
    print(f"  Dropped:  {dropped}")
    print(f"  Output:   {scored_file}")
    print(f"  Scores:   {scores_file}")
    if dropped > 0:
        print(f"  Rejected: {rejected_file}")

    if all_averages:
        print(f"\n  Score distribution:")
        print(f"    Mean:   {sum(all_averages) / len(all_averages):.2f}")
        print(f"    Min:    {min(all_averages):.1f}")
        print(f"    Max:    {max(all_averages):.1f}")

        # Histogram
        buckets = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
        for avg in all_averages:
            bucket = max(1, min(5, int(avg)))
            buckets[bucket] += 1
        print(f"    Distribution: ", end="")
        for b, c in sorted(buckets.items()):
            print(f"{b}★={c} ", end="")
        print()

    # Per-category breakdown
    cat_scores: dict[str, list[float]] = {}
    for example, score in results:
        cat = example.get("category", "unknown")
        cat_scores.setdefault(cat, []).append(score.get("average", 0))

    if len(cat_scores) > 1:
        print(f"\n  Per-category averages:")
        for cat, scores in sorted(cat_scores.items()):
            avg = sum(scores) / len(scores) if scores else 0
            print(f"    {cat}: {avg:.2f} ({len(scores)} examples)")


if __name__ == "__main__":
    asyncio.run(main())
