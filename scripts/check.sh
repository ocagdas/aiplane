#!/usr/bin/env bash
set -euo pipefail

scripts/format.sh check
python -m ruff check src tests
PYTHONPATH=src python -m pytest -q
