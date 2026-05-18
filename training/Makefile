# Training pipeline tooling.
#
# Five-stage flow (full docs in INSTRUCTIONS.md):
#
#   ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐
#   │   eval   │ → │ generate │ → │  filter  │ → │  train   │ → │   eval   │
#   │ (baseline)│  │ (teacher │   │ (validate│   │  (GPU,   │   │(candidate│
#   │          │   │  writes) │   │ +score   │   │ Unsloth  │   │ + compare│
#   │          │   │          │   │ +stats)  │   │  LoRA)   │   │          │
#   └──────────┘   └──────────┘   └──────────┘   └──────────┘   └──────────┘
#       ↓               ↓              ↓              ↓               ↓
#   eval_results/    raw/         scored/       gemma4_gguf/    eval_results/
#                                                              (compare to ①)
#
# Reuses the repo-root env/ virtualenv. The targets here are wrappers — each
# step is still independently runnable as `env/bin/python scripts/<name>.py`
# for debugging.
#
# Quick recipe:
#   make prepare                                       # one-time: build seeds + eval suite
#   make eval MODEL=medical-wayfinder-gemma-4-e2b                      # 1. baseline
#   make generate                                      # 2. teacher writes 248 batches
#   make filter                                        # 3. clean + score + stats
#   #  ...copy output/03_scored/<file>.jsonl to a GPU box, run finetune.py...
#   make eval MODEL=wayfinder-v2                       # 5a. candidate eval
#   make compare BASELINE=<old.json> CANDIDATE=<new.json>  # 5b. diff

REPO_ROOT := $(realpath ..)
VENV      := $(REPO_ROOT)/env
PY        := $(VENV)/bin/python

# Override at the command line, e.g. `make eval MODEL=health-wayfinder:v2`.
MODEL     ?= gemma4:e2b

# Default judge for eval AND for `make score`. Override per-run if you
# have a stronger judge behind a different endpoint.
JUDGE_MODEL    ?= gemma4-31b
JUDGE_ENDPOINT ?= http://localhost:11434/v1

# Teacher used by `make generate` to write synthetic training conversations.
# Should be a strong, different-family model from JUDGE_MODEL to avoid
# self-preference bias (see ~/training/data/prompts/criteria.json).
# Default endpoint is localhost — for real fine-tuning you'll typically point
# this at a remote box with a larger model. Override per-run or set in
# training/.env (see .env.example).
TEACHER_MODEL    ?= qwen3.5-122b
TEACHER_ENDPOINT ?= http://localhost:11434/v1

# Concurrency knobs. CONCURRENCY caps target parallelism (match
# OLLAMA_NUM_PARALLEL on the target box). JUDGE_CONCURRENCY caps judge
# parallelism — drop to 1 when the judge endpoint serializes (single-slot
# llama-swap, large remote judge). Defaults match config.py's CONCURRENCY=3.
CONCURRENCY       ?= 3
JUDGE_CONCURRENCY ?= 3

.PHONY: help prepare eval eval-quick eval-resume generate filter validate score score-resume stats compare clean-rejected

help:
	@echo "Training pipeline targets (run from training/):"
	@echo ""
	@echo "  make prepare           Build seeds + eval suite (raw_*.json -> *.jsonl)"
	@echo "  make eval              Run eval against MODEL=$(MODEL)"
	@echo "  make eval-quick        Eval first 5 examples (smoke test)"
	@echo "  make eval-resume       Resume an interrupted eval run"
	@echo "  make generate          Generate synthetic training data"
	@echo "                         (teacher = TEACHER_MODEL @ TEACHER_ENDPOINT)"
	@echo "  make filter            Validate + score + stats on the latest raw file"
	@echo "                         (judge = JUDGE_MODEL @ JUDGE_ENDPOINT)"
	@echo "  make validate [FILE=]  Validate raw .jsonl (defaults to latest)"
	@echo "  make score    [FILE=]  Score validated .jsonl (defaults to latest)"
	@echo "                         (judge = JUDGE_MODEL @ JUDGE_ENDPOINT)"
	@echo "  make score-resume [FILE=]  Resume an interrupted score run"
	@echo "  make stats    [FILE=]  Show stats on scored .jsonl (defaults to latest)"
	@echo "  make compare BASELINE=<file> CANDIDATE=<file>"
	@echo "                         Diff two eval_summary_*.json files"
	@echo ""
	@echo "Variables (override on the command line):"
	@echo "  MODEL=$(MODEL)"
	@echo "  JUDGE_MODEL=$(JUDGE_MODEL)"
	@echo "  JUDGE_ENDPOINT=$(JUDGE_ENDPOINT)"
	@echo "  TEACHER_MODEL=$(TEACHER_MODEL)"
	@echo "  TEACHER_ENDPOINT=$(TEACHER_ENDPOINT)"

