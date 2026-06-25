#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_PREFIX="$SCRIPT_DIR/.conda_env"
PSYCHOPY_HOME="$SCRIPT_DIR/.home"

if [ ! -x "$ENV_PREFIX/bin/python" ]; then
  echo "Missing environment at $ENV_PREFIX"
  echo "Create it with:"
  echo "  cd \"$SCRIPT_DIR\""
  echo "  conda env create -p ./.conda_env -f environment.yml"
  exit 1
fi

mkdir -p "$PSYCHOPY_HOME"
export HOME="$PSYCHOPY_HOME"

exec "$ENV_PREFIX/bin/python" "$SCRIPT_DIR/run_experiment.py" "$@"
