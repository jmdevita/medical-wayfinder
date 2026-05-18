#!/usr/bin/env python3
"""
Run the eval suite against a model and score responses.

Concurrent: target + judge calls are issued up to CONCURRENCY in flight,
matching llama-swap's slot count (see config.py).

Usage:
  # Eval base Gemma E2B (local) with Qwen judge (remote)
  OPENAI_BASE_URL=http://localhost:11434/v1 OPENAI_MODEL=gemma4:e2b \
    python eval_runner.py --judge-model qwen3.5-122b --judge-endpoint http://your-llm-host:11434/v1

  # Quick test (first 5 examples)
  python eval_runner.py --limit 5

  # Eval a specific category
  python eval_runner.py --category multilingual

To tweak evaluation criteria, edit these files under training/data/prompts/:
  - criteria.json   — single source of truth. Add/remove/reorder criteria,
                      edit labels/descriptions/scales. Shared with score.py.
  - eval_rubric.txt — preamble + {criteria_block} placeholder. Edit only to
                      change the judge's framing, not the criterion list.
The criterion list and schema are built from criteria.json at load time; no
Python changes are needed to experiment with different criteria.
"""

import argparse
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from tqdm import tqdm as _tqdm
from tqdm.asyncio import tqdm_asyncio

from config import (
    BASE_URL,
    CONCURRENCY,
    EVAL_DIR,
    EVAL_RESULTS_DIR,
    MODEL,
    build_criteria_schema,
    ensure_dirs,
    get_client,
    load_criteria,
    load_eval_rubric,
    render_rubric,
)
from eval_checks import deterministic_checks

CRITERIA_CFG = load_criteria()
EVAL_SCHEMA = build_criteria_schema(CRITERIA_CFG)
EVAL_RUBRIC = render_rubric(load_eval_rubric(), CRITERIA_CFG)

CRITERIA: list[str] = [c["key"] for c in CRITERIA_CFG["criteria"]]
NOTES_FIELD: str = CRITERIA_CFG["notes_field"]

# Pass/fail thresholds. PASS_FLOORS applies per-criterion minima on top of the
# average; entries whose criterion doesn't exist in the schema are ignored.
PASS_AVG: float = 3.5
PASS_FLOORS: dict[str, int] = {"correctness": 4}


def _example_key(d: dict) -> str:
    """Stable identity for an eval example, used to match on resume.

    Prefers the eval suite's `id` when present; falls back to a
    (facility, user_message) tuple. Eval results carry both `user_message`
    and `facility` at the top level; raw eval inputs carry `id` too.
    """
    if d.get("id"):
        return f"id:{d['id']}"
    return f"fum:{d.get('facility','')}::{d.get('user_message','')}"


def zero_score(note: str) -> dict:
    return {
        "scores": [0] * len(CRITERIA),
        "average": 0,
        "pass": False,
        NOTES_FIELD: note,
    }


async def call_target(target, ex: dict) -> tuple[str, str | None]:
    """Target-only phase. Returns (response, error_or_none).

    Split from the judge so the two stages can be gated by separate
    semaphores — local Ollama and the remote judge typically have
    different slot counts, and serializing both behind one semaphore
    leaves slots idle. With this split, a coroutine releases the
    target slot the moment its target call completes and queues for
    the judge slot independently.
    """
    user_turn = ex.get("wrapped_user_message")
    if user_turn is None:
        context = ex.get("context_block", "")
        user_turn = (
            f"CONTEXT:\n{context}\n\nUSER: {ex['user_message']}"
            if context
            else ex["user_message"]
        )
    try:
        r = await target.chat.completions.create(
            model=MODEL,
            temperature=0.3,
            max_tokens=2048,
            messages=[
                {"role": "system", "content": ex["system_prompt"]},
                {"role": "user", "content": user_turn},
            ],
            extra_body={"reasoning_effort": "none", "think": False},
        )
        response = (r.choices[0].message.content or "").strip()
        if not response:
            return ("(empty)", "Empty response")
        return (response, None)
    except Exception as e:
        return (f"TARGET ERROR: {e}", str(e))


