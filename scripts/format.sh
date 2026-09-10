#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-check}"

case "$MODE" in
  check)
    python -m ruff format --check src tests scripts
    ;;
  fix|write)
    python -m ruff format src tests scripts
    python -m ruff check --fix src tests scripts
    ;;
  *)
    echo "Usage: scripts/format.sh [check|fix]" >&2
    exit 2
    ;;
esac
