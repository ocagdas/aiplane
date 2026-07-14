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

- `aiplane` is a local-first environment doctor and configuration compiler for AI workflow environments: profiles, providers, model aliases, runtimes, endpoints, hardware fit, readiness checks, exports, MCP inspection, policy, and audit.
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
| Model catalogs | Hugging Face, NVIDIA on HF, local files, media sources | Resolve model IDs/artifacts and discovery metadata | Multiple catalog adapters, discovered cache, add/promote/clone, provider-kind grouping | Core in-scope configuration function |
| Infrastructure tooling | Docker/Compose, OpenSSH, Dev Containers, Terraform/OpenTofu, Vagrant, Packer, Ansible, Helm, kubectl | Build runtime/machine/container/workspace targets | Readiness checks, non-mutating plans, guarded helper calls and generated exports | Boundary is explicit: planning+readiness, not ownership of infra platform |
| Orchestration / workflow frameworks | LangGraph, CrewAI, AutoGen, Semantic Kernel, LlamaIndex, OpenHands | Run autonomous agent/workflow execution in application runtime | Stack role metadata, policy labels, starter exports, stack doctor/planner | In-scope as setup/binding/export only |
| Benchmark and validation | lm-eval, vLLM serving benchmarks, Locust | Compare quality/throughput/latency on a workload | Smoke/custom benchmark scaffolding and planning commands | In-scope as aid-to-selection, not a benchmark SaaS replacement |
| Secret / auth / infra services | Azure Speech, ElevenLabs, key-vault style services | Secret handling, hosted services, and shared endpoint control | Credential refs and provider tests are supported; direct secret writes / platform control are not | Explicitly out of scope for the current wedge |

Scope-change protocol: if any overlap row moves toward owning execution, marketplace behavior, or broad platform automation, update Strategy + roadmap anchors explicitly and document the policy change in `session-handoff.md` before implementation.




## Public Adoption Wedge and Milestone Priorities

### Priority 1: Prove the core workflow

The public wedge is now a narrow onboarding path:

```text
aiplane discover
aiplane doctor
aiplane recommend
aiplane export continue
```

A new user should reach a useful result with one command:

```text
aiplane quickstart local-coding
```

That command should automatically:

1. Detect hardware
2. Detect installed runtimes
3. Detect local models
4. Detect supported coding tools
5. Detect existing endpoint configuration
6. Create a draft profile
7. Run doctor
8. Recommend suitable models
9. Print exact export commands

**Success criteria**

1. No manual YAML editing required for the first successful run
2. No more than two user decisions during onboarding
3. Useful output produced within five minutes
4. The command can run safely in dry run mode
5. Repeated execution does not overwrite manual changes without warning

### Priority 2: Reduce configuration duplication

**Target**

Track how much configuration is detected automatically.

The workflow should surface a summary like:

```text
Detected values: 24
Generated values: 8
User supplied values: 2
Unresolved values: 1
```

**Success criteria**

1. At least 80 percent of local setup values are discovered or inferred
2. The user should manually enter no more than credentials and policy decisions
3. Every generated value includes provenance
4. Existing Continue, Aider, Cline and endpoint configuration can be imported
5. The tool clearly distinguishes detected, inferred and user supplied values

### Priority 3: Simplify the public command surface

**Target**

Make these the main commands shown in the README and onboarding:

```text
aiplane discover
aiplane doctor
aiplane recommend
aiplane export continue
```

Existing detailed commands can remain, but should be treated as advanced commands.

**Success criteria**

1. The first page of the README shows no more than four primary commands
2. A new user can complete the main workflow without understanding stacks, bridges, targets or orchestrators
3. Advanced terminology appears only after the first successful workflow
4. Each primary command has clear text and JSON output
5. Each command produces a suggested next command

### Priority 4: Make doctor output fully actionable

**Target**

Every blocking or advisory finding must contain:

1. Severity
2. Reason
3. Impact
4. Exact remediation command
5. Whether the command mutates state
6. Whether dry run is supported

**Success criteria**

