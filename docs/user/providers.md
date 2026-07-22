# Model Providers and Runtime Helpers

In `aiplane`, **provider** means a model source/catalog: a place where model ids, model files, or model artifacts come from.

Examples:

- `ollama`: Ollama model library names such as `text-generation:0.5b`.
- `huggingface`: Hugging Face Hub repos such as `Provider/Code-Large-Instruct`.
- `nvidia`: NVIDIA open model repos on Hugging Face, including Nemotron language, reasoning, retrieval, speech, vision, and safety models.
- `huggingface_gguf`: GGUF files hosted on Hugging Face or similar file stores.
- `local_file`: a local model path.
- `azure_speech`: Azure Speech text-to-speech voice configuration.
- `elevenlabs`: ElevenLabs hosted text-to-speech voices.
- `openai`, `anthropic`, `azure_openai`, `ollama_cloud`: managed providers. These are hosted services, so they need endpoint/API-key configuration and profile-owned model entries before IDE exports can use them. Other catalogs can be added in `model-providers.user.yaml` when their discovery path is reliable for your environment.

A **runtime** is different. A runtime loads model files into CPU/GPU memory and serves inference. Examples: `ollama`, `vllm`, `tgi`, `llamacpp`, `transformers`, `localai`, `lmstudio`, `faster_whisper`, `diffusers`, and `comfyui`. Managed services such as `azure_speech` and `elevenlabs` are hosted service providers/endpoints, not local runtime-fit targets.

For NVIDIA open model repos, the practical local/runtime targets currently modeled in `aiplane` are `vllm`, `tgi`, and `transformers`, because those repos are Hugging Face-style model artifacts. NVIDIA-optimized deployment paths such as NIM, TensorRT-LLM, and SGLang can be represented later as runtime helpers, but they are not first-class `aiplane` runtime helpers yet.

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
aiplane models list --group-by provider-kind
aiplane models list --self-managed-only
aiplane models list --managed-service-only
```

`provider-kind` groups first by ownership (`self_managed` or `managed_service`) and then by provider/source. `providers list --group-by ownership` gives the same ownership split at the provider/source level before any model aliases are added. Keep `provider` populated for managed services; it identifies the hosted service or endpoint family. Managed-service models are not runtime-fit candidates, so runtime grouping places them under `no_runtime`; `preferred_runtime` and `supported_runtimes` are ignored for managed-service aliases.

Managed-service providers do not have local model weights for `aiplane` to pull. `aiplane models pull` and `aiplane runtimes pull` are for self-managed runtimes/sources such as Ollama, Hugging Face/vLLM/TGI/Transformers, GGUF, or local files. For OpenAI, Anthropic, Azure OpenAI, Ollama Cloud, Azure Speech, and ElevenLabs, configure credentials/endpoints and test reachability instead of pulling a model.

Managed-service model aliases must not be combined with local runtime fields. `preferred_runtime` and `supported_runtimes` are ignored in list/grouping output and rejected by runtime operations and execution paths. Use `provider`, `endpoint_family`, credentials, and endpoint configuration instead.

## Managed Providers In Practice

Managed providers are not local runtimes. They sit in `aiplane` as hosted provider endpoint families plus optional catalog discovery adapters:

1. `providers endpoint-types` shows which hosted API families and catalog adapters `aiplane` understands. If a provider uses a different API shape, live discovery/test support needs a code update.
2. `model-providers.yaml` or ignored `model-providers.user.yaml` records provider metadata: ownership, endpoint family, catalog adapter, auth requirement, and default credential env var or endpoint.
3. `providers models PROVIDER --online` can discover provider models/deployments only when a catalog adapter exists and credentials are configured when required. Otherwise use `profile_catalog` and add model aliases manually.
4. `models add`/`models promote` creates profile-owned aliases under `models:`. For Azure OpenAI, the alias `model` value is the deployment name.
5. `models list` and `models show` expose these aliases as `managed_service` entries under `no_runtime`; they are not runtime-fit candidates.
6. `integrations plan/export` turns selected aliases into IDE/tool config using the provider endpoint, protocol, and API-key environment variable.
7. `aiplane run` or `models test` can use managed aliases through supported endpoint protocols and policy/credential checks. Current execution protocols cover OpenAI-compatible chat completions, Azure OpenAI chat completions, and Anthropic Messages. Runtime bundle/install/start/pull paths remain self-managed only.

The practical flow is:

1. Keep model source/provider discovery settings in `model-providers.yaml` or ignored `model-providers.user.yaml`. Keep managed endpoint overrides and credential refs in ignored local provider/credential config when the built-in endpoint default is not enough.
2. Discover available models/deployments, then add or promote a profile-owned model entry under `models:`. For Azure OpenAI, the `model` value is the deployment name.
3. Run `aiplane integrations plan ...` to inspect which entries, endpoints, and API-key env vars will be used.
4. Run `aiplane integrations export ...` and merge the printed config into the target tool.

Examples:

```bash
export OPENAI_API_KEY=...
aiplane integrations export continue --model managed-chat-small

