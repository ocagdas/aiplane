# Model Providers and Runtime Helpers

In `aiplane`, **provider** means a model source/catalog: a place where model ids, model files, or model artifacts come from.

Examples:

- `ollama`: Ollama model library names such as `qwen2.5-coder:0.5b`.
- `huggingface`: Hugging Face Hub repos such as `Qwen/Qwen2.5-Coder-32B-Instruct`.
- `huggingface_gguf`: GGUF files hosted on Hugging Face or similar file stores.
- `local_file`: a local model path.
- `piper_voices`: Piper text-to-speech voice catalog.
- `openai`, `anthropic`, `azure_openai`, `ollama_cloud`: managed providers. These are hosted services, so they need endpoint/API-key configuration and curated model aliases before IDE exports can use them. Other catalogs can be added in `model-providers.user.yaml` when their discovery path is reliable for your environment.

A **runtime** is different. A runtime loads model files into CPU/GPU memory and serves inference. Examples: `ollama`, `vllm`, `tgi`, `llamacpp`, `transformers`, `localai`, `lmstudio`, `faster_whisper`, `piper`, `diffusers`, and `comfyui`.

An **endpoint** is the URL a client calls, for example `http://localhost:11434/v1` for Ollama's OpenAI-compatible API.

## Why Names Can Overlap

`ollama` is both a model provider and a runtime:

- Provider meaning: the Ollama model library/pull namespace.
- Runtime meaning: the local `ollama serve` process that runs pulled models.

That overlap is real in the ecosystem, but `aiplane` keeps the concepts separate in output:

- `provider` / `source`: where the model comes from.
- `supported_runtimes`: runtimes that can plausibly run it.
- `runtime_endpoint`: the configured runtime endpoint selected in the profile entry, for example `ollama`, `vllm`, or `llamacpp`.
- `configured_runtime_endpoints`: compatible runtime endpoint names already present in the profile config.

## Ownership Groups

Models are grouped by ownership:

- `self_managed`: local, workstation, VM, container, or Kubernetes-hosted runtimes you operate.
- `managed_service`: hosted providers such as OpenAI, Anthropic, Azure OpenAI, and Ollama Cloud.

Useful commands:

```bash
aiplane models list --group-by ownership
aiplane models list --self-managed-only
aiplane models list --managed-service-only
```

## Managed Providers In Practice

Managed providers are not local runtimes. They become useful to Continue/Cline/Aider/Zed only after you have a profile model alias in `models.yaml`. The flow is:

1. Configure the managed provider endpoint and API-key environment variable under `providers:` in `models.yaml`.
2. Add or enable a model alias under `models:`. For Azure OpenAI, the `model` value is the deployment name.
3. Run `aiplane integrations plan ...` to inspect which aliases, endpoints, and API-key env vars will be used.
4. Run `aiplane integrations export ...` and merge the printed config into the target tool.

Examples:

```bash
export OPENAI_API_KEY=...
aiplane integrations export continue --model openai-gpt-4o-mini

export AZURE_OPENAI_API_KEY=...
aiplane providers models azure_openai --online --limit 20
aiplane integrations export openai-compatible --model azure-openai-chat-deployment --endpoint https://YOUR-RESOURCE.openai.azure.com
```

Use managed providers deliberately. They can send selected IDE context to a hosted service and may incur cost. Keep local defaults for local-only workflows, and use explicit `--model`, `--provider`, or role overrides when you want a managed model.

For multiple accounts, keep credentials in the ignored local credentials file and reference them by name:

```yaml
providers:
  openai:
    endpoint: https://api.openai.com/v1
    credential_ref: openai.personal
  custom_openai_gateway:
    endpoint: https://llm-gateway.example.com/v1
    protocol: openai_compatible
    credential_ref: custom_openai_compatible.lab_gateway
```

Well-known managed providers have built-in defaults and adapters where safe. Custom providers should specify an endpoint, protocol, and credential reference. The profile should not contain raw API keys.

## Provider Commands

List known model providers:

```bash
aiplane providers list
aiplane providers list --runtime ollama
aiplane providers list --runtime vllm --group-by runtime
```

Show one model provider and the profile catalog aliases that come from it:

```bash
aiplane providers show ollama
aiplane providers show huggingface
```

List known source-native model ids for one model provider:

```bash
aiplane providers models ollama
aiplane providers models huggingface
```

Query an online catalog where an adapter exists:

```bash
aiplane providers models ollama --online --query qwen --limit 500
aiplane providers models huggingface --online --query qwen2.5-coder --limit 500
aiplane providers models huggingface_gguf --online --query llama-3.1-8b --limit 500
aiplane providers models piper_voices --online --query en_US --limit 500
```

Current default online adapters are `ollama`, `huggingface`, `huggingface_gguf`, `piper_voices`, and `azure_openai` deployments when endpoint/key configuration is present. If an online query fails or the provider has no adapter yet, `aiplane` falls back to the profile catalog and includes the reason. Fallback is non-destructive: it does not update or prune local entries because it is only re-reading the local profile.

## Provider Configuration Files

Provider definitions are profile-local YAML, not hidden built-ins:

- `model-providers.yaml`: default/provider seed entries for this profile.
- `model-providers.user.yaml`: user additions and overrides. This is where CLI edits go.

If neither file exists, `aiplane` can fall back to its hardcoded seed so a fresh developer checkout still works. To make the seed explicit, dump it into the profile:

```bash
aiplane providers init-defaults
aiplane providers init-defaults --overwrite
```

Without `--overwrite`, `init-defaults` writes `model-providers.yaml` only when it does not already exist. If the file exists, the command exits with an error instead of replacing your provider config.

To add, disable, enable, remove, or clear provider config:

```bash
aiplane providers add private_hf --runtime vllm --online-adapter huggingface
aiplane providers disable ollama
aiplane providers enable all
aiplane providers remove local_file
aiplane providers clear
aiplane providers clear --scope user
aiplane providers clear --scope embedded
aiplane providers clear --scope all
```

`clear`, `clear --scope all`, and `clear --scope embedded` write an empty `model-providers.yaml` marker. That marker intentionally suppresses the hardcoded fallback until you run `providers init-defaults --overwrite`.

## Model Catalog Refresh

`aiplane models refresh` imports model-provider catalog entries into `models.generated.yaml` so you can later filter locally by runtime, role, capability, score, RAM/VRAM fit, and benchmark results without replacing curated aliases in `models.yaml`. It is online-first where an adapter exists, and it is not runtime inventory.

When an online source adapter succeeds, the source result is treated as authoritative for generated/imported aliases when it is not a query or limit-truncated window: new source ids are imported into `models.generated.yaml`, stale generated ids are pruned, and changed source metadata updates generated aliases. Curated aliases in `models.yaml` are preserved; if a curated alias points at a returned source id, only source-derived metadata is refreshed while human-maintained fields stay intact. In this context, curated means profile data such as aliases, enabled/disabled state, roles, preferred runtime, manual capability scores, RAM/VRAM overrides, and notes.

When online contact fails or no online adapter exists, refresh reports the error/reason and falls back to local profile entries without pruning or updating.

```bash
aiplane models refresh --dry-run
aiplane models refresh --provider huggingface --query qwen2.5-coder --limit 500 --dry-run
aiplane models refresh --limit 100 --provider-limit huggingface=500 --provider-limit ollama=500 --dry-run
aiplane models refresh --provider huggingface --limit 10 --dry-run --verbose
```

`--limit` is the default per-provider maximum. Repeat `--provider-limit PROVIDER=COUNT` to override a particular model provider. For example, use a large Hugging Face limit and a smaller/larger provider-specific limit when refreshing all providers. By default refresh prints provider-level counts only; add `--verbose` to include per-model change rows.

Review generated aliases before making them curated profile entries. Promotion copies one alias from `models.generated.yaml` into `models.yaml`; by default it removes the generated copy so the curated alias becomes authoritative:

```bash
aiplane models promote generated-alias --dry-run
aiplane models promote generated-alias --as reviewed-alias
aiplane models promote generated-alias --as reviewed-alias --keep-generated
```