1. 100 percent of blocking findings contain an exact remediation command
2. 100 percent of mutating commands clearly identify themselves
3. Doctor exit codes distinguish healthy, advisory and blocking states
4. JSON output contains stable fields for CI usage
5. Tests cover every doctor finding category

### Priority 5: Validate recommendation quality

**Status: Implemented for deterministic fixture coverage; external calibration remains ongoing.**

**Target**

Create test cases covering:

1. CPU only machine
2. Small NVIDIA GPU
3. 24 GB NVIDIA GPU
4. 32 GB NVIDIA GPU
5. AMD GPU
6. Apple unified memory
7. Remote GPU endpoint
8. Cloud managed model
9. Policy restricted environment
10. Unsupported runtime format

For each case, define expected recommended, usable and rejected models.

**Success criteria**

1. Recommendation decisions are deterministic
2. Each recommendation includes ranking rationale
3. Policy blocked models never appear as recommended
4. Runtime incompatible models never appear as recommended
5. Hardware unsuitable models are clearly separated
6. Benchmark data influences ranking only when available
7. Missing benchmark data does not break ranking

### Priority 6: Prove deterministic exports

**Status: Implemented for supported fixture exports and saved-plan replay coverage.**

**Target**

Generate stable expected outputs for:

1. Continue
2. Aider
3. Cline
4. Zed
5. Generic OpenAI compatible clients
6. MCP clients

**Success criteria**

1. The same profile produces byte stable output where possible
2. Machine specific fields are clearly isolated
3. Every export includes a plan identifier
4. Every export can be reproduced from the plan identifier
5. Export output records profile version and selected model aliases
6. Client configuration changes trigger visible test failures
7. Exporters are version aware where the client format changes

### Priority 7: Make policy behaviour predictable

**Status: Implemented for current allow / approval-required / blocked decisions; temporary approvals, overrides, and organization audit workflows remain planned governance extensions.**

**Target**

Use a consistent set of policy outcomes:

1. Allowed
2. Allowed with warning
3. Approval required
4. Temporarily approved
5. Blocked
6. Overridden with audit record

**Success criteria**

1. Every model and endpoint decision returns one policy outcome
2. Export commands block disallowed providers
3. Overrides require an explicit reason
4. Temporary approvals have an expiry
5. Every override creates an audit entry
6. Doctor reports policy drift
7. Policy behaviour is identical across CLI, MCP and exports

### Priority 8: Tighten the product boundary

**Status: Implemented as a command category inventory in command coverage, with README and top-level help leading on the core workflow.**

**Target**

Create a command inventory with three categories.

Core: discovery, doctor, recommendation, policy, export, profile management

Supporting: runtime status, remote endpoint checks, hardware inventory, MCP inspection, benchmark summaries

Deferred from public focus: broad provisioning, general agent execution, rich chat experience, cloud platform behaviour, infrastructure replacement, general workflow orchestration

**Success criteria**

1. README leads only with core commands
2. Public demo spends at least 80 percent of its time on core commands
3. New features require a written explanation of which category they belong to
4. No new top level command is added without a scope review
5. Deferred areas do not block the external beta

### Priority 9: Test clean machine onboarding

**Target**

Test repeatable onboarding on at least six environments:

1. Ubuntu with Ollama and Continue
2. Ubuntu with vLLM
3. Windows with Ollama
4. macOS with Apple Silicon
5. Clean machine with no AI tools installed
6. Remote workstation with local client

**Success criteria**

1. Installation succeeds from documented steps
2. Discovery completes without manual file changes
3. Doctor produces useful findings
4. At least one working export is generated
5. A tester completes the flow without developer assistance
6. Median time to first useful export is below ten minutes
7. Every failure is classified as product defect, documentation defect or unsupported environment

### Priority 10: Gather external evidence

**Target**

Recruit ten users from the intended audience:

1. Three local AI power users
2. Two software consultancies
3. Two teams using local and cloud models
4. Two privacy sensitive organisations
5. One developer using a remote GPU workstation

**Success criteria**

1. At least seven complete onboarding
2. At least five generate and use an export
3. At least three use more than one integration
4. At least three report that `aiplane` replaced manual configuration or scripts
5. Record every point where users needed help
6. Collect time to first successful result
7. Collect the number of manual values entered