export AZURE_OPENAI_API_KEY=...
aiplane providers models azure_openai --online --limit 20
aiplane integrations export openai-compatible --model managed-azure-chat --endpoint https://YOUR-RESOURCE.openai.azure.com
```

Use managed providers deliberately. They can send selected IDE context to a hosted service and may incur cost. Keep local defaults for local-only workflows, and use explicit `--model`, `--provider`, or role overrides when you want a managed model.

For hosted TTS, ElevenLabs can be used as a managed provider/source. `aiplane` can discover voices and track selected voice aliases, but it does not synthesize audio in this milestone:

```bash
export ELEVENLABS_API_KEY=...
aiplane providers models elevenlabs --online --limit 20
aiplane models refresh --provider elevenlabs --dry-run --verbosity 2 --limit 20
aiplane models list --provider elevenlabs --role text_to_speech
```

For multiple accounts, keep credentials in the ignored local credentials file and reference them by name from local provider overrides or command options. Well-known managed providers have built-in endpoint defaults and adapters where safe. Custom providers should specify an endpoint, protocol, and credential reference in ignored local config. The profile should not contain raw API keys.

Example ignored `.aiplane/credentials.yaml` with multiple accounts:

```yaml
providers:
  openai:
    accounts:
      personal:
        api_key_env: OPENAI_PERSONAL_API_KEY
        endpoint: https://api.openai.com/v1
      business_a:
        api_key_env: OPENAI_BUSINESS_A_API_KEY
        endpoint: https://api.openai.com/v1
  azure_openai:
    accounts:
      business_a:
        api_key_env: AZURE_OPENAI_BUSINESS_A_KEY
        endpoint: https://YOUR-RESOURCE.openai.azure.com
        api_version: 2024-02-01
  anthropic:
    accounts:
      personal:
        api_key_env: ANTHROPIC_PERSONAL_API_KEY
