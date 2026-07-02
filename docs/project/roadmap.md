# Project Roadmap

This document is the developer-facing status map. It separates what is implemented from what is in progress, planned, or deferred. For product boundary and architecture direction, see [Strategy](strategy.md).

## Status Labels

- **Implemented**: available in the current CLI, scripts, docs, or tests.
- **In progress**: partially implemented; useful pieces exist, but the area is not complete.
- **Planned**: intended direction, but not implemented yet.
- **Research**: worth investigating before committing to a design.
- **Deferred**: intentionally not a near-term priority.

## Current Milestone: Early Beta Release Hardening

Goal: make the repository coherent and useful for early open-source users after the history cleanup.

Required outcomes:

1. Keep code, docs, command coverage, roadmap, handoff, implemented behavior, and tests aligned to a high open-source quality bar.
2. Keep README and user docs focused on current commands and explicit caveats.
3. Preserve the product boundary: `aiplane` is a control-plane CLI, not an agent, runtime, proxy, or hidden cloud deployment engine.
4. Keep local/private direction notes in ignored local files only.
5. Run full tests, profile validation, setup doctor, and representative smoke commands before calling the branch release-ready.

## Implemented

- Profile loading, validation, templates, selected/default profile handling, ignored local config, and external profile directory support.
- Ignored local credential references with redacted credential inspection commands and provider connection tests for selected managed endpoints.
- Environment planning and doctor checks for system Python, `venv`, Conda, and Docker execution mode; setup helpers install the CLI and bootstrap ignored `profiles/local-dev` from the shipped template before profile-aware checks.
- External tool catalog, doctors, guarded install previews, non-mutating plans, and starter exports for Azure CLI, OpenTofu/Terraform, Pulumi, Vagrant, Packer, Docker/Compose, Dev Container CLI, kubectl, Helm, OpenSSH, Ansible, and benchmark helpers.
- Provider/model catalog foundations for Ollama, Ollama Cloud placeholder, OpenAI-compatible runtimes, OpenAI, Anthropic, Azure OpenAI, ElevenLabs TTS, Hugging Face, NVIDIA Hugging Face-scoped open model repos, GGUF/local files, and user-defined discovery providers. Shipped profile templates keep `models.yaml` structural, runtime/provider endpoint values live as conventional built-in defaults with local override support, and model grouping separates managed-service providers from self-managed runtime sources while preserving managed endpoint metadata for exports, stacks, and orchestrator plans.
- Ignored discovered provider/model cache flow plus `profiles bootstrap-local`, `models add`, `models clone`, and `models promote` as reviewed paths into editable local profile YAML; `models clear-cache` clears discovered entries and profile-owned review entries by default so discovery can be repopulated from providers.
- Runtime/source mapping for Ollama, Hugging Face, NVIDIA Hugging Face-style repos, GGUF/local files, vLLM, TGI, Transformers, llama.cpp, LocalAI, LM Studio, and selected media runtimes.
- Runtime helper delegation through `aiplane runtimes ...` where supported by `scripts/provider_helper.sh`, including Ollama native and Docker substrate paths plus vLLM/TGI-style runtimes.
- Hardware discovery, active hardware selection, machine schema/templates, model-fit checks, and hardware-aware recommendations.
- Machine inventory commands for import/list/show/validate/recommend, Azure SKU discovery/import, cache list/clear, Azure status, and remote profiling plans.
- Stack commands for setup/list/show/plan/doctor/status/export plus same-host lifecycle commands `prepare/start/stop/restart`.
- Stack preflight checks for runtime prerequisites, local port availability, endpoint auth policy, and cache-path hints.
- Azure target planning and doctor checks for AKS and VM targets, plus a narrow guarded Azure VM apply path.
- Orchestrator catalog commands for LangGraph, CrewAI, AutoGen, OpenHands, Semantic Kernel, and LlamaIndex Workflows.
- Agent application templates with non-mutating `agents templates/plan/export` commands.
- Stack artifact exports for Continue, OpenAI-compatible endpoint config, Dockerfile, Conda YAML, and starter Docker Compose.
- SSH tunnel plan/start/status/stop for configured remote model endpoints.
- Model list/show/defaults/use/add/clone/remove/enable/disable/refresh/promote/clear-cache/pull/test/benchmark commands.
- Benchmark framework list/doctor/install/plan helpers for smoke/custom checks, lm-evaluation-harness, vLLM serving benchmarks, and Locust-style load tests.
- `aiplane run` for single-prompt routing through configured model defaults with dry-run and policy-gated non-local escalation.
- Integration plan/setup/export for Continue, Cline, Zed, Aider, generic OpenAI-compatible clients, and MCP client snippets.
- MCP stdio server with read tools and narrow guarded writes for model defaults, hardware selection, runtime preference, model refresh, and SSH tunnel lifecycle.
- Policy checks, approval handling, secret redaction, JSONL audit foundations, and shared JSON output ordering.