To clear generated model aliases, use `clear-cache`. This operates on refresh/import data in `models.generated.yaml` plus legacy refresh-imported aliases in `models.yaml`; it does not remove or disable model providers from `model-providers.yaml` or `model-providers.user.yaml`. The command reports counts by provider, not every removed alias. By default it keeps hand-curated/template aliases; add `--include-curated` only when you intentionally want to remove curated/template aliases too:

```bash
aiplane models clear-cache --dry-run
aiplane models clear-cache --provider huggingface --dry-run
aiplane models clear-cache --provider huggingface --include-curated --dry-run
aiplane models clear-cache
```

Important output fields:

- `source_models_returned`: number of model ids returned by the source catalog for that provider. This is the online source API count where an adapter exists, or the profile catalog fallback count when no online adapter/result is available.
- `profile_models_before_refresh`: total profile aliases already stored for that provider before this refresh writes anything.
- `profile_curated_models_before_refresh`: hand-curated/template aliases for that provider. These are preserved by refresh and normal `clear-cache`.
- `profile_refresh_imported_models_before_refresh`: aliases previously imported by `models refresh`. These are written to `models.generated.yaml` and removed by normal `clear-cache`.
- `source_models_already_profiled`: returned source ids already represented by profile aliases.
- `source_models_to_import`: returned source ids that would be imported.
- `source_models_to_update`: returned source ids that already exist locally but have changed source-derived metadata.
- `source_contacted`: whether an online/source API was contacted successfully. `false` means the result came from fallback/profile data; see `source_discovery_reason` for the error or missing-adapter reason.
- `source_discovery_method`: where the result came from, for example `source_api` or `profile_catalog` fallback.
- `prune_enabled`: whether missing source ids are allowed to remove generated aliases. Pruning is enabled only after a successful authoritative online/source response. Query results, limit-truncated source windows, and profile-catalog fallback do not prune.
- `model_changes_count`: number of per-model change rows hidden from the default summary.
- `model_changes`: shown only with `--verbose`; contains aliases that would be imported/imported, would be updated/updated, or would be removed/removed. In verbose rows, `model.id` is the provider-native model id, `model.source` is the model provider, and `runtime_endpoint` is the configured runtime endpoint such as `ollama`, `vllm`, `transformers`, or `llamacpp`.

New entries are enabled by default. Use `--disable-new` to import them disabled.

## Runtime Inventory

Runtime inventory means models already pulled, loaded, or exposed by a running runtime. Use runtime commands for that:

```bash
aiplane runtimes list-runtime-models ollama
aiplane runtimes status ollama
aiplane runtimes doctor ollama
```

For Ollama, the local API `/api/tags` reports models already pulled into that Ollama runtime. It does not enumerate the full public Ollama library. Use `aiplane runtimes pull ollama --model <alias-or-id>` to download a model.

## Runtime Helper Commands

Common Ollama flow:

```bash
aiplane runtimes install ollama --dry-run
aiplane runtimes install ollama
aiplane runtimes start ollama
aiplane runtimes pull ollama --model qwen-tiny
aiplane runtimes list-runtime-models ollama
aiplane runtimes status ollama
```

Common OpenAI-compatible runtime checks:

```bash
aiplane runtimes configure vllm
aiplane runtimes install vllm --dry-run
aiplane runtimes pull vllm --model qwen-coder-32b-vllm --dry-run
aiplane runtimes start vllm --model qwen-coder-32b-vllm --dry-run
aiplane runtimes list-runtime-models vllm
```

The runtime helper layer delegates to `scripts/provider_helper.sh` and runtime-specific helpers such as `scripts/ollama_helper.sh`. Direct helper scripts remain available for debugging.

## Current Scope

Online catalog discovery is implemented provider by provider because each source has different APIs and metadata quality:

- Hugging Face Hub has a live online query adapter via its model API.
- Hugging Face GGUF uses the Hugging Face adapter with a GGUF-oriented search.
- Ollama has local runtime inventory and pull support; complete public library enumeration still needs a separate catalog adapter or curated index.
- Piper voices and local files are represented in the source model map and profile catalog. Other specialist catalogs can be added through user provider config once their API/metadata path is stable enough.

Runtime lifecycle support is documented in [Model Sources and Runtimes](runtime-model-map.md).