```

Set the environment variables in your shell, shell profile, direnv, or secret manager. Then inspect refs without exposing secrets:

```bash
aiplane credentials list
aiplane credentials show openai.personal
aiplane credentials show azure_openai.business_a
```

Test a managed provider endpoint and credential without printing the secret:

```bash
aiplane providers test openai --credential-ref openai.personal
aiplane providers test azure_openai --credential-ref azure_openai.business_a
aiplane providers test elevenlabs
```

The test command has live adapters for Azure OpenAI deployment listing, ElevenLabs voice listing, Anthropic model listing, and OpenAI-compatible `/v1/models` endpoints. Custom OpenAI-compatible endpoints can explicitly declare that authentication is not required; hosted defaults still fail closed when credentials are missing.

## Provider Commands

Inspect discovery readiness without making a network request or revealing credential values:

```bash
aiplane providers diagnose
aiplane providers diagnose openai
aiplane providers diagnose anthropic
```

The versioned result separates adapter, endpoint, and credential-reference checks and gives the next online query command. Use `providers test` afterward when you intend to contact the endpoint.

List known model providers. The list includes `ownership` so you can distinguish `self_managed` model sources from `managed_service` providers:

```bash
aiplane providers list
aiplane providers list --status enabled
aiplane providers list --status disabled
aiplane providers list --status all
aiplane providers list --group-by ownership
aiplane providers list --runtime ollama
aiplane providers list --runtime vllm --group-by runtime
```

Enable or disable providers without editing YAML directly:

```bash
aiplane providers disable nvidia
aiplane providers enable nvidia
aiplane providers disable all
aiplane providers enable all
```

Refresh the profile-local default provider list after updating `aiplane`:

```bash
aiplane providers update-defaults
```

`update-defaults` rewrites `model-providers.yaml` from the current built-in provider definitions, preserving existing `enabled` values in that file and leaving `model-providers.user.yaml` untouched. This lets code updates add providers or update provider metadata without overwriting a provider you disabled manually or through `providers disable`. Prefer this command over hand-editing provider files.

### Local File Models

`local_file` is for model artifacts that already exist on this machine or on a known mounted path. It is disabled by default because local paths are machine-specific. Enable it when you want profile aliases for GGUF files, checkpoint directories, ONNX files, local Whisper models, Diffusers folders, or ComfyUI assets:

```bash
aiplane providers enable local_file
aiplane models add local_gguf --provider local_file --model /models/mistral.Q4_K_M.gguf --runtime llamacpp --role chat --role analysis
aiplane models add local_diffusion --provider local_file --model /models/diffusers/my-model --runtime diffusers --role image_generation
```

For normal providers, `models add` promotes a reviewed discovered entry from `models.discovered.yaml` into durable `models.yaml`. `local_file` is the exception: because there is no remote catalog to discover from, `--provider local_file --model PATH` writes a direct profile-owned entry. `--model` is the local path; repeat `--runtime` to declare compatible local runtimes, and use `--preferred-runtime` when more than one runtime is listed. `aiplane` records the path; it does not copy, validate, or delete the model file.

Remove individual profile-owned aliases by name without deleting model files or discovery cache entries:

```bash
aiplane models remove local_gguf --dry-run
aiplane models remove local_gguf
```

Discovered entries in `models.discovered.yaml` are provider/cache state. Leave them to `models refresh` or provider-scoped cache clearing instead of deleting them one alias at a time. Likewise, `models enable` and `models disable` apply only to profile-owned aliases in `models.yaml`; promote or add a discovered model first when you want persistent enablement policy.

Clear all local-file aliases/imports from the profile/cache with provider-scoped cache clearing:

```bash
aiplane models clear-cache --provider local_file --dry-run
aiplane models clear-cache --provider local_file
```

Show one model provider and the profile catalog entries that come from it:

```bash
aiplane providers show ollama
aiplane providers show huggingface
```

List known source-native model ids for one model provider:

```bash
aiplane providers models ollama
aiplane providers models huggingface
```

Test one provider endpoint and credential:

```bash
aiplane providers test azure_openai --credential-ref azure_openai.personal
```

Query an online catalog where an adapter exists:

```bash
aiplane providers models ollama --online --query model_row --limit 500
aiplane providers models huggingface --online --query text-generation --limit 500
aiplane providers models huggingface --online --query text-to-speech --limit 50
aiplane providers models nvidia --online --query Nemotron --limit 50
aiplane providers models openai --online --query chat --limit 20
aiplane providers models elevenlabs --online --query voice --limit 20
aiplane providers models huggingface --online --query text-to-image --limit 50
aiplane providers models huggingface --online --query text-to-video --limit 50
aiplane providers models huggingface_gguf --online --query llama-3.1-8b --limit 500
```

Current default catalog adapters are `ollama`, `huggingface`, `nvidia`, `huggingface_gguf`, OpenAI-compatible `/v1/models` for `openai` when endpoint/key configuration is present, `azure_openai` deployments when endpoint/key configuration is present, and `elevenlabs` voices when `ELEVENLABS_API_KEY` or a credential reference is configured. The `nvidia` provider uses the Hugging Face adapter scoped to NVIDIA-owned repos. Hugging Face discovery can return media pipeline metadata that `models refresh` maps into roles such as `text_to_speech`, `image_generation`, and `video_generation` before candidates are filtered or promoted. If a self-managed online query fails or the provider has no adapter yet, `aiplane` falls back to the profile catalog and includes the reason. Fallback is non-destructive: it does not update or prune local entries because it is only re-reading the local profile. Managed providers with live catalog adapters report missing endpoint/credential configuration as structured refresh failures instead of presenting an empty local fallback as success.

## Provider Configuration Files

Model-provider discovery definitions are profile-local YAML. The shipped defaults live under `profile-templates/local-dev/`; the editable `profiles/` directory is local user state and is gitignored. The template keeps `models.yaml` structural only: it does not ship profile-owned model entries, defaults, credentials, discovered model caches, or runtime endpoint overrides.

For the common local setup, use the bootstrap helper:

```bash
aiplane profiles bootstrap-local
aiplane profiles bootstrap-local --provider ollama --limit 25
aiplane profiles bootstrap-local --no-discovery
```

`bootstrap-local` copies `profile-templates/local-dev` into `profiles/local-dev` when missing, preserves an existing profile unless `--overwrite` is explicit, validates the profile, and, unless `--no-discovery` is set, runs a bounded `models refresh` into ignored `models.discovered.yaml`.

- `model-providers.yaml`: default/provider seed entries for this profile.
- `model-providers.user.yaml`: ignored user additions and overrides. This is where CLI edits go, and it is the extension point for private cloud endpoints or internal catalogs.

If neither file exists, `aiplane` can fall back to its built-in provider seed so a fresh developer checkout still has discovery providers. That seed contains provider metadata, not model entries. To make the seed explicit, dump it into the profile:

```bash
aiplane providers init-defaults
aiplane providers init-defaults --overwrite
```

Without `--overwrite`, `init-defaults` writes `model-providers.yaml` only when it does not already exist. If the file exists, the command exits with an error instead of replacing your provider config.

Provider APIs are not universally standardized. A user-added provider must declare one of the endpoint families and catalog adapters listed by `aiplane providers endpoint-types`. If the provider uses a different catalog API, auth scheme, pagination shape, or deployment/listing API, `aiplane` needs a code update before live discovery or provider tests can support it. Use `--catalog-adapter openai` for OpenAI-compatible `/v1/models` catalogs, and use `--catalog-adapter profile_catalog` for providers whose model list is curated manually instead of fetched from a live API.

Use `--runtime` only for `self_managed` providers that supply model artifacts for local runtimes. Use `--endpoint-family` for `managed_service` providers. Managed services can declare `--auth-method`, `--api-key-env`, `--credential-ref`, and `--endpoint`; raw keys still belong in environment variables or ignored `.aiplane/credentials.yaml`, not provider YAML.

To inspect supported provider API shapes and add, disable, enable, remove, or clear provider config:

```bash
aiplane providers endpoint-types
aiplane providers add private_hf --ownership self_managed --runtime vllm --catalog-adapter huggingface
aiplane providers add my_gateway --ownership managed_service --endpoint-family custom_openai_compatible --catalog-adapter openai --endpoint https://gateway.example.com/v1 --auth-method bearer --api-key-env MY_GATEWAY_API_KEY
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

