# Practical Workflows

This page shows common ways to combine profiles, model sources, runtimes, setup, integrations, MCP, machines, stacks, and refresh commands. Use it as a recipe index after reading the [Practical Overview](overview.md).

## Terminology Used Here

- **Profile**: the editable configuration set under `profiles/<name>/`. It owns defaults, model aliases, runtime endpoints, machines, targets, tools, and approvals.
- **Model source** or **model provider**: where model ids or files come from, such as Ollama Library, Hugging Face Hub, GGUF repos, Piper voices, or local files.
- **Runtime**: software that serves or loads the model, such as Ollama, vLLM, TGI, llama.cpp, Transformers, LocalAI, or LM Studio.
- **Runtime endpoint**: the configured service a client calls, usually an OpenAI-compatible `/v1` URL.
- **Curated model alias**: a human-maintained entry in `models.yaml`. Defaults should point at curated aliases.
- **Generated model alias**: an entry imported by `models refresh` into `models.generated.yaml`.
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
aiplane runtimes pull ollama --model qwen-tiny

aiplane runtimes status ollama
aiplane runtimes list-runtime-models ollama
aiplane models doctor
```

Practical tips:

- Run `--dry-run` before installs or pulls on a new machine.
- `runtimes pull ollama --model qwen-tiny` accepts either a profile alias or a raw Ollama id.
- `models doctor` checks whether configured model aliases are currently usable; it is not an online catalog search.

## Workflow 2: Continue in VS Code

Use this when Continue should call selected local or remote model endpoints.

```bash
aiplane integrations roles continue
aiplane integrations plan continue
aiplane integrations setup continue --dry-run
aiplane integrations setup continue
aiplane integrations export continue
```

What happens:

- `roles` shows that Continue can use `chat`, `autocomplete`, and `embedding` selections.
- `plan` explains the chosen aliases, runtimes, endpoints, and reasons.
- `setup` starts missing selected runtimes and pulls missing selected models where helper support exists. It does not install the runtime.
- `export` prints the Continue YAML to paste or merge into Continue config.

Practical tips:

- Install runtimes explicitly first when needed: `aiplane runtimes install ollama --dry-run`.
- Use explicit role overrides when defaults are not what you want:

```bash
aiplane integrations plan continue \
  --chat llama-8b \
  --autocomplete qwen-coder-1.5b-base \
  --embedding nomic-embed-text

aiplane integrations export continue \
  --chat llama-8b \
  --autocomplete qwen-coder-1.5b-base \
  --embedding nomic-embed-text
```

## Workflow 3: Single-Model IDE or CLI Client

Use this for Cline, Zed, Aider, or a generic OpenAI-compatible client.

```bash
aiplane integrations plan cline --model qwen-coder-32b-vllm --endpoint http://localhost:8000/v1
aiplane integrations export cline --model qwen-coder-32b-vllm --endpoint http://localhost:8000/v1

aiplane integrations plan aider --select-best --runtime ollama --capability code_generation>=3
aiplane integrations export aider --select-best --runtime ollama --capability code_generation>=3

aiplane integrations export openai-compatible --model qwen-tiny
```

Practical tips:

- Single-model targets use `selection.primary` in `plan` output.
- `--endpoint` is the URL the target tool will call. For a tunnel, this is usually a local URL even when the model runs elsewhere.
- `export` can select a model directly, or it can use the same `--runtime`, `--capability`, and `--select-best` logic as `plan`.

## Workflow 4: MCP Plus Model Endpoint

Use this when an IDE or agent should query `aiplane` as tools as well as call a model endpoint.

```bash
aiplane integrations export continue
aiplane integrations export vscode-mcp
aiplane mcp manifest
aiplane mcp serve
```

How to think about it:

- The model endpoint is for inference: chat, autocomplete, embeddings, or code assistance.
- MCP is for structured `aiplane` tools: profile inspection, model lists, hardware recommendations, integration snippets, tunnel plans, and guarded profile edits.
- MCP exports do not select inference models.

## Workflow 5: Refresh Source Catalogs Without Breaking Defaults

Use this when you want local searchable model-source data while preserving curated defaults.

```bash
aiplane models refresh --provider huggingface --query qwen2.5-coder --limit 25 --dry-run --verbose
aiplane models refresh --provider huggingface --query qwen2.5-coder --limit 25

aiplane models list --source huggingface --limit 10
aiplane models list --runtime vllm --capability code_generation>=4 --enabled-only --sort-by avg --limit 10
```

Storage rules:

- Curated aliases live in `models.yaml`.
- Generated refresh/import aliases live in `models.generated.yaml`.
- Curated aliases win if the same alias exists in both files.
- Refresh can update source metadata on a curated alias, but it must not delete curated aliases or remove profile defaults.

Cleanup:

```bash
aiplane models clear-cache --dry-run
aiplane models clear-cache --provider huggingface --dry-run
aiplane models clear-cache
```

Use `--include-curated` only when you intentionally want to remove curated aliases from `models.yaml` too.

## Workflow 6: Choose or Change Model Defaults

Use this when integrations or `aiplane run` should use different profile defaults.

```bash
aiplane models defaults
aiplane models show llama-8b
aiplane models use chat_model llama-8b
aiplane models use autocomplete_model qwen-coder-1.5b-base
aiplane models use embedding_model nomic-embed-text
aiplane profiles validate
```

Practical tips:

- Defaults should point at curated aliases in `models.yaml`, not generated discovery entries.
- Use `models list --role chat --sort-by role` to inspect candidates.
- Use `profiles validate` after changing defaults to catch missing aliases.

## Workflow 7: vLLM or TGI on a GPU Host

Use this when a Hugging Face model should run behind an OpenAI-compatible endpoint.

```bash
aiplane models show qwen-coder-32b-vllm
aiplane runtimes install vllm --dry-run
aiplane runtimes pull vllm --model qwen-coder-32b-vllm --dry-run
aiplane runtimes start vllm --model qwen-coder-32b-vllm --dry-run
aiplane runtimes status vllm

aiplane integrations export continue --model qwen-coder-32b-vllm --endpoint http://localhost:8000/v1
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
  --model qwen-coder-32b-vllm \
  --machine gpu_workstation_ssh \
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
aiplane models benchmark qwen-tiny --dry-run
aiplane models benchmark qwen-tiny
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
aiplane environment doctor
aiplane runtimes prerequisites all
aiplane runtimes doctor
aiplane models doctor
aiplane integrations plan continue
```

Common fixes:

- Missing default model alias: restore or add the alias in `models.yaml`, then run `profiles validate`.
- Runtime not reachable: run `runtimes prerequisites <runtime>`, then preview `runtimes install <runtime> --dry-run` or `runtimes start <runtime> --dry-run` where helper support exists.
- Model not pulled: run `runtimes pull <runtime> --model <alias>`.
- Wrong IDE endpoint: rerun `integrations plan/export` with `--endpoint`.
- Catalog too noisy: use `models clear-cache --dry-run`, then clear generated entries.
