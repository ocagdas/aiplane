# Practical Workflows

This page shows common ways to combine profiles, model sources, runtimes, setup, integrations, MCP, machines, stacks, and refresh commands. Use it as a recipe index after reading the [Practical Overview](overview.md).

## Terminology Used Here

- **Profile**: the editable configuration set under `profiles/<name>/`. It owns defaults, model aliases, local overrides, machines, targets, tools, and approvals. Runtime endpoint values are built-in conventional defaults unless the profile or local ignored config overrides them.
- **Model source** or **model provider**: where model ids or files come from, such as Ollama Library, Hugging Face Hub, GGUF repos, Azure Speech voices, managed-provider catalogs, or local files.
- **Runtime**: software that serves or loads the model, such as Ollama, vLLM, TGI, llama.cpp, Transformers, LocalAI, or LM Studio.
- **Runtime endpoint**: the configured service a client calls, usually an OpenAI-compatible `/v1` URL.
- **Profile-owned model entry**: a human-maintained entry in the selected profile's `models.yaml`. Defaults should point at profile-owned entries.
- **Discovered model entry**: a temporary discovery entry imported by `models refresh` into ignored `models.discovered.yaml`.
- **Plan**: explain a selection or action without changing runtime or IDE config.
- **Setup**: prepare the selected runtime/model where helpers support it.
- **Export**: print configuration text for another tool. Export does not install extensions or edit settings files.
- **Doctor**: readiness check for profiles, tools, providers, runtimes, or models.

## Workflow 1: First Local Ollama Setup

Use this when you want a small local model reachable from `aiplane` and IDE tools.

```bash
aiplane profiles list
aiplane profiles show --selected
aiplane profiles validate

aiplane runtimes install ollama --dry-run
aiplane runtimes install ollama
aiplane runtimes start ollama
aiplane runtimes pull ollama --model MODEL_ALIAS

aiplane runtimes status ollama
aiplane runtimes list-runtime-models ollama
aiplane models doctor
```

Practical tips:

- Run `--dry-run` before installs or pulls on a new machine.
- `runtimes pull ollama --model MODEL_ALIAS` accepts either a profile alias or a raw Ollama id.
- `models doctor` checks whether configured model aliases are currently usable; it is not an online catalog search.

## Workflow 2: Continue in VS Code

Use this when Continue should call selected local or remote model endpoints.

```bash
aiplane integrations roles continue
aiplane models refresh --provider ollama --query chat --dry-run --limit 10
aiplane integrations plan continue --chat CHAT_ALIAS --autocomplete AUTOCOMPLETE_ALIAS --embedding EMBEDDING_ALIAS
aiplane integrations setup continue --chat CHAT_ALIAS --autocomplete AUTOCOMPLETE_ALIAS --embedding EMBEDDING_ALIAS --dry-run
aiplane integrations export continue --chat CHAT_ALIAS --autocomplete AUTOCOMPLETE_ALIAS --embedding EMBEDDING_ALIAS
```

What happens:

- `roles` shows that Continue can use `chat`, `autocomplete`, and `embedding` selections.
- `plan` explains the chosen aliases, runtimes, endpoints, and reasons. On a freshly bootstrapped profile, pass explicit aliases discovered into `models.discovered.yaml` or added/promoted into local `models.yaml`.
- `setup` starts missing selected runtimes and pulls missing selected models where helper support exists. It does not install the runtime.
- `export` prints the Continue YAML to paste or merge into Continue config.

Practical tips:

- Install runtimes explicitly first when needed: `aiplane runtimes install ollama --dry-run`.
- Use explicit role overrides when defaults are not what you want:

```bash
aiplane integrations plan continue \
  --chat CHAT_ALIAS \
  --autocomplete AUTOCOMPLETE_ALIAS \
  --embedding EMBEDDING_ALIAS

aiplane integrations export continue \
  --chat CHAT_ALIAS \
  --autocomplete AUTOCOMPLETE_ALIAS \
  --embedding EMBEDDING_ALIAS
```

## Workflow 3: Single-Model IDE or CLI Client

Use this for Cline, Zed, Aider, or a generic OpenAI-compatible client.

```bash
aiplane integrations plan cline --model MODEL_ALIAS --endpoint http://localhost:8000/v1
aiplane integrations export cline --model MODEL_ALIAS --endpoint http://localhost:8000/v1

aiplane integrations plan aider --select-best --runtime ollama --capability code_generation>=3
aiplane integrations export aider --select-best --runtime ollama --capability code_generation>=3

aiplane integrations export openai-compatible --model MODEL_ALIAS
```