`aiplane models refresh` imports model-provider catalog entries into the ignored `models.discovered.yaml` cache so you can later filter locally by runtime, role, capability, score, RAM/VRAM fit, explicit GPU vendor/API requirements, benchmark results, and target hardware. The template `models.yaml` starts empty except for `defaults:` and `models:`. Source discovery definitions come from `model-providers.yaml`, ignored user overrides, and built-in source seeds. Runtime/provider endpoint values such as localhost ports are conventional built-in defaults used for planning, exports, and doctor/test hints; they are not proof that a runtime is installed or configured. Discovered entries are repopulated from provider discovery whenever you refresh. It is online-first where an adapter exists, and it is not runtime inventory.

Refresh also generates an ignored, materialized query cache at
`.aiplane/cache/model-catalog-v1.json`. Editable YAML remains the source of
truth. The cache stores safe enriched model fields, exact-match indexes, and the
latest local benchmark summary so repeated queries do not reparse and enrich the
whole catalog. It excludes secret-bearing properties, is written atomically, and
is rebuilt automatically when its schema, enrichment rules, profile catalog,
discovery cache, or benchmark inputs change. A missing or corrupt cache falls
back to the source files and is regenerated.

When an online source adapter succeeds, the source result is treated as authoritative for discovered/imported entries when it is not a query or limit-truncated window: new source ids are imported into `models.discovered.yaml`, stale discovered ids are pruned, and changed source metadata updates discovered entries. Profile-owned entries in `models.yaml` are preserved by refresh; if a local profile-owned entry points at a returned source id, only source-derived metadata is refreshed while human-maintained fields stay intact. In this context, profile-owned means human-maintained data such as entry names, enabled/disabled state, roles, preferred runtime, RAM/VRAM overrides, and notes.