### Priority 11: Define adoption metrics

**Target**

Track these metrics:

1. Installation completion rate
2. Discovery completion rate
3. Doctor success rate
4. Time to first useful export
5. Number of detected values
6. Number of manually entered values
7. Number of successful integrations
8. Number of policy blocks correctly explained
9. Number of repeatable profile replays
10. Number of users returning within seven days

**Initial targets**

1. 80 percent onboarding completion
2. Median first export below ten minutes
3. At least 80 percent configuration auto detected
4. At least 70 percent of users successfully use one generated export
5. At least 40 percent successfully use two integrations
6. Fewer than three unexplained errors per ten onboarding sessions

### Priority 12: Improve documentation structure

**Status: Implemented in the user documentation entrypoints with Start here, Common workflows, and Advanced concepts sections. Clean-machine onboarding commands are added to the public demo plan for Priority 9 trials.**

**Target**

Split documentation by user maturity:

Start here:

1. Install
2. Quickstart
3. Doctor
4. Recommend
5. Export

Common workflows:

1. Local Ollama
2. Local vLLM
3. Remote GPU workstation
4. Managed provider
5. Privacy restricted repository

Advanced concepts:

1. Providers
2. Runtimes
3. Machines
4. Stacks
5. Policies
6. MCP
7. Orchestrators

**Success criteria**

1. The first page contains one primary workflow
2. No advanced concept is required to complete onboarding
3. Every example is tested in CI where practical
4. Every example identifies whether it mutates state
5. Every workflow ends with a verifiable outcome

### Recommended delivery order

#### Milestone 1: External beta readiness

1. Single command onboarding
2. Actionable doctor output
3. Configuration provenance
4. Deterministic exports
5. Recommendation test matrix
6. Simplified README
7. Clean machine tests

Exit target: five external users complete the main workflow without developer assistance.

#### Milestone 2: Team reproducibility

1. Stable plan replay
2. Policy state model
3. Profile comparison
4. Policy drift detection
5. Shared profile validation
6. Remote workstation workflow

Exit target: Two teams reproduce the same approved setup across at least three machines.

#### Milestone 3: Commercial validation

1. Central profile registry prototype
2. Signed policy support
3. Central audit collection
4. Fleet inventory
5. Role based administration
6. Organisation reporting

Exit target: At least two organisations agree that team governance capability is valuable enough to pay for.

### Immediate next sprint (high-priority and blocking)

1. Implemented: add `aiplane discover`
2. Implemented: make `aiplane quickstart local-coding` consume discovery output automatically
3. Implemented: add provenance to generated/detected/user-supplied/unresolved profile values
4. Implemented: ensure every doctor failure includes exact structured remediation metadata
5. Add golden file tests for Continue, Aider, Cline, and MCP exports
6. Run the workflow on three clean environments and document every failure

### Scope freeze until the sprint completes

Do not add new orchestrators, cloud providers, benchmark frameworks or runtime types until those six targets are complete.

## Current Milestone: External Beta Readiness

The roadmap is now actively executing the priorities above; completed work in each earlier milestone is being stabilized as execution hardens. P0 quickstart sufficiency is implemented with offline-safe defaults, idempotent profile preservation, bounded no-model guidance, and one exact next action.

P0.6 stable doctor contract v1 is implemented with uniform findings and authoritative 0/1/2 exit semantics.
P0.7 Tier-1 export contracts are implemented with four versioned golden formats and cross-OS installed-wheel verification.
P0.8 public profile schema v1 is implemented with external validation and canonical rendering.

## Implemented

