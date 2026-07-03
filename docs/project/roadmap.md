# Project Roadmap

This document is the developer-facing status map. It separates what is implemented from what is in progress, planned, or deferred. For product boundary and architecture direction, see [Strategy](strategy.md).

## Status Labels

- **Implemented**: available in the current CLI, scripts, docs, or tests.
- **In progress**: partially implemented; useful pieces exist, but the area is not complete.
- **Planned**: intended direction, but not implemented yet.
- **Research**: worth investigating before committing to a design.
- **Deferred**: intentionally not a near-term priority.

## Current Milestone: Post-Merge Architecture and Integration Hardening

Goal: turn the merged MVP surface into a maintainable beta foundation before adding broad new execution scope.

Required outcomes:

1. Keep the public CLI, docs, command coverage, MCP surface, planned/implemented skills, and tests aligned after the PR merge.
2. Reduce architectural pressure from the large CLI, model catalog, integration manager, runtime catalog, shell helpers, and monolithic MVP test file without changing user-visible behavior gratuitously.
3. Solidify MCP as the structured inspection/planning/export surface, with narrow audited writes only where guardrails are clear.
4. Add a versioned `aiplane` agent skill package for Codex-style and other skill-capable assistants, distinct from MCP and focused on safe workflow guidance.
5. Move orchestrator support from catalog/setup scaffolding toward explicit multi-agent workflow metadata: roles, model aliases, endpoints, tool policies, approvals, audit labels, and exports for established frameworks.
6. Keep provider/model discovery, runtime setup, stack planning, and local execution reliable enough for repeatable demos and early adopters.

## Implemented

- Profile loading, validation, templates, selected/default profile handling, ignored local config, and external profile directory support.
- Ignored local credential references with redacted credential inspection commands and provider connection tests for selected managed endpoints.
- Environment planning and doctor checks for system Python, `venv`, Conda, and Docker execution mode; setup helpers install the CLI and bootstrap ignored `profiles/local-dev` from the shipped template before profile-aware checks.
- External tool catalog, doctors, guarded install previews, non-mutating plans, and starter exports for Azure CLI, OpenTofu/Terraform, Pulumi, Vagrant, Packer, Docker/Compose, Dev Container CLI, kubectl, Helm, OpenSSH, Ansible, and benchmark helpers.
- Provider/model catalog foundations for Ollama, Ollama Cloud placeholder, OpenAI-compatible runtimes, OpenAI, Anthropic, Azure OpenAI, ElevenLabs TTS, Hugging Face, NVIDIA Hugging Face-scoped open model repos, GGUF/local files, and user-defined discovery providers. Shipped profile templates keep `models.yaml` structural, runtime/provider endpoint values live as conventional built-in defaults with local override support, and model grouping separates managed-service providers from self-managed runtime sources while preserving managed endpoint metadata for exports, stacks, and orchestrator plans.
- Ignored discovered provider/model cache flow plus `profiles bootstrap-local`, `models add`, `models clone`, and `models promote` as reviewed paths into editable local profile YAML; `models clear-cache` clears discovered entries and profile-owned review entries by default so discovery can be repopulated from providers, and `models refresh --reset-cache` combines clearing and repopulating for refreshed providers.
- Runtime/source mapping for Ollama, Hugging Face, NVIDIA Hugging Face-style repos, GGUF/local files, vLLM, TGI, Transformers, llama.cpp, LocalAI, LM Studio, and selected media runtimes.
- Runtime helper delegation through `aiplane runtimes ...` where supported by `scripts/provider_helper.sh`, including Ollama native and Docker substrate paths, guarded Ollama pulled-model remove/clear, plus vLLM/TGI-style runtimes.
- Hardware discovery, active hardware selection, machine schema/templates, model-fit checks, and hardware-aware recommendations.
- Machine inventory commands for import/list/show/validate/recommend, Azure SKU discovery/import, cache list/clear, Azure status, and remote profiling plans.
- Stack commands for setup/list/show/plan/doctor/status/export plus same-host lifecycle commands `prepare/start/stop/restart`.
- Stack preflight checks for runtime prerequisites, local port availability, endpoint auth policy, and cache-path hints.
- Azure target planning and doctor checks for AKS and VM targets, plus a narrow guarded Azure VM apply path.
- Orchestrator catalog commands for LangGraph, CrewAI, AutoGen, OpenHands, Semantic Kernel, and LlamaIndex Workflows.
- Agent application templates with non-mutating `agents templates/plan/export` commands, plus a versioned `skills/aiplane/SKILL.md` package for assistant workflow guidance.
- Stack artifact exports for Continue, OpenAI-compatible endpoint config, Dockerfile, Conda YAML, and starter Docker Compose.
- SSH tunnel plan/start/status/stop for configured remote model endpoints.
- Model list/show/defaults/use/add/clone/remove/enable/disable/refresh/promote/clear-cache/pull/test/benchmark commands.
- Benchmark framework list/doctor/install/plan helpers for smoke/custom checks, lm-evaluation-harness, vLLM serving benchmarks, and Locust-style load tests.
- `aiplane run` for single-prompt routing through configured model defaults with dry-run and policy-gated non-local escalation.
- Integration role inspection plus plan/setup/export for Continue, Cline, Zed, Aider, generic OpenAI-compatible clients, and MCP client snippets; setup can dry-run or execute supported helper install/start/pull actions for selected runtime/model aliases and skips unsupported source/runtime pull combinations with an explicit reason.
- MCP stdio server with read tools and narrow guarded writes for model defaults, hardware selection, runtime preference, model refresh, and SSH tunnel lifecycle. Read/planning tools cover models, providers, hardware, machine recommendations, stack inspection/planning/doctor checks, integrations, orchestrators, runtime status, and tunnel plans.
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

