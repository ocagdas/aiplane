# Practical Overview

`aiplane` is an environment-doctor and configuration compiler for self-managed AI development environments. It helps you describe, inspect, prepare, and connect local or remote model runtimes across laptops, shared GPU workstations, Docker hosts, cloud VMs, and cluster targets.

It is not a coding agent, chat UI, model marketplace, or production AI gateway. Those tools sit above or beside it. `aiplane` focuses on the operational layer that makes self-managed model environments reproducible and connectable.

`aiplane` is specifically aimed at the AI setup layer that people often call “AI Ops”: making environment setup, migration, and model/runtime matching repeatable so teams can focus on research, experimentation, and shipping AI features.
The nearest analogy is not exactly Terraform, Vagrant, or a dev-container tool. Terraform provisions infrastructure, Vagrant/dev-env tools create general development machines, and Docker Compose runs containers. `aiplane` is narrower: it understands AI-specific concerns such as model catalogs, runtime compatibility, hardware/VRAM fit, provider endpoints, IDE model roles, and model setup checks.

## Core onboarding flow

For a first successful run, use this command sequence:

```bash
aiplane discover
aiplane doctor
aiplane recommend
aiplane export continue
```

Or use the single command path:

```bash
aiplane quickstart local-coding
```

These are the public-first, inspect-first commands for onboarding before advanced stack/workflow features.

## What It Can Do Now

- Create and use profiles that hold provider/source, model, runtime, endpoint, hardware, machine, stack, target, and environment settings.
- Manage the environment used by `aiplane` itself: system Python, `venv`, Conda, Docker CLI images, and profile-level Docker execution mode.
- Drive runtime helper operations from the main CLI, including installing, configuring, starting, stopping, checking, and pulling models where a helper is available.
- Work with Ollama through `aiplane runtimes install/start/stop/pull/list-runtime-models ...` instead of requiring direct `ollama` commands for the common path.
- List model providers and show which profile catalog entries come from each source.
- Maintain profile-owned model entries in `models.yaml` and discovery refresh/import entries in `models.discovered.yaml`, with task capability scores, hardware fit metadata, source/runtime mappings, and preferred runtimes.
- Discover local hardware and compare it with configured hardware templates.
- Recommend models by capability, model provider, runtime compatibility, ownership, RAM, and VRAM constraints, with versioned source, sample-count, and uncertainty provenance in JSON output.
- Export IDE/CLI model endpoint snippets for Continue, Cline, Zed, Aider, and generic OpenAI-compatible clients.
- Export MCP client config snippets for VS Code MCP clients, Continue, Cline-style MCP clients, and generic `mcpServers` clients.
- Serve an MCP adapter so tools can query `aiplane` for profiles, providers, models, recommendations, hardware, integrations, and guarded profile changes.
- Render SSH tunnel plans and guarded start/stop commands for remote self-managed endpoints.
- Render checksummed runtime bundles using only the Docker, Conda, or native handoff modes each of the six primary runners actually supports, without building, starting, or applying them.
- Render schema-linked Azure VM/AKS, remote-host, local-VM, and Dev Container starter artifact families without applying infrastructure.

## Common Terms

- **Profile**: The editable YAML source of truth for an intended setup. It records reviewed model aliases, runtimes, endpoints, hardware expectations, tool roles, and policy; machine-local secrets and runtime data stay outside it.
- **Profile render**: `aiplane profiles render PROFILE` assembles one consistently ordered JSON snapshot from the nine canonical profile YAML files. It is comparison, validation, CI, and archival evidence—not restorable source YAML or target-tool configuration.
- **Profile archive**: `aiplane profiles archive PROFILE --output PATH` validates and packages reviewed profile YAML with SHA-256 checksums and an explicit exclusion manifest. It rejects raw credential material and excludes generated or runtime-owned state.
- **Replay**: Preview and restore a portable archive into a new profile with `aiplane profiles restore ARCHIVE --as PROFILE --yes`, validate it, inspect the destination, and compile fresh integration configuration there. Existing profiles are never overwritten.
- **Profile comparison**: `aiplane profiles compare LEFT RIGHT` classifies canonical portable evidence as exact, capability-equivalent, materially incompatible, or unresolved; archive operands are explicit with `--left-source archive` or `--right-source archive`.
- **Machine drift**: `aiplane profiles drift PROFILE` compares explicit active hardware evidence with live discovery and explains selected-model fit using provenance-aware facts. It is read-only; `--source archive` assesses an archive directly.
- **Multi-client replay proof**: `aiplane profiles replay-check APPROVED --source archive --client-archive A --client-archive B` verifies at least two independently returned replay archives in one deterministic, read-only result.
- **Provider / Model Source / Catalog**: Where model identifiers or weights come from, such as the Ollama library, Hugging Face Hub, GGUF files, Azure Speech voices, or a local file path.
- **Runtime**: The software that loads model weights and serves inference, such as Ollama, vLLM, llama.cpp server, TGI, Transformers, LocalAI, faster-whisper, Diffusers, or ComfyUI.
- **Runtime Endpoint**: A configured service URL exposed by a runtime, such as local Ollama, vLLM on a shared workstation, or llama.cpp behind an SSH tunnel.
- **Model**: A profile-owned entry that maps to a source-native model id, hardware requirements, task capability scores, model provider, and supported runtimes.
- **Endpoint**: The URL an IDE/CLI uses for inference. For OpenAI-compatible local Ollama this is usually `http://localhost:11434/v1`.
- **Machine**: A hardware/OS profile for a local PC, shared workstation, VM, or cluster node. A machine can be discovered live or imported from a captured schema.
- **Stack**: A pairing of machine, runtime, model, and deployment/access settings. It answers questions like “run this model with vLLM on that GPU machine”.
- **Target**: A deployment or access target such as an Azure VM plan, AKS plan, Docker host, or SSH tunnel target.
- **Integration Export**: Configuration text compiled from the selected profile into another tool's syntax. It prints to stdout; it does not install the tool, modify its settings, start runtimes, or copy credentials.
- **MCP Adapter**: A stdio server that lets IDEs/agents query `aiplane` as structured tools. It is separate from the model inference endpoint.
- **Doctor**: A readiness check. It explains whether required tools, endpoints, credentials, or runtimes look usable.
- **Benchmark**: A small smoke test for a model/runtime/profile combination. Current scores are practical smoke indicators, not formal benchmark claims.
- **Self-managed**: You manage the runtime and machine, whether it is on a laptop, workstation, VM, Docker host, or cluster.
- **Managed service**: A third-party/cloud API owns model hosting, scaling, and the runtime, such as OpenAI or Azure OpenAI.

