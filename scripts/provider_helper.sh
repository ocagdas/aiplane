#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
if [[ -d "$SOURCE_ROOT/src/aiplane" ]]; then
  PROJECT_ROOT="$SOURCE_ROOT"
  AIPLANE_SOURCE_PATH="$SOURCE_ROOT/src"
else
  PROJECT_ROOT="${AIPLANE_PROJECT_ROOT:-$PWD}"
  AIPLANE_SOURCE_PATH=""
fi
PROVIDER_HELPER="$SCRIPT_DIR/provider_helper.sh"
OLLAMA_HELPER="$SCRIPT_DIR/ollama_helper.sh"
PROVIDER="ollama"
ACTION="doctor"
PROFILE="local-dev"
MODEL=""
DRY_RUN=0
SUBSTRATE="native"
AIPLANE_STATE_DIR="$PROJECT_ROOT/.aiplane/runtimes"

usage() {
  cat <<'USAGE'
Usage: scripts/provider_helper.sh [options]

Providers:
  --provider ollama       Local Ollama provider
  --provider ollama_cloud Ollama Cloud provider env/template checks
  --provider openai       OpenAI cloud provider env/template checks
  --provider anthropic    Anthropic cloud provider env/template checks
  --provider azure_openai Azure OpenAI cloud provider env/template checks
  --provider vllm         vLLM OpenAI-compatible runtime checks/start helper
  --provider tgi          Hugging Face TGI OpenAI-compatible runtime checks/start helper
  --provider transformers Hugging Face Transformers Python library setup guidance
  --provider localai      LocalAI OpenAI-compatible runtime checks/start helper
  --provider lmstudio     LM Studio OpenAI-compatible local server checks
  --provider llamacpp     llama.cpp OpenAI-compatible server checks/start helper
  --provider all          Run supported action across all known providers where applicable

Actions:
  --action doctor         Check provider readiness (default)
  --action configure      Create/update local provider env template without secrets
  --action install        Install provider runtime when supported
  --action update         Update provider runtime when supported
  --action update-installed Update all helper-managed runtimes that can be updated; intended with --provider all
  --action start          Start provider service when supported
  --action stop           Stop provider service when supported
  --action restart        Restart provider service when supported
  --action status         Show provider status
  --action pull           Pull provider models when supported
  --action repull         Re-pull models already present in a runtime when discoverable; Ollama supports this directly
  --action remove         Remove one pulled runtime model where supported; Ollama supports this directly
  --action clear          Remove all pulled runtime models where supported; Ollama supports this directly
  --action list           List provider models when supported

Options:
  --profile NAME          aiplane profile (default: local-dev)
  --model NAME            configured model name, raw model id, or all (default: none; pass an alias, runtime-native id, or all)
  --substrate native|docker Runtime substrate where supported; Ollama supports native and docker (default: native)
  --dry-run               Print commands without executing them
  -h, --help              Show this help

Examples:
  scripts/provider_helper.sh --provider ollama --action install --dry-run
  scripts/provider_helper.sh --provider ollama --action install --substrate docker --dry-run
  scripts/provider_helper.sh --provider ollama --action start
  scripts/provider_helper.sh --provider ollama --action pull --model MODEL_ALIAS
  scripts/provider_helper.sh --provider ollama --action remove --model MODEL_ALIAS --dry-run
  scripts/provider_helper.sh --provider ollama --action clear --dry-run
  scripts/provider_helper.sh --provider ollama --action repull
  scripts/provider_helper.sh --provider all --action update-installed --dry-run
  scripts/provider_helper.sh --provider openai --action configure
  scripts/provider_helper.sh --provider vllm --action install --dry-run
  scripts/provider_helper.sh --provider vllm --action pull --model MODEL_ALIAS --dry-run
  scripts/provider_helper.sh --provider vllm --action start --dry-run
  scripts/provider_helper.sh --provider tgi --action start --dry-run
  scripts/provider_helper.sh --provider llamacpp --action start --dry-run
  scripts/provider_helper.sh --provider all --action doctor
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

pid_file_for() {
  printf '%s/%s.pid
' "$AIPLANE_STATE_DIR" "$1"
}

log_file_for() {
  printf '%s/%s.log
' "$AIPLANE_STATE_DIR" "$1"
}

start_managed() {
  runtime="$1"
  shift
  mkdir -p "$AIPLANE_STATE_DIR"
  pid_file="$(pid_file_for "$runtime")"
  log_file="$(log_file_for "$runtime")"
  if [[ -f "$pid_file" ]] && kill -0 "$(cat "$pid_file")" 2>/dev/null; then
    echo "$runtime helper-managed process already running with PID $(cat "$pid_file")"
    return 0
  fi
  command_text=""
  printf -v command_text '%q ' "$@"
  run_shell "nohup $command_text > '$log_file' 2>&1 & echo \$! > '$pid_file'"
  echo "PID file: $pid_file"
  echo "Log: $log_file"
}

stop_managed() {
  runtime="$1"
  pid_file="$(pid_file_for "$runtime")"
  if [[ ! -f "$pid_file" ]]; then
    echo "No helper-managed $runtime PID file found at $pid_file"
    return 0
  fi
  pid="$(cat "$pid_file")"
  if kill -0 "$pid" 2>/dev/null; then
    run kill "$pid"
  fi
  run rm -f "$pid_file"
}

status_managed() {
  runtime="$1"
  pid_file="$(pid_file_for "$runtime")"
  if [[ -f "$pid_file" ]] && kill -0 "$(cat "$pid_file")" 2>/dev/null; then
    echo "$runtime helper-managed process running with PID $(cat "$pid_file")"
  else
    echo "$runtime helper-managed process is not running"
  fi
}

run_model_resolver() {
  if [[ -n "$AIPLANE_SOURCE_PATH" ]]; then
    PYTHONPATH="$AIPLANE_SOURCE_PATH" python - "$@"
  else
    python - "$@"
  fi
}

resolve_configured_model_id() {
  runtime="$1"
  if [[ "$MODEL" == "all" ]]; then
    printf '%s
' all
    return 0
  fi
  if [[ "$MODEL" == */* || "$MODEL" == *:* || "$MODEL" == *.gguf || "$MODEL" == http://* || "$MODEL" == https://* ]]; then
    printf '%s
' "$MODEL"
    return 0
  fi
  run_model_resolver "$PROFILE" "$MODEL" <<'PYMODEL'
from pathlib import Path
import sys
from aiplane.config import load_profile
from aiplane.model_catalog import ModelCatalog
profile = load_profile(sys.argv[1], Path.cwd())
model = ModelCatalog(profile).get(sys.argv[2])
print(model.get("model", ""))
PYMODEL
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --provider) PROVIDER="${2:?missing value for --provider}"; shift 2 ;;
    --action) ACTION="${2:?missing value for --action}"; shift 2 ;;
    --profile) PROFILE="${2:?missing value for --profile}"; shift 2 ;;
    --model) MODEL="${2:?missing value for --model}"; shift 2 ;;
    --substrate) SUBSTRATE="${2:?missing value for --substrate}"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

case "$PROVIDER" in
  ollama|ollama_cloud|openai|anthropic|azure_openai|vllm|tgi|transformers|localai|lmstudio|llamacpp|all) ;;
  *) echo "Unsupported provider: $PROVIDER" >&2; exit 2 ;;
esac

case "$SUBSTRATE" in
  native|docker) ;;
  *) echo "Unsupported substrate: $SUBSTRATE" >&2; exit 2 ;;
esac

case "$ACTION" in
  doctor|configure|install|update|update-installed|start|stop|restart|status|pull|repull|remove|clear|list) ;;
  *) echo "Unsupported action: $ACTION" >&2; exit 2 ;;
esac

if [[ "$ACTION" == "install" || "$ACTION" == "update" || "$ACTION" == "update-installed" ]]; then
  if [[ "$(uname -s)" != "Linux" ]]; then
    echo "aiplane runtime install helpers are not supported on this platform: $(uname -s)" >&2
    echo "Install the runtime with the platform-native installer, then use aiplane discover, doctor, recommend, and export." >&2
    exit 2
  fi
fi

cd "$PROJECT_ROOT"

dry_run_args() {
  if [[ "$DRY_RUN" -eq 1 ]]; then
    printf '%s\n' --dry-run
  fi
}

aiplane_cmd() {
  if command -v aiplane >/dev/null 2>&1; then
    printf 'aiplane'
  elif [[ -n "$AIPLANE_SOURCE_PATH" ]]; then
    printf 'PYTHONPATH=%q python -m aiplane' "$AIPLANE_SOURCE_PATH"
  else
    printf 'python -m aiplane'
  fi
}

ollama_action() {
  model_args=()
  if [[ -n "$MODEL" ]]; then
    model_args=(--model "$MODEL")
  fi
  if [[ "$DRY_RUN" -eq 1 ]]; then
    "$OLLAMA_HELPER" --action "$ACTION" --profile "$PROFILE" --substrate "$SUBSTRATE" "${model_args[@]}" --dry-run
  elif [[ "$ACTION" == "status" || "$ACTION" == "list" || "$ACTION" == "doctor" ]]; then
    "$OLLAMA_HELPER" --action "$ACTION" --profile "$PROFILE" --substrate "$SUBSTRATE" "${model_args[@]}"
  else
    run "$OLLAMA_HELPER" --action "$ACTION" --profile "$PROFILE" --substrate "$SUBSTRATE" "${model_args[@]}"
  fi
}

env_template_path() {
  printf '%s
' "$PROJECT_ROOT/.env.providers.example"
}

write_env_template() {
  path="$(env_template_path)"
  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "+ write provider env template to $path"
    return 0
  fi
  cat > "$path" <<'ENVEOF'
# Provider environment template. Copy to your shell profile, direnv, or secret manager.
# Do not commit real API keys.

# Ollama Cloud
OLLAMA_API_KEY=

# OpenAI
OPENAI_API_KEY=

# Anthropic
ANTHROPIC_API_KEY=

# Azure OpenAI
AZURE_OPENAI_API_KEY=
AZURE_OPENAI_ENDPOINT=
AZURE_OPENAI_DEPLOYMENT=

# ElevenLabs
ELEVENLABS_API_KEY=
ELEVENLABS_ENDPOINT=https://api.elevenlabs.io/v1

# OpenAI-compatible local runtimes
VLLM_MODEL=PROVIDER/MODEL_ID
VLLM_ENDPOINT=http://localhost:8000/v1
TGI_MODEL=PROVIDER/MODEL_ID
TGI_ENDPOINT=http://localhost:8081/v1
TRANSFORMERS_MODEL=PROVIDER/MODEL_ID
LLAMACPP_MODEL_PATH=
LLAMACPP_ENDPOINT=http://localhost:8080/v1
LOCALAI_ENDPOINT=http://localhost:8082/v1
LOCALAI_MODELS_PATH=./models
LMSTUDIO_ENDPOINT=http://localhost:1234/v1
ENVEOF
  echo "Wrote $path"
}

cloud_doctor() {
  provider="$1"
  case "$provider" in
    ollama_cloud)
      [[ -n "${OLLAMA_API_KEY:-}" ]] && echo "ollama_cloud: OLLAMA_API_KEY is set" || echo "ollama_cloud: missing OLLAMA_API_KEY"
      ;;
    openai)
      [[ -n "${OPENAI_API_KEY:-}" ]] && echo "openai: OPENAI_API_KEY is set" || echo "openai: missing OPENAI_API_KEY"
      ;;
    anthropic)
      [[ -n "${ANTHROPIC_API_KEY:-}" ]] && echo "anthropic: ANTHROPIC_API_KEY is set" || echo "anthropic: missing ANTHROPIC_API_KEY"
      ;;
    azure_openai)
      [[ -n "${AZURE_OPENAI_API_KEY:-}" ]] && echo "azure_openai: AZURE_OPENAI_API_KEY is set" || echo "azure_openai: missing AZURE_OPENAI_API_KEY"
      [[ -n "${AZURE_OPENAI_ENDPOINT:-}" ]] && echo "azure_openai: AZURE_OPENAI_ENDPOINT is set" || echo "azure_openai: missing AZURE_OPENAI_ENDPOINT"
      [[ -n "${AZURE_OPENAI_DEPLOYMENT:-}" ]] && echo "azure_openai: AZURE_OPENAI_DEPLOYMENT is set" || echo "azure_openai: missing AZURE_OPENAI_DEPLOYMENT"
      ;;
  esac
}


openai_compatible_action() {
  provider="$1"
  model_id=""
  case "$ACTION" in
    start|restart|pull|repull) model_id="$(resolve_configured_model_id "$provider")" ;;
  esac

  case "$provider" in
    vllm)
      endpoint="${VLLM_ENDPOINT:-http://localhost:8000/v1}"
      start_command=(python -m vllm.entrypoints.openai.api_server --model "${model_id:-${VLLM_MODEL:-MODEL_ID_REQUIRED}}" --host 127.0.0.1 --port 8000)
      install_command=(python -m pip install vllm huggingface_hub)
      update_command=(python -m pip install --upgrade vllm huggingface_hub)
      pull_command=(python -c "from huggingface_hub import snapshot_download; snapshot_download('${model_id:-${VLLM_MODEL:-MODEL_ID_REQUIRED}}')")
      install_hint="python -m pip install vllm huggingface_hub"
      ;;
    tgi)
      endpoint="${TGI_ENDPOINT:-http://localhost:8081/v1}"
      start_command=(docker run --rm --gpus all -p 8081:80 -e MODEL_ID="${model_id:-${TGI_MODEL:-MODEL_ID_REQUIRED}}" ghcr.io/huggingface/text-generation-inference:latest)
      install_command=(docker pull ghcr.io/huggingface/text-generation-inference:latest)
      update_command=(docker pull ghcr.io/huggingface/text-generation-inference:latest)
      pull_command=(python -c "from huggingface_hub import snapshot_download; snapshot_download('${model_id:-${TGI_MODEL:-MODEL_ID_REQUIRED}}')")
      install_hint="Install Docker with GPU support, then docker pull ghcr.io/huggingface/text-generation-inference:latest."
      ;;
    transformers)
      endpoint=""
      start_command=()
      install_command=(python -m pip install transformers accelerate torch huggingface_hub)
      update_command=(python -m pip install --upgrade transformers accelerate torch huggingface_hub)
      pull_command=(python -c "from huggingface_hub import snapshot_download; snapshot_download('${model_id:-${TRANSFORMERS_MODEL:-MODEL_ID_REQUIRED}}')")
      install_hint="python -m pip install transformers accelerate torch huggingface_hub"
      ;;
    localai)
      endpoint="${LOCALAI_ENDPOINT:-http://localhost:8082/v1}"
      start_command=(docker run --rm -p 8082:8080 -v "${LOCALAI_MODELS_PATH:-./models}":/models localai/localai:latest)
      install_command=(docker pull localai/localai:latest)
      update_command=(docker pull localai/localai:latest)
      pull_command=()
      install_hint="Install/run LocalAI from its container or native release. Put model files under LOCALAI_MODELS_PATH."
      ;;
    lmstudio)
      endpoint="${LMSTUDIO_ENDPOINT:-http://localhost:1234/v1}"
      start_command=()
      install_command=()
      update_command=()
      pull_command=()
      install_hint="Install LM Studio, load a model, and enable its local server from the app."
      ;;
    llamacpp)
      endpoint="${LLAMACPP_ENDPOINT:-http://localhost:8080/v1}"
      start_command=(llama-server -m "${LLAMACPP_MODEL_PATH:-${model_id:-/path/to/model.gguf}}" --host 127.0.0.1 --port 8080)
      install_command=()
      update_command=()
      pull_command=()
      if [[ "${model_id:-}" == http://* || "${model_id:-}" == https://* ]]; then
        mkdir -p models
        filename="models/$(basename "$model_id")"
        pull_command=(curl -L "$model_id" -o "$filename")
      fi
      install_hint="Install llama.cpp and make llama-server available on PATH. Configure LLAMACPP_MODEL_PATH for GGUF files."
      ;;
  esac

  case "$ACTION" in
    configure)
      write_env_template
      ;;
    doctor)
      if [[ "$provider" == "transformers" ]]; then
        echo "$provider library runtime: $install_hint"
        python - <<'PYEOF'
try:
    import transformers
    print("transformers: installed")
except Exception as exc:
    print(f"transformers: not importable: {exc}")
PYEOF
      else
        status_managed "$provider"
        echo "$provider endpoint: $endpoint"
        run bash -lc "$(aiplane_cmd) providers models --profile '$PROFILE' '$provider'"
      fi
      ;;
    status)
      if [[ "$provider" == "transformers" ]]; then
        python - <<'PYEOF'
try:
    import transformers
    print("transformers: installed")
except Exception as exc:
    print(f"transformers: not importable: {exc}")
PYEOF
      else
        status_managed "$provider"
        echo "$provider endpoint: $endpoint"
        run bash -lc "$(aiplane_cmd) runtimes doctor --profile '$PROFILE' '$provider'"
      fi
      ;;
    list)
      run bash -lc "$(aiplane_cmd) providers models --profile '$PROFILE' '$provider'"
      ;;
    install)
      if [[ ${#install_command[@]} -eq 0 ]]; then
        echo "$provider install is not fully automated. Suggested setup: $install_hint"
      else
        run "${install_command[@]}"
      fi
      ;;
    update|update-installed)
      if [[ ${#update_command[@]} -eq 0 ]]; then
        echo "$provider update is not fully automated. Suggested setup: $install_hint"
      else
        run "${update_command[@]}"
      fi
      ;;
    start)
      if [[ ${#start_command[@]} -eq 0 ]]; then
        echo "$provider must be started from its native application/library path. $install_hint"
      else
        start_managed "$provider" "${start_command[@]}"
      fi
      ;;
    stop)
      if [[ "$provider" == "transformers" || "$provider" == "lmstudio" ]]; then
        echo "$provider is not managed as a helper background process. $install_hint"
      else
        stop_managed "$provider"
      fi
      ;;
    restart)
      if [[ ${#start_command[@]} -eq 0 ]]; then
        echo "$provider must be restarted from its native application/library path. $install_hint"
      else
        stop_managed "$provider"
        start_managed "$provider" "${start_command[@]}"
      fi
      ;;
    pull|repull|remove|clear)
      if [[ "$ACTION" == "remove" || "$ACTION" == "clear" ]]; then
        echo "$provider runtime cache deletion is not automated. Remove files through the runtime/provider cache tooling."
        return 0
      fi
      if [[ "$ACTION" == "repull" ]]; then
        echo "$provider cannot discover already downloaded model cache entries reliably. Re-pulling the selected/configured model instead."
      fi
      if [[ "$provider" == "localai" ]]; then
        echo "LocalAI model pull is file/config based. Put models under LOCALAI_MODELS_PATH=${LOCALAI_MODELS_PATH:-./models}, or use a LocalAI gallery/config flow."
      elif [[ "$provider" == "llamacpp" && ${#pull_command[@]} -eq 0 ]]; then
        echo "llama.cpp pull needs a direct GGUF URL or preconfigured LLAMACPP_MODEL_PATH. Example: --model https://.../model.gguf"
      elif [[ ${#pull_command[@]} -eq 0 ]]; then
        echo "$provider model downloads are runtime-specific. $install_hint"
      else
        run "${pull_command[@]}"
      fi
      ;;
  esac
}

cloud_action() {
  provider="$1"
  case "$ACTION" in
    configure)
      write_env_template
      ;;
    doctor|status)
      cloud_doctor "$provider"
      run bash -lc "$(aiplane_cmd) models doctor --profile '$PROFILE'"
      ;;
    install|update|update-installed|start|stop|restart|pull|repull|remove|clear|list)
      echo "$provider does not have a local runtime for action '$ACTION'. Use --action configure or --action doctor."
      ;;
  esac
}

all_action() {
  case "$ACTION" in
    doctor|status)
      "$OLLAMA_HELPER" --action status --profile "$PROFILE" --model "$MODEL" $(dry_run_args) || true
      cloud_doctor ollama_cloud
      cloud_doctor openai
      cloud_doctor anthropic
      cloud_doctor azure_openai
      run bash -lc "$(aiplane_cmd) providers models --profile '$PROFILE' vllm" || true
      run bash -lc "$(aiplane_cmd) providers models --profile '$PROFILE' tgi" || true
      run bash -lc "$(aiplane_cmd) providers models --profile '$PROFILE' localai" || true
      run bash -lc "$(aiplane_cmd) providers models --profile '$PROFILE' lmstudio" || true
      run bash -lc "$(aiplane_cmd) providers models --profile '$PROFILE' llamacpp" || true
      run bash -lc "$(aiplane_cmd) models doctor --profile '$PROFILE'"
      ;;
    configure)
      write_env_template
      ;;
    update|update-installed)
      echo "Updating helper-managed runtimes where supported."
      "$PROVIDER_HELPER" --provider ollama --action update --profile "$PROFILE" --model "$MODEL" $(dry_run_args) || true
      "$PROVIDER_HELPER" --provider vllm --action update --profile "$PROFILE" --model "$MODEL" $(dry_run_args) || true
      "$PROVIDER_HELPER" --provider tgi --action update --profile "$PROFILE" --model "$MODEL" $(dry_run_args) || true
      "$PROVIDER_HELPER" --provider transformers --action update --profile "$PROFILE" --model "$MODEL" $(dry_run_args) || true
      "$PROVIDER_HELPER" --provider localai --action update --profile "$PROFILE" --model "$MODEL" $(dry_run_args) || true
      "$PROVIDER_HELPER" --provider llamacpp --action update --profile "$PROFILE" --model "$MODEL" $(dry_run_args) || true
      "$PROVIDER_HELPER" --provider lmstudio --action update --profile "$PROFILE" --model "$MODEL" $(dry_run_args) || true
      ;;
    repull)
      echo "Re-pulling runtime models where already-pulled model discovery is supported."
      "$PROVIDER_HELPER" --provider ollama --action repull --profile "$PROFILE" --model "$MODEL" $(dry_run_args) || true
      echo "For vLLM/TGI/Transformers, use --provider <runtime> --action pull --model <alias> to refresh a selected Hugging Face snapshot."
      ;;
    install|start|stop|restart|pull|remove|clear|list)
      echo "Action '$ACTION' with --provider all currently applies only to Ollama. Use a specific runtime for broader control."
      PROVIDER="ollama"
      ollama_action
      ;;
  esac
}

case "$PROVIDER" in
  ollama)
    ollama_action
    ;;
  ollama_cloud|openai|anthropic|azure_openai)
    cloud_action "$PROVIDER"
    ;;
  vllm|tgi|transformers|localai|lmstudio|llamacpp)
    openai_compatible_action "$PROVIDER"
    ;;
  all)
    all_action
    ;;
esac
