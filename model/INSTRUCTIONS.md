# Model

This directory holds the fine-tuned Gemma 4 E2B GGUF (~3.2 GB). It's used
in **both** of the app's run modes — just via different mechanisms:

- **`ollama` mode (default)** — you register the GGUF with a local Ollama
  instance (`ollama create medical-wayfinder-gemma-4-e2b -f Modelfile`); the Flutter app
  then talks to Ollama over HTTP. The Modelfile points at `./model/model.gguf`,
  so the file needs to be here.
- **`device` mode (real iPhone)** — Flutter bundles the GGUF as an asset via
  the relative symlink `health_wayfinder/assets/models/model.gguf →
  ../../../model/model.gguf`, then llama.cpp + Metal GPU loads it on-device.

In both cases, once you've saved the real file as `model/model.gguf`, no
further wiring is needed. The GGUF is gitignored — only the small text-file
stub (described below) is checked in.

## Download from Hugging Face

The fine-tuned, Q4_K_M-quantized model is published at:

**[`jmdevita/medical-wayfinder-gemma-4-e2b`](https://huggingface.co/jmdevita/medical-wayfinder-gemma-4-e2b)**

The repo also hosts the merged BF16 safetensors and the LoRA adapter — see the model card there if you want to re-quantize or work at full precision. For running the app, you only need the Q4_K_M GGUF.

### Option A — `huggingface-cli` (recommended)

```bash
pip install -U huggingface_hub

# from the repo root:
huggingface-cli download jmdevita/medical-wayfinder-gemma-4-e2b \
    gemma-4-e2b-it.Q4_K_M.gguf \
    --local-dir model/ \
    --local-dir-use-symlinks False

# rename to the canonical name the app expects:
mv model/gemma-4-e2b-it.Q4_K_M.gguf model/model.gguf
```

### Option B — direct download

```bash
# from the repo root:
curl -L -o model/model.gguf \
    "https://huggingface.co/jmdevita/medical-wayfinder-gemma-4-e2b/resolve/main/gemma-4-e2b-it.Q4_K_M.gguf"
```

(The HF repo file is named `gemma-4-e2b-it.Q4_K_M.gguf`; the app's symlink chain expects `model/model.gguf`. The rename happens above; `curl` writes directly to the right name.)

## Verify

```bash
ls -lh model/model.gguf                          # should be ~3.2 GB
file model/model.gguf                            # "data" (binary)
ls -l health_wayfinder/assets/models/model.gguf  # symlink resolves
```

If the symlink shows as broken, you saved the file under a different name —
either rename to `model.gguf` or re-point the symlink:

```bash
ln -sf ../../../model/<your-filename>.gguf health_wayfinder/assets/models/model.gguf
```

## About the tracked `model.gguf` stub

This directory ships with a tiny text-file stub named `model.gguf` so the
Flutter asset bundler (`flutter analyze`, `flutter test`, `flutter build`)
and CI have something concrete to point at on a fresh checkout. When you
download the real weights above, you'll overwrite this stub.

Once overwritten, git will see `model/model.gguf` as a multi-gigabyte
modification on every `git status`. Tell git to ignore the local change so
you don't accidentally commit it:

```bash
git update-index --skip-worktree model/model.gguf
```

To undo (e.g. if the stub itself ever needs updating):

```bash
git update-index --no-skip-worktree model/model.gguf
```

## Build the iOS app with the model bundled

```bash
cd health_wayfinder
flutter run --dart-define=GEMMA_MODE=device -d <your-iphone>
```

First launch copies the GGUF from the app bundle into the device's Documents
directory (~30 s). Subsequent launches reuse the copy. See
`health_wayfinder/README.md` for the full device-mode walkthrough.

## Why isn't the model in git?

GGUF files are multiple gigabytes; GitHub rejects files over 100 MB and even
Git LFS makes clones painful. The standard pattern for shipping
large-artifact ML apps is: keep the code in git, host the weights on
Hugging Face, and document the fetch step here.
