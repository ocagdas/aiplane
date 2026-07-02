#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ACTION="doctor"
PROFILE="local-dev"
MODEL=""
ENDPOINT="http://localhost:11434"
DRY_RUN=0
SUBSTRATE="native"
OLLAMA_DOCKER_IMAGE="${OLLAMA_DOCKER_IMAGE:-ollama/ollama:latest}"
OLLAMA_DOCKER_CONTAINER="${OLLAMA_DOCKER_CONTAINER:-aiplane-ollama}"
OLLAMA_DOCKER_VOLUME="${OLLAMA_DOCKER_VOLUME:-aiplane-ollama}"
OLLAMA_DOCKER_GPUS="${OLLAMA_DOCKER_GPUS:-}"
PID_FILE="$PROJECT_ROOT/.aiplane/ollama.pid"
LOG_FILE="$PROJECT_ROOT/.aiplane/ollama.log"

usage() {
  cat <<'USAGE'
Usage: scripts/ollama_helper.sh [options]

Actions:
  --action install     Install Ollama using the official Linux install script, or pull ollama/ollama with --substrate docker
  --action update      Re-run the official Ollama install script to update
  --action start       Start `ollama serve` in the background, or start the ollama/ollama container with --substrate docker
  --action stop        Stop the background service started by this helper
  --action restart     Stop then start Ollama
  --action status      Show version and endpoint status
  --action doctor      Run endpoint status and aiplane model diagnostics
  --action pull        Pull one configured model, a raw Ollama model id, or all configured Ollama models
  --action repull      Re-pull models already present in the local Ollama store, or configured models with --model all
  --action remove      Remove one pulled model from the local Ollama store
  --action clear       Remove all pulled models from the local Ollama store
  --action list        List local models known to Ollama

Options:
  --profile NAME       aiplane profile to inspect (default: local-dev)
  --model NAME         configured model name, raw model id, or `all` for pull (default: none)
  --endpoint URL       Ollama endpoint (default: http://localhost:11434)
  --substrate native|docker Runtime substrate to use (default: native)
  --dry-run            Print commands without executing them
  -h, --help           Show this help

Examples:
  scripts/ollama_helper.sh --action install --dry-run
  scripts/ollama_helper.sh --action install --substrate docker --dry-run
  scripts/ollama_helper.sh --action start
  scripts/ollama_helper.sh --action pull --model MODEL_ALIAS
  scripts/ollama_helper.sh --action pull --model all
  scripts/ollama_helper.sh --action repull
  scripts/ollama_helper.sh --action remove --model MODEL_ALIAS
  scripts/ollama_helper.sh --action clear --dry-run
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
    --substrate) SUBSTRATE="${2:?missing value for --substrate}"; shift 2 ;;
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
  if [[ -n "$MODEL" && "$MODEL" != "all" ]]; then
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

remove_model() {
  if [[ -z "$MODEL" || "$MODEL" == "all" ]]; then
    echo "remove requires --model with one configured alias or runtime model id; use --action clear for all pulled models" >&2
    exit 2
  fi
  model_id="$(resolve_model_id)"
  if [[ -z "$model_id" ]]; then
    echo "Unknown configured model '$MODEL'. Use an Ollama alias, a Hugging Face GGUF alias compatible with Ollama, or a raw id like provider-text-small:0.5b or hf.co/provider/model." >&2
    exit 1
  fi
  run ollama rm "$model_id"
}

clear_models() {
  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "+ ollama list | awk 'NR > 1 && NF {print \$1}' | xargs -r -n1 ollama rm"
    return 0
  fi
  pulled_model_ids | while read -r model_id; do
    [[ -n "$model_id" ]] && run ollama rm "$model_id"
  done
}

case "$SUBSTRATE" in
  native|docker) ;;
  *) echo "Unsupported substrate: $SUBSTRATE" >&2; exit 2 ;;
esac

case "$ACTION" in
  install|update|start|stop|restart|status|doctor|pull|repull|remove|clear|list) ;;
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

docker_args() {
  args=(--rm -d --name "$OLLAMA_DOCKER_CONTAINER" -p 11434:11434 -v "$OLLAMA_DOCKER_VOLUME:/root/.ollama")
  if [[ -n "$OLLAMA_DOCKER_GPUS" ]]; then
    args+=(--gpus "$OLLAMA_DOCKER_GPUS")
  fi
  printf '%s\n' "${args[@]}"
}

docker_install_or_update() {
  run docker pull "$OLLAMA_DOCKER_IMAGE"
}

docker_start_ollama() {
  if [[ "$DRY_RUN" -eq 1 ]]; then
    args=(--rm -d --name "$OLLAMA_DOCKER_CONTAINER" -p 11434:11434 -v "$OLLAMA_DOCKER_VOLUME:/root/.ollama")
    if [[ -n "$OLLAMA_DOCKER_GPUS" ]]; then
      args+=(--gpus "$OLLAMA_DOCKER_GPUS")
    fi
    args+=("$OLLAMA_DOCKER_IMAGE")
    run docker run "${args[@]}"
    return 0
  fi
  if docker ps --format '{{.Names}}' | grep -Fxq "$OLLAMA_DOCKER_CONTAINER"; then
    echo "Ollama Docker container already running: $OLLAMA_DOCKER_CONTAINER"
    return 0
  fi
  if docker ps -a --format '{{.Names}}' | grep -Fxq "$OLLAMA_DOCKER_CONTAINER"; then
    run docker rm "$OLLAMA_DOCKER_CONTAINER"
  fi
  args=(--rm -d --name "$OLLAMA_DOCKER_CONTAINER" -p 11434:11434 -v "$OLLAMA_DOCKER_VOLUME:/root/.ollama")
  if [[ -n "$OLLAMA_DOCKER_GPUS" ]]; then
    args+=(--gpus "$OLLAMA_DOCKER_GPUS")
  fi
  args+=("$OLLAMA_DOCKER_IMAGE")
  run docker run "${args[@]}"
}