## In Progress

- Provider discovery: Ollama, Hugging Face, NVIDIA Hugging Face-scoped repos, Hugging Face GGUF, OpenAI-compatible `/v1/models`, Azure OpenAI deployment paths, structural shipped profile templates, profile-local provider default refresh with enabled-flag preservation, ignored user provider overrides, and discovery-derived AI media roles exist; richer managed-provider and specialist media catalog discovery needs hardening.
- Runtime and stack lifecycle: same-host/local helpers exist; remote execution, endpoint authentication, GPU mapping, service management, and production tuning remain early.
- Tool integrations: doctors, install previews, plans, and starter exports exist; provider-specific modules/playbooks/templates remain planned.
- Azure deployment: planning, doctor checks, and narrow VM apply exist; broader AKS/cloud apply needs hardening before expansion.
- MCP governance: read tools and audited narrow writes exist; broader write tools require explicit risk controls.
- Benchmarking: smoke/custom tasks and framework planning exist; repeated runs, token metrics, comparison views, and sandboxed grading remain planned.
- IDE/CLI integration: config export exists; deeper Cursor, JetBrains, Windsurf, Copilot, Codex, and Claude Code integration remains research/planned.

## Planned Milestones

### Demo / PR Merge Readiness

1. **Manual demo validation** - Current
   - Rehearse the disposable-profile demo path from clean setup through provider discovery, filtered model selection, Continue export, MCP export, stack dry-runs, and Azure discovery.
   - Keep all demo commands inspect-first: use doctors, dry-runs, discovered entries, and exports before mutation.
   - Verify terminal output is concise enough for recording and does not show secrets, raw account identifiers, tenant IDs, subscription IDs, or private local notes.
   - Confirm the prepared media clip/audio is generated outside the tracked repo and can be played at the end of the recording.

2. **Release hygiene and CI gate** - Current
   - Keep `scripts/format.sh check`, `python -m ruff check src tests`, and the pytest suite passing in separate CI jobs.
   - Keep README, user docs, command coverage, roadmap, handoff notes, MCP coverage, planned/implemented agent skills, and tests aligned during pre-PR cleanup and recurring MCP/skills synchronization checkpoints.
   - Keep ignored/generated state out of git, especially credentials, discovered model caches, local strategy notes, logs, PID files, and demo artifacts.
   - Treat secret scans and GitHub history cleanup verification as merge blockers.

### Next Hardening

3. **Provider discovery and model import** - In progress
   - Harden Azure OpenAI deployment discovery and provider-specific live credential tests.
   - Add Anthropic/OpenAI discovery fallbacks where APIs or maintained catalogs allow it.
   - Keep shipped `models.yaml` templates structural; profile-owned model entries and defaults should come from ignored discovery caches, direct local add/clone, or deliberate local promotion.
   - Keep `models promote` as the reviewed flow from discovered provider entry to editable local profile model; use `models add` when the real provider model id is already known but still present in discovery, and `models clone` when one real model needs multiple local purposes.
   - Make refresh/promote/add/clone output explain the safe next step from dry-run discovery to discovered entries to traceable profile-owned model entries.

4. **Tool/task matrix and setup doctor expansion** - In progress
   - Keep `environment doctor` as the default human setup check with text output.
   - Keep every external tool mapped to the workflows it enables, whether it is mandatory or optional, and whether `aiplane` can attempt installation.
   - Grow doctor scope as new tool families are integrated without turning optional workflows into mandatory prerequisites.
   - Keep workflow-level readiness summaries in `tools matrix` useful for release review and demos.

5. **Stack lifecycle and endpoint hardening** - Planned
   - Improve same-host lifecycle result reporting and status verification after prepare/start.
   - Add Docker-aware stack lifecycle paths after same-host helper execution is stable.
   - Let stacks bind managed-service model endpoints where the runtime field represents a hosted protocol or endpoint contract, while keeping those entries out of self-managed runtime fit checks.
   - Add first-class plans for reverse proxy or gateway auth in front of public/shared model endpoints.
   - Keep remote execution boundaries explicit for SSH/Azure/AKS stacks.

