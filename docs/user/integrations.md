# IDE and CLI Integrations

`aiplane` integrates by exporting configuration and launching existing tools. It
does not try to replace IDE assistants or CLI agents.

## What Export Means

`aiplane integrations export ...` prints configuration to stdout. It does not
install an IDE extension, edit your IDE settings, start a server, or create an
account. The intent is to make model/provider selection repeatable and then let
you paste or commit the generated snippet in the target tool's normal config
location.

The exported values come from the selected `aiplane` profile: provider, model
name, endpoint/base URL, and API key environment variable where applicable. Use
`--endpoint` when the model is hosted somewhere other than the provider default,
for example a shared workstation or cloud gateway.

## Plan, Setup, Export

The integration flow has three separate steps:

```bash
aiplane integrations plan continue
aiplane integrations setup continue --dry-run
aiplane integrations export continue
```

- `plan` prints the decision: selected model aliases, provider, runtime, endpoint, supported runtimes, capability scores, role score, and the reason each model was selected. It does not start services, pull models, edit IDE files, or print the final target config.
- `setup --dry-run` uses the plan and prints the runtime/model preparation actions that would be needed, such as starting Ollama/vLLM or pulling a selected model.
- `setup` executes supported helper actions by default; `setup --dry-run` previews them.
- `export` prints the target config snippet to paste into Continue, Cline, Zed, Aider, or a generic OpenAI-compatible client.

### What `integrations plan` Output Means

A Continue plan has three selections because Continue can use separate models for different jobs:

- `selection.chat`: chat, edit, and apply style work.
- `selection.autocomplete`: tab autocomplete.
- `selection.embedding`: embeddings/retrieval.

Single-model tools such as Cline, Zed, Aider, and generic OpenAI-compatible clients use `selection.primary`.

Important fields inside each selected row:

| Field | Meaning |
| --- | --- |
| `name` | The `aiplane` model alias from the profile catalog. |
| `model` | Provider/runtime-native model id, such as `qwen2.5-coder:7b` or `Qwen/Qwen2.5-Coder-32B-Instruct`. |
| `provider` | The configured model source/catalog recorded on the model alias. Some systems, such as Ollama, are both a source and a runtime. |
| `runtime` | Runtime selected for serving, such as `ollama`, `vllm`, or `llamacpp`. |
| `endpoint` | Base URL the IDE/tool should call. Override with `--endpoint` for SSH tunnels, LAN endpoints, or gateways. |
| `supported_runtimes` | Runtimes that can plausibly serve the model. |
| `capability_scores` | Catalog capability hints on the 0-5 scale. These are selection hints, not benchmark percentages. |
| `role_capabilities` | Capabilities considered important for the selected role. |
| `role_score` | Average fit for the requested role or roles. Higher is better within the current catalog data. |
| `reason` | Why the row was selected: profile default, manual override, or best catalog match. |

### Discover Models Before Planning

First inspect the roles a target can use:

```bash
aiplane integrations roles continue
aiplane integrations roles cline
aiplane integrations plan continue --runtime ollama
```

Continue can use separate `chat`, `autocomplete`, and `embedding` selections.
Most other targets currently use one primary chat/code model. MCP targets do not
select inference models; they expose aiplane tools to an MCP-capable client.

Search/filter models explicitly before exporting config:

```bash
aiplane models list --group-by provider
aiplane models list --runtime ollama --role chat --enabled-only --sort-by role --limit 3
aiplane models list --runtime ollama --role autocomplete --enabled-only --sort-by role --limit 3
aiplane models list --runtime ollama --role embedding --enabled-only --sort-by role --limit 3
aiplane models list --runtime ollama --role chat --role autocomplete --role embedding --enabled-only --sort-by role --limit 5
aiplane models list --runtime vllm --capability code_generation>=4 --capability debugging>=3 --enabled-only
aiplane models list --runtime vllm --capability code_generation>=4 --capability tool_use>=3 --vram-gb 96 --sort-by avg --limit 10
aiplane models show qwen-coder-32b
```

The repeated-role form is useful when you want one model that is a good overall
fit for several roles. For Continue, it is often better to query each role
separately and then pass the chosen aliases with `--chat`, `--autocomplete`, and
`--embedding`.

### Mix And Match