prepare:
	$(PY) scripts/build_seeds.py
	$(PY) scripts/build_eval.py

eval:
	OPENAI_MODEL=$(MODEL) $(PY) scripts/eval_runner.py \
	    --judge-model $(JUDGE_MODEL) --judge-endpoint $(JUDGE_ENDPOINT) \
	    --concurrency $(CONCURRENCY) --judge-concurrency $(JUDGE_CONCURRENCY)

eval-quick:
	OPENAI_MODEL=$(MODEL) $(PY) scripts/eval_runner.py --limit 5 \
	    --judge-model $(JUDGE_MODEL) --judge-endpoint $(JUDGE_ENDPOINT) \
	    --concurrency $(CONCURRENCY) --judge-concurrency $(JUDGE_CONCURRENCY)

eval-resume:
	OPENAI_MODEL=$(MODEL) $(PY) scripts/eval_runner.py --resume \
	    --judge-model $(JUDGE_MODEL) --judge-endpoint $(JUDGE_ENDPOINT) \
	    --concurrency $(CONCURRENCY) --judge-concurrency $(JUDGE_CONCURRENCY)

generate:
	$(PY) scripts/generate.py \
	    --model $(TEACHER_MODEL) --endpoint $(TEACHER_ENDPOINT)

# One-shot post-generation pipeline: validate -> score -> stats on the
# latest raw_*.jsonl. Auto-picks the most recent input at each stage so
# you don't have to copy timestamps around. Use the individual targets
# (validate FILE=..., score FILE=...) if you need to operate on a
# specific older file.
filter:
	@RAW=$$(ls -t output/01_raw/*.jsonl 2>/dev/null | head -1); \
	  if [ -z "$$RAW" ]; then echo "No file in output/01_raw/ — run 'make generate' first"; exit 1; fi; \
	  echo "==> Validating $$RAW"; \
	  $(PY) scripts/validate.py "$$RAW" || exit $$?
	@VAL=$$(ls -t output/02_validated/*.jsonl 2>/dev/null | head -1); \
	  if [ -z "$$VAL" ]; then echo "No file in output/02_validated/"; exit 1; fi; \
	  echo "==> Scoring $$VAL (judge: $(JUDGE_MODEL) @ $(JUDGE_ENDPOINT))"; \
	  $(PY) scripts/score.py "$$VAL" \
	      --model $(JUDGE_MODEL) --endpoint $(JUDGE_ENDPOINT) || exit $$?
	@$(MAKE) -s stats

# validate / score default to the latest file in their input dir but
# always print which file was picked. Override with FILE=<path> for
# explicit selection. The visible echo matters: it's the safety net
# against silently processing the wrong file when multiple runs are
# lying around (e.g. you ran two `make generate` invocations in a row).
validate:
	@FILE_TO_USE="$(FILE)"; \
	  if [ -z "$$FILE_TO_USE" ]; then \
	    FILE_TO_USE=$$(ls -t output/01_raw/*.jsonl 2>/dev/null | head -1); \
	    if [ -z "$$FILE_TO_USE" ]; then \
	      echo "No file in output/01_raw/ — run 'make generate' first, or pass FILE=<path>"; \
	      exit 1; \
	    fi; \
	    COUNT=$$(ls output/01_raw/*.jsonl 2>/dev/null | wc -l | tr -d ' '); \
	    echo "==> Validating $$FILE_TO_USE"; \
	    echo "    (latest of $$COUNT raw file(s); override with FILE=<path>)"; \
	  else \
	    echo "==> Validating $$FILE_TO_USE"; \
	  fi; \
	  $(PY) scripts/validate.py "$$FILE_TO_USE"

score:
	@FILE_TO_USE="$(FILE)"; \
	  if [ -z "$$FILE_TO_USE" ]; then \
	    FILE_TO_USE=$$(ls -t output/02_validated/*.jsonl 2>/dev/null | head -1); \
	    if [ -z "$$FILE_TO_USE" ]; then \
	      echo "No file in output/02_validated/ — run 'make validate' first, or pass FILE=<path>"; \
	      exit 1; \
	    fi; \
	    COUNT=$$(ls output/02_validated/*.jsonl 2>/dev/null | wc -l | tr -d ' '); \
	    echo "==> Scoring $$FILE_TO_USE (judge: $(JUDGE_MODEL) @ $(JUDGE_ENDPOINT))"; \
	    echo "    (latest of $$COUNT validated file(s); override with FILE=<path>)"; \
	  else \
	    echo "==> Scoring $$FILE_TO_USE (judge: $(JUDGE_MODEL) @ $(JUDGE_ENDPOINT))"; \
	  fi; \
	  $(PY) scripts/score.py "$$FILE_TO_USE" \
	      --model $(JUDGE_MODEL) --endpoint $(JUDGE_ENDPOINT)

score-resume:
	@FILE_TO_USE="$(FILE)"; \
	  if [ -z "$$FILE_TO_USE" ]; then \
	    FILE_TO_USE=$$(ls -t output/02_validated/*.jsonl 2>/dev/null | head -1); \
	    if [ -z "$$FILE_TO_USE" ]; then \
	      echo "No file in output/02_validated/ — run 'make validate' first, or pass FILE=<path>"; \
	      exit 1; \
	    fi; \
	    echo "==> Resuming score for $$FILE_TO_USE (judge: $(JUDGE_MODEL) @ $(JUDGE_ENDPOINT))"; \
	  else \
	    echo "==> Resuming score for $$FILE_TO_USE (judge: $(JUDGE_MODEL) @ $(JUDGE_ENDPOINT))"; \
	  fi; \
	  $(PY) scripts/score.py "$$FILE_TO_USE" --resume \
	      --model $(JUDGE_MODEL) --endpoint $(JUDGE_ENDPOINT)

stats:
	@FILE_TO_USE="$(FILE)"; \
	  if [ -z "$$FILE_TO_USE" ]; then \
	    FILE_TO_USE=$$(ls -t output/03_scored/*.jsonl 2>/dev/null | head -1); \
	    if [ -z "$$FILE_TO_USE" ]; then \
	      echo "No file in output/03_scored/ — run 'make score' first, or pass FILE=<path>"; \
	      exit 1; \
	    fi; \
	    COUNT=$$(ls output/03_scored/*.jsonl 2>/dev/null | wc -l | tr -d ' '); \
	    echo "==> Stats for $$FILE_TO_USE"; \
	    echo "    (latest of $$COUNT scored file(s); override with FILE=<path>)"; \
	  else \
	    echo "==> Stats for $$FILE_TO_USE"; \
	  fi; \
	  $(PY) scripts/stats.py "$$FILE_TO_USE"

compare:
	@if [ -z "$(BASELINE)" ] || [ -z "$(CANDIDATE)" ]; then \
	    echo "Usage: make compare BASELINE=<old_summary.json> CANDIDATE=<new_summary.json>"; \
	    echo "       (or pass --baseline/--candidate substrings to compare_runs.py directly)"; \
	    exit 1; \
	fi
	$(PY) scripts/compare_runs.py "$(BASELINE)" "$(CANDIDATE)"

clean-rejected:
	rm -f output/rejected/*.jsonl