6. **Cloud, VM, and workstation workflow hardening** - In progress
   - Use OpenTofu as the default provider-agnostic IaC target, Terraform as a compatible alternative, and Pulumi as an optional language-native IaC path.
   - Harden Vagrant, Packer, Ansible, Dev Container, and IaC starter exports into provider-specific workflows.
   - Keep local install, local VM provisioning, remote VM provisioning, remote PC setup, and cloud provisioning distinct.
   - Keep public demo paths focused on repeatable local, endpoint, MCP, stack, and Azure discovery workflows without unsafe mutation.

### Later Expansion

7. **Runtime packaging and deployment reproducibility** - Planned
   - Broaden tests for stack export content across runtime/orchestrator combinations.
   - Add cache mounts, richer GPU flags, environment variables, and auth notes.
   - Keep image builds, registry pushes, VM creation, and cloud apply explicit and previewable.

8. **IDE, MCP, and agent-tool integrations** - Planned
   - Maintain Continue, Cline, Zed, Aider, generic OpenAI-compatible, and MCP config exports as config-level integrations.
   - Keep model endpoint export separate from MCP tool export.
   - Add recurring MCP coverage checkpoints, including pre-PR cleanup: compare current CLI/options with MCP tools, expose read/planning/export features when useful to agents, and keep risky mutation CLI-only or deferred until guardrails and audit semantics are clear. These checkpoints are periodic, not required after every feature or at every milestone.
   - Add a versioned `aiplane` agent skill target for Codex-style and other skill-capable assistants. The skill should document safe workflows, command selection, MCP usage, provider/model/runtime concepts, docs/test maintenance, and release-boundary checks.
   - Keep skills distinct from MCP: skills are assistant instructions and workflow guidance; MCP is the live callable tool surface.
   - Add planned agent-to-agent coordination support as profile/stack/orchestrator metadata: roles, model entries, endpoints, tool policies, approvals, and audit labels for frameworks such as LangGraph, CrewAI, AutoGen, Semantic Kernel, and OpenHands.
   - Keep agent-to-agent work focused on setup, policy, export, and repeatability; do not turn `aiplane` into the autonomous agent runner.
   - Research deeper IDE/tool integrations before adding brittle custom paths.

9. **Benchmark and recommendation quality** - Planned
   - Add repeated benchmark runs, timing/token metrics, and local result summaries.
   - Add benchmark comparison across models, runtimes, and machines.
   - Defer automated code execution grading until sandboxing and language runners are designed.

10. **Test-suite performance and isolation** - Planned
   - Keep the full automated suite useful as a PR gate without letting local discovery caches or external-machine state dominate runtime.
   - Split the large MVP test module into focused files by area so slow tests and ownership are easier to see.
   - Continue replacing repeated full-catalog enrichment with cached or single-pass helpers where behavior is unchanged.
   - Evaluate `pytest-xdist` only after filesystem, environment-variable, and profile-fixture isolation are strong enough for safe parallel execution.
   - Keep quality intact: optimize hot paths and fixtures, not assertions or behavioral coverage.

## Planned But Not Implemented

- `aiplane launch` wrappers for Continue, Codex, Claude Code, Cursor, or Ollama `launch`.
- `aiplane session` active chat/session management.
- Provider-specific production-ready Vagrant/Packer/OpenTofu/Terraform/Pulumi/Ansible/Dev Container modules and apply workflows.
- Custom VS Code extension or marketplace publishing.
- Full custom coding agent, agent orchestrator, autocomplete engine, inference runtime, or general model proxy.
- Direct agent-to-agent runtime execution inside `aiplane`; near-term support should be config, stack binding, policy, and export for established orchestrator frameworks.
- Broad cloud deployment apply for AKS/AWS/generic Kubernetes.
- Production-grade API gateway/auth management for shared endpoints.
- Arbitrary shell execution through MCP.

## Deferred / Non-Goals

- Replacing Continue, Cline, Cursor, Copilot, Codex CLI, Claude Code, Aider, or similar coding agents.
- Implementing model inference engines inside `aiplane`.
- Becoming a general model proxy competing with LiteLLM/OpenRouter-style tools.
- Hidden IDE policy bypasses or direct model edits without review.
