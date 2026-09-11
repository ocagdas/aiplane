# Architecture

## Core Concepts

- **Provider / model source**: where model ids, files, or deployments come from. Examples: Ollama library, Hugging Face Hub, GGUF files, OpenAI, Anthropic, Azure OpenAI.
- **Runtime**: software that loads model weights or serves inference. Examples: Ollama, vLLM, TGI, llama.cpp server, LocalAI, Transformers, LM Studio.
- **Runtime endpoint**: the URL exposed by a runtime, often OpenAI-compatible `/v1`.
- **Model**: a profile-approved alias mapped to a source-native model id or deployment plus metadata.
- **Profile**: editable YAML source of truth for an intended workflow or machine class; secrets and runtime-owned state remain external.
- **Profile render**: canonical read-only JSON evidence assembled from a profile for validation, comparison, CI, or archival; it is not restore input or target-tool configuration.
- **Replay**: validate a reviewed profile against another machine, explain destination drift, and compile fresh exports. Identical or capability-equivalent machines may satisfy the same profile despite non-material hardware differences.
- **Machine**: normalized hardware, OS, runtime, and capacity description.
- **Stack**: operational binding of machine, runtime, primary model, optional orchestrator, and access policy.
- **Target**: deployment or access target such as Azure VM, AKS, Docker host, or SSH tunnel plan.
- **Integration export**: target-tool configuration text compiled from a selected profile. It prints for review and does not install, edit, start, or provision the target tool or runtime.
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

