#!/usr/bin/env bash
# One-time environment setup for the training pipeline and tools/.
#
# Creates the shared `env/` virtualenv at repo root and installs the Python
# dependencies that training/ and tools/ both rely on. Atlas requires
# additional packages — after this script, run `cd atlas && make install`
# to install those into the same virtualenv.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENV="$ROOT/env"

if [ -d "$VENV" ]; then
    echo "Virtualenv already exists at $VENV"
else
    echo "Creating virtualenv at $VENV"
    python3 -m venv "$VENV"
fi

"$VENV/bin/pip" install --upgrade pip
"$VENV/bin/pip" install -r "$ROOT/training/requirements.txt"

echo
echo "Done. Python deps installed in $VENV"
echo
echo "Next steps:"
echo "  • Training pipeline:   see training/INSTRUCTIONS.md"
echo "  • Topology authoring:  see tools/INSTRUCTIONS.md"
echo "  • Atlas dashboard:     cd atlas && make install"
