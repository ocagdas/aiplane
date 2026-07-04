# Integrations Roadmap

See also: [Strategy](strategy.md) and [Project Roadmap](roadmap.md).

The platform is being built as an orchestration/governance/setup control plane first. Integrations should attach
to the same profile, provider, model, runtime, endpoint, policy, tool, approval, and audit layers
instead of each integration inventing its own configuration.

## Target Direction

Prioritize **VS Code + Continue** first because it has the simplest config export
path, but keep the integration layer generic. Add Cline, Zed, Aider, Cursor, and
JetBrains paths where they can consume OpenAI-compatible endpoints, MCP config,
or a small launch wrapper. Avoid spending too much effort on a custom always-on
chat UI before the provider/session contracts are stable.

## Recommended Order and Status

1. **Configuration exporters for existing tools - Implemented / ongoing**
   - Implemented: Continue, Cline, Zed, Aider, generic OpenAI-compatible endpoint exports.
   - Implemented: VS Code MCP, Continue MCP, Cline-style MCP, and generic MCP config exports.
   - Ongoing: validate more client-specific config shapes as tools evolve.

2. **CLI wrapper commands - Partially implemented**
   - Implemented: `aiplane chat`, which resolves a chat-capable profile alias and uses configured endpoints by default; `--native-ollama` delegates Ollama-runnable aliases to `ollama run <model>`.
   - Planned: broader launch wrappers around stable tool-native CLIs such as `ollama launch`, Continue CLI, Codex-style tools, or Claude Code where support is explicit.

3. **Thin `aiplane session` layer - Planned**
   - Not implemented yet.
   - Keep this minimal at first: session metadata, selected model, transcript path, and audit events.
   - Do not build a full Copilot/Codex clone.
   - Prefer delegating interactive chat to mature provider or IDE tools when they exist.

4. **Patch proposal workflow - Planned**
   - Not implemented as a general workflow yet.
   - Intended behavior: generate diffs, validate/show patches, and apply only with approval.

5. **Local HTTP/API adapter - Planned**
   - Not implemented yet.
   - The MCP stdio server is implemented and should remain the first structured tool surface.
   - A local HTTP service should only be added if multiple clients need it.

6. **Agent-to-agent setup and export - Partial / next hardening focus**
   - Implemented today: orchestrator catalog/readiness, package/setup scaffolding, stack binding to an optional orchestrator, and starter agent exports.
   - Next target shape: describe agent roles, model aliases, managed or self-managed endpoints, tool policies, approval modes, limits, and audit labels in profile/stack/orchestrator metadata.
   - Export starter configuration for established orchestrator frameworks instead of running autonomous agent conversations inside `aiplane`.
   - Managed-service models are valid endpoint choices for this layer when the orchestrator can call them directly; they should not be treated as local runtime candidates.

## Integration Matrix

`aiplane` should integrate with mature tools at the lowest useful level. It
should generate config, run readiness checks, call official CLIs, and export
starter artifacts. It should not reimplement IDE agents, infrastructure
provisioners, model runtimes, or configuration-management engines.

| Tool / family | Planned use in `aiplane` | Integration level | Status |
| --- | --- | --- | --- |
| Continue | First VS Code coding assistant path; consume local or remote OpenAI-compatible endpoints and optional MCP tools. | Config export, setup plan, MCP config export. | Implemented / hardening. |
| VS Code MCP clients | Let IDEs query `aiplane` for models, hardware, recommendations, integration snippets, and guarded profile changes. | MCP stdio server plus client config export. | Implemented / hardening. |
| Cline / Roo-style clients | Alternative VS Code agent surfaces that can use endpoints and MCP tools. | Config export and MCP config export; wrappers only after stable CLI/API review. | Export implemented; wrappers planned. |
| Zed | Editor path for OpenAI-compatible endpoints and MCP-capable workflows. | Config export first. | Implemented / needs end-to-end validation. |
| Aider | CLI pair-programming path against selected model endpoints. | Config/export first; launch wrapper later if useful. | Export implemented; wrapper planned. |
| Cursor / Windsurf | Commercial IDE paths where custom endpoint or MCP support is available. | Research, config export where supported, no brittle plugin assumptions. | Research/planned. |
| Codex CLI / Claude Code / Copilot-style tools | Existing agentic CLI or IDE tools. | Possible launch wrappers and environment/config handoff only. | Planned/research. |
| Ollama | Local/self-managed runtime and optional native CLI chat. | Install/update/start/stop/status/pull helpers; endpoint-backed `aiplane chat` by default, with `--native-ollama` delegating to `ollama run`. | Implemented for core flow. |
| vLLM / llama.cpp / TGI / LocalAI / LM Studio | Self-managed model serving runtimes. | Runtime catalog, setup helpers where practical, endpoint export, stack lifecycle planning. | Partial/ongoing. |
| LangGraph / CrewAI / AutoGen / OpenHands / Semantic Kernel / LlamaIndex Workflows | Agent/workflow orchestration frameworks on top of model endpoints, including future agent-to-agent role graphs. | Catalog/readiness metadata now; stack binding and package/export support; planned multi-agent role metadata; no custom agent runner yet. | Partial/ongoing. |
| Docker / Compose | Reproducible local or VM-hosted runtime stacks. | Tool doctor/install hints, stack artifact export, future Docker-aware lifecycle execution. | Partial/ongoing. |
| Azure CLI | Account, quota, SKU, VM/AKS discovery, and guarded Azure operations. | Tool doctor/install helper, CLI wrapper, profile-driven planning/apply for narrow VM flows. | Partial/ongoing. |
| OpenTofu / Terraform | Repeatable VM/AKS infrastructure provisioning without reinventing IaC. | Generate variables/modules or starter plans, call official CLI, keep apply guarded. | Planned. |
| kubectl / Helm | AKS/Kubernetes runtime deployment and inspection. | Tool doctor/install helper, generated manifests/charts or value files, guarded apply later. | Planned. |
| SSH / OpenSSH | Remote workstation/VM access and local endpoint tunnels. | Tunnel plan/start/status/stop and stack access policy. | Implemented / hardening. |
| Ansible | Optional host configuration over SSH when shell scripts become too fragile. | Tool doctor/install helper and generated playbook hooks only if needed. | Research/planned. |