### Post-Merge Foundation

1. **Architecture and codebase cleanup** - Current
   - Split `src/aiplane/cli.py` into smaller command registration/handler modules by area while keeping one public `aiplane` entrypoint.
   - Define clearer service boundaries for provider discovery, model catalog rows, runtime compatibility, integration planning, MCP tools, and output shaping so source/runtime/endpoint rules are not reimplemented in several places.
   - Move hand-maintained tool schemas and CLI parser choices toward shared definitions where practical, especially for model filters and integration roles.
   - Keep shell helpers as thin delegates to official tools; avoid growing provider-specific business logic in Bash when Python catalog/runtime code already owns the decision.
   - Preserve inspect-first behavior and avoid compatibility shims unless a released interface requires them.

2. **MCP and agent skill hardening** - Implemented foundation
   - Audit MCP against the current CLI/options and docs; close useful read/planning/export gaps such as newer model filters, integration role planning, stack/orchestrator inspection, machine recommendations, and command coverage where safe.
   - Keep risky operations out of MCP until they have explicit approval, audit, dry-run, and rollback semantics. Runtime installs, model pulls, cloud apply, secret writes, and arbitrary shell execution remain blocked or CLI-only by default.
   - Add a versioned `aiplane` skill target for Codex-style and other skill-capable assistants. The skill should explain the product boundary, profile/provider/model/runtime concepts, preferred commands, MCP usage, docs/test maintenance, and pre-PR/release checks.
   - Add focused tests that compare MCP schemas and behavior with the CLI surfaces they intentionally mirror.
   - Treat MCP/skills synchronization as a recurring checkpoint and pre-PR cleanup task, not a requirement after every small feature.

3. **Orchestrator and multi-agent workflow metadata** - Current
   - Extend stack/orchestrator config beyond one primary model into explicit roles such as planner, coder, reviewer, researcher, tool-runner, and summarizer.
   - Bind each role to a reviewed model alias, endpoint, runtime/provider ownership, tool policy, approval mode, and audit label.
   - Export starter configs for LangGraph, CrewAI, AutoGen, Semantic Kernel, LlamaIndex Workflows, and OpenHands where those frameworks can consume the selected endpoints directly.
   - Keep `aiplane` as setup/config/policy/export, not the autonomous multi-agent runner.
   - Add doctor/plan checks that explain missing packages, missing endpoints, model/runtime incompatibility, and unsafe tool-policy combinations before anything is run.

### Product Hardening

4. **Provider discovery and model import** - Implemented foundation / ongoing provider hardening
   - Shipped `models.yaml` templates stay structural; profile-owned model entries and defaults come from ignored discovery caches, direct local add/clone, or deliberate local promotion.
   - `models promote` is the reviewed flow from discovered provider entry to editable local profile model; use `models add` when the real provider model id is already known but still present in discovery, and `models clone` when one real model needs multiple local purposes.
   - Refresh/promote/add/clone output explains the safe next step from dry-run discovery to discovered entries to traceable profile-owned model entries.
   - `models list` now filters from active hardware, named/imported machines, external machine files, the currently probed machine, and explicit RAM/VRAM/GPU/API/parameter constraints. Parameter count remains explicit because it is a model property rather than a machine-derived fact.
   - Ongoing hardening remains for Azure OpenAI deployment discovery, provider-specific live credential tests, and Anthropic/OpenAI discovery fallbacks where APIs or maintained catalogs allow it.

5. **Runtime, stack lifecycle, and endpoint hardening** - In progress
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

7. **Tool/task matrix and setup doctor expansion** - In progress
   - Keep `environment doctor` as the default human setup check with text output.
   - Keep every external tool mapped to the workflows it enables, whether it is mandatory or optional, and whether `aiplane` can attempt installation.
   - Grow doctor scope as new tool families are integrated without turning optional workflows into mandatory prerequisites.
   - Keep workflow-level readiness summaries in `tools matrix` useful for release review and demos.

### Later Expansion

8. **Runtime packaging and deployment reproducibility** - Planned
   - Broaden tests for stack export content across runtime/orchestrator combinations.
   - Add cache mounts, richer GPU flags, environment variables, and auth notes.
   - Keep image builds, registry pushes, VM creation, and cloud apply explicit and previewable.

9. **IDE, launch, and session integrations** - Planned
   - Maintain Continue, Cline, Zed, Aider, generic OpenAI-compatible, and MCP config exports as config-level integrations.
   - Keep model endpoint export separate from MCP tool export.
   - Research deeper Cursor, JetBrains, Windsurf, Copilot, Codex, and Claude Code integration before adding brittle custom paths.
   - Add launch wrappers only where a stable tool-native CLI exists and `aiplane` can export/check the needed environment first.
   - Keep any future `aiplane session` layer thin: selected model, endpoint, transcript path, and audit metadata, not a full custom chat product.

10. **Benchmark and recommendation quality** - Planned
   - Add repeated benchmark runs, timing/token metrics, and local result summaries.
   - Add benchmark comparison across models, runtimes, and machines.
   - Defer automated code execution grading until sandboxing and language runners are designed.

11. **Test-suite performance and isolation** - Planned
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
