#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

TEST_PROFILE_TEMPLATE="${AIPLANE_TEST_PROFILE_TEMPLATE:-local-dev}"
TEST_PROFILE_NAME="${AIPLANE_TEST_PROFILE_NAME:-ci-test}"
SOURCE_PROFILE_ROOT="${PROJECT_ROOT}/profile-templates/${TEST_PROFILE_TEMPLATE}"
if [[ ! -d "$SOURCE_PROFILE_ROOT" ]]; then
  echo "warning: profile template '$TEST_PROFILE_TEMPLATE' not found; falling back to local-dev" >&2
  SOURCE_PROFILE_ROOT="${PROJECT_ROOT}/profile-templates/local-dev"
  TEST_PROFILE_NAME="ci-test"
  TEST_PROFILE_TEMPLATE="local-dev"
fi

WORK_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/aiplane-test-clean.XXXXXX")"
trap 'rm -rf "$WORK_ROOT"' EXIT

mkdir -p "$WORK_ROOT/profiles"
cp -R "$SOURCE_PROFILE_ROOT" "$WORK_ROOT/profiles/$TEST_PROFILE_NAME"
if [[ "$TEST_PROFILE_NAME" != "local-dev" ]]; then
  cp -R "$WORK_ROOT/profiles/$TEST_PROFILE_NAME" "$WORK_ROOT/profiles/local-dev"
fi

# Keep a deterministic workspace-local profiles directory so direct filesystem fixture
# paths used by older tests (for example profiles/local-dev) remain valid.
REPO_PROFILES_DIR="${PROJECT_ROOT}/profiles"
mkdir -p "$REPO_PROFILES_DIR"
rm -rf \
  "$REPO_PROFILES_DIR/$TEST_PROFILE_NAME" \
  "$REPO_PROFILES_DIR/local-dev"
cp -R "$WORK_ROOT/profiles/$TEST_PROFILE_NAME" "$REPO_PROFILES_DIR/$TEST_PROFILE_NAME"
cp -R "$WORK_ROOT/profiles/local-dev" "$REPO_PROFILES_DIR/local-dev"

printf 'Using profile template %s as temporary profile %s at %s\\n' \
  "$TEST_PROFILE_TEMPLATE" "$TEST_PROFILE_NAME" "$WORK_ROOT/profiles/$TEST_PROFILE_NAME" >&2

cd "$PROJECT_ROOT"
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="${PYTHONPATH:-src}"
export AIPLANE_PROFILES_DIR="$WORK_ROOT/profiles"

if [[ "$#" -eq 0 ]]; then
  set -- -m pytest -q
fi

PYTHON_BIN="${PYTHON:-python}"
exec "$PYTHON_BIN" "$@"
