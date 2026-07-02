# Strategy

For status tracking and future milestones, see [Project Roadmap](roadmap.md). This document explains the product boundary and architecture direction; `roadmap.md` is the source of truth for implemented vs planned status.

## Project Quality Principles

`aiplane` should be a professional-grade, community-first open-source tool: reliable, well documented, testable, inspectable, and respectful of the complexity of real AI coding environments.

Good design choices flow from that standard:

- Prefer transparency over magic. Significant operations should be inspectable before they run.
- Prefer composability over replacement. Integrate with tools developers already use rather than duplicating them.
- Prefer explicitness over convenience at the cost of control. Profile-driven configuration is intentionally visible.
- Prefer depth over breadth. Do the control-plane job well before expanding scope.

## Positioning

`aiplane` is a configuration and operations control-plane CLI for local, remote, VM, and cloud-adjacent AI development environments.

It is not a coding agent, IDE assistant, chat UI, inference server, model marketplace, model proxy, or cloud platform. Existing tools such as Continue, Cline, Cursor, Codex-like CLIs, Claude Code, Aider, OpenHands, Ollama, LM Studio, vLLM, TGI, llama.cpp, LocalAI, OpenAI, Anthropic, and Azure OpenAI already cover large parts of those domains. `aiplane` should configure, check, plan, export, and govern those pieces rather than replacing them.

## Core Problem

AI coding setups are fragmented:

- local runtimes have different install, model, GPU, and API behavior;
- managed providers have different keys, model catalogs, deployment names, and policy constraints;
- IDEs and CLI agents require separate configuration;
- teams need repo-sensitive rules for when cloud or remote endpoints are allowed;
- hardware capability matters: CPU, RAM, GPU, VRAM, container runtime, and device passthrough all change what models are practical;
- repeatable setup requires doctors, plans, exports, and tests that explain what works now and what is only planned.

`aiplane` solves this by making those choices explicit and profile-driven.

## Product Boundary

### Own

- Profile-based configuration for providers, models, runtimes, hardware, machines, stacks, tools, credentials references, approvals, and policy.
- Environment planning for system Python, `venv`, Conda, and Docker execution modes.
- Readiness checks through `doctor` commands.
- Provider/model discovery and profile-owned model entries.
- Hardware and machine inventory with model-fit recommendations.
- Stack planning that binds a machine, runtime, primary model, optional orchestrator, and access policy.
- Non-mutating config exports for IDEs, CLI agents, MCP clients, tools, and starter deployment artifacts.
- Narrow, auditable lifecycle helpers where the native tool boundary is clear.
- Local audit, secret redaction, and approval foundations.

### Do Not Own

- A full coding agent or IDE assistant.
- A custom inference runtime.
- A general model proxy or production gateway.
- A marketplace extension as the primary integration path.
- Hidden cloud deployment, broad shell execution, or secret writes through MCP.

## Core Concepts

- **Provider / model source**: where model ids, files, or deployments come from. Examples: Ollama library, Hugging Face Hub, GGUF files, OpenAI, Anthropic, Azure OpenAI.
- **Runtime**: software that loads model weights or serves inference. Examples: Ollama, vLLM, TGI, llama.cpp server, LocalAI, Transformers, LM Studio.
- **Runtime endpoint**: the URL exposed by a runtime, often OpenAI-compatible `/v1`.
- **Model**: a profile-approved alias mapped to a source-native model id or deployment plus metadata.
- **Profile**: editable YAML configuration for one workflow or machine context.
- **Machine**: normalized hardware, OS, runtime, and capacity description.
- **Stack**: operational binding of machine, runtime, primary model, optional orchestrator, and access policy.
- **Target**: deployment or access target such as Azure VM, AKS, Docker host, or SSH tunnel plan.
- **Integration export**: generated config text for an IDE or CLI tool. It does not edit the target tool.
- **MCP adapter**: stdio tool surface for structured `aiplane` inspection and guarded mutations.

## Architecture Direction

`aiplane` should support the same configuration model across local PCs, shared workstations, local VMs, cloud VMs, and Kubernetes or cloud-adjacent targets. The key separation is:

- model source and provider identity;
- runtime and endpoint shape;
- machine and hardware capacity;
- stack binding and access policy;
- integration export for the user-facing tool.

Remote deployment should start as planning, validation, and starter artifact generation around official tools: OpenSSH, Docker/Compose, Azure CLI, OpenTofu/Terraform, Pulumi, Vagrant, Packer, Dev Container CLI, Ansible, kubectl, and Helm. Direct mutation stays guarded, previewable, and auditable.

## Post-Merge Architecture Priorities

The merged MVP has enough surface area that maintainability now matters as much as feature growth. Near-term architecture work should focus on consolidation and clear contracts:

- Keep source/provider, runtime, endpoint, profile model alias, machine, stack, MCP tool, and agent skill concepts separate in code as well as docs.
- Reduce duplication between CLI parser options, MCP schemas, output filters, and manager method signatures. Model-list filters, integration roles, and provider/runtime compatibility are the first places to centralize.
- Move runtime/source compatibility decisions toward Python catalog services and keep shell helpers focused on invoking official tools.
- Treat MCP as a structured adapter over existing managers, not a parallel implementation of CLI behavior.
- Treat skills as versioned assistant workflow guidance, not live tools. A skill can explain when to call MCP, but it should not duplicate MCP schemas.
- Treat orchestrators as external frameworks. `aiplane` should generate role/endpoint/policy config and readiness checks, not run autonomous agent conversations itself.
- Keep tests close to behavior boundaries. As the code is split, tests should move from one large MVP file into focused modules for profiles/config, provider/model catalog, runtimes, integrations, MCP, orchestrators, stacks, and CLI smoke coverage.

## Execution Fabric Tracks

The current product direction is organized around three execution-fabric tracks.

### Agentic Environments and Workflows

Create, configure, and validate external agent applications that use model endpoints and credentials managed by `aiplane`. Current support includes starter agent templates and non-mutating `agents templates/plan/export` commands. Future work should generate fuller project directories, add run/test checks, and cover richer research, news, coding, and multi-agent workflows.

### Provisioning and Automation Tools

Interface cleanly with tools that prepare machines and environments instead of replacing them. Current support includes readiness checks plus non-mutating plans and starter exports for Vagrant, Packer, OpenTofu/Terraform, Pulumi, Dev Containers, Ansible, and related infrastructure tools. Future work should harden provider-specific modules and keep remote mutation behind explicit plans, SSH controls, and audit output.

### Benchmarking and Evaluation

Benchmark models and endpoints using the right tool in the right place. Current support includes smoke/custom model checks plus benchmark framework list, doctor, install-plan, and plan helpers. Future work should add placement metadata, latency/throughput/token metrics, repeated-run summaries, and comparison views.

## Success Criteria

`aiplane` is successful if a user can say:

1. Here is my hardware and privacy posture.
2. Here are the providers, runtimes, credentials references, and endpoints I am allowed to use.
3. Here are the approved models for this profile or repo.
4. Configure my environment and tools without hiding important choices.
5. Tell me what works and what does not.
6. Export my chosen IDE, CLI assistant, MCP client, stack artifact, or agent scaffold with the right configuration.
7. Keep policy, approvals, and audit consistent.

If it becomes another chat UI, IDE assistant, inference engine, or hidden cloud deployment tool, it has left its strongest lane.
