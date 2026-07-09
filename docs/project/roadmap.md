# Project Roadmap

This document is the developer-facing status map. It separates what is implemented from what is in progress, planned, or deferred. For product boundary and architecture direction, see [Strategy](strategy.md).

## Status Labels

- **Implemented**: available in the current CLI, scripts, docs, or tests.
- **In progress**: partially implemented; useful pieces exist, but the area is not complete.
- **Planned**: intended direction, but not implemented yet.
- **Research**: worth investigating before committing to a design.
- **Deferred**: intentionally not a near-term priority.

## Scope Anchors

These anchors are deliberate product constraints, not incidental wording. Change them only with an explicit roadmap/strategy update that says the project is changing course.

- `aiplane` is a local-first control plane for AI model application environments: profiles, providers, model aliases, runtimes, endpoints, hardware fit, readiness checks, exports, MCP inspection, policy, and audit.
- The strongest public wedge is: **make local and hybrid AI model workflow stacks reproducible, inspectable, policy-aware, and portable from one profile**.
- `aiplane` configures and checks tools such as Ollama, vLLM, Continue, Aider, Cline, MCP clients, OpenAI-compatible endpoints, Anthropic, OpenAI, and Azure OpenAI; it does not replace them.
- Do not grow `aiplane` into a coding agent, full chat UI, inference runtime, general model proxy, model marketplace, IDE extension, production cloud platform, or Terraform/Ansible/Docker replacement.
- Runtime helpers must stay thin delegates to official tools. Deployment features must stay AI-specific, inspectable, previewable, and guarded.
- Orchestrator support means metadata, role bindings, endpoint/policy export, and readiness checks for established frameworks, not running autonomous agent conversations inside `aiplane`.
- MCP remains a structured inspection/planning/export surface with narrow audited writes. Arbitrary shell execution, broad cloud apply, secret writes, runtime installs, and model pulls stay out unless guardrails are explicitly designed and documented.

### Ecosystem Overlap Register (mvp_0.3 baseline)

This register tracks overlap by layer so scope drift is intentional rather than accidental. A row stays in the table even when overlap is minimal, so boundary decisions remain visible during planning.

| Tooling family | Open-source / paid examples | What it does | Current aiplane overlap | Boundary position |
| --- | --- | --- | --- | --- |
| AI coding assistants | Continue, Aider, Cline, Cursor, Codex-style/Claude Code, JetBrains, Copilot | Runs coding sessions and owns agent interaction model | Exports and plans for endpoints/roles; no agent runtime ownership | In-scope by design: `aiplane` configures and checks, then hands off |
| Local inference runtimes | Ollama, vLLM, TGI, llama.cpp, LocalAI, LM Studio | Serve local model inference and model lifecycle | Provider/runtime mapping, helper wrappers, endpoint-aware runner checks, lifecycle ops where helper exists | Thin delegate only: native tools remain lifecycle authority |
| Managed APIs / services | OpenAI, Anthropic, Azure OpenAI | Hosted APIs with auth and endpoint contracts | Catalog adapters, endpoint/protocol metadata, provider tests, and task/chat execution for supported protocols | In-scope as configured endpoint caller, not marketplace or gateway |
| IDE integration surfaces | VS Code + Continue, Zed, IDE MCP clients | Connect editors/workflow tools to endpoints and MCP | Config snippets, MCP manifests, integration plan/export | In-scope only as config and readiness surfaces |
| Model catalogs | Hugging Face, NVIDIA on HF, local files, media sources | Resolve model IDs/artifacts and discovery metadata | Multiple catalog adapters, discovered cache, add/promote/clone, provider-kind grouping | Core in-scope control plane function |
| Infrastructure tooling | Docker/Compose, OpenSSH, Dev Containers, Terraform/OpenTofu, Vagrant, Packer, Ansible, Helm, kubectl | Build runtime/machine/container/workspace targets | Readiness checks, non-mutating plans, guarded helper calls and generated exports | Boundary is explicit: planning+readiness, not ownership of infra platform |
| Orchestration / workflow frameworks | LangGraph, CrewAI, AutoGen, Semantic Kernel, LlamaIndex, OpenHands | Run autonomous agent/workflow execution in application runtime | Stack role metadata, policy labels, starter exports, stack doctor/planner | In-scope as setup/binding/export only |
| Benchmark and validation | lm-eval, vLLM serving benchmarks, Locust | Compare quality/throughput/latency on a workload | Smoke/custom benchmark scaffolding and planning commands | In-scope as aid-to-selection, not a benchmark SaaS replacement |
| Secret / auth / infra services | Azure Speech, ElevenLabs, key-vault style services | Secret handling, hosted services, and shared endpoint control | Credential refs and provider tests are supported; direct secret writes / platform control are not | Explicitly out of scope for the current wedge |

