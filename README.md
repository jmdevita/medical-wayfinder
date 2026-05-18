# Medical Wayfinder

[![Flutter CI](https://github.com/jmdevita/medical-wayfinder/actions/workflows/flutter-ci.yml/badge.svg)](https://github.com/jmdevita/medical-wayfinder/actions/workflows/flutter-ci.yml) [![Hugging Face Model](https://img.shields.io/badge/%F0%9F%A4%97%20Hugging%20Face-Model-yellow)](https://huggingface.co/jmdevita/medical-wayfinder-gemma-4-e2b)

A healthcare wayfinding assistant. Patients describe a destination in English or Spanish; the app returns step-by-step directions with landmarks, accessibility info, and check-in instructions. The model — a fine-tuned Gemma 4 E2B — runs on-device.

Model weights (merged safetensors, LoRA adapter, Q4_K_M GGUF) are published at [`jmdevita/medical-wayfinder-gemma-4-e2b`](https://huggingface.co/jmdevita/medical-wayfinder-gemma-4-e2b). See [`model/INSTRUCTIONS.md`](model/INSTRUCTIONS.md) for fetch commands.

## Live demo

Because the model runs **fully on-device** with no backend, there is no hosted URL to click — the demo *is* the local build. Two ways to see it in action:

- **Watch the video walkthrough** — linked from the Kaggle writeup.
- **Run it yourself** — follow [Quick start](#quick-start) below. On a Mac with Flutter + Ollama installed, you'll be at the home screen within a few minutes of `git clone`.

## Repo map

| Directory | What's there | Start here |
|---|---|---|
| [`health_wayfinder/`](health_wayfinder/) | Flutter app (iOS, Android, macOS) | [`health_wayfinder/README.md`](health_wayfinder/README.md) |
| [`training/`](training/) | Data-generation + fine-tuning pipeline (Python) | [`training/INSTRUCTIONS.md`](training/INSTRUCTIONS.md) |
| [`tools/`](tools/) | Per-hospital topology authoring scripts | [`tools/INSTRUCTIONS.md`](tools/INSTRUCTIONS.md) |
| [`atlas/`](atlas/) | V2 web dashboard for authoring topology data | [`atlas/README.md`](atlas/README.md) |

## Quick start

### 1. Install dependencies

- [Flutter SDK](https://docs.flutter.dev/get-started/install) 3.27+
- [Ollama](https://ollama.com/download) — required for the default `ollama` run mode
- macOS only: Xcode 15+ for iOS Simulator builds

### 2. Fetch the fine-tuned model

The app's default mode talks to a local Ollama serving the fine-tuned Gemma 4 E2B. Download the GGUF per [`model/INSTRUCTIONS.md`](model/INSTRUCTIONS.md) (Hugging Face), then register it with Ollama under the name the app expects:

```bash
# from the repo root, after model/model.gguf is in place:
printf 'FROM ./model/model.gguf\nPARAMETER num_ctx 8192\n' > /tmp/Modelfile.wf
ollama create medical-wayfinder-gemma-4-e2b -f /tmp/Modelfile.wf
```

### 3. Clone and run

```bash
git clone https://github.com/jmdevita/medical-wayfinder.git
cd medical-wayfinder

ollama serve                                            # leave running
cd health_wayfinder && flutter pub get && flutter run   # in another shell
```

For full prerequisites, on-device (real iPhone) mode, and gotchas see [`health_wayfinder/README.md`](health_wayfinder/README.md). To set up the **training pipeline** or **tools/**, run `./scripts/setup.sh` from the repo root (creates the shared `env/` virtualenv). To set up **atlas**, run `cd atlas && make install`.

## Development

Run the same checks CI runs on PRs:

```bash
./scripts/check.sh    # facility data validation + flutter analyze + flutter test
```

CI (`.github/workflows/flutter-ci.yml`) runs on PRs and pushes to `main` that touch `health_wayfinder/**` or the facility validator. The training pipeline and atlas aren't CI-gated.

## Built for

[The Gemma 4 Good Hackathon](https://www.kaggle.com/competitions/gemma-4-good-hackathon) — fine-tuning Gemma 4 E2B for healthcare navigation.
