# User Documentation

These docs cover day-to-day use of `aiplane`: installing it, configuring providers and models, checking hardware, connecting IDEs/CLIs, and exposing MCP tools.

## Start Here

- [Practical Overview](overview.md): what `aiplane` does, terminology, implemented capabilities, and first useful flows.
- [Practical Workflows](workflows.md): end-to-end recipes for local Ollama, Continue, MCP, refresh, remote endpoints, stacks, cloud planning, and troubleshooting.
- [Setup](setup.md): install `aiplane` with local Python, `venv`, Conda, or Docker CLI images; also covers profile execution modes.
- [External Toolchain](tools.md): check and install prerequisite CLIs such as Azure CLI, OpenTofu, Docker, kubectl, Helm, SSH, and Ansible.
- [Providers](providers.md): configure and check model providers such as Ollama Library, Hugging Face, GGUF sources, Azure Speech voices, and manual/local sources.
- [Model Sources and Runtimes](runtime-model-map.md): understand catalogs, runtimes, preferred runtimes, lifecycle helper commands, and runtime bundle plans.
- [Model Capabilities](model-capabilities.md): understand task suitability scores shown by model list/show and hardware recommendations.
- [Benchmarks](benchmarks.md): run small local smoke tests and understand how benchmark scores are calculated.
- [Hardware](hardware.md): discover local CPU/RAM/GPU resources and configure hardware/resource profiles.
- [Machines, Stacks, and Orchestrators](machines-and-stacks.md): work with local, shared workstation, Azure, self-managed machines, stack lifecycle, and orchestrator bindings.
- [Integrations](integrations.md): VS Code/Continue setup and IDE/CLI config snippets for local or remote model endpoints.
- [MCP Adapter](mcp.md): run the MCP server for LLM/agent access to `aiplane`, including guarded write tools.
- [Cloud Deployment](cloud-deployment.md): plan and check Azure targets from the local CLI.

## Common First Commands

```bash
aiplane profiles list
aiplane profiles show --selected
aiplane environment show
aiplane providers list
aiplane models refresh --provider huggingface --query text-generation --limit 25 --dry-run
aiplane integrations roles continue
aiplane integrations export vscode-mcp
```

Project strategy, developer policy, and future roadmap details live under [docs/project](../project/README.md), not in the user documentation.

## Profile Selection

Most commands accept `--profile`, but it is optional. `aiplane` resolves the profile in this order:

1. `--profile <name>` on the command.
2. `AIPLANE_PROFILE` if set.
3. `default_profile` in the local `.aiplane/config.yaml`.
4. The only available profile, when exactly one exists.

If no profile exists, bootstrap the default local profile with:

```bash
aiplane profiles bootstrap-local
```

This copies the shipped `local-dev` template into `profiles/local-dev`, validates it, and attempts a bounded provider discovery refresh into ignored `models.discovered.yaml`. Use `--no-discovery` when you only want the editable profile files, or `--dry-run` to preview the create/discovery steps.

Use `--profile` only when you need to override the default for one command.
