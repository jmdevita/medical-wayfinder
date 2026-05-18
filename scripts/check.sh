#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"

echo "== validate facility data =="
python3 "$ROOT/tools/validate_facility.py" --all

cd "$ROOT/health_wayfinder"

echo "== flutter pub get =="
flutter pub get

echo "== flutter analyze =="
# --no-fatal-warnings: the on-device GGUF asset (model/model.gguf) is fetched
# separately per model/INSTRUCTIONS.md, so the bundled-asset path is allowed
# to be missing in a fresh checkout. Warnings still print; only errors abort.
flutter analyze --no-fatal-warnings

echo "== flutter test =="
flutter test

echo "All checks passed."
