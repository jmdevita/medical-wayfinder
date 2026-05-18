# Training Pipeline

End-to-end pipeline for fine-tuning Gemma 4 E2B on healthcare wayfinding,
organized around five stages. Each stage is one Make target and one Python
script. Run them in order, or use the underlying scripts directly for
debugging.

All commands run from `training/`. Python uses the repo-root `env/`
virtualenv (`env/bin/python`).

---

## Prerequisites

From the repo root, run the setup script once. It creates the shared `env/`
virtualenv (used by training, tools, and atlas) and installs the Python
dependencies in `training/requirements.txt`:

```bash
./scripts/setup.sh
```

Then configure the LLM endpoint(s) in `training/.env` (start from `.env.example`):

```bash
OPENAI_BASE_URL=http://localhost:11434/v1   # the TARGET (small on-device model)
OPENAI_API_KEY=not-needed                   # any string for local Ollama
OPENAI_MODEL=medical-wayfinder-gemma-4-e2b                  # target model name
```

The pipeline uses **three** logical models:
- **Target** — the small model being trained/evaluated (lives on `OPENAI_BASE_URL`)
- **Teacher** — strong model that writes synthetic training data
- **Judge** — strong, different-family model that scores teacher output

Defaults (in `Makefile`):

| Var | Default | Used by |
|---|---|---|
| `MODEL` | `gemma4:e2b` | `eval`, `eval-quick`, `eval-resume` (target) |
| `JUDGE_MODEL` | `gemma4-31b` | `eval`, `score` |
| `JUDGE_ENDPOINT` | `http://localhost:11434/v1` | `eval`, `score` |
| `TEACHER_MODEL` | `qwen3.5-122b` | `generate` |
| `TEACHER_ENDPOINT` | `http://your-llm-host:11434/v1` | `generate` |
| `CONCURRENCY` | `3` | `eval` (target slots) |
| `JUDGE_CONCURRENCY` | `3` | `eval` (judge slots) |

Override per-run on the command line, e.g.
`make eval MODEL=wayfinder-v2 JUDGE_ENDPOINT=http://remote:11434/v1`.

Teacher and judge are deliberately different model families to avoid
self-preference bias when the judge scores teacher output.

---

## The 5-stage flow

```
            eval  →  generate  →  filter  →  train  →  eval (+ compare)
            ↓          ↓             ↓         ↓          ↓
        BASELINE    output/01_raw/   output/    GPU box   output/eval_results/
        SCORE                     scored/   GGUF model
```

One command per stage:

```bash
make prepare                                       # one-time: build seeds + eval suite
make eval MODEL=medical-wayfinder-gemma-4-e2b                      # 1. baseline
make generate                                      # 2. teacher writes 248 batches
make filter                                        # 3. validate + score + stats
# 4. fine-tune on a GPU box (see Stage 4 below)
make eval MODEL=wayfinder-v2                       # 5a. candidate eval
make compare BASELINE=<old.json> CANDIDATE=<new.json>  # 5b. diff
```

`make help` lists every target with one-line descriptions.

---

## Stage 0: Prepare (one-time)

Compiles seeds and eval cases from their hand-edited source files. Re-run
whenever you edit `raw_seeds.json` or `raw_eval.json`.

```bash
make prepare
# Runs: build_seeds.py + build_eval.py
```

**Reads:**
- `data/seeds/raw_seeds.json` — 24 hand-written multi-turn conversations
- `data/eval/raw_eval.json` — 100 eval cases
- `data/facilities/*.json` — facility data (symlink to app assets)
- `data/facilities/*.topology.json` — campus graphs
- `data/prompts/system_prompt.txt` — static system prompt

**Writes:**
- `data/seeds/seeds.jsonl` — compiled seeds (system prompt + CONTEXT-wrapped user turns)
- `data/eval/eval_suite.jsonl` — compiled eval suite (same shape as inference)

Both compiled files match app inference exactly: static system prompt,
`CONTEXT:\n<block>\n\nUSER: <raw>` user turn.

---

## Stage 1: Eval (baseline)

Measures the unmodified target model so you have a number to beat after
fine-tuning.

```bash
make eval MODEL=medical-wayfinder-gemma-4-e2b JUDGE_ENDPOINT=http://your-llm-host:11434/v1
```

**Reads:**
- `data/eval/eval_suite.jsonl` (100 cases)
- `data/prompts/criteria.json` (5-criterion rubric)
- `data/prompts/eval_rubric.txt`

