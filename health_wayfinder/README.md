# Medical Wayfinder — Flutter app

Patients describe a destination in English or Spanish; the app returns step-by-step directions, landmarks, accessibility info, and check-in instructions. The model — a fine-tuned Gemma 4 E2B — runs **on-device** in production, with a host-LLM fallback for development.

Model artifacts (merged safetensors, LoRA adapter, Q4_K_M GGUF) live at **[`jmdevita/medical-wayfinder-gemma-4-e2b`](https://huggingface.co/jmdevita/medical-wayfinder-gemma-4-e2b)** on the Hugging Face Hub.

This README covers the Flutter app. For the training pipeline see [`../training/INSTRUCTIONS.md`](../training/INSTRUCTIONS.md); for the model fetch/setup see [`../model/INSTRUCTIONS.md`](../model/INSTRUCTIONS.md).

## Prerequisites

| Tool | Why | Version |
|---|---|---|
| Flutter SDK | Build/run the app | Dart `^3.11.4` (Flutter 3.27+) |
| Xcode | iOS builds + Simulator | 15+ on macOS 14+ |
| Android Studio | Android builds + emulator | Hedgehog or newer |
| Ollama (or any OpenAI-compatible endpoint) | **Required for default `ollama` mode** — serves the fine-tuned model. Not needed if you build in `device` mode for real iPhone hardware. | Any recent |

Real-device iOS testing also requires an Apple Developer account (free tier works for 7-day installs).

## First-time setup

```bash
cd health_wayfinder
flutter pub get
flutter gen-l10n        # generate localization classes from app_en.arb / app_es.arb
```

The localization step writes to `lib/l10n/generated/` (committed). Re-run it any time you edit the `.arb` files.

## Run modes

`GemmaService` (`lib/services/gemma_service.dart`) supports two LLM backends, switched at compile time via a Dart define:

| Mode | Flag | What it does | When to use |
|---|---|---|---|
| `ollama` (default) | `--dart-define=GEMMA_MODE=ollama` (or omit) | POSTs to `http://127.0.0.1:11434/v1/chat/completions`. Pair with a local Ollama running the fine-tuned model. | Simulator, macOS, fast iteration. |
| `device` | `--dart-define=GEMMA_MODE=device` | On-device llama.cpp via `llama_cpp_dart` + Metal GPU. Loads `assets/models/model.gguf`. | Real iOS hardware. The IPA bundles a ~3.4 GB GGUF. |

Endpoint and model name can be overridden with additional defines — see the constants at the top of `gemma_service.dart` (`OLLAMA_URL`, `OLLAMA_MODEL`, `OLLAMA_API_KEY`).

### Ollama mode (recommended for dev)

```bash
# Terminal 1: serve the fine-tune
ollama serve
ollama run medical-wayfinder-gemma-4-e2b   # or whatever you tagged it

# Terminal 2: run the app
cd health_wayfinder
flutter run
```

### Device mode (real iPhone only)

1. Download the fine-tuned GGUF (~3.2 GB) into `model/model.gguf` — see [`../model/INSTRUCTIONS.md`](../model/INSTRUCTIONS.md) for the Hugging Face fetch commands. The asset bundle reaches it via the relative symlink at `assets/models/model.gguf`.
2. Build and run with the device-mode flag:
   ```bash
   flutter run --dart-define=GEMMA_MODE=device -d <your-iphone>
   ```
3. First launch copies the GGUF from the app bundle into the app's Documents directory (~30 s). Subsequent launches reuse the copy.

The iOS Simulator does **not** support device mode — llama.cpp's Metal backend needs real hardware. Use Ollama mode there.

## Daily commands

```bash
flutter analyze                                 # lints
flutter test                                    # all unit + widget tests
flutter test test/services/foo_test.dart        # one file
flutter test --name "parses steps"              # one test by name

# Run CI-equivalent checks (facility validation + analyze + test):
../scripts/check.sh
```

## Project layout

```
lib/
  app.dart                  MaterialApp shell; owns the home → loading → guide screen swap
  screens/                  home_screen, loading_screen, guide_screen, splash_screen
  services/
    gemma_service.dart      LLM backend (Ollama or on-device llama.cpp)
    response_parser.dart    Decodes JSON model output into GuideMessage objects
    facility_service.dart   Loads facility JSON from assets/
    speech_service.dart     STT (microphone -> text)
    photo_location_service.dart
    wayfinding_tools.dart   Tool/function calls the model can request
  models/                   Facility, GuideMessage, Topology, etc.
  l10n/                     app_en.arb, app_es.arb, generated/
  theme.dart                Colors, typography
assets/
  facilities/               Facility JSON (symlinked into training/data/)
  system_prompt.txt         Single source of truth for the model's system prompt
  models/model.gguf         Bundled GGUF (device mode only — symlinked, gitignored)
ios/, android/, macos/       Platform projects
test/                       Unit + widget tests
```

## Data contracts that must stay in sync

Three files describe the same schema; changing one without the others silently breaks parsing or training:

1. `assets/system_prompt.txt` — system prompt shipped to the model. Defines the JSON response contract.
2. `lib/services/response_parser.dart` — Dart parser. Block types (`destination`, `steps`, `disambig`, `guide_text`, `arrival`) and accessibility badges are hard-coded here.
3. `../training/data/prompts/` — generation prompt and scoring rubric used during fine-tuning. References the same `system_prompt.txt`.

When in doubt, the system prompt asset is the source of truth.

## Common gotchas

- **GGUF (~3.2 GB) is not in git.** New checkouts will see `assets/models/model.gguf` as a dangling symlink until you fetch the weights into `model/model.gguf` per [`../model/INSTRUCTIONS.md`](../model/INSTRUCTIONS.md). Ollama mode doesn't need the file.
- **Simulator can't reach `localhost:11434` automatically.** Info.plist has `NSAllowsLocalNetworking=true` so it works on the simulator; on Android emulators use `10.0.2.2` instead of `127.0.0.1`.
- **`flutter clean` deletes the bundled GGUF copy** inside `build/`. Not a problem unless you were relying on it as your only copy of the model — keep the source GGUF outside the build tree.
- **`flutter gen-l10n` needs to run** after every ARB edit. The generated files are committed so reviewers can diff strings.

## Contributing

PRs touching `health_wayfinder/**` trigger `.github/workflows/flutter-ci.yml` (pub get + analyze + test). Run `../scripts/check.sh` locally before pushing to match CI.

For substantive changes, the three-way data contract above is the key architectural invariant — touch one, touch all three.