When a self-managed online source fails or no online adapter exists, refresh reports the reason and falls back to local profile entries without pruning or updating. Managed providers with live catalog adapters, such as OpenAI-compatible `/v1/models`, Azure OpenAI deployments, or ElevenLabs voices, report a structured refresh failure when endpoint or credential configuration is missing; fix `providers show` / `providers test` first, then rerun refresh.

```bash
aiplane models refresh --dry-run
aiplane models refresh --provider huggingface --query text-generation --limit 500 --dry-run
aiplane models refresh --limit 100 --provider-limit huggingface=500 --provider-limit ollama=500 --dry-run
aiplane models refresh --provider huggingface --limit 10 --dry-run --verbosity 2
```

`--limit` is the default per-provider maximum. Repeat `--provider-limit PROVIDER=COUNT` to override a particular model provider. For example, use a large Hugging Face limit and a smaller/larger provider-specific limit when refreshing all providers. Refresh verbosity controls output shape: `--verbosity 0` (default) prints only top-level summary, `--verbosity 1` adds `provider_summary`, and `--verbosity 2` includes the full provider `results` map and per-model change rows. Refresh output also includes `next_steps` so dry runs and writes show the safe path from discovery, to discovered entries, to reviewed promotion.

When provider metadata includes popularity fields, `models list` can filter and rank by them after normal provider/source, role, runtime, capability, and hardware filters:

```bash
aiplane models list --source huggingface --role chat --min-likes 100 --sort-by likes --limit 10
aiplane models list --source huggingface --role embedding --sort-by downloads --limit 10
aiplane models list --provider huggingface --runtime vllm --sort-by popularity --limit 10
aiplane models list --provider ollama --runner ollama --alias local_chat
aiplane models list --model-id qwen2.5-coder:7b --min-parameters-b 7 --max-parameters-b 14
aiplane models list --provider ollama --runner ollama --min-benchmark-score 80 --property quantization=q4
```

`--property FIELD=VALUE` performs an exact match against safe catalog metadata
and accepts dotted paths for nested values. Repeat it to require several model
properties. `--runner` is an alias for `--runtime`.

Materialization is optional per query and directly manageable:

```bash
aiplane models list --provider ollama --catalog-cache off
aiplane models list --provider ollama --catalog-cache rebuild
aiplane models catalog-cache status
aiplane models catalog-cache rebuild
aiplane models catalog-cache clear
```

`models clear-cache` clears provider discovery data. `models catalog-cache
clear` clears only the derived query cache; the next normal query rebuilds it.

Compact text output places the Aiplane `ALIAS` beside the provider-native
`MODEL`, so commands such as `models show`, `models promote`, `models pull`, and
`chat --model` can use the correct alias. The default identity mode is `both`.
Use one-value-per-line output when scripting or copying a particular identity:

```bash
aiplane models list --provider ollama --runtime ollama --role chat --format text
aiplane models list --provider ollama --runtime ollama --role chat --identity alias
aiplane models list --provider ollama --runtime ollama --role chat --identity model
aiplane models list --provider ollama --runtime ollama --role chat --identity both
```

Discovered entries are stored per model entry name under `models.discovered.yaml`. A refresh can create an entry like this:

```yaml
models:
  ollama-llama3-2-3b:
    provider: ollama
    model: llama3.2:3b
    source: ollama
    roles: [chat, analysis, generation]
    supported_runtimes: [ollama]
    source_metadata:
      likes: 420
      downloads: 12000
    capability_scores:
      general_chat: 4
      code_generation: 3
    capability_score_source: catalog_heuristic
    imported_by: aiplane_refresh
```