**Writes (streamed):**
- `output/eval_results/eval_results_<model>_<ts>.jsonl` — per-example details
- `output/eval_results/eval_summary_<model>_<ts>.json` — aggregates

**What to look at in the summary:**
- `mean_score` and `pass_rate` — headline numbers
- `json_parse_rate` — % of responses that decoded as valid data contract
- `verbatim_rate` — when CONTEXT had a `Route from X:` block, did `steps[]` copy it verbatim?
- `language_split.delta_en_minus_es` — multilingual gap
- `per_criterion` — Format, Landmarks, Accessibility are the dimensions fine-tuning needs to lift most

**Knobs:**

```bash
# Resume an interrupted run (auto-skips already-completed examples)
make eval-resume MODEL=medical-wayfinder-gemma-4-e2b JUDGE_ENDPOINT=...

# Smoke-test against the first 5 cases only
make eval-quick MODEL=medical-wayfinder-gemma-4-e2b JUDGE_ENDPOINT=...

# Tune concurrency to match the endpoint slot counts
make eval MODEL=... CONCURRENCY=3 JUDGE_CONCURRENCY=1

# CI-gate flags (script-level; bypass Makefile)
env/bin/python scripts/eval_runner.py --min-pass-rate 0.70 --min-json-parse 0.90 --min-verbatim 0.75
```

---

## Stage 2: Generate

Teacher writes 248 batches of synthetic conversations across 19 categories.

```bash
make generate
# (teacher = qwen3.5-122b @ your-llm-host by default)
```

**Reads:**
- `data/prompts/generation.txt` — meta-prompt for the teacher
- `data/prompts/categories.json` — batch counts, phrase buckets, per-category instructions
- `data/prompts/system_prompt.txt` — injected into each example's system slot
- `data/facilities/*.json` — full facility JSON included in each teacher prompt
- `data/seeds/seeds.jsonl` — 3 few-shot examples sampled per batch
- `data/real_data/mined/best_phrases.json` — 1000 real-world directional phrases

**Writes:**
- `output/01_raw/raw_<ts>.jsonl` — ~248 examples (one per batch × `BATCH_SIZE=1`)
- `output/rejected/generation_errors_<ts>.jsonl` — if any batch double-failed

**Knobs:**

```bash
# Override teacher model/endpoint
make generate TEACHER_MODEL=gpt-oss-120b TEACHER_ENDPOINT=http://remote:11434/v1

# Generate only one category (for backfilling a weak category mid-iteration)
env/bin/python scripts/generate.py --category clean_resolution_es \
  --model qwen3.5-122b --endpoint http://your-llm-host:11434/v1

# Smoke-test plumbing without hitting the teacher
env/bin/python scripts/generate.py --dry-run
```

**Expected runtime:** ~15-25 min on a fast remote teacher with 3-concurrency.

---

## Stage 3: Filter

Cleans the raw output: rule-based structural validation, then LLM-judge
quality scoring, then a stats summary.

```bash
make filter
# Reads the latest output/01_raw/*.jsonl by default; override with FILE=<path>
```

**Three sub-steps chained:**

1. **`validate.py`** — 11 structural checks (no LLM). Reads `output/01_raw/<file>.jsonl`,
   writes `output/02_validated/<file>_validated.jsonl` and `output/rejected/<file>_rejected.jsonl`.
   Catches: missing fields, invalid block types, filler phrases, language mismatch,
   building-name hallucinations, malformed JSON.

2. **`score.py`** — LLM judge scores each example on 5 criteria, keeps those averaging
   ≥3.5. Reads `output/02_validated/<file>.jsonl`, writes `output/03_scored/<file>_scored.jsonl`
   (passes) and `output/03_scored/<file>_scores.jsonl` (every score, kept or not) and
   `output/rejected/<file>_low_score.jsonl` (drops).

3. **`stats.py`** — Reads the latest `output/03_scored/*.jsonl` and prints category
   distribution, EN/ES split, turn count histogram, score histogram.

**Reads:**
- `output/01_raw/<file>.jsonl` (latest, or `FILE=`)
- `data/prompts/criteria.json` (5-criterion rubric — same as eval)
- `data/prompts/scoring_rubric.txt`

**Writes:**
- `output/02_validated/<file>_validated.jsonl` — passes structural checks
- `output/rejected/<file>_rejected.jsonl` — with per-example issue lists
- `output/03_scored/<file>_validated_scored.jsonl` — the file you fine-tune on
- `output/03_scored/<file>_validated_scores.jsonl` — every score for analysis
- `output/rejected/<file>_low_score.jsonl` — sub-threshold drops