Continue supports explicit role-level mix and match:

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

Single-model targets use one primary model:

```bash
aiplane integrations plan cline --model qwen-coder-32b --endpoint http://localhost:8000/v1
aiplane integrations export cline --model qwen-coder-32b --endpoint http://localhost:8000/v1

aiplane integrations plan aider --select-best --runtime vllm --capability code_generation>=4
aiplane integrations export aider --select-best --runtime vllm --capability code_generation>=4
```

Selection flags work with `plan`, `setup`, and `export`. Manual overrides (`--model`, or Continue's `--chat`/`--autocomplete`/`--embedding`) win over best-fit selection.

## VS Code Quick Start

For VS Code, the first concrete path is Continue:

1. Install the Continue extension in VS Code.
2. Use `aiplane` to install/start the runtime and pull the model, for example Ollama:

```bash
aiplane runtimes install ollama --dry-run
aiplane runtimes install ollama
aiplane runtimes start ollama
aiplane runtimes pull ollama --model qwen-tiny
```

3. Generate the Continue config bundle:

```bash
aiplane integrations export continue
```

4. Paste or merge the printed YAML into Continue's config file. On a normal Linux install this is usually `~/.continue/config.yaml`. In VS Code, open Continue from the side bar and use its config/edit-config command if available. The bundle uses profile defaults for chat, autocomplete, and embeddings.

For a larger local model, first check the hardware recommendation and pull it:

```bash
aiplane hardware recommend
aiplane models pull qwen-coder-32b
aiplane integrations export continue --model qwen-coder-32b
```

## Continue / VS Code

Continue is an open-source coding assistant/agent surface that has been
available as a CLI, VS Code extension, and JetBrains plugin. `aiplane` treats
Continue as one export target, not as the strategic foundation for all IDE work.

Generate a Continue config bundle from profile defaults:

```bash
aiplane integrations export continue
```

By default this emits chat, autocomplete, and embedding settings using `chat_model`, `autocomplete_model`, and `embedding_model` from the active profile. To export a single model entry instead, pass `--model <alias>`.

For a shared workstation or cloud-hosted OpenAI-compatible endpoint, override the
endpoint:

```bash
aiplane integrations export continue --endpoint https://llm-workstation.example.com/v1
```

To export one specific model entry for that endpoint:

```bash
aiplane integrations export continue --model qwen-tiny --endpoint https://llm-workstation.example.com/v1
```

The exporter prints YAML shaped for Continue's configuration. Paste that snippet into Continue's YAML config, normally `~/.continue/config.yaml` on this PC. If the file already has a `models:` section, merge generated entries under the existing list instead of creating duplicate top-level keys.

`--model` is a single-model export. It does not accept multiple values. For Continue's multi-role config, use `--chat`, `--autocomplete`, and `--embedding`, or omit all three to use profile defaults.

To avoid repeating selection flags, save the plan and export from it:

```bash
aiplane integrations plan continue \
  --chat openai-gpt-4o-mini \
  --autocomplete qwen-coder-1.5b-base \
  --embedding nomic-embed-text > continue-plan.json

aiplane integrations export continue --from-plan continue-plan.json
```

The provider is set to `openai` because local Ollama and many gateways expose
OpenAI-compatible `/v1` endpoints. For local Ollama, the default endpoint is:

```text
http://localhost:11434/v1
```

A minimal local Ollama entry looks like:

```yaml
models:
  - name: qwen-tiny
    provider: openai
    model: qwen2.5-coder:0.5b
    apiBase: http://localhost:11434/v1
    apiKey: ollama
```

Before using it, make sure Ollama is running and the model is pulled. You can do that through `aiplane` for the common path:

```bash
aiplane runtimes start ollama
aiplane runtimes pull ollama --model qwen-tiny
```

The equivalent native commands are:

```bash
ollama serve
ollama pull qwen2.5-coder:0.5b
```

## Managed Provider Exports

Managed providers use the same profile alias flow as local runtimes. The difference is that the endpoint and API key usually point to a hosted service instead of `localhost`.

Managed-provider exports prefer `api_key_env` from the model/provider entry or from a named local credential reference. Raw keys from `.aiplane/credentials.yaml` are not printed into IDE config.

For OpenAI-style managed endpoints:

```bash
export OPENAI_API_KEY=...
aiplane integrations plan continue \
  --chat openai-gpt-4o-mini \
  --autocomplete qwen-coder-1.5b-base \
  --embedding nomic-embed-text
aiplane integrations export continue \
  --chat openai-gpt-4o-mini \
  --autocomplete qwen-coder-1.5b-base \
  --embedding nomic-embed-text
```

For Azure OpenAI, configure `providers.azure_openai.endpoint` in `models.yaml` or pass an endpoint at export time. The model alias should use the Azure deployment name:

```bash
export AZURE_OPENAI_API_KEY=...
aiplane providers models azure_openai --online --limit 20
aiplane integrations export openai-compatible --model azure-openai-chat-deployment --endpoint https://YOUR-RESOURCE.openai.azure.com
```

For Anthropic, keep the alias in `models.yaml` for planning and catalog visibility. Dedicated target-tool exporters are intentionally conservative; use the target tool's native Anthropic provider settings when it supports them, or keep using local/OpenAI-compatible exports where that is the supported shape.

Continue can mix local and managed roles. For example, use OpenAI for chat, local Ollama for autocomplete, and local Ollama embeddings by passing role overrides to `integrations plan/export continue`.

## MCP Tools

Use MCP when an IDE or agent needs to inspect `aiplane` configuration as tools: list models, discover hardware, get recommendations, export integration snippets, or render SSH tunnel plans.

Start the server with:

```bash
aiplane mcp serve
```

For client-specific MCP config examples, see [MCP Adapter](mcp.md). MCP is separate from model endpoint export: endpoint export tells an IDE where to send model inference requests, while MCP lets an IDE/agent ask `aiplane` about configuration and plans.

## OpenAI-Compatible Runtime Use

The same endpoint pattern works for local or remote vLLM, LM Studio, llama.cpp server, Ollama `/v1`, and API gateways that expose OpenAI-compatible chat completions. Configure the provider endpoint in the profile or override it during export:

```bash
aiplane integrations export continue --model qwen-coder-32b-vllm --endpoint http://localhost:8000/v1
```

For a remote/shared endpoint, use the tunnel or gateway URL as the endpoint. The IDE sends inference requests to that URL; MCP is separate and is used for querying `aiplane` configuration and plans.

For SSH tunnel targets, the IDE endpoint is local even though the model runs remotely:

```bash
aiplane remote tunnel plan --target gpu_workstation_ssh
aiplane remote tunnel start --target gpu_workstation_ssh
aiplane integrations export continue --endpoint http://localhost:11434/v1
```

In the tunnel plan, `local_bind` is the address opened on your laptop,
`remote_service` is what the remote SSH host can reach, and `ide_endpoint` is
what Continue/Cline/Aider should use. This is normal SSH `-L` local forwarding;
it does not require a reverse tunnel unless the network path only works in the
opposite direction.

## Other Plan And Export Targets

Continue is the first VS Code path, but the plan/export surface is broader:

```bash
aiplane integrations list

aiplane integrations plan cline --model qwen-coder-32b --endpoint http://localhost:8000/v1
aiplane integrations export cline --model qwen-coder-32b --endpoint http://localhost:8000/v1

aiplane integrations plan zed --select-best --runtime ollama
aiplane integrations export zed --select-best --runtime ollama

aiplane integrations plan aider --runtime vllm --capability code_generation>=4
aiplane integrations export aider --runtime vllm --capability code_generation>=4

aiplane integrations export openai-compatible --model qwen-coder-32b --endpoint http://localhost:8000/v1
aiplane integrations export vscode-mcp
aiplane integrations export continue-mcp
```

- `cline` prints an OpenAI-compatible provider/model payload that can be mapped into Cline-style provider settings.
- `zed` prints a Zed assistant/provider-shaped payload. Treat it as a starting point because Zed settings can vary by version.
- `aider` prints shell environment variables plus an `aider --model openai/...` command.
- `openai-compatible` prints a neutral JSON payload with `base_url`, `model`, and `api_key_env` for tools without a dedicated exporter yet.
- `vscode-mcp`, `continue-mcp`, `cline-mcp`, and `generic-mcp` print MCP client config snippets that launch `aiplane mcp serve`. These are for querying `aiplane`; they are not model endpoint configs and do not select an inference model.

`setup` is available for Continue and single-model endpoint tools (`cline`, `zed`, `aider`, and `openai-compatible`). It prepares the selected runtime/model where helpers exist, but it still does not edit the target tool's configuration file.

## Agent Applications

An agent application is the code that owns the prompt, state, tools, and model-call loop. `aiplane` does not become that agent; it selects and documents the endpoint/model the agent code should call, then prints a starter scaffold you can review.

List starter templates:

```bash
aiplane agents templates
```

Plan a small LangGraph agent against a configured model alias:

```bash
aiplane agents plan repo-helper --framework langgraph --model qwen-tiny
```

Print one scaffold file at a time:

```bash
aiplane agents export repo-helper --framework langgraph --model qwen-tiny --file agent.py
aiplane agents export repo-helper --framework langgraph --model qwen-tiny --file requirements.txt
aiplane agents export repo-helper --framework langgraph --model qwen-tiny --file .env.example
aiplane agents export repo-helper --framework langgraph --model qwen-tiny --file README.md
```

The generated `agent.py` is intentionally small: it reads `OPENAI_BASE_URL`, `AIPLANE_MODEL`, and an API-key env var, then calls the selected endpoint. For local Ollama, the endpoint is usually `http://localhost:11434/v1` and a dummy API key is often accepted. For managed providers, set the configured API-key env var first.

Agent artifact paths are intentionally separate from profiles. Use `--output-dir`, `AIPLANE_AGENT_ARTIFACTS_DIR`, or local config `agent_artifacts_dir` to choose where generated agent projects should live. The default is `.aiplane/agents`, which is ignored by git.

This is the step after environment preparation: once `environment doctor`, runtime setup, model aliases, and endpoint exports are understood, the agent application is the actual Python code that uses those settings to perform a task.

## CLI Chat Wrapper

For local Ollama models, `aiplane` can resolve the model alias and delegate to
Ollama's native chat CLI:

```bash
aiplane chat --dry-run
aiplane chat
```

The actual command is based on the active profile's `chat_model` default, for example:

```bash
ollama run llama3.1:8b
```

## Local and Remote Endpoint Pattern

A local IDE/CLI can connect to:

- a local laptop endpoint, such as `http://localhost:11434/v1`;
- a shared workstation endpoint, such as `https://llm-workstation.example.com/v1`;
- a cloud-hosted self-managed endpoint, such as vLLM/Ollama behind a gateway.

The local code does not have to be uploaded wholesale when the IDE/tool sends
selected context to the endpoint. Remote workspace and remote job-runner patterns
are separate deployment modes and should be explicit in target/profile config.

## Cursor

Cursor remains a target, but we should verify the supported custom-provider or
MCP-style integration surface before writing a deep adapter. The first practical
step is to export generic OpenAI-compatible endpoint details that can be reused
where Cursor or related tools support them.

## Other IDE and Agent Targets

Continue is not the only possible interface. It is just the first one because it
has a simple config-file path and works well with OpenAI-compatible endpoints.

Currently implemented additional exporters:

- **Cline**: OpenAI-compatible provider/model payload.
- **Zed**: assistant/provider-shaped payload for OpenAI-compatible endpoints.
- **Aider**: CLI environment variables and launch command.

Useful next targets:
- **Cursor and Windsurf-style IDEs**: useful if their custom-provider or MCP
  surfaces let us inject endpoints cleanly without maintaining brittle settings.
- **JetBrains**: likely through either Continue/Cline-style plugins or generic
  provider settings after the VS Code path is stable.

Deprioritized or watch-list targets:

- **Roo Code**: its docs currently say the extension was shut down on May 15,
  2026. Treat it as historical unless a maintained fork or successor is chosen.
- **One-off marketplace plugins** that do not support OpenAI-compatible
  endpoints, MCP, or external config. These are expensive to support and easy to
  break.

## Other Agent Tools

Tools such as OpenClaw/OpenClawd-style assistants, Claude Code, Codex CLI,
Cursor, Cline, Aider, and OpenHands sit above `aiplane`. They provide the
interactive agent experience. `aiplane` should provide the boring but important
parts around them: selected model, endpoint, API key environment variable, local
or remote target, hardware assumptions, and policy checks.