# Retry policy: AWS-style "full jitter" exponential backoff.
# sleep = random.uniform(0, min(CAP, BASE * 2^attempt))
# Full jitter spreads retry storms when many concurrent coroutines hit the
# same upstream failure (e.g. judge endpoint hiccup) — without it, all
# retries would land at the same moment and amplify the original spike.
# Refs:
#   https://aws.amazon.com/blogs/architecture/exponential-backoff-and-jitter/
RETRY_BACKOFF_BASE_S = 2.0
RETRY_BACKOFF_CAP_S = 30.0
RETRY_MAX_ATTEMPTS = 3


def _retry_sleep_seconds(attempt: int) -> float:
    """Full-jitter exponential backoff. `attempt` is 0-indexed."""
    import random
    ceiling = min(RETRY_BACKOFF_CAP_S, RETRY_BACKOFF_BASE_S * (2 ** attempt))
    return random.uniform(0, ceiling)


async def call_judge(judge, judge_model: str, ex: dict, response: str) -> dict:
    """Judge-only phase. Bounded retries with full-jitter exponential backoff."""
    prompt = EVAL_RUBRIC.format(
        user_message=ex["user_message"],
        response=response,
        expected=ex["expected"],
        category=ex["category"],
    )
    for attempt in range(RETRY_MAX_ATTEMPTS):
        try:
            jr = await judge.chat.completions.create(
                model=judge_model,
                temperature=0,
                max_tokens=12288,
                messages=[{"role": "user", "content": prompt}],
                response_format=EVAL_SCHEMA,
            )
            raw = json.loads(jr.choices[0].message.content)
            scores_list = [raw[c] for c in CRITERIA]
            avg = sum(scores_list) / len(scores_list)
            passes = avg >= PASS_AVG and all(
                raw.get(c, 5) >= floor
                for c, floor in PASS_FLOORS.items()
                if c in CRITERIA
            )
            return {
                "scores": scores_list,
                "average": round(avg, 2),
                "pass": passes,
                NOTES_FIELD: raw.get(NOTES_FIELD, ""),
            }
        except Exception as e:
            if attempt < RETRY_MAX_ATTEMPTS - 1:
                wait = _retry_sleep_seconds(attempt)
                _tqdm.write(f"  Judge error (attempt {attempt+1}/{RETRY_MAX_ATTEMPTS}): "
                            f"{e} — retrying in {wait:.1f}s...")
                await asyncio.sleep(wait)
            else:
                return zero_score(f"Judge error after {RETRY_MAX_ATTEMPTS} attempts: {e}")
    return zero_score("Judge: unreachable code path")


class PhaseStats:
    """Lightweight running stats for tqdm postfix: per-phase progress,
    in-flight counts, and rolling mean phase latencies. All updates are
    synchronous (asyncio single-threaded), no lock needed.
    """
    def __init__(self):
        self.target_inflight = 0
        self.judge_inflight = 0
        self.target_done = 0
        self.judge_done = 0
        self.target_total_s = 0.0
        self.judge_total_s = 0.0
        self.target_cap = 0
        self.judge_cap = 0
        self.total = 0   # set once at run start

    def fmt(self) -> str:
        # Per-phase progress against the run total. The bar itself shows
        # "examples that finished BOTH phases"; these two counters show
        # how many got past each individual phase.
        return (
            f"tgt {self.target_done}/{self.total}  "
            f"jdg {self.judge_done}/{self.total}"
        )