Runtime fit is stored on each model entry when discovery can infer it, usually as `supported_runtimes` and sometimes `preferred_runtime`. Provider definitions still matter: they describe the provider/source and any default runtime relationship, while the discovered model entry captures model-specific runtime hints and source metadata.

You can use discovered entries directly by name in commands that read the model catalog, because `aiplane` overlays `models.discovered.yaml` with profile-owned entries from `models.yaml`. What you do not get is durable project configuration: discovered entries are ignored cache state, can be removed by `models clear-cache`, and can be updated or pruned by the next authoritative provider refresh.

Review discovered entries before making them profile-owned entries. Promotion copies one discovered entry name from `models.discovered.yaml` into `models.yaml`; the discovered copy is kept by default and the profile-owned entry records `discovered_entry` so the two files remain linked. Use promotion when discovery already found the real model and you want to keep its provider metadata, roles, runtime hints, RAM/VRAM hints, source metadata, popularity fields, and catalog-derived scores:

```bash
aiplane models promote DISCOVERED_ENTRY_NAME --dry-run
aiplane models promote DISCOVERED_ENTRY_NAME --as local_chat
aiplane models promote DISCOVERED_ENTRY_NAME --as local_chat --keep-discovered
aiplane models promote DISCOVERED_ENTRY_NAME --as existing_entry --overwrite
```

Use `models add` when you want to create a profile-owned entry with a deliberate local name while still requiring a discovered source. You can resolve the source by discovered alias or by provider/model id. Repeat `--role` for multiple roles. `models add` rejects aliases or provider/model ids that are not present in `models.discovered.yaml`, because it is meant to turn reviewed discovery into stable local configuration, not invent model metadata by hand. This writes to the selected profile's `models.yaml` and records `discovered_entry`:

```bash
aiplane models add local_chat --alias ollama-llama3-2-3b --role chat --role analysis
aiplane models add local_chat --provider ollama --model llama3.2:3b --role chat --runtime ollama
aiplane models add azure_chat --alias azure-openai-gpt-4o-prod --role chat --disable --dry-run
```

Use `models clone` when the same underlying model should have a second local purpose, role, or note. The target entry still points at the same provider-native `model` value unless you override it with `--set model=...`:

```bash
aiplane models clone local_chat local_fast_draft --role completion --notes "Fast draft model for local workflow tasks."
aiplane models clone DISCOVERED_ENTRY_NAME local_chat --role chat --runtime ollama --dry-run
```

To clear model catalog entries, use `clear-cache`. This operates on discovery/import data in `models.discovered.yaml` plus matching profile-owned review entries in `models.yaml`; it does not remove or disable model providers from `model-providers.yaml` or `model-providers.user.yaml`. The command reports counts by provider, not every removed entry. By default it includes profile-owned review entries in `models.yaml`, so the local model cache and review-time entries can be emptied and later repopulated from provider discovery; add `--keep-curated` when you only want to remove discovered/imported entries:

```bash
aiplane models clear-cache --dry-run
aiplane models clear-cache --provider huggingface --dry-run
aiplane models clear-cache --provider huggingface --keep-curated --dry-run
aiplane models clear-cache
```

Use `models refresh --reset-cache` when you want the clear and refresh phases in one command. It clears refresh/import entries for the refreshed provider before querying the source catalog again. With `--provider all`, `local_file` is skipped because local paths have no remote catalog to repopulate from:

```bash
aiplane models refresh --provider huggingface --reset-cache --dry-run
aiplane models refresh --provider huggingface --reset-cache
aiplane models refresh --reset-cache --dry-run
```

Important output fields:

- `source_models_returned`: number of model ids returned by the source catalog for that provider. This is the online source API count where an adapter exists, or the profile catalog fallback count when no online adapter/result is available.
- `profile_models_before_refresh`: total profile model entries already stored for that provider before this refresh writes anything.
- `profile_curated_models_before_refresh`: profile-owned/template entries for that provider. These are preserved by refresh but included by default in `clear-cache` unless `--keep-curated` is used.
- `profile_refresh_imported_models_before_refresh`: entries previously imported by `models refresh`. These are written to `models.discovered.yaml` and removed by `clear-cache`.
- `source_models_already_profiled`: returned source ids already represented by profile model entries.
- `source_models_to_import`: returned source ids that would be imported.
- `source_models_to_update`: returned source ids that already exist locally but have changed source-derived metadata.
- `source_contacted`: whether an online/source API was contacted successfully. `false` means the result came from fallback/profile data; see `source_discovery_reason` for the error or missing-adapter reason.
- `source_discovery_method`: where the result came from, for example `source_api` or `profile_catalog` fallback.
- `prune_enabled`: whether missing source ids are allowed to remove discovered entries. Pruning is enabled only after a successful authoritative online/source response. Query results, limit-truncated source windows, and profile-catalog fallback do not prune.
- `provider_summary`: compact provider list of status/counts shown with `--verbosity 1`.
- `model_changes_count`: number of per-model change rows hidden from the default summary.
- `model_changes`: shown only in `--verbosity 2` results; contains entries that would be imported/imported, would be updated/updated, or would be removed/removed. In those rows, `model.id` is the provider-native model id, `model.source` is the model provider, and `runtime_endpoint` is the configured runtime endpoint such as `ollama`, `vllm`, `transformers`, or `llamacpp`.
- `next_steps`: command-specific guidance for the safe review flow, such as writing a dry-run refresh, promoting one discovered entry, validating the profile, or previewing cache cleanup.

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

Common Ollama native flow:

```bash
aiplane runtimes install ollama --dry-run
aiplane runtimes install ollama
aiplane runtimes start ollama
aiplane runtimes pull ollama --model MODEL_ALIAS
aiplane runtimes list-runtime-models ollama
aiplane runtimes status ollama
```

Ollama can also run through the official `ollama/ollama` container image when Docker is available. Use dry-run first; this is a runtime substrate choice, not the same thing as running the `aiplane` CLI in Docker:

```bash
aiplane runtimes install ollama --substrate docker --dry-run
aiplane runtimes start ollama --substrate docker --dry-run
aiplane runtimes pull ollama --substrate docker --model MODEL_ALIAS --dry-run
aiplane runtimes status ollama --substrate docker
```

Common OpenAI-compatible runtime checks:

```bash
aiplane runtimes configure vllm
aiplane runtimes install vllm --dry-run
aiplane runtimes pull vllm --model MODEL_ALIAS --dry-run
aiplane runtimes start vllm --model MODEL_ALIAS --dry-run
aiplane runtimes list-runtime-models vllm
```

The runtime helper layer delegates to `scripts/provider_helper.sh` and runtime-specific helpers such as `scripts/ollama_helper.sh`. Direct helper scripts remain available for debugging.

## Current Scope

Online catalog discovery is implemented provider by provider because each source has different APIs and metadata quality:

- Hugging Face Hub has a live online query adapter via its model API.
- Hugging Face GGUF uses the Hugging Face adapter with a GGUF-oriented search.
- Ollama has local runtime inventory and pull support; complete public library enumeration still needs a separate catalog adapter or maintained index.
- Azure Speech voices, local files, and other specialist catalogs can be added through user provider config once their API/metadata path is stable enough. Open-weight media models from Hugging Face should normally flow through online refresh into `models.discovered.yaml` first.

Runtime lifecycle support is documented in [Model Sources and Runtimes](runtime-model-map.md).

## Support declarations and contributor adapter fixtures

~~~bash
aiplane support list
aiplane support list --kind runtime
aiplane support list --full
aiplane support show provider huggingface
aiplane providers adapter-schema
aiplane providers adapter-validate tests/fixtures/adapter-v1.json
~~~

An empty upstream_versions list means no exact upstream version has been verified. The 1.0 adapter contract requires stable IDs, provider identity, provenance, unique entries, and secret-free fields. Its schema is schemas/aiplane-adapter-v1.schema.json. Aiplane does not dynamically execute arbitrary adapter files.
