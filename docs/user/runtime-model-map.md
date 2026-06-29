# Model Sources and Runtimes

A **model source/catalog** is where model files or model identifiers come from. A
**runtime** is the program that loads those files into CPU/GPU memory and answers
prompts.

```mermaid
flowchart LR
  HF["Hugging Face Hub"] --> VLLM["vLLM"]
  HF --> TGI["TGI"]
  HF --> TR["Transformers library"]
  HFGGUF["HF GGUF / local GGUF"] --> LLAMACPP["llama.cpp server"]
  HFGGUF --> LOCALAI["LocalAI"]
  HFGGUF --> OLLAMA_IMPORT["Ollama import"]
  OLLAMACAT["Ollama library"] --> OLLAMA["Ollama"]
  OLLAMA_IMPORT --> OLLAMA

  VLLM --> OAI_API["OpenAI-compatible /v1 API"]
  TGI --> OAI_API
  LLAMACPP --> OAI_API
  LOCALAI --> OAI_API
  OLLAMA --> OAI_API
  LMSTUDIO["LM Studio server"] --> OAI_API
  OAI_API --> IDE["Continue / Cline / Zed / Cursor-style clients"]
  OAI_API --> CLI["Aider / aiplane / other CLI tools"]
  OLLAMA --> OLLAMA_NATIVE["Ollama native API + ollama run"]
  OLLAMA_NATIVE --> CLI
```

The `OpenAI-compatible /v1 API` node is an API shape, not the OpenAI cloud
provider. Continue and similar tools can use vLLM, Ollama, llama.cpp server,
LocalAI, LM Studio, or TGI gateways when they expose a compatible endpoint and
the selected tool supports that endpoint configuration. Managed cloud providers
are provider/service entries, not self-managed runtimes. Keep their `provider`
set to the hosted service such as `openai`, `azure_openai`, or `elevenlabs`; do not null it.
Runtime-fit filters intentionally exclude managed-service models unless the
model explicitly declares compatible runtime metadata.

## Commands

Show the source/runtime map:

```bash
aiplane runtimes map
aiplane runtimes sources
aiplane runtimes list
```

Group configured models by runtime:

```bash
aiplane runtimes models
aiplane runtimes models vllm
```

Show which runtimes can run one model:

```bash
aiplane runtimes model MODEL_ALIAS
```

Set a preferred runtime for a model:

```bash
aiplane runtimes use MODEL_ALIAS vllm
aiplane runtimes use MODEL_ALIAS tgi
```

This writes `preferred_runtime` to the editable profile model entry. It does not
modify the checked-in profile template.

Check runtime availability:

```bash
aiplane runtimes doctor
aiplane runtimes doctor vllm
```

Check runtime installer/start prerequisites before using the helper:

```bash
aiplane runtimes prerequisites ollama
aiplane runtimes prerequisites vllm
aiplane runtimes prerequisites all
```

`runtimes doctor` answers "is the runtime reachable or usable now?".
`runtimes prerequisites` answers "are the host tools present for `aiplane` to attempt install/start/pull workflows?". When a runtime is unavailable, runtime status output includes suggested follow-up commands, usually a prerequisites check and helper dry-runs such as `aiplane runtimes install vllm --dry-run` or `aiplane runtimes start vllm --dry-run`.


## Runtime Command Reference

All runtime lifecycle commands use this shape:

```bash
aiplane runtimes <command> --profile <profile> <runtime> [--model <model>] [--dry-run]
```

Common options:

- `--profile`: selects the editable profile, for example `local-dev`. The profile provides runtime endpoints, model aliases, default models, and provider config.
- `<runtime>`: the runtime/provider name to operate on, such as `ollama`, `vllm`, `tgi`, `transformers`, `localai`, `llamacpp`, or `lmstudio`.
- `--model`: model alias or runtime-native model id. It can be a configured alias like `MODEL_ALIAS`, a Hugging Face id like `Provider/Code-Large-Instruct`, a raw Ollama id like `text-generation:0.5b`, a direct GGUF URL for llama.cpp, or `all` where the runtime supports it.
- `--dry-run`: prints the helper command and delegated runtime command without installing packages, downloading models, starting services, or changing files.

Lifecycle commands:

- `configure`: writes or previews non-secret provider/runtime environment templates. It does not write real API keys.
- `install`: installs the runtime where supported. Examples: pip install for `vllm`/`transformers`, Docker image pull for `tgi`/`localai`, Ollama official installer for `ollama`. Real installs run a prerequisites preflight first; if required host tools are missing, `aiplane` prints the missing tools and Ubuntu/Debian package hints instead of delegating to the helper.
- `update`: updates one runtime where supported. Usually pip upgrade, Docker image pull, or the Ollama installer update path.
- `update-installed`: intended with runtime `all`; updates helper-managed runtimes where `aiplane` has an update path. Use `--dry-run` first.
- `pull`: downloads model files where the runtime has a meaningful download path. Ollama uses `ollama pull`; vLLM/TGI/Transformers use Hugging Face snapshot download; llama.cpp can download a direct GGUF URL; LocalAI is model-file/config based.
- `repull`: refreshes models already present in a runtime when the runtime can list them. Ollama supports this directly by reading `ollama list` and re-running `ollama pull` for each listed model. Other runtimes generally cannot reliably enumerate local caches, so `repull` refreshes the selected/configured model when possible.
- `start`: starts a helper-managed background process where supported. PID/log files are written under `.aiplane/runtimes/`.
- `stop`: stops a helper-managed background process.
- `restart`: runs `stop` then `start` for helper-managed runtimes.
- `status`: shows helper process state and runtime endpoint status where available.
- `list-runtime-models`: asks the runtime/provider for available models when it exposes a model-list API, otherwise falls back to configured catalog entries.
- `doctor`: checks runtime availability directly from `aiplane`; it does not call install/update/pull.

Model catalog refresh is separate from runtime inventory. The checked-in profile is provider-only: curated aliases are optional local entries in `models.yaml`, while generated refresh/import aliases live in the ignored `models.generated.yaml` cache. `models refresh` works
against model providers, not runtime endpoints:

```bash
aiplane models refresh --dry-run
aiplane models refresh --provider huggingface --query text-generation --limit 500 --dry-run
aiplane models refresh --limit 100 --provider-limit huggingface=500 --provider-limit ollama=500 --dry-run
aiplane models clear-cache --dry-run
aiplane models clear-cache --provider huggingface --keep-curated --dry-run
aiplane models refresh --provider huggingface --limit 10 --dry-run --verbose
```

The refresh result includes `results` grouped by model provider. Provider
results show `source_models_returned`, `profile_models_before_refresh`,
`profile_curated_models_before_refresh`,
`profile_refresh_imported_models_before_refresh`,
`source_models_already_profiled`, `source_models_to_import`,
`source_models_to_update`, `source_contacted`, `source_discovery_method`,
`source_discovery_reason`, and `model_changes_count`. Per-model `model_changes`
rows are hidden by default and shown with `--verbose`; those rows use
`model.id`/`model.source` for the model source and `runtime_endpoint` for the
configured runtime endpoint.
`prune_enabled: true` means a successful authoritative online source response is being used
as the source of truth for stale generated ids. Curated aliases in `models.yaml` are preserved by refresh. `models clear-cache` includes curated aliases by default unless `--keep-curated` is used, so discovery state can be cleared and repopulated from providers. Profile-catalog fallback never updates
or prunes.

Runtime inventory is queried separately with `aiplane runtimes
list-runtime-models <runtime>`. For Ollama, runtime inventory comes from the
local `/api/tags` endpoint and means "models already pulled here", not "every
model in the public Ollama library".

Online source-catalog querying currently exists for Hugging Face Hub, Hugging
Face GGUF searches, and Ollama Library. Other model providers fall back to profile
catalog entries until dedicated adapters are added. Use `--limit` for the default
per-provider import window and repeated `--provider-limit PROVIDER=COUNT` for
provider-specific overrides.

New imported entries are enabled by default. Add `--disable-new` if you want new
entries written disabled.

Examples:

```bash
aiplane runtimes update-installed all --dry-run
aiplane runtimes install ollama --dry-run
aiplane runtimes install ollama --substrate docker --dry-run
aiplane runtimes start ollama --substrate docker --dry-run
aiplane runtimes install vllm --dry-run
aiplane runtimes pull vllm --model MODEL_ALIAS --dry-run
aiplane runtimes start vllm --model MODEL_ALIAS --dry-run
aiplane runtimes status vllm
aiplane runtimes stop vllm
aiplane runtimes list-runtime-models vllm
```


## What `models defaults` Prints