## Candidate IDEs and Tools

Initial candidates:

- **VS Code**: highest priority. It is the broadest target and Ollama documents
  VS Code under its launchable integrations.
- **Continue**: first concrete IDE integration target. Continue provides a VS
  Code extension, CLI, and JetBrains plugin, and its docs identify it as an
  open-source coding agent. We should generate Continue config from our provider
  catalog rather than asking users to hand-copy model settings.
- **Cline**: strong candidate after Continue. It has VS Code, terminal, JetBrains,
  MCP, and broad editor positioning, so it fits both endpoint export and MCP
  configuration.
- **Cursor**: target after Continue. Cursor is worth supporting, but the first
  path should be config/export or MCP-style integration rather than assuming it
  can use every local provider directly. We should verify the supported custom
  model/provider surface before writing a deep adapter.
- **JetBrains IDEs**: secondary target after the config/session contracts are
  stable. Continue has a JetBrains plugin path, but Continue itself recommends
  its CLI over the JetBrains plugin.
- **Zed**: useful local-model-friendly editor path with provider, gateway, local
  model, and MCP surfaces.
- **Aider**: CLI-first pair-programming target. Useful because it can consume
  Ollama and OpenAI-compatible endpoints.
- **Roo Code**: watch-list only unless a maintained successor is selected; its
  docs currently say the extension was shut down on May 15, 2026.
- **Codex CLI-like interface**: prefer wrapper/delegation first, not a large
  custom chat implementation.

## CLI Session Strategy - Mostly Planned

A full custom active chat/session UI is medium effort and easy to overbuild. The
better first implementation is a thin command layer. Current status:

```bash
# Implemented: endpoint-backed chat for configured chat-capable aliases.
aiplane chat --prompt "Say hello"

# Implemented: optional Ollama-native chat for configured Ollama-runnable aliases.
aiplane chat --native-ollama

# Planned / not implemented yet:
aiplane launch --tool continue --model MODEL_ALIAS
aiplane launch --tool codex --model MODEL_ALIAS
aiplane session start --model MODEL_ALIAS
```

Future wrappers should:

- Resolve model aliases from `models.yaml`.
- Check provider readiness with `doctor` before launch.
- Export the needed environment variables or config snippets.
- Start the provider-native CLI/tool when available.
- Record audit/session metadata locally.

## Ollama CLI Chat and Launch

Ollama provides a native CLI chat flow:

```bash
ollama run text-generation:0.5b
```

It also has `ollama launch`, which can configure and launch supported external
applications. Ollama docs list supported launch integrations including OpenCode,
Claude Code, Codex, VS Code, and Droid. That makes Ollama a good first provider
for wrapper commands because `aiplane` can select the configured model and then
delegate the interactive UX to Ollama.

## Decision and Current Status

Start with:

1. Continue config generation for VS Code. - **Implemented**
2. `aiplane chat` endpoint-backed smoke chat, plus `--native-ollama` for `ollama run`. - **Implemented for configured chat-capable aliases; native Ollama path is opt-in**
3. `aiplane launch` wrapper for `ollama launch` where supported. - **Planned, not implemented**
4. Cline/Zed/Aider exporter or wrapper research against their documented endpoint/MCP/config surfaces. - **Exporters implemented; wrappers still planned/research**
5. Minimal session metadata/audit around those launches. - **Planned, not implemented**
6. Agent-to-agent role metadata and orchestrator config export for established frameworks. - **Partial scaffolding implemented; multi-role schema/export planned next**
7. Cursor research/config-export path after the generic endpoint/MCP exporters are stable. - **Research/planned**

Do **not** start by building a heavy custom chat UI. Use existing CLI/IDE tools
where they are good, and let `aiplane` own configuration, provider selection,
policy, setup, readiness, and audit.

## Non-Goals for the First Integration Milestone

- No direct file mutation by models without patch review.
- No IDE-specific hidden policy bypass.
- No separate provider/model configuration inside each IDE adapter.
- No direct autonomous agent-to-agent execution inside `aiplane`; use established orchestrator frameworks and export/review their config.
- No cloud escalation until policy, secret scanning, and audit behavior are
  explicit for that profile.