Practical tips:

- Single-model targets use `selection.primary` in `plan` output.
- `--endpoint` is the URL the target tool will call. For a tunnel, this is usually a local URL even when the model runs elsewhere.
- `export` can select a model directly, or it can use the same `--runtime`, `--capability`, and `--select-best` logic as `plan`.

## Workflow 4: Run One Prompt Through a Configured Model

Use this when you want a quick smoke prompt against a reviewed profile model alias without opening an IDE or agent framework. `aiplane run` is a thin execution path: it sends one prompt to the selected model endpoint and returns text. It does not edit files, run tools, or start an autonomous agent loop.

```bash
aiplane run --dry-run --model MODEL_ALIAS "explain this setup"
aiplane run --model MODEL_ALIAS "summarize this repository goal"
aiplane run --escalate "draft a short migration checklist"
```

Supported execution protocols are currently:

- local Ollama API for Ollama-backed aliases;
- OpenAI-compatible chat completions for OpenAI, vLLM, TGI, llama.cpp, LocalAI, LM Studio, and custom OpenAI-compatible endpoints when configured as reachable HTTP endpoints;
- Azure OpenAI chat completions, where the model id is the deployment name;
- Anthropic Messages API for Anthropic aliases.

If a model points at a provider/runtime without one of those protocols, `aiplane run` and `models test` fail explicitly instead of guessing. Use `--dry-run` first to confirm the selected alias and prompt.

## Workflow 5: MCP Plus Model Endpoint

Use this when an IDE or agent should query `aiplane` as tools as well as call a model endpoint.

```bash
aiplane integrations export continue --chat CHAT_ALIAS --autocomplete AUTOCOMPLETE_ALIAS --embedding EMBEDDING_ALIAS
aiplane integrations export vscode-mcp
aiplane mcp manifest
aiplane mcp serve
```

How to think about it:

- The model endpoint is for inference: chat, autocomplete, embeddings, or code assistance.
- MCP is for structured `aiplane` tools: profile inspection, model lists, hardware recommendations, integration snippets, tunnel plans, and guarded profile edits.
- MCP exports do not select inference models.

## Workflow 6: Refresh Source Catalogs Without Breaking Defaults

Use this when you want local searchable model-source data in the ignored discovery cache. The shipped profile has no model defaults; local defaults should be added only after discovery and review.

```bash
aiplane models refresh --provider huggingface --query text-generation --limit 25 --dry-run --verbose
aiplane models refresh --provider huggingface --query text-generation --limit 25

aiplane models list --source huggingface --limit 10
aiplane models list --runtime vllm --capability code_generation>=4 --enabled-only --sort-by avg --limit 10
```

Storage rules:

- Profile-owned model entries live in `models.yaml`.
- Discovery refresh/import entries live in `models.discovered.yaml`.
- Profile-owned entries in `models.yaml` win if the same entry name exists in both files.
- Refresh can update source metadata on a profile-owned entry, but it must not delete profile-owned entries or remove profile defaults. Use `models clear-cache` when you intentionally want to clear discovered entries and profile-owned review entries, or `models refresh --reset-cache` when you want clear-then-refresh in one step.
- Enable/disable is persistent profile policy, so `models enable` and `models disable` write only profile-owned entries in `models.yaml`; discovered-only cache entries must be added or promoted first.

Cleanup:

```bash
aiplane models clear-cache --dry-run
aiplane models clear-cache --provider huggingface --dry-run
aiplane models clear-cache
aiplane models refresh --provider huggingface --reset-cache --dry-run
```

Use `--keep-curated` when you want to preserve profile-owned entries in `models.yaml` and clear only discovered refresh/import entries.

## Workflow 6: Choose or Change Model Defaults

Use this when integrations or `aiplane run` should use different profile defaults.

```bash
aiplane models defaults
aiplane models show CHAT_ALIAS
aiplane models use chat_model CHAT_ALIAS
aiplane models use autocomplete_model AUTOCOMPLETE_ALIAS
aiplane models use embedding_model EMBEDDING_ALIAS
aiplane profiles validate
```

Practical tips:

- Defaults should point at profile-owned entries in `models.yaml`, not discovered model entries.
- Use `models list --role chat --sort-by role`, `models list --role text_to_speech`, `models list --role image_generation --runtime diffusers`, or `models list --role video_generation --runtime diffusers` to inspect profile-owned and discovered candidates.
- Use `profiles validate` after changing defaults to catch missing aliases.

