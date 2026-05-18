#!/usr/bin/env python3
"""
Diff two eval_summary_*.json files side-by-side. Use after running
eval_runner.py against two models (e.g. old fine-tune vs candidate).

Usage:

  # Pass summaries directly:
  python compare_runs.py training/output/eval_results/eval_summary_v1.json \\
                         training/output/eval_results/eval_summary_v2.json

  # Or auto-find the latest summary for two model IDs (pattern-matched
  # against the filename written by eval_runner.py):
  python compare_runs.py --baseline gemma4_e2b --candidate medical-wayfinder-gemma-4-e2b-cp78

  # CI gating: exit 1 if any tracked metric regresses by more than --tolerate
  # (defaults to 0.0 — strict). Useful to block promoting a fine-tune that
  # gained on average but lost on a specific axis (e.g. off_topic).
  python compare_runs.py v1.json v2.json --fail-on-regression --tolerate 0.02

The "candidate" is the new run; the "baseline" is what we're trying to beat.
Δ columns are candidate − baseline, so positive = improvement.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import EVAL_RESULTS_DIR

# ANSI colors for the terminal. We only colorize if stdout is a TTY so piping
# to a file (or CI logs) stays clean.
_USE_COLOR = sys.stdout.isatty()


def c(text: str, code: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _USE_COLOR else text


def green(s: str) -> str:
    return c(s, "32")


def red(s: str) -> str:
    return c(s, "31")


def dim(s: str) -> str:
    return c(s, "2")


def fmt_delta(delta: float, *, pp: bool = False, decimals: int = 2) -> str:
    """Render a signed delta with green/red color. `pp` formats as percentage points."""
    if delta == 0:
        return dim(f"{'±0' if not pp else '±0pp'}")
    suffix = "pp" if pp else ""
    sign = "+" if delta > 0 else ""
    text = f"{sign}{delta:.{decimals}f}{suffix}"
    return green(text) if delta > 0 else red(text)


def find_latest_summary(model_substring: str) -> Path:
    """Find the most-recent eval_summary file whose filename contains `substring`."""
    candidates = sorted(
        EVAL_RESULTS_DIR.glob("eval_summary_*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for p in candidates:
        if model_substring in p.stem:
            return p
    raise SystemExit(f"No eval_summary file matching '{model_substring}' in {EVAL_RESULTS_DIR}")


def load(path: Path) -> dict[str, Any]:
    with open(path) as f:
        return json.load(f)


def headline_row(label: str, base: float | None, cand: float | None,
                 *, pp: bool = False, decimals: int = 2,
                 lower_is_better: bool = False) -> tuple[str, float]:
    """Return (formatted line, signed_delta_for_gating).

    `lower_is_better` flips the colour and the sign returned for gating —
    used for the EN−ES gap, where a widening gap is a regression even though
    the raw arithmetic delta is positive.
    """
    if base is None or cand is None:
        return (f"  {label:<28s} {'—':>8s} {'—':>8s} {'—':>10s}", 0.0)
    raw_delta = cand - base
    quality_delta = -raw_delta if lower_is_better else raw_delta
    base_str = f"{base*100:.1f}%" if pp else f"{base:.{decimals}f}"
    cand_str = f"{cand*100:.1f}%" if pp else f"{cand:.{decimals}f}"
    # Render the displayed value as the raw arithmetic delta, but colour it
    # by quality so the reader sees red when things got worse.
    value = raw_delta * (100 if pp else 1)
    if quality_delta == 0:
        rendered = dim(f"{'±0' if not pp else '±0pp'}")
    else:
        suffix = "pp" if pp else ""
        sign = "+" if value > 0 else ""
        text = f"{sign}{value:.{decimals}f}{suffix}"
        rendered = green(text) if quality_delta > 0 else red(text)
    return (
        f"  {label:<28s} {base_str:>8s} {cand_str:>8s} {rendered:>20s}",
        quality_delta,
    )


def print_section(title: str, rows: list[tuple[str, float]]) -> list[float]:
    """Print a section and return the deltas for gating."""
    print(f"\n{title}")
    print(f"  {'Metric':<28s} {'Base':>8s} {'Cand':>8s} {'Δ':>10s}")
    print(f"  {'-'*28} {'-'*8} {'-'*8} {'-'*10}")
    deltas: list[float] = []
    for line, delta in rows:
        print(line)
        deltas.append(delta)
    return deltas


def main() -> None:
    parser = argparse.ArgumentParser(description="Diff two eval_summary_*.json runs side-by-side.")
    parser.add_argument("baseline", nargs="?", help="Path to baseline summary JSON")
    parser.add_argument("candidate", nargs="?", help="Path to candidate summary JSON")
    parser.add_argument("--baseline", dest="baseline_kw", help="Substring of model name to find latest baseline summary")
    parser.add_argument("--candidate", dest="candidate_kw", help="Substring of model name to find latest candidate summary")
    parser.add_argument("--fail-on-regression", action="store_true",
                        help="Exit 1 if any tracked metric drops by more than --tolerate")
    parser.add_argument("--tolerate", type=float, default=0.0,
                        help="Allowable regression magnitude (default: 0.0 — strict).")
    args = parser.parse_args()

    # Resolve paths. Positional args win; otherwise use --baseline/--candidate
    # to glob the latest matching summary.
    if args.baseline:
        base_path = Path(args.baseline)
    elif args.baseline_kw:
        base_path = find_latest_summary(args.baseline_kw)
    else:
        sys.exit("ERROR: provide either a positional baseline path or --baseline <substring>")

    if args.candidate:
        cand_path = Path(args.candidate)
    elif args.candidate_kw:
        cand_path = find_latest_summary(args.candidate_kw)
    else:
        sys.exit("ERROR: provide either a positional candidate path or --candidate <substring>")

    base = load(base_path)
    cand = load(cand_path)

    print(f"Baseline:  {base.get('model', '?')}  ({base_path.name})")
    print(f"Candidate: {cand.get('model', '?')}  ({cand_path.name})")
    if base.get("total_examples") != cand.get("total_examples"):
        print(red(f"WARNING: example counts differ ({base.get('total_examples')} vs {cand.get('total_examples')}) "
                  f"— scores may not be directly comparable."))

    deltas: list[tuple[str, float]] = []

    # === Headline ===
    rows = [
        headline_row("Mean score (0–5)",   base.get("mean_score"),       cand.get("mean_score")),
        headline_row("Pass rate",          base.get("pass_rate"),        cand.get("pass_rate"),       pp=True),
        headline_row("JSON parse rate",    base.get("json_parse_rate"),  cand.get("json_parse_rate"), pp=True),
        headline_row("Verbatim route",     base.get("verbatim_rate"),    cand.get("verbatim_rate"),   pp=True),
    ]
    for line, d in rows:
        deltas.append(("headline", d))
    print_section("Headline metrics", rows)

    # === Language split ===
    base_lang = base.get("language_split", {})
    cand_lang = cand.get("language_split", {})
    rows = [
        headline_row("EN mean score",
                     base_lang.get("en", {}).get("mean"),
                     cand_lang.get("en", {}).get("mean")),
        headline_row("ES mean score",
                     base_lang.get("es", {}).get("mean"),
                     cand_lang.get("es", {}).get("mean")),
        # EN−ES delta: smaller gap is better. headline_row inverts the
        # quality sign so a widening gap renders red and counts as a
        # regression.
        headline_row("EN−ES delta",
                     base_lang.get("delta_en_minus_es"),
                     cand_lang.get("delta_en_minus_es"),
                     lower_is_better=True),
    ]
    for line, d in rows:
        deltas.append(("language", d))
    print_section("Language split", rows)

    # === Per-category ===
    cat_keys = sorted(set((base.get("per_category") or {}).keys()) |
                      set((cand.get("per_category") or {}).keys()))
    if cat_keys:
        rows = []
        for k in cat_keys:
            b = (base.get("per_category") or {}).get(k, {}).get("mean")
            ca = (cand.get("per_category") or {}).get(k, {}).get("mean")
            rows.append(headline_row(k, b, ca))
        for line, d in rows:
            deltas.append(("category", d))
        print_section("Per-category mean scores", rows)

    # === Per-criterion ===
    crit_keys = sorted(set((base.get("per_criterion") or {}).keys()) |
                       set((cand.get("per_criterion") or {}).keys()))
    if crit_keys:
        rows = []
        for k in crit_keys:
            b = (base.get("per_criterion") or {}).get(k)
            ca = (cand.get("per_criterion") or {}).get(k)
            rows.append(headline_row(k, b, ca))
        for line, d in rows:
            deltas.append(("criterion", d))
        print_section("Per-criterion averages", rows)

    # === Gate ===
    if args.fail_on_regression:
        regressions = [(scope, d) for scope, d in deltas if d < -args.tolerate]
        if regressions:
            print(red(f"\nGATE FAILED: {len(regressions)} metric(s) regressed beyond tolerance ({args.tolerate})"))
            sys.exit(1)
        print(green("\nGate passed."))


if __name__ == "__main__":
    main()
