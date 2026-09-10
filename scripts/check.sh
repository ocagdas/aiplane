#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-full}"

case "$MODE" in
  full)
    scripts/format.sh check
    python -m ruff check src tests scripts
    python scripts/check_repository_standard.py
    python -m pytest -q -n "${AIPLANE_TEST_WORKERS:-4}" --dist loadfile
    ;;
  quick)
    scripts/format.sh check
    python -m ruff check src tests scripts
    python scripts/check_repository_standard.py
    python -m pytest -q tests/test_contracts.py tests/test_quick_smoke.py
    ;;
  *)
    echo "Usage: scripts/check.sh [full|quick]" >&2
    echo "Runs with the Python environment in which the script is invoked." >&2
    exit 2
    ;;
esac
