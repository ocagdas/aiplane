#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ACTION="doctor"
PROFILE="local-dev"
MODEL="qwen-tiny"
ENDPOINT="http://localhost:11434"
DRY_RUN=0
PID_FILE="$PROJECT_ROOT/.aiplane/ollama.pid"
LOG_FILE="$PROJECT_ROOT/.aiplane/ollama.log"

usage() {
  cat <<'USAGE'
Usage: scripts/ollama_helper.sh [options]

Actions:
  --action install     Install Ollama using the official Linux install script
  --action update      Re-run the official Ollama install script to update
  --action start       Start `ollama serve` in the background
  --action stop        Stop the background service started by this helper
  --action restart     Stop then start Ollama
  --action status      Show version and endpoint status
  --action doctor      Run endpoint status and aiplane model diagnostics
  --action pull        Pull one configured model, a raw Ollama model id, or all configured Ollama models
  --action repull      Re-pull models already present in the local Ollama store, or configured models with --model all
  --action list        List local models known to Ollama

Options:
  --profile NAME       aiplane profile to inspect (default: local-dev)
  --model NAME         configured model name, raw model id, or `all` for pull (default: qwen-tiny)
  --endpoint URL       Ollama endpoint (default: http://localhost:11434)
  --dry-run            Print commands without executing them
  -h, --help           Show this help

Examples:
  scripts/ollama_helper.sh --action install --dry-run
  scripts/ollama_helper.sh --action start
  scripts/ollama_helper.sh --action pull --model qwen-tiny
  scripts/ollama_helper.sh --action pull --model all
  scripts/ollama_helper.sh --action repull
  scripts/ollama_helper.sh --action doctor
USAGE
}

run() {
  printf '+'
  printf ' %q' "$@"
  printf '
'
  if [[ "$DRY_RUN" -eq 0 ]]; then
    "$@"
  fi
}

run_shell() {
  printf '+ %s
' "$*"
  if [[ "$DRY_RUN" -eq 0 ]]; then
    bash -lc "$*"
  fi
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --action) ACTION="${2:?missing value for --action}"; shift 2 ;;
    --profile) PROFILE="${2:?missing value for --profile}"; shift 2 ;;
    --model) MODEL="${2:?missing value for --model}"; shift 2 ;;
    --endpoint) ENDPOINT="${2:?missing value for --endpoint}"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

pulled_model_ids() {
  if ! command -v ollama >/dev/null 2>&1; then
    echo "ollama is not on PATH" >&2
    exit 1
  fi
  ollama list | awk 'NR > 1 && NF {print $1}'
}

repull_models() {
  if [[ "$MODEL" == "all" ]]; then
    pull_models
    return 0
  fi
  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "+ ollama list | awk 'NR > 1 && NF {print \$1}' | xargs -r -n1 ollama pull"
    return 0
  fi
  pulled_model_ids | while read -r model_id; do
    [[ -n "$model_id" ]] && run ollama pull "$model_id"
  done
}

case "$ACTION" in
  install|update|start|stop|restart|status|doctor|pull|repull|list) ;;
  *) echo "Unsupported action: $ACTION" >&2; exit 2 ;;
esac

cd "$PROJECT_ROOT"

aiplane_cmd() {
  if command -v aiplane >/dev/null 2>&1; then
    printf 'aiplane'
  else
    printf 'PYTHONPATH=%q python -m aiplane' "$PROJECT_ROOT/src"
  fi
}

install_or_update() {
  run_shell "curl -fsSL https://ollama.com/install.sh | sh"
}

start_ollama() {
  mkdir -p "$PROJECT_ROOT/.aiplane"
  if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    echo "Ollama helper service already running with PID $(cat "$PID_FILE")"
    return 0
  fi
  run_shell "nohup ollama serve > '$LOG_FILE' 2>&1 & echo \$! > '$PID_FILE'"
  echo "Log: $LOG_FILE"
}

stop_ollama() {
  if [[ ! -f "$PID_FILE" ]]; then
    echo "No helper-managed Ollama PID file found at $PID_FILE"
    return 0
  fi
  pid="$(cat "$PID_FILE")"
  if kill -0 "$pid" 2>/dev/null; then
    run kill "$pid"
  fi
  run rm -f "$PID_FILE"
}

