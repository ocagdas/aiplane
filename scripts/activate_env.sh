#!/usr/bin/env bash
# Source this file to activate a project environment in the current shell.
# Examples:
#   source scripts/activate_env.sh venv
#   source scripts/activate_env.sh conda aiplane

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  echo "This helper must be sourced so activation affects your current shell:" >&2
  echo "  source scripts/activate_env.sh venv" >&2
  echo "  source scripts/activate_env.sh conda aiplane" >&2
  exit 2
fi

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODE="${1:-venv}"
CONDA_ENV="${2:-aiplane}"

case "$MODE" in
  venv)
    source "$PROJECT_ROOT/.venv/bin/activate"
    ;;
  conda)
    if ! command -v conda >/dev/null 2>&1; then
      echo "conda is not on PATH" >&2
      return 1
    fi
    eval "$(conda shell.bash hook)"
    conda activate "$CONDA_ENV"
    ;;
  *)
    echo "Unsupported activation mode: $MODE" >&2
    return 2
    ;;
esac

aiplane profiles bootstrap-local --no-discovery >/dev/null && echo "Activated $MODE environment; aiplane is available."