async def evaluate_one(
    target,
    judge,
    judge_model: str,
    ex: dict,
    target_sem: asyncio.Semaphore,
    judge_sem: asyncio.Semaphore,
    stats: PhaseStats | None = None,
) -> dict:
    """Run one example through target then judge, gated by separate semaphores
    so a coroutine waiting on the (often serial) remote judge doesn't hold
    a target slot idle.
    """
    import time
    user_turn_for_checks = ex.get("wrapped_user_message") or (
        f"CONTEXT:\n{ex.get('context_block', '')}\n\nUSER: {ex['user_message']}"
        if ex.get("context_block")
        else ex["user_message"]
    )

    async with target_sem:
        if stats:
            stats.target_inflight += 1
        t0 = time.monotonic()
        response, target_err = await call_target(target, ex)
        t_elapsed = time.monotonic() - t0
        if stats:
            stats.target_inflight -= 1
            stats.target_done += 1
            stats.target_total_s += t_elapsed

    if target_err is not None:
        return {
            "id": ex.get("id"),
            "category": ex["category"],
            "facility": ex["facility"],
            "user_message": ex["user_message"],
            "expected": ex["expected"],
            "model_response": response,
            "score": zero_score(target_err),
            "checks": {"json_ok": False, "verbatim": {"applicable": False}, "language": "en"},
            "phase_seconds": {"target": round(t_elapsed, 2), "judge": 0.0},
        }

    checks = deterministic_checks(
        response=response,
        system_prompt=user_turn_for_checks,
        user_message=ex["user_message"],
    )

    async with judge_sem:
        if stats:
            stats.judge_inflight += 1
        j0 = time.monotonic()
        score = await call_judge(judge, judge_model, ex, response)
        j_elapsed = time.monotonic() - j0
        if stats:
            stats.judge_inflight -= 1
            stats.judge_done += 1
            stats.judge_total_s += j_elapsed

    return {
        "id": ex.get("id"),
        "category": ex["category"],
        "facility": ex["facility"],
        "user_message": ex["user_message"],
        "expected": ex["expected"],
        "model_response": response,
        "score": score,
        "checks": checks,
        "phase_seconds": {"target": round(t_elapsed, 2), "judge": round(j_elapsed, 2)},
    }