format_tags_json() {
  PYTHONPATH="$PROJECT_ROOT/src" python - <<'PYFORMAT'
import json
import os

try:
    payload = json.loads(os.environ.get("TAGS_JSON", ""))
except Exception as exc:
    print(f"  models: unavailable ({exc})")
    raise SystemExit(0)
models = payload.get("models", []) if isinstance(payload, dict) else []

def _format_size(value):
    try:
        size = float(value)
    except (TypeError, ValueError):
        return "unknown"
    units = ["B", "KB", "MB", "GB", "TB"]
    index = 0
    while size >= 1024 and index < len(units) - 1:
        size /= 1024
        index += 1
    return f"{size:.1f}{units[index]}"

print(f"  models: {len(models)}")
for model in models:
    if not isinstance(model, dict):
        continue
    details = model.get("details", {}) if isinstance(model.get("details"), dict) else {}
    caps = model.get("capabilities", [])
    caps_text = ", ".join(str(item) for item in caps) if isinstance(caps, list) else ""
    fields = [
        f"model={model.get('model') or model.get('name')}",
        f"size={_format_size(model.get('size'))}",
        f"params={details.get('parameter_size') or 'unknown'}",
        f"quant={details.get('quantization_level') or 'unknown'}",
    ]
    if caps_text:
        fields.append(f"capabilities={caps_text}")
    print("  - " + str(model.get("name") or model.get("model") or "unknown"))
    print("    " + "; ".join(fields))
PYFORMAT
}

helper_process_status() {
  if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    echo "running (pid $(cat "$PID_FILE"))"
  else
    echo "not running or not helper-managed"
  fi
}

status_ollama() {
  echo "Ollama status"
  echo "  endpoint: $ENDPOINT"
  echo "  helper_process: $(helper_process_status)"
  if command -v ollama >/dev/null 2>&1; then
    version="$(ollama --version 2>&1 || true)"
    echo "  version: ${version:-unknown}"
  else
    echo "  version: unavailable (ollama is not on PATH)"
  fi
  if ! command -v curl >/dev/null 2>&1; then
    echo "  api_running: unknown (curl is not on PATH)"
    return 0
  fi
  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "  api_running: dry-run (would query $ENDPOINT/api/tags)"
    return 0
  fi
  tags_json="$(curl -fsS "$ENDPOINT/api/tags" 2>/dev/null || true)"
  if [[ -z "$tags_json" ]]; then
    echo "  api_running: no"
    echo "  models: unavailable"
    return 0
  fi
  echo "  api_running: yes"
  TAGS_JSON="$tags_json" format_tags_json
}

list_ollama() {
  echo "Local Ollama models"
  if ! command -v ollama >/dev/null 2>&1; then
    echo "  unavailable: ollama is not on PATH"
    return 1
  fi
  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "  dry-run: would run ollama list"
    return 0
  fi
  ollama list
}

configured_model_ids() {
  PYTHONPATH="$PROJECT_ROOT/src" python - "$PROFILE" <<'PYMODEL'
from pathlib import Path
import sys
from aiplane.config import load_profile
from aiplane.model_catalog import ModelCatalog
profile = load_profile(sys.argv[1], Path.cwd())
for name, model in ModelCatalog(profile).models().items():
    if model.get("provider") == "ollama" and model.get("enabled", True):
        print(f"{name}	{model.get('model')}")
PYMODEL
}

resolve_model_id() {
  if [[ "$MODEL" == *":"* ]]; then
    printf '%s
' "$MODEL"
    return 0
  fi
  configured_model_ids | awk -F '	' -v wanted="$MODEL" '$1 == wanted {print $2}'
}

pull_models() {
  if [[ "$MODEL" == "all" ]]; then
    configured_model_ids | while IFS=$'	' read -r _name model_id; do
      [[ -n "$model_id" ]] && run ollama pull "$model_id"
    done
    return 0
  fi
  model_id="$(resolve_model_id)"
  if [[ -z "$model_id" ]]; then
    echo "Unknown configured model '$MODEL'. Use --model all or a raw Ollama id like qwen2.5-coder:0.5b." >&2
    exit 1
  fi
  run ollama pull "$model_id"
}

pulled_model_ids() {
  if ! command -v ollama >/dev/null 2>&1; then
    echo "ollama is not on PATH" >&2
    exit 1
  fi
  ollama list | awk 'NR > 1 && NF {print $1}'
}

repull_models() {
  if [[ "$MODEL" == "all" ]]; then
    pull_models
    return 0
  fi
  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "+ ollama list | awk 'NR > 1 && NF {print \$1}' | xargs -r -n1 ollama pull"
    return 0
  fi
  pulled_model_ids | while read -r model_id; do
    [[ -n "$model_id" ]] && run ollama pull "$model_id"
  done
}

case "$ACTION" in
  install|update)
    install_or_update
    ;;
  start)
    start_ollama
    ;;
  stop)
    stop_ollama
    ;;
  restart)
    stop_ollama
    start_ollama
    ;;
  status)
    status_ollama
    ;;
  doctor)
    status_ollama || true
    run_shell "$(aiplane_cmd) models doctor --profile '$PROFILE'"
    ;;
  pull)
    pull_models
    ;;
  repull)
    repull_models
    ;;
  list)
    list_ollama
    ;;
esac