- Profile loading, validation, templates, selected/default profile handling, ignored local config, and external profile directory support.
- Ignored local credential references with redacted credential inspection commands and provider connection tests for selected managed endpoints.
- Local AI workflow quickstart with opt-in runtime-helper model pull preview/execution plus top-level local AI workflow stack doctor with profile, environment, provider/endpoint, role default, selected endpoint readiness, hardware-fit, Continue/Aider readiness, and MCP manifest/read-surface summaries; environment planning and doctor checks cover system Python, `venv`, Conda, and Docker execution mode; setup helpers install the CLI and bootstrap ignored `profiles/local-dev` from the shipped template before profile-aware checks.
- Local config now supports profile-aware and command-aware format/verbosity defaults (`text`/`json`, `0`/`1`/`2`) via `config format`/`config verbosity` with precedence: CLI `--format`/`--verbosity` > command override > profile override > global default.
- External tool catalog, doctors, guarded install previews, non-mutating plans, and starter exports for Azure CLI, OpenTofu/Terraform, Pulumi, Vagrant, Packer, Docker/Compose, Dev Container CLI, kubectl, Helm, OpenSSH, Ansible, and benchmark helpers.
- Provider/model catalog foundations for Ollama, Ollama Cloud placeholder, OpenAI-compatible runtimes, OpenAI, Anthropic, Azure OpenAI, ElevenLabs TTS, Hugging Face, NVIDIA Hugging Face-scoped open model repos, GGUF/local files, and user-defined discovery providers. Shipped profile templates keep `models.yaml` structural, runtime/provider endpoint values live as conventional built-in defaults with local override support, and model grouping separates managed-service providers from self-managed runtime sources while preserving managed endpoint metadata for exports, stacks, and orchestrator plans.
- Non-destructive bootstrap plus install/activation flows preserve existing editable profiles unless `--overwrite` is explicit; static wheels include shipped config/profile templates and runtime helper scripts and are verified in a clean venv.
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

1. **Architecture and codebase cleanup** - Implemented
   - `src/aiplane/cli.py` delegates every command family to focused owners and is limited to parser composition and dispatch. Launch/session planning, profile views/validation, presentation/progress reporting, and public onboarding workflows live in dedicated modules. The root decreased from 3,171 to 456 lines while preserving one public `aiplane` entrypoint.
   - Shared CLI parsing/progress helpers live outside the monolithic CLI so provider refresh, profile bootstrap, hardware/machine/stack settings, and future command modules do not duplicate low-level parsing behavior.
   - Model filter parser choices and MCP schema choices are shared definitions; integration roles are shared contracts. Keep moving shared definitions only where they prevent drift.
   - Keep shell helpers as thin delegates to official tools; avoid growing provider-specific business logic in Bash when Python catalog/runtime code already owns the decision.
   - Preserve inspect-first behavior and coherent early-beta interfaces; do not keep inconsistent flags or compatibility shims until a released interface requires them.

2. **MCP and agent skill hardening** - Implemented / hardening
   - Audit MCP against the current CLI/options and docs; close useful read/planning/export gaps such as newer model filters, integration role planning, stack/orchestrator inspection, machine recommendations, and command coverage where safe.
   - Keep risky operations out of MCP until they have explicit approval, audit, dry-run, and rollback semantics. Runtime installs, model pulls, cloud apply, secret writes, and arbitrary shell execution remain blocked or CLI-only by default.
   - Add a versioned `aiplane` skill target for Codex-style and other skill-capable assistants. The skill should explain the product boundary, profile/provider/model/runtime concepts, preferred commands, MCP usage, docs/test maintenance, and pre-PR/release checks.
   - Add focused tests that compare MCP schemas and behavior with the CLI surfaces they intentionally mirror.
   - Treat MCP/skills synchronization as a recurring checkpoint and pre-PR cleanup task, not a requirement after every small feature.

3. **Orchestrator and multi-agent workflow metadata** - Implemented / hardening
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

9. **IDE, launch, and session integrations** - Implemented / hardening
   - Continue, Cline, Zed, Aider, generic OpenAI-compatible, and MCP config exports are implemented at config level.
   - `aiplane launch` is implemented for stable tools (`continue`, `ollama`, `aider`) with profile-driven model selection, policy checks, and optional `--app` for Ollama tool launching.
   - `aiplane session start` is implemented for thin session handoff metadata, transcript defaults, and local audit records.
   - Add launch wrappers for additional stable CLIs (Codex, Cursor, Claude Code) only when contracts and usage patterns are stable.
   - Keep future `aiplane session` extensions thin: selected model, endpoint, transcript path, and audit metadata, not a full custom chat product.