async def main():
    parser = argparse.ArgumentParser(description="Run eval suite against a model")
    parser.add_argument("--judge-model", type=str, default="gemma4-31b", help="Model to use as judge")
    parser.add_argument("--judge-endpoint", type=str, default="http://localhost:11434/v1", help="API endpoint for judge model")
    parser.add_argument("--category", type=str, help="Only eval this category")
    parser.add_argument("--limit", type=int, help="Only eval first N examples")
    parser.add_argument("--concurrency", type=int, default=CONCURRENCY,
                        help=f"Parallel target calls in-flight (default: {CONCURRENCY}). "
                             f"Match this to OLLAMA_NUM_PARALLEL on the target side.")
    parser.add_argument("--judge-concurrency", type=int, default=None,
                        help="Parallel judge calls in-flight (default: same as --concurrency). "
                             "Lower this when the judge endpoint has fewer slots than the target "
                             "— e.g. a 122B judge on a single-slot llama-swap should be 1.")
    parser.add_argument("--resume", action="store_true",
                        help="Resume from a prior interrupted run. Skips examples whose ids "
                             "appear in the most recent eval_results_*.jsonl for this model.")
    # CI-gate flags. When any *-min flag is passed, the run exits non-zero if
    # the corresponding metric falls below it. Useful for blocking a fine-tune
    # from being promoted to the on-device bundle.
    parser.add_argument("--min-pass-rate", type=float, default=None,
                        help="Fail with exit 1 if pass rate < this (0.0–1.0).")
    parser.add_argument("--min-json-parse", type=float, default=None,
                        help="Fail with exit 1 if JSON parse rate < this (0.0–1.0).")
    parser.add_argument("--min-verbatim", type=float, default=None,
                        help="Fail with exit 1 if route-verbatim rate < this (0.0–1.0). Only counts examples whose CONTEXT had a Route block.")
    args = parser.parse_args()

    ensure_dirs()

    eval_file = EVAL_DIR / "eval_suite.jsonl"
    if not eval_file.exists():
        print("ERROR: eval_suite.jsonl not found. Run `python build_eval.py` first.")
        sys.exit(1)

    examples = []
    with open(eval_file) as f:
        for line in f:
            line = line.strip()
            if line:
                examples.append(json.loads(line))

    if args.category:
        examples = [e for e in examples if e["category"] == args.category]
    if args.limit:
        examples = examples[:args.limit]

    target = get_client(base_url=BASE_URL)
    judge_endpoint = args.judge_endpoint or BASE_URL
    judge_model = args.judge_model or MODEL
    judge = get_client(base_url=judge_endpoint)

    model_name = MODEL.replace("/", "_").replace(":", "_")
    timestamp = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
    results_file = EVAL_RESULTS_DIR / f"eval_results_{model_name}_{timestamp}.jsonl"

    # --resume: skip examples already done in the most recent partial run.
    # We match on a stable key (id when present, else user_message+facility).
    completed_keys: set[str] = set()
    if args.resume:
        prior = sorted(
            EVAL_RESULTS_DIR.glob(f"eval_results_{model_name}_*.jsonl"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if prior:
            results_file = prior[0]
            with open(results_file) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        r = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    completed_keys.add(_example_key(r))
            print(f"Resume: appending to {results_file}, {len(completed_keys)} already done")
        else:
            print("Resume: no prior run found, starting fresh")

    def _filter_remaining(exs):
        return [e for e in exs if _example_key(e) not in completed_keys]

    pending = _filter_remaining(examples) if completed_keys else examples

    judge_concurrency = args.judge_concurrency or args.concurrency

    print(f"Eval suite: {len(examples)} examples ({len(pending)} pending)")
    print(f"Target: {MODEL} @ {BASE_URL}")
    print(f"Judge:  {judge_model} @ {judge_endpoint}")
    print(f"Criteria: {', '.join(CRITERIA)}")
    print(f"Concurrency: target={args.concurrency}, judge={judge_concurrency}")
    print(f"Results streaming to: {results_file}")
    print()

    target_sem = asyncio.Semaphore(args.concurrency)
    judge_sem = asyncio.Semaphore(judge_concurrency)

    stats = PhaseStats()
    stats.target_cap = args.concurrency
    stats.judge_cap = judge_concurrency
    stats.total = len(pending)

    # Stream each completed example to disk so an interrupted run can be
    # inspected (and resumed via --resume). Open in append mode in case
    # we're resuming; "a+" creates if missing.
    results: list[dict] = []
    file_lock = asyncio.Lock()
    out_f = open(results_file, "a", encoding="utf-8")

    async def eval_and_persist(ex):
        r = await evaluate_one(
            target, judge, judge_model, ex, target_sem, judge_sem, stats=stats
        )
        async with file_lock:
            out_f.write(json.dumps(r, ensure_ascii=False) + "\n")
            out_f.flush()
        results.append(r)
        return r

    try:
        from tqdm import tqdm as _tqdm
        coroutines = [eval_and_persist(ex) for ex in pending]
        if coroutines:
            # Use as_completed + manual tqdm so we can update postfix with
            # in-flight slot counts and rolling per-phase latency. A
            # background ticker also refreshes the postfix every second
            # between completions — without it the bar appears frozen
            # whenever no example happens to complete (e.g. all 3 target
            # slots filled, all waiting on a slow remote judge).
            # Safe because asyncio is single-threaded: the ticker and the
            # as_completed loop yield to each other at await points.
            with _tqdm(total=len(coroutines), desc="Evaluating") as pbar:
                stop_ticker = asyncio.Event()

                async def ticker():
                    while not stop_ticker.is_set():
                        pbar.set_postfix_str(stats.fmt())
                        pbar.refresh()
                        try:
                            await asyncio.wait_for(stop_ticker.wait(), timeout=1.0)
                        except asyncio.TimeoutError:
                            continue

                ticker_task = asyncio.create_task(ticker())
                try:
                    for fut in asyncio.as_completed(coroutines):
                        await fut
                        pbar.set_postfix_str(stats.fmt())
                        pbar.update(1)
                finally:
                    stop_ticker.set()
                    await ticker_task
    finally:
        out_f.close()

    # Load already-completed rows back in so the summary reflects everything,
    # not just this run's pending slice. Dedup by stable key, keeping the
    # LAST occurrence of each — so a partial-then-resumed run that wrote a
    # duplicate row still reports a clean per-example count.
    if completed_keys:
        deduped: dict[str, dict] = {}
        with open(results_file) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                deduped[_example_key(r)] = r
        results = list(deduped.values())

    # === Report ===
    print(f"\n{'='*60}")
    print(f"EVAL REPORT: {MODEL}")
    print(f"{'='*60}")

    all_scores = [r["score"]["average"] for r in results if r["score"]["average"] > 0]
    all_pass = [r["score"]["pass"] for r in results if isinstance(r["score"].get("pass"), bool)]

    if all_scores:
        print(f"\nOverall:")
        print(f"  Examples evaluated: {len(results)}")
        print(f"  Mean score: {sum(all_scores) / len(all_scores):.2f} / 5.0")
        print(f"  Pass rate: {sum(all_pass)}/{len(all_pass)} ({sum(all_pass)/len(all_pass)*100:.0f}%)")

    # Per-category
    cat_results: dict[str, list] = {}
    for r in results:
        cat_results.setdefault(r["category"], []).append(r)

    print(f"\nPer-category scores:")
    print(f"  {'Category':<25s} {'Avg':>5s} {'Pass':>6s} {'Count':>6s}")
    print(f"  {'-'*25} {'-'*5} {'-'*6} {'-'*6}")
    for cat in sorted(cat_results.keys()):
        rs = cat_results[cat]
        scores = [r["score"]["average"] for r in rs if r["score"]["average"] > 0]
        passes = [r["score"]["pass"] for r in rs if isinstance(r["score"].get("pass"), bool)]
        avg = sum(scores) / len(scores) if scores else 0
        pct = f"{sum(passes)}/{len(passes)}" if passes else "?"
        print(f"  {cat:<25s} {avg:>5.2f} {pct:>6s} {len(rs):>6d}")

    # Per-criterion
    criterion_labels = [c.replace("_", " ").title() for c in CRITERIA]
    criterion_scores: dict[str, list] = {n: [] for n in criterion_labels}
    for r in results:
        scores = r["score"].get("scores", [])
        for i, label in enumerate(criterion_labels):
            if i < len(scores) and scores[i] > 0:
                criterion_scores[label].append(scores[i])

    print(f"\nPer-criterion averages:")
    for label in criterion_labels:
        vals = criterion_scores[label]
        if vals:
            avg = sum(vals) / len(vals)
            bar = "█" * int(avg * 4)
            print(f"  {label:<15s} {avg:.2f} / 5.0  {bar}")

    # Failed examples
    failed = [r for r in results if not r["score"].get("pass", True)]
    if failed:
        print(f"\nFailed examples ({len(failed)}):")
        for r in sorted(failed, key=lambda x: x["score"]["average"])[:5]:
            print(f"  [{r['score']['average']:.1f}] {r['category']}: \"{r['user_message'][:50]}\"")
            print(f"       → {r['score'].get(NOTES_FIELD, '')[:80]}")

    # === Deterministic checks (JSON parse-rate, verbatim, language split) ===
    json_total = len(results)
    json_ok = sum(1 for r in results if r.get("checks", {}).get("json_ok"))
    json_rate = json_ok / json_total if json_total else 0.0

    verbatim_applicable = [r for r in results
                           if r.get("checks", {}).get("verbatim", {}).get("applicable")]
    verbatim_ok = sum(1 for r in verbatim_applicable
                      if r["checks"]["verbatim"].get("ok"))
    verbatim_rate = verbatim_ok / len(verbatim_applicable) if verbatim_applicable else None

    # Per-language scores. Skip examples where the judge errored (avg=0).
    lang_scores: dict[str, list[float]] = {"en": [], "es": []}
    for r in results:
        if r["score"]["average"] <= 0:
            continue
        lang = r.get("checks", {}).get("language", "en")
        if lang in lang_scores:
            lang_scores[lang].append(r["score"]["average"])
    en_avg = sum(lang_scores["en"]) / len(lang_scores["en"]) if lang_scores["en"] else 0.0
    es_avg = sum(lang_scores["es"]) / len(lang_scores["es"]) if lang_scores["es"] else 0.0

    print(f"\nDeterministic checks:")
    print(f"  JSON parse rate:       {json_ok}/{json_total} ({json_rate*100:.1f}%)")
    if verbatim_rate is not None:
        print(f"  Route verbatim:        {verbatim_ok}/{len(verbatim_applicable)} ({verbatim_rate*100:.1f}%) "
              f"(of examples with a Route block in CONTEXT)")
    else:
        print(f"  Route verbatim:        N/A (no eval examples had a Route block)")
    print(f"  Language split (avg):  EN {en_avg:.2f} (n={len(lang_scores['en'])}) · "
          f"ES {es_avg:.2f} (n={len(lang_scores['es'])}) · Δ {en_avg - es_avg:+.2f}")

    # Per-phase latency breakdown — tells you whether target or judge is the
    # rate limiter for this hardware combo. The phase_seconds field is
    # populated for runs done with the split-semaphore architecture.
    target_lat = [r["phase_seconds"]["target"] for r in results if r.get("phase_seconds")]
    judge_lat = [r["phase_seconds"]["judge"] for r in results
                 if r.get("phase_seconds") and r["phase_seconds"].get("judge", 0) > 0]
    if target_lat and judge_lat:
        t_avg = sum(target_lat) / len(target_lat)
        j_avg = sum(judge_lat) / len(judge_lat)
        # Effective throughput per phase, given configured concurrency.
        # Bottleneck = max of the two phase-rates.
        t_rate = args.concurrency / t_avg if t_avg > 0 else 0
        j_rate = judge_concurrency / j_avg if j_avg > 0 else 0
        bottleneck = "target" if t_rate < j_rate else "judge"
        print(f"\nPhase latencies:")
        print(f"  Target:  avg {t_avg:5.2f}s · {t_rate:.2f} ex/s @ concurrency={args.concurrency}")
        print(f"  Judge:   avg {j_avg:5.2f}s · {j_rate:.2f} ex/s @ concurrency={judge_concurrency}")
        print(f"  Bottleneck: {bottleneck} "
              f"({'serialised by ' + str(judge_concurrency) + '-slot judge' if bottleneck=='judge' else 'target throughput'})")

    print(f"\nFull results: {results_file}")

    # Save summary
    pass_rate_value = sum(all_pass) / len(all_pass) if all_pass else 0
    summary = {
        "model": MODEL,
        "judge_model": judge_model,
        "timestamp": timestamp,
        "criteria": CRITERIA,
        "pass_avg": PASS_AVG,
        "pass_floors": PASS_FLOORS,
        "total_examples": len(results),
        "mean_score": sum(all_scores) / len(all_scores) if all_scores else 0,
        "pass_rate": pass_rate_value,
        "json_parse_rate": json_rate,
        "verbatim_rate": verbatim_rate,
        "verbatim_applicable_count": len(verbatim_applicable),
        "language_split": {
            "en": {"mean": en_avg, "count": len(lang_scores["en"])},
            "es": {"mean": es_avg, "count": len(lang_scores["es"])},
            "delta_en_minus_es": en_avg - es_avg,
        },
        "per_category": {
            cat: {
                "mean": sum(r["score"]["average"] for r in rs if r["score"]["average"] > 0) / max(1, len([r for r in rs if r["score"]["average"] > 0])),
                "count": len(rs),
            }
            for cat, rs in cat_results.items()
        },
        "per_criterion": {
            label: sum(vals) / len(vals) if vals else 0
            for label, vals in criterion_scores.items()
        },
    }
    summary_file = EVAL_RESULTS_DIR / f"eval_summary_{model_name}_{timestamp}.json"
    with open(summary_file, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"Summary: {summary_file}")

    # CI gate. Each --min-* flag is independent — we report all violations,
    # then exit non-zero if any tripped, so a single run shows everything
    # broken at once instead of one error at a time.
    gate_violations: list[str] = []
    if args.min_pass_rate is not None and pass_rate_value < args.min_pass_rate:
        gate_violations.append(
            f"pass_rate {pass_rate_value:.2f} < {args.min_pass_rate:.2f}"
        )
    if args.min_json_parse is not None and json_rate < args.min_json_parse:
        gate_violations.append(
            f"json_parse_rate {json_rate:.2f} < {args.min_json_parse:.2f}"
        )
    if (
        args.min_verbatim is not None
        and verbatim_rate is not None
        and verbatim_rate < args.min_verbatim
    ):
        gate_violations.append(
            f"verbatim_rate {verbatim_rate:.2f} < {args.min_verbatim:.2f}"
        )
    if gate_violations:
        print("\nGATE FAILED:")
        for v in gate_violations:
            print(f"  - {v}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