`aiplane models defaults` prints the profile's configured default model aliases by role. It does **not** show what is already pulled locally, and it does **not** search online catalogs.

Examples of roles:

- `self_managed_model`: default self-managed model used by `aiplane run` when no explicit model is supplied.
- `code_model`: preferred general code model for future code-oriented routing.
- `completion_model`: preferred completion model.
- `chat`: model role label for conversational use.
- `autocomplete`: model role label for code completion/autocomplete use.
- `embedding`: model role label for vector/retrieval models such as `EMBEDDING_ALIAS`.
- `reasoning_model`: preferred reasoning/analysis model.

The command now groups by provider by default:

```bash
aiplane models defaults
aiplane models defaults --group-by none
aiplane models defaults --group-by provider
```

To see what is pulled or reachable, use runtime checks instead:

```bash
aiplane providers models ollama
aiplane runtimes list-runtime-models ollama
aiplane models doctor
```

## Model Listing and Grouping

Model catalog output can be grouped when the flat list is hard to read:

```bash
aiplane models list
aiplane models list --group-by provider
aiplane models list --group-by source
aiplane models list --group-by provider-kind
aiplane models list --group-by runtime
aiplane models list --group-by model
aiplane models defaults --group-by provider
```

Grouping meanings:

- `provider`: groups by model source/catalog, such as `ollama`, `huggingface`, `huggingface_gguf`, or `local_file`.
- `source`: same source/catalog value as `provider`; kept as an explicit source field in model rows.
- `provider-kind`: groups first by ownership (`self_managed` or `managed_service`) and then by provider/source.
- `runtime`: groups by each supported runtime. A model may appear in more than one runtime group when it can run under multiple runtimes, for example vLLM, TGI, and Transformers. Managed-service aliases appear under `no_runtime`; `preferred_runtime` and `supported_runtimes` are ignored for managed-service aliases so they cannot be combined with local runtime config.
- `model`: groups by provider-native model id. This is useful when multiple profile aliases point at the same underlying model id. It is less useful when equivalent models use different naming schemes across sources.
- defaults grouped by `provider`: shows which default roles, such as `chat_model`, `autocomplete_model`, `embedding_model`, `self_managed_model`, or `reasoning_model`, resolve to each provider.

## Current Runtime Policy

- **Ollama**: full helper support for install/update/start/stop/restart/status/doctor/pull/list. Native is the default; `--substrate docker` uses the official `ollama/ollama` image when Docker is available.
- **vLLM**: helper support for pip install/update, Hugging Face snapshot download, background start/stop/restart/status, provider list, and doctor checks. Advanced GPU tuning remains runtime-native.
- **TGI**: helper support for Docker image pull/update, Hugging Face snapshot download, background start/stop/restart/status, provider list, and doctor checks.
- **llama.cpp**: partial helper support for background start/stop/restart/status when `llama-server` is installed and `LLAMACPP_MODEL_PATH` or a direct GGUF URL is configured. Native build/install remains manual because CPU/GPU build choices vary.
- **Transformers**: partial helper support for pip install/update and Hugging Face snapshot download. It is a Python library path, not a running HTTP server by default.
- **LocalAI**: partial helper support for Docker image pull/update and background start/stop/restart/status. Model pull is file/config based under `LOCALAI_MODELS_PATH`.
- **LM Studio**: GUI-managed. It can still be used as an endpoint, but `aiplane` does not install or operate the GUI.


## Helper Lifecycle Commands

Use the same helper surface across manageable runtimes from the main CLI:

```bash
aiplane runtimes update-installed all --dry-run
aiplane runtimes install ollama --dry-run
aiplane runtimes install ollama --substrate docker --dry-run
aiplane runtimes start ollama --substrate docker --dry-run
aiplane runtimes install vllm --dry-run
aiplane runtimes pull vllm --model MODEL_ALIAS --dry-run
aiplane runtimes start vllm --model MODEL_ALIAS --dry-run
aiplane runtimes status vllm
aiplane runtimes stop vllm

aiplane runtimes install tgi --dry-run
aiplane runtimes start tgi --model MODEL_ALIAS --dry-run

aiplane runtimes start llamacpp --dry-run
aiplane runtimes start localai --dry-run
aiplane runtimes pull transformers --model MODEL_ALIAS --dry-run
```

These commands delegate to `scripts/provider_helper.sh`. Direct helper usage still works when debugging the shell layer:

```bash
scripts/provider_helper.sh --provider vllm --action start --model MODEL_ALIAS --dry-run
```

Audio, image, and video generation should come from provider discovery or deliberately promoted aliases, not hard-coded showcase defaults. Use online catalog refresh to populate ignored `models.generated.yaml`, then filter the generated candidates by role, runtime, RAM/VRAM, and target hardware. Promote only the specific alias you have reviewed and chosen for a real workflow.

```bash
aiplane providers models huggingface --online --query text-to-speech --limit 20
aiplane providers models elevenlabs --online --query voice --limit 20
aiplane models refresh --provider huggingface --query text-to-speech --dry-run --verbose --limit 20
aiplane models refresh --provider huggingface --query text-to-speech --disable-new --limit 20
aiplane models list --role text_to_speech --sort-by role

aiplane models refresh --provider huggingface --query text-to-image --disable-new --limit 20
aiplane models list --role image_generation --runtime diffusers --ram-gb 64 --vram-gb 16 --sort-by role

aiplane models refresh --provider huggingface --query text-to-video --disable-new --limit 20
aiplane models list --role video_generation --runtime diffusers --ram-gb 128 --vram-gb 16 --sort-by role
```

For demos, it is fine to show the Azure or GPU resource command path, kick off the generation job, fast-forward the runtime wait, and play the generated clip at the end. `aiplane` should make the discovered model, runtime, machine, and access policy explicit; it should not hide media generation behind an unrelated utility.

Helper-managed background processes write PID and log files under:

```text
.aiplane/runtimes/<runtime>.pid
.aiplane/runtimes/<runtime>.log
```


## Installation Modes

There is value in supporting native, `venv`, Conda, and Docker installation modes, but they fit different runtimes:

- **Native install**: best for Ollama, system services, GPU drivers, Docker, and host tools such as `llama-server` when you want direct access to host CPU/GPU devices.
- **venv**: good for Python runtimes such as vLLM and Transformers when you want isolation from system Python without Conda.
- **Conda**: useful for GPU/PyTorch/CUDA stacks where Conda packages solve binary compatibility more predictably on a workstation.
- **Docker**: best for repeatable runtime servers such as TGI, LocalAI, vLLM containers, and shared/cloud VM deployments. Docker is also the cleanest route to package a working setup for reuse.

A practical Docker workflow would work like this:

1. Start from a base image, for example CUDA runtime plus Python.
2. Let `aiplane`/helpers install runtime packages and model-server dependencies.
3. Run doctor/smoke tests until the image satisfies the use case.
4. Emit a Dockerfile or lockfile-style build recipe that reproduces the successful image.
5. Optionally publish the resulting image to a registry for a team or cloud VM/AKS deployment.

This is a good direction. The main caution is that model files can be very large, so the image should usually contain runtime dependencies, while model weights are mounted, cached, or downloaded to a volume unless there is a strong reason to bake them into the image.

## Runtime Parameters

`aiplane` should keep sensible startup defaults and let users pass through or
persist native runtime options over time. It should not hide important runtime
knobs behind a weak abstraction.

Recommended split:

- `aiplane` owns profile metadata, endpoint selection, preferred runtime,
  model/source compatibility, readiness checks, and safe default start commands.
- Native runtime config owns deep tuning: tensor parallelism, quantization,
  context length, GPU memory utilization, CPU threads, batching, cache settings,
  and engine-specific flags.
- Profiles can later store an `runtime_options` block so a manually tuned command
  can be reused by helpers without making every option a first-class CLI flag.

## What Happens When Running

When `aiplane` runs a model, it checks the model's supported runtimes and
preferred runtime. If at least one supported runtime is available, it uses that
runtime. If none are available, it fails with the supported runtime list and the
availability reason for each runtime.


## Integration Planning and Runtime Setup

Use integration planning when you want `aiplane` to choose or validate a set of models for an IDE/tool role instead of hand-picking one model at a time.

```bash
aiplane integrations plan continue --select-best --runtime ollama
aiplane integrations setup continue --select-best --runtime ollama --dry-run
aiplane integrations export continue --select-best --runtime ollama
```

`plan` explains the selected provider/source, runtime, endpoint, native model id, and role-capability scores. `setup --dry-run` previews runtime helper actions. `setup` can start supported runtimes and pull selected models through the existing provider helper scripts. `export` prints the Continue/Cline/Zed/Aider config payload.