docker_stop_ollama() {
  run docker rm -f "$OLLAMA_DOCKER_CONTAINER"
}

docker_exec_ollama() {
  run docker exec "$OLLAMA_DOCKER_CONTAINER" ollama "$@"
}

docker_status_ollama() {
  echo "Ollama Docker status"
  echo "  image: $OLLAMA_DOCKER_IMAGE"
  echo "  container: $OLLAMA_DOCKER_CONTAINER"
  echo "  endpoint: $ENDPOINT"
  if command -v docker >/dev/null 2>&1; then
    docker ps --filter "name=^/${OLLAMA_DOCKER_CONTAINER}$" --format '  container_status: {{.Status}}' || true
  else
    echo "  container_status: unavailable (docker is not on PATH)"
  fi
  status_ollama
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


def ollama_pull_id(model):
    provider = str(model.get("provider") or "")
    source = str(model.get("source") or provider)
    model_id = str(model.get("model") or "")
    supported = [
        str(value)
        for value in model.get("supported_runtimes") or model.get("suitable_runtimes") or []
    ]
    preferred = str(model.get("preferred_runtime") or "")
    if preferred and preferred not in supported:
        supported.insert(0, preferred)
    if provider == "ollama":
        return model_id
    if source == "huggingface_gguf" and "ollama" in supported:
        if model_id.startswith("hf.co/"):
            return model_id
        if model_id.startswith(("http://", "https://")):
            return ""
        if "/" in model_id:
            return f"hf.co/{model_id}"
    return ""


profile = load_profile(sys.argv[1], Path.cwd())
for name, model in ModelCatalog(profile).models().items():
    if not model.get("enabled", True):
        continue
    model_id = ollama_pull_id(model)
    if model_id:
        print(f"{name}	{model_id}")
PYMODEL
}

resolve_model_id() {
  if [[ "$MODEL" == hf.co/* || "$MODEL" == *":"* ]]; then
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
    echo "Unknown configured model '$MODEL'. Use --model all, an Ollama alias, a Hugging Face GGUF alias compatible with Ollama, or a raw id like provider-text-small:0.5b or hf.co/provider/model." >&2
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
  if [[ -n "$MODEL" && "$MODEL" != "all" ]]; then
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

if [[ "$SUBSTRATE" == "docker" ]]; then
  case "$ACTION" in
    install|update)
      docker_install_or_update
      ;;
    start)
      docker_start_ollama
      ;;
    stop)
      docker_stop_ollama
      ;;
    restart)
      docker_stop_ollama
      docker_start_ollama
      ;;
    status)
      docker_status_ollama
      ;;
    doctor)
      docker_status_ollama || true
      run_shell "$(aiplane_cmd) models doctor --profile '$PROFILE'"
      ;;
    pull)
      if [[ "$MODEL" == "all" ]]; then
        configured_model_ids | while IFS=$'	' read -r _name model_id; do
          [[ -n "$model_id" ]] && docker_exec_ollama pull "$model_id"
        done
      else
        model_id="$(resolve_model_id)"
        if [[ -z "$model_id" ]]; then
          echo "Unknown configured model '$MODEL'. Use --model all, an Ollama alias, a Hugging Face GGUF alias compatible with Ollama, or a raw id like provider-text-small:0.5b or hf.co/provider/model." >&2
          exit 1
        fi
        docker_exec_ollama pull "$model_id"
      fi
      ;;
    repull)
      echo "Docker Ollama repull uses the running container store. Use --model all to repull configured aliases, or pass one alias/id."
      if [[ "$MODEL" == "all" ]]; then
        configured_model_ids | while IFS=$'	' read -r _name model_id; do
          [[ -n "$model_id" ]] && docker_exec_ollama pull "$model_id"
        done
      elif [[ -n "$MODEL" ]]; then
        model_id="$(resolve_model_id)"
        [[ -n "$model_id" ]] && docker_exec_ollama pull "$model_id"
      else
        docker_exec_ollama list
      fi
      ;;
    remove)
      if [[ -z "$MODEL" || "$MODEL" == "all" ]]; then
        echo "remove requires --model with one configured alias or runtime model id; use --action clear for all pulled models" >&2
        exit 2
      fi
      model_id="$(resolve_model_id)"
      if [[ -z "$model_id" ]]; then
        echo "Unknown configured model '$MODEL'. Use an Ollama alias, a Hugging Face GGUF alias compatible with Ollama, or a raw id like provider-text-small:0.5b or hf.co/provider/model." >&2
        exit 1
      fi
      docker_exec_ollama rm "$model_id"
      ;;
    clear)
      if [[ "$DRY_RUN" -eq 1 ]]; then
        echo "+ docker exec $OLLAMA_DOCKER_CONTAINER ollama list | xargs -r -n1 docker exec $OLLAMA_DOCKER_CONTAINER ollama rm"
      else
        docker exec "$OLLAMA_DOCKER_CONTAINER" ollama list | awk 'NR > 1 && NF {print $1}' | while read -r model_id; do
          [[ -n "$model_id" ]] && docker_exec_ollama rm "$model_id"
        done
      fi
      ;;
    list)
      docker_exec_ollama list
      ;;
  esac
else
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
    remove)
      remove_model
      ;;
    clear)
      clear_models
      ;;
    list)
      list_ollama
      ;;
  esac
fi