Scope-change protocol: if any overlap row moves toward owning execution, marketplace behavior, or broad platform automation, update Strategy + roadmap anchors explicitly and document the policy change in `session-handoff.md` before implementation.



## Public Adoption Wedge

The first public story should be narrow enough to be polished:

```bash
aiplane quickstart local-coding
aiplane doctor
aiplane integrations export continue
aiplane integrations export aider
aiplane mcp manifest
```

That flow should answer: what is installed, which models/endpoints are configured, what fits this hardware, which model aliases are approved for chat/autocomplete/embedding/code roles, whether cloud escalation is allowed, what is unsafe or missing, and what config to export.

Recommended public roadmap:

1. **Local AI Workflow Stack Doctor**: local Ollama/vLLM-style endpoints, Continue/Aider exports, hardware recommendations, model alias policy, doctor output, MCP read surface, and clean examples.
2. **Remote GPU Workstation Profile**: SSH tunnel checks, remote runtime endpoint status, vLLM/Ollama model fit, stack doctor, endpoint export, and safety checks.
3. **Team Policy and Governance**: shared profile templates, repo-level allowed-provider policy, cloud escalation rules, audit output, supportable reference stacks, and optional managed profile sync later.

Advanced cloud, Kubernetes, broad provisioning, custom IDEs, general agent execution, and full session products should not lead the public story. They remain later or explicit-change-course work.

## Current Milestone: Team Policy and Governance

Goal: make policy and governance outcomes explicit and enforceable before adding broader workflow breadth.

Required outcomes:

1. Finalize profile policy surface in docs + UX: allowed-providers policy, repo classification, cloud escalation controls, and policy explain output.
2. Add focused tests for `policy explain`, policy-readiness blocks in doctor, and policy-aware behavior on stack role/tool-policy risk checks.
3. Close `local-doctor`/`tools matrix` alignment for policy readiness signals and missing-config risk surfacing.
4. Update demo/onboarding narrative to show where policy blocks, warns, and what approval/override actions are needed.
5. Keep remote workflow artifacts stable by moving to read-only demo/coverage checks; no regression in existing remote milestone.

## Implemented

- Profile loading, validation, templates, selected/default profile handling, ignored local config, and external profile directory support.
- Ignored local credential references with redacted credential inspection commands and provider connection tests for selected managed endpoints.
- Local AI workflow quickstart with opt-in runtime-helper model pull preview/execution plus top-level local AI workflow stack doctor with profile, environment, provider/endpoint, role default, selected endpoint readiness, hardware-fit, Continue/Aider readiness, and MCP manifest/read-surface summaries; environment planning and doctor checks cover system Python, `venv`, Conda, and Docker execution mode; setup helpers install the CLI and bootstrap ignored `profiles/local-dev` from the shipped template before profile-aware checks.
- Local config now supports profile-aware and command-aware format/verbosity defaults (`text`/`json`, `0`/`1`/`2`) via `config format`/`config verbosity` with precedence: CLI `--format`/`--verbosity` > command override > profile override > global default.
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
- Stack artifact exports for Continue, OpenAI-compatible endpoint config, Dockerfile, Conda YAML, starter Docker Compose, and framework starter metadata for LangGraph, CrewAI, AutoGen, Semantic Kernel, LlamaIndex Workflows, and OpenHands.
- SSH tunnel plan/start/status/stop for configured remote model endpoints.
- Model list/show/defaults/use/add/clone/remove/enable/disable/refresh/promote/clear-cache/pull/test/benchmark commands.
- Benchmark framework list/doctor/install/plan helpers for smoke/custom checks, lm-evaluation-harness, vLLM serving benchmarks, and Locust-style load tests.
- `aiplane run` for single-prompt routing through configured model defaults with dry-run, policy-gated non-local escalation, and protocol backends for Ollama, OpenAI-compatible chat completions, Azure OpenAI chat completions, and Anthropic Messages.
- Strict allowlisted runtime bridge commands (`bridge list/exec`) for delegating selected native runtime CLIs by shorthand action without exposing arbitrary shell passthrough.
- Integration role inspection plus plan/setup/export for Continue, Cline, Zed, Aider, generic OpenAI-compatible clients, and MCP client snippets; setup can dry-run or execute supported helper install/start/pull actions for selected runtime/model aliases and skips unsupported source/runtime pull combinations with an explicit reason.
- MCP stdio server with read tools and narrow guarded writes for model defaults, hardware selection, runtime preference, model refresh, and SSH tunnel lifecycle. Read/planning tools cover models, providers, hardware, machine recommendations, stack inspection/planning/doctor checks, integrations, orchestrators, runtime status, and tunnel plans.
- Policy checks, approval handling, secret redaction, JSONL audit foundations, and shared JSON output ordering.