10. **Benchmark and recommendation quality** - Planned
   - Add repeated benchmark runs, timing/token metrics, and local result summaries.
   - Add benchmark comparison across models, runtimes, and machines.
   - Defer automated code execution grading until sandboxing and language runners are designed.

11. **Test-suite structure, performance, and isolation** - Structurally complete / incremental
   - Production loaders are no longer globally replaced by the test harness; temporary profile roots contain deterministic synthetic model data and exercise normal disk loading.
   - The quick gate now runs ten contracts plus four intentional smoke checks; the empty legacy aggregate module is no longer included.
   - Shared injectable command/HTTP boundaries now cover every production process and HTTP owner; only `boundaries.py` calls `subprocess` or `urllib` directly, enforced by a contract test.
   - Model refresh reconciliation, stack lifecycle, static tool catalog data, and provider-registry tests now live in focused modules instead of their former large mixed owners.
   - Model pull/execution/endpoint readiness now lives in `model_execution.py`; stack role normalization/policy checks live in `stack_roles.py`. Oversized model and profile/config test owners are split into focused refresh, mutation, listing, lifecycle, config, and governance modules.
   - CI keeps the full Python 3.11 gate and validates contracts plus clean static-wheel installation on Python 3.12 and 3.13.
   - Split the large MVP test module into focused files by area so slow tests and ownership are easier to see. Start with behavior boundaries that already exist in code: profiles/config, providers/models, runtimes/execution, integrations/chat, MCP, machines/stacks, deployment, and CLI smoke coverage.
   - Shared test infrastructure now separates isolated profile/model materialization (`profile_fixtures.py`), recording process/HTTP fakes (`boundary_fakes.py`), and in-process CLI output capture (`cli_fixtures.py`). Continue migrating repeated local doubles when touching their owning suites.
   - Keep the full automated suite useful as a PR gate without letting local discovery caches or external-machine state dominate runtime.
   - Runtime progress timing is injectable for tests, eliminating a two-second sleep while retaining real threaded reporter coverage; synthetic hardware recommendation matrices no longer probe host GPU tools. Continue replacing repeated full-catalog enrichment with cached or single-pass helpers where behavior is unchanged.
   - `pytest-xdist` 3.8.0 is pinned for development. The full gate uses four workers with file-level scheduling after three clean parallel full-suite runs; `AIPLANE_TEST_WORKERS` can tune the count or select `0` for serial troubleshooting.
   - Keep quality intact: move tests and optimize fixtures, not assertions or behavioral coverage.

## Planned But Not Implemented

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

### Repository Safety Review Register

The prioritized July 2026 code-quality and safety findings are tracked in
[Code Quality and Safety Review — July 2026](code-quality-review-2026-07.md).
SEC-1 is implemented: `aiplane tool` no longer assumes approval; risky operations
require an interactive confirmation or explicit per-invocation `--yes`, while
read-only tools remain non-interactive.

Audit log reads are crash-tolerant: `audit tail` skips malformed/non-object JSONL
records, distinguishes a likely interrupted final append, returns the requested
number of recent valid events where available, and emits metadata-only recovery
warnings on stderr without exposing corrupt content.

SSH tunnel lifecycle state is now identity-safe and collision-resistant. Start saves
versioned atomic JSON containing the PID and captured process identity; status/stop
verify that identity, Linux termination uses `pidfd` when available, stale or reused
PIDs are never signalled, malformed state fails closed, and identity-capture failure
terminates the new unowned process without persisting state.


Configuration and state snapshots now use a shared atomic persistence boundary. Writes use same-directory fsynced temporary files followed by atomic replacement, while audit JSONL uses a serialized fsynced append. Cross-process advisory locks have a bounded deadline, nonblocking jittered polling, and reject nested persistence locks to avoid lock-order deadlocks; transactional YAML mutation preserves concurrent changes.

Audit hardening now minimizes recorded tool data and broadens secret sanitation for sensitive keys, command flags, common provider tokens, bearer values, and PEM material. Tool output, raw command arguments, and exception messages are not persisted or returned through MCP failure details.