## Ollama From `aiplane`

A local Ollama setup can be driven from `aiplane`:

```bash
aiplane runtimes install ollama --dry-run
aiplane runtimes install ollama
aiplane runtimes start ollama
aiplane runtimes pull ollama --model MODEL_ALIAS
aiplane runtimes list-runtime-models ollama
aiplane runtimes status ollama
```

Use `--dry-run` first when you want to see the delegated helper/native commands before changing the machine.

## What It Does Not Do Yet

- It does not publish a native VS Code extension. The first VS Code path is exporting configuration for Continue and MCP-capable clients.
- It does not replace Continue, Cline, Aider, Cursor, Copilot, Codex CLI, or other agent tools.
- It does not run arbitrary shell commands through MCP.
- Runtime bundle plans do not automatically build Docker images, create Conda environments, or deploy cloud infrastructure; they are rendered plans for review. The setup helper can build Docker images for the `aiplane` CLI itself.
- It does not provide production authentication, quota, cost control, rollback, or secret management for every deployment path yet.

## First Useful Flows

```bash
# See the selected profile and providers.
aiplane profiles list
aiplane providers list

# Install/start/pull a tiny local Ollama model.
aiplane runtimes install ollama --dry-run
aiplane runtimes start ollama
aiplane runtimes pull ollama --model MODEL_ALIAS

# Export a Continue config snippet for VS Code.
aiplane integrations export continue

# Export an MCP client config snippet.
aiplane integrations export vscode-mcp

# Render a deterministic runtime bundle recipe.
aiplane runtimes bundle vllm --model MODEL_ALIAS --mode docker --format dockerfile
```

## Complete Recipes

For end-to-end command sequences and combinations, see [Practical Workflows](workflows.md).


## AI Workflow Stack Doctor

"Doctor" means a read-only readiness diagnosis, not an automated repair: it compares the profile, local capabilities, runtimes, endpoints, models, and tool requirements and explains what is ready or missing. The JSON form follows the versioned [doctor output contract](doctor-contract.md): every finding identifies its severity, reason, impact, affected resource, exact remediation, mutation status, and dry-run support. Exit codes are 0 for healthy, 1 for advisory-only, and 2 for blocking.


Start with `aiplane quickstart local-coding` when evaluating a laptop, workstation, or hybrid AI workflow profile. It creates or previews the editable local profile through the same bootstrap path, runs the AI workflow doctor when the profile exists, and reports one exact next action based on current readiness. Use `aiplane doctor` when you only want to inspect an already configured profile. It aggregates the environment-doctor checks that matter for AI workflow readiness: profile files, required environment tools, runtime prerequisites, model defaults with provider/endpoint details, selected role-default endpoint readiness, active hardware and role-model fit, provider state, Continue/Aider role capability readiness, and MCP manifest and local AI read-surface readiness. The doctor itself is read-only. The quickstart preserves existing profile files, skips provider network discovery by default, and reports one exact next action. With no configured model it offers at most two no-YAML setup paths and a dry-run runtime plan. Use `--discovery` to contact configured catalogs; model pulls remain opt-in with `--pull-model`. It does not edit IDE config or mutate cloud resources.

```bash
aiplane quickstart local-coding
aiplane quickstart local-coding --dry-run
aiplane quickstart local-coding --pull-model MODEL_ALIAS
aiplane quickstart local-coding --discovery
aiplane doctor
aiplane doctor --format json
aiplane doctor --include-optional
```