## In Progress

- Provider discovery: Ollama, Hugging Face, NVIDIA Hugging Face-scoped repos, Hugging Face GGUF, OpenAI-compatible `/v1/models`, Azure OpenAI deployment paths, structural shipped profile templates, profile-local provider default refresh with enabled-flag preservation, ignored user provider overrides, and discovery-derived AI media roles exist; richer managed-provider and specialist media catalog discovery needs hardening.
- Runtime and stack lifecycle: same-host/local helpers exist; remote execution, endpoint authentication, GPU mapping, service management, and production tuning remain early. Single-prompt execution is protocol-based for Ollama/OpenAI-compatible/Azure OpenAI/Anthropic, while richer chat/task UX remains planned.
- Tool integrations: doctors, install previews, plans, and starter exports exist; provider-specific modules/playbooks/templates remain planned.
- Azure deployment: planning, doctor checks, and narrow VM apply exist; broader AKS/cloud apply needs hardening before expansion.
- MCP governance: read tools and audited narrow writes exist; broader write tools require explicit risk controls.
- Benchmarking: smoke/custom tasks and framework planning exist; repeated runs, token metrics, comparison views, and sandboxed grading remain planned.
- IDE/CLI integration: config export exists; deeper Cursor, JetBrains, Windsurf, Copilot, Codex, and Claude Code integration remains research/planned.

## Planned Milestones

### Post-Merge Foundation

1. **Architecture and codebase cleanup** - Implemented foundation / ongoing cleanup
   - `src/aiplane/cli.py` now delegates integration and model command registration/handling to focused modules while keeping one public `aiplane` entrypoint. Continue splitting command families when it reduces real ownership pressure.
   - Shared CLI parsing/progress helpers live outside the monolithic CLI so provider refresh, profile bootstrap, hardware/machine/stack settings, and future command modules do not duplicate low-level parsing behavior.
   - Model filter parser choices and MCP schema choices are shared definitions; integration roles are shared contracts. Keep moving shared definitions only where they prevent drift.
   - Keep shell helpers as thin delegates to official tools; avoid growing provider-specific business logic in Bash when Python catalog/runtime code already owns the decision.
   - Preserve inspect-first behavior and coherent early-beta interfaces; do not keep inconsistent flags or compatibility shims until a released interface requires them.

2. **MCP and agent skill hardening** - Implemented foundation
   - Audit MCP against the current CLI/options and docs; close useful read/planning/export gaps such as newer model filters, integration role planning, stack/orchestrator inspection, machine recommendations, and command coverage where safe.
   - Keep risky operations out of MCP until they have explicit approval, audit, dry-run, and rollback semantics. Runtime installs, model pulls, cloud apply, secret writes, and arbitrary shell execution remain blocked or CLI-only by default.
   - Add a versioned `aiplane` skill target for Codex-style and other skill-capable assistants. The skill should explain the product boundary, profile/provider/model/runtime concepts, preferred commands, MCP usage, docs/test maintenance, and pre-PR/release checks.
   - Add focused tests that compare MCP schemas and behavior with the CLI surfaces they intentionally mirror.
   - Treat MCP/skills synchronization as a recurring checkpoint and pre-PR cleanup task, not a requirement after every small feature.

3. **Orchestrator and multi-agent workflow metadata** - Implemented foundation / ongoing hardening
   - Stack setup can carry optional role metadata such as planner, coder, reviewer, researcher, tool-runner, and summarizer while preserving one primary lifecycle model for runtime install/pull/start actions.
   - Role metadata binds reviewed model aliases to provider/runtime or managed endpoint ownership plus tool policy, approval mode, limits, and audit labels; stack plan/doctor/status/export surface the metadata, and doctor warns on disabled role models, missing managed endpoints, and risky tool-policy/approval combinations.
   - Framework starter exports now emit reviewed role/endpoint/tool/approval/audit metadata for LangGraph, CrewAI, AutoGen, Semantic Kernel, LlamaIndex Workflows, and OpenHands; next harden framework-specific templates where stable APIs justify it.
   - Keep `aiplane` as setup/config/policy/export, not the autonomous multi-agent runner.
   - Keep extending doctor/plan checks so they explain missing packages, missing endpoints, model/runtime incompatibility, and unsafe tool-policy combinations before anything is run.

### Product Hardening