## Workflow 7: vLLM or TGI on a GPU Host

Use this when a Hugging Face model should run behind an OpenAI-compatible endpoint.

```bash
aiplane models show MODEL_ALIAS
aiplane runtimes install vllm --dry-run
aiplane runtimes pull vllm --model MODEL_ALIAS --dry-run
aiplane runtimes start vllm --model MODEL_ALIAS --dry-run
aiplane runtimes status vllm

aiplane integrations export continue --model MODEL_ALIAS --endpoint http://localhost:8000/v1
```

Practical tips:

- `runtimes start vllm --dry-run` is where you inspect the serving command before using GPU resources.
- Runtime helpers are useful starters, not full production GPU tuning.
- For remote hosts, configure a tunnel or stack and export the endpoint clients should call.

## Workflow 8: Remote Workstation Through SSH Tunnel

Use this when the runtime runs on another machine but your IDE should call a local forwarded URL.

```bash
aiplane remote tunnel plan --target gpu_workstation_ssh
aiplane remote tunnel start --target gpu_workstation_ssh
aiplane remote tunnel status --target gpu_workstation_ssh

aiplane integrations export continue --endpoint http://localhost:8000/v1
```

Practical tips:

- The remote service endpoint is what the SSH host can reach.
- The IDE endpoint is the local forwarded URL.
- Start the runtime on the remote host separately unless the stack lifecycle path owns it.

## Workflow 9: Machines and Stacks

Use this when you want to bind machine, runtime, model, access policy, and optional orchestrator into one named plan.

```bash
aiplane machines list
aiplane machines discover
aiplane stacks setup coding_agents \
  --runtime vllm \
  --model MODEL_ALIAS \
  --machine azure_h100_remote \
  --target gpu_workstation_ssh \
  --access ssh_tunnel \
  --dry-run

aiplane stacks plan coding_agents
aiplane stacks doctor coding_agents
aiplane stacks export continue coding_agents
```

Practical tips:

- Stack planning includes install, pull, start, tunnel, and export steps in one view.
- Stack lifecycle execution is intentionally guarded and local-first while remote/cloud execution hardens.
- Use stacks when repeated deployment/access combinations are more important than one-off exports.

## Workflow 10: Cloud Target Planning

Use this when you want to inspect configured Azure VM or AKS targets before applying anything.

```bash
aiplane deploy list
aiplane deploy show --target azure_gpu_vm
aiplane deploy plan --target azure_gpu_vm
aiplane deploy doctor --target azure_gpu_vm
```

Practical tips:

- Cloud target commands depend on external tools such as `az`, `kubectl`, Docker, and SSH.
- Check tools first: `aiplane tools doctor azure-cli`.
- Treat `deploy apply` as a guarded bootstrap path, not a full infrastructure platform.

## Workflow 11: Benchmarks and Model Fit

Use this when you want a practical smoke signal before making a model default.

```bash
aiplane hardware recommend
aiplane models benchmark MODEL_ALIAS --dry-run
aiplane models benchmark MODEL_ALIAS
aiplane models list --sort-by benchmark --require-benchmark
```

Practical tips:

- Capability scores are catalog hints on a 0-5 scale.
- Benchmark scores are local smoke-test results on a 0-100 scale.
- Hardware fit, role score, and benchmark score answer different questions; use them together.

## Troubleshooting Checklist

```bash
aiplane profiles validate
aiplane tools doctor
aiplane environment doctor --format text
aiplane runtimes prerequisites all
aiplane runtimes doctor
aiplane models doctor
aiplane integrations roles continue
aiplane integrations plan continue --chat CHAT_ALIAS --autocomplete AUTOCOMPLETE_ALIAS --embedding EMBEDDING_ALIAS
```

Common fixes:

- Missing model entry: run provider discovery into `models.discovered.yaml`, promote a reviewed entry or use `models add` if you want a profile-owned default, or pass explicit `--chat`/`--autocomplete`/`--embedding` entries.
- Runtime not reachable: run `runtimes prerequisites <runtime>`, then preview `runtimes install <runtime> --dry-run` or `runtimes start <runtime> --dry-run` where helper support exists.
- Model not pulled: run `runtimes pull <runtime> --model <alias>`.
- Wrong IDE endpoint: rerun `integrations plan/export` with `--endpoint`.
- Catalog too noisy: use `models clear-cache --dry-run`, review whether profile-owned entries are included, and add `--keep-curated` if you only want to clear discovered entries.