SSH command planning now uses a shared strict network-input boundary. Tunnel and remote-profile plans reject option-like or malformed hosts/users, validate ports, accept only credential-free HTTP(S) endpoint URLs, render IPv6 forwarding safely, and shell-quote the remote `aiplane` command.


MCP stdio now fails closed for writes: the server defaults to read-only, operator startup must explicitly pass `--allow-writes`, and each actual mutation must also carry `confirm=true`. Blocked attempts never reach domain managers and are audited without raw payloads.

The CLI process boundary now redacts expected error text, suppresses unexpected exception details by default, handles broken pipes quietly, and returns 130 for interruption. `--debug` or `AIPLANE_DEBUG=true` is an explicit diagnostic opt-in and may expose sensitive local traceback context.


Platform behavior is now an explicit capability contract rather than scattered OS checks. Portable operations work independently of mutation helpers; native Ubuntu/Debian is the supported runtime-helper mutation path, WSL is inspection-only for those helpers, and non-Linux hardware discovery skips Linux commands with visible coverage notes.

Model catalog persistence is isolated in `ModelCatalogStore`, provider reconciliation remains in `ModelRefreshCoordinator`, Azure retail pricing is an injectable HTTP service, and Azure CLI execution/redaction/timeouts are a separate adapter. Structural tests prevent those responsibilities returning to the large domain modules.

The external MVP/adoption review was evaluated against current code and recorded as [Product, Adoption, and Monetization Backlog — July 2026](product-adoption-backlog-2026-07.md), including services-first monetization and evidence gates for team/enterprise work.


DOC-1 is complete: public onboarding examples use concrete export targets, the empty README workflow heading is removed, and focused contract tests enforce concrete export commands, nonempty sections, and sequential workflow numbering.


The positioning and default-help pass is complete. README, package metadata, user entrypoints, strategy, launch review, demo framing, and CLI help lead with the environment doctor and configuration compiler outcome. Top-level help groups all commands into Core workflow, Advanced and supporting, and Experimental tiers, prints one safe next command, and fails its contract test if a command is unclassified.


Standard no-clone installation and release automation are implemented. Versioned GitHub Release wheels are the declared evaluation channel; normal CI validates `pip`, `pipx`, and `uv tool` install/verify/upgrade-or-replace/uninstall lifecycles on Linux, macOS, and Windows. Tag builds must match package version, rebuild wheel and sdist, pass all installer checks, and only then create the release. Bare package-index commands remain deliberately undocumented as available until trusted publishing is enabled and verified.


README and package metadata now keep the environment-doctor/configuration-compiler wedge dominant throughout the page, not only in the opening. Broad parallel execution tracks and specialist feature inventories were replaced by a subordinate advanced/experimental maturity link; package keywords now emphasize environment diagnostics, configuration, and reproducibility. A final P0 public-surface consistency sweep remains explicitly scheduled after items 4-9.


The P0 platform CI matrix is implemented. Every Ubuntu, macOS, and Windows packaging job runs the synthetic capability suite and a built-wheel portable workflow from clean temporary workspaces through pip, pipx, and uv. The smoke covers bootstrap, validation, hardware discovery, recommendation, policy, and offline deterministic export. Unsupported runtime mutations and Windows SSH lifecycle status/start/stop fail with `unsupported_platform` before helper execution, process spawn, or state access; tunnel planning remains portable.


P0.9 practical threat modeling is complete. The tracked model covers credential references, redaction and debug limits, generated-config disclosure, external helper boundaries, two-stage MCP write guards, identity-safe tunnel ownership, unsigned profile trust, and local audit sensitivity. Every control row cites deterministic regression tests and every row states its residual limitation. Focused security validation passes 62 tests.

An interim P0 README/documentation consistency sweep followed items 8-9. It corrected quickstart's stale “three next commands” wording to its tested one-action contract, removed remaining positive “control plane” positioning from user/project entrypoints, aligned help and strategy with the narrow product promise, and corrected the P0 range after converting item 10 into an unnumbered gate. This is not the final gate result: repeat the sweep after the three user demonstrations. Focused consistency gate: 76 passed; full suite: 449 passed.