4. **Provider discovery and model import** - Implemented foundation / ongoing provider hardening
   - Shipped `models.yaml` templates stay structural; profile-owned model entries and defaults come from ignored discovery caches, direct local add/clone, or deliberate local promotion.
   - `models promote` is the reviewed flow from discovered provider entry to editable local profile model; use `models add` when the real provider model id is already known but still present in discovery, and `models clone` when one real model needs multiple local purposes.
   - Refresh/promote/add/clone output explains the safe next step from dry-run discovery to discovered entries to traceable profile-owned model entries.
   - `models list` now filters from active hardware, named/imported machines, external machine files, the currently probed machine, and explicit RAM/VRAM/GPU/API/parameter constraints. Parameter count remains explicit because it is a model property rather than a machine-derived fact.
- `models list --format text` now supports compact output at verbosity 0 with explicit warning/fallback to JSON payload at verbosity 1+.
   - Managed-provider online catalog failures, such as an unconfigured Azure OpenAI deployment endpoint/key, now return structured refresh failure JSON with provider-test/show next steps instead of silently looking successful through an empty profile-catalog fallback.
   - OpenAI-compatible `/v1/models`, Azure OpenAI deployment, and ElevenLabs voice discovery now share the managed-provider failure path when endpoint/key configuration is missing. Ongoing hardening remains for richer managed-provider discovery, provider-specific live credential tests, and Anthropic discovery fallbacks where APIs or maintained catalogs allow it.

5. **Runtime, stack lifecycle, and endpoint hardening** - Implemented foundation / ongoing lifecycle hardening
   - Same-host lifecycle result reporting includes execution mode, step counts, failed step, timing fields, stdout/stderr tails, and best-effort runtime status before and after execution.
   - Stack endpoint planning now records endpoint auth/TLS/gateway hints, surfaces `stacks endpoint-plan`, and feeds plan/doctor checks for public/shared endpoint readiness.
   - Stacks can bind managed-service model endpoints where the runtime field represents a hosted protocol or endpoint contract, while keeping those entries out of self-managed runtime fit checks.
   - Remote execution boundaries remain explicit for SSH/Azure/AKS stacks; non-local lifecycle commands still return plans rather than executing.
   - Docker-aware stack lifecycle paths remain the next hardening area after same-host helper execution and endpoint planning.

6. **Cloud, VM, and workstation workflow hardening** - Implemented foundation / in progress
   - Use OpenTofu as the default provider-agnostic IaC target, Terraform as a compatible alternative, and Pulumi as an optional language-native IaC path.
   - Harden Vagrant, Packer, Ansible, Dev Container, and IaC starter exports into provider-specific workflows.
   - Keep local install, local VM provisioning, remote VM provisioning, remote PC setup, and cloud provisioning distinct. `deploy workflow-plan` now exposes those boundaries and recommended tool ownership.
   - Keep mutating target bootstrap behind explicit confirmation; `deploy apply` requires `--yes` and broad cloud apply remains out of scope until provider-specific guardrails are ready.
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
   - Research an optional Ollama `launch` adapter for Ollama-specific coding-tool setup so `aiplane` can plan/validate model, endpoint, hardware, and policy decisions while delegating tool-native launch/install behavior to Ollama instead of duplicating its menu.
   - Keep any future `aiplane session` layer thin: selected model, endpoint, transcript path, and audit metadata, not a full custom chat product.

10. **Benchmark and recommendation quality** - Planned
   - Add repeated benchmark runs, timing/token metrics, and local result summaries.
   - Add benchmark comparison across models, runtimes, and machines.
   - Defer automated code execution grading until sandboxing and language runners are designed.

11. **Test-suite structure, performance, and isolation** - Structurally complete / incremental
   - Split the large MVP test module into focused files by area so slow tests and ownership are easier to see. Start with behavior boundaries that already exist in code: profiles/config, providers/models, runtimes/execution, integrations/chat, MCP, machines/stacks, deployment, and CLI smoke coverage.
   - Extract shared test fixtures and helpers for isolated profiles, local model caches, mocked HTTP endpoints, mocked subprocess boundaries, and CLI stdout/stderr capture.
   - Keep the full automated suite useful as a PR gate without letting local discovery caches or external-machine state dominate runtime.
   - Continue replacing repeated full-catalog enrichment with cached or single-pass helpers where behavior is unchanged.
   - Evaluate `pytest-xdist` only after filesystem, environment-variable, and profile-fixture isolation are strong enough for safe parallel execution.
   - Keep quality intact: move tests and optimize fixtures, not assertions or behavioral coverage.

## Planned But Not Implemented

- `aiplane launch` wrappers for Continue, Codex, Claude Code, Cursor, or an optional Ollama `launch` adapter.
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