**Knobs:**

```bash
# Run one sub-step against a specific file
make validate FILE=output/01_raw/raw_<ts>.jsonl
make score    FILE=output/02_validated/<file>_validated.jsonl
make stats    FILE=output/03_scored/<file>_validated_scored.jsonl

# Stricter scoring
env/bin/python scripts/score.py output/02_validated/<file>.jsonl --threshold 4.0

# Different-model judge
make filter JUDGE_MODEL=qwen3.5-27b JUDGE_ENDPOINT=http://your-llm-host:11434/v1
```

**Expected attrition:** ~25-40% validation reject + ~20-30% scoring reject →
~248 raw becomes ~115-130 final.

**Read the stats output before fine-tuning.** If a category dropped below ~5
surviving examples, regenerate just that one (`generate.py --category <name>`)
before training, or the fine-tune will overfit to the well-represented
categories.

---

## Stage 4: Train (GPU only)

Runs on a CUDA machine — not on Mac. Use Google Colab (free T4), a desktop
GPU, or a rented box.

```bash
# On the GPU machine, after copying the scored file over:
pip install unsloth trl datasets

python training/finetune/finetune.py \
  --data <path>/raw_<ts>_validated_scored.jsonl \
  --epochs 2 --lora-rank 16 --gguf gemma4_gguf
```

**Reads:**
- `output/03_scored/<file>_validated_scored.jsonl` — the dataset

**Writes:**
- `gemma4_lora/` — LoRA adapter
- `gemma4_gguf/` — quantized GGUF for Ollama (when `--gguf` passed)

**Defaults:** Unsloth, rank 8, 1 epoch, batch 1, lr 2e-4, max_seq_length 8192,
base `unsloth/gemma-4-E2B-it`. For ~115-example datasets, `--epochs 2 --lora-rank 16`
gives the fine-tune more capacity.

**Register the GGUF in local Ollama after copying back:**

```bash
printf 'FROM ./gemma4_gguf/<file>.gguf\nPARAMETER num_ctx 8192\n' > /tmp/Modelfile.wf
ollama create wayfinder-v2 -f /tmp/Modelfile.wf
```

The `num_ctx 8192` matters — without it Ollama defaults to 4K which truncates
the system prompt mid-rule.

---

## Stage 5: Eval (candidate) + Compare

Re-run the same eval suite against the fine-tuned model, then diff against the
baseline.

```bash
make eval MODEL=wayfinder-v2 JUDGE_ENDPOINT=http://your-llm-host:11434/v1

make compare \
  BASELINE=output/eval_results/eval_summary_medical-wayfinder-gemma-4-e2b_<ts>.json \
  CANDIDATE=output/eval_results/eval_summary_wayfinder-v2_<ts>.json
```

**Reads:**
- Two `eval_summary_*.json` files

**Writes:** stdout only (side-by-side diff)

**What the comparison shows:**
- Mean score delta (headline)
- Pass-rate delta
- JSON parse rate delta
- Per-criterion deltas (Correctness, Format, Landmarks, Accessibility, Scope)
- Per-category deltas
- Language split delta (EN−ES gap — widening gap counts as regression)

**Knobs:**

```bash
# Promote-or-block gate: exit 1 if any metric regresses > 0.05
make compare BASELINE=... CANDIDATE=... \
  # (or call compare_runs.py directly with --fail-on-regression --tolerate 0.05)
```

**What a successful fine-tune looks like:**

| Metric | Baseline (typical) | Fine-tune target |
|---|---:|---:|
| Mean score | 2.0–3.0 | 4.0+ |
| Pass rate | 20–30% | 70%+ |
| JSON parse rate | 50–80% | 95%+ |
| Format criterion | 2.0–2.7 | 4.5+ |
| Landmarks criterion | 1.5–2.0 | 3.5+ |
| Verbatim rate | 0–20% | 60%+ |

---

## Folder map

Quick reference of which stage reads/writes each folder:

| Folder | Stage(s) | Purpose |
|---|---|---|
| `data/seeds/raw_seeds.json` | 0 (input) | Hand-written multi-turn seeds |
| `data/seeds/seeds.jsonl` | 0 (output), 2 (read) | Compiled few-shot pool |
| `data/eval/raw_eval.json` | 0 (input) | Hand-written eval cases |
| `data/eval/eval_suite.jsonl` | 0 (output), 1+5 (read) | Compiled eval suite |
| `data/prompts/*.txt`, `*.json` | 1, 2, 3 (read) | All prompt files |
| `data/facilities/` | 0, 2 (read) | Facility JSON + topology (symlink) |
| `data/real_data/mined/best_phrases.json` | 2 (read) | 1000 mined directional phrases |
| `output/01_raw/` | 2 (write), 3 (read) | Teacher's raw output |
| `output/02_validated/` | 3 (read/write) | Post structural validation |
| `output/03_scored/` | 3 (write), 4 (read) | Final training data |
| `output/rejected/` | 3 (write) | Drops, with issue lists |
| `output/eval_results/` | 1, 5 (write), 5 (read) | Eval results + summaries |
| `output/04_final/` | reserved | Merged dataset (future) |

---

## Three sources of truth — keep them in sync

The wayfinding contract is defined in three places that **must** agree:

1. **`data/prompts/system_prompt.txt`** — shipped to the on-device model.
   Defines the 5 block types and 5 accessibility badges.
2. **`data/prompts/data_contract.json`** — JSON Schema enforced by `validate.py`.
3. **`health_wayfinder/lib/services/response_parser.dart`** — Dart parser that
   decodes model output. Hard-codes the same valid block types and badges.

Changing the contract in one place silently breaks the others. The system
prompt file lives under `training/` and is symlinked into the app at
`health_wayfinder/assets/system_prompt.txt`, so editing once updates both.
The training pipeline references `criteria.json` for evaluation; the Dart
parser references the contract for runtime parsing.

---

## Iteration loop

When the candidate eval shows a regression or insufficient lift, the loop is:

1. Read `compare_runs` output to find the weakest category or criterion
2. Inspect failed eval examples for that category in
   `output/eval_results/eval_results_<model>_<ts>.jsonl`
3. Choose the fix:
   - **Bad teacher output for a category** → `generate.py --category <name>` (regenerates only that category)
   - **Missing seed coverage** → add cases to `raw_seeds.json`, `make prepare`, regenerate
   - **Eval suite blind spot** → add cases to `raw_eval.json`, `make prepare`, re-eval baseline
   - **Validator letting bad data through** → tighten `validate.py` rules, re-filter existing raw file
   - **Judge being unreliable** → swap `JUDGE_MODEL` to a different-family alternative
4. `make filter && make eval && make compare` — one iteration cycle is ~45-60 min

---

## Two-judge cross-check (optional, post-fine-tune)

If the fine-tune wins by a small margin (<0.3 mean-score), validate the result
isn't a judge quirk by re-running with a different-family judge:

```bash
make eval MODEL=wayfinder-v2 JUDGE_MODEL=qwen3.5-27b JUDGE_ENDPOINT=http://your-llm-host:11434/v1
make compare \
  BASELINE=output/eval_results/eval_summary_wayfinder-v2_<gemma-judge-ts>.json \
  CANDIDATE=output/eval_results/eval_summary_wayfinder-v2_<qwen-judge-ts>.json
```

If both judges show the same wins on the same criteria, the result is robust.
If they disagree, the wins are judge-specific — investigate the failed cases.

---

## Directory layout

```
training/
  Makefile              # 5-stage orchestrator
  config.py             # paths, endpoints, helpers (single source of truth)
  requirements.txt      # openai, tqdm, python-dotenv
  INSTRUCTIONS.md       # this file
  .env.example          # template for training/.env

  scripts/              # one script per stage
    build_seeds.py      # stage 0
    build_eval.py       # stage 0
    generate.py         # stage 2
    validate.py         # stage 3
    score.py            # stage 3
    stats.py            # stage 3
    eval_runner.py      # stages 1 + 5
    eval_checks.py      # stage 1+5 helper (deterministic checks module)
    compare_runs.py     # stage 5

  data/                 # human-edited inputs
    seeds/              # raw + compiled seed conversations
    eval/               # raw + compiled eval cases
    prompts/            # system prompt, generation prompt, rubrics, schemas
    facilities/         # symlink to ../../health_wayfinder/assets/facilities
    real_data/          # mined phrases + raw datasets + mining scripts

  output/               # generated artifacts (gitignored content)
    raw/                # stage 2 output
    validated/          # stage 3 intermediate
    scored/             # stage 3 final (input to stage 4)
    rejected/           # stage 3 drops, with reasons
    eval_results/       # stage 1 + 5 output
    final/              # reserved for merged datasets

  finetune/             # GPU-only training (stage 4)
    finetune.py         # Unsloth LoRA fine-tuning
    smoke_litert.py     # LiteRT runtime probe (one-off)
```
