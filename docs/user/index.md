# User Documentation

This page mirrors [README.md](README.md) for tools that link to `index.md`.
It is focused on AI setup and environment operations (setup, migration, and model/runtime pairing) so teams can spend more time on model work.

## Start Here

`aiplane` is a control-plane CLI for self-managed AI development environments: it plans, prepares, and connects model runtimes rather than replacing your IDE assistant, chat UI, or model-serving endpoint.


- [Practical Overview](overview.md): what `aiplane` does, terminology, implemented capabilities, and first useful flows.
- [Practical Workflows](workflows.md): end-to-end recipes for local Ollama, Continue, MCP, refresh, remote endpoints, stacks, cloud planning, and troubleshooting.
- [Setup](setup.md): install `aiplane` with local Python, `venv`, Conda, or Docker CLI images; also covers profile execution modes.
- [External Toolchain](tools.md): run setup/doctor checks and inspect prerequisite CLIs such as Azure CLI, OpenTofu, Docker, kubectl, Helm, SSH, Ansible, and runtime host tools.
- [Providers](providers.md): configure and check model providers such as Ollama,
  Ollama Cloud, OpenAI, Anthropic, and Azure OpenAI.
- [Model Sources and Runtimes](runtime-model-map.md): understand catalogs, runtimes, lifecycle helper commands, and runtime bundle plans.
- [Model Capabilities](model-capabilities.md): understand task suitability scores
  shown by model list/show and hardware recommendations.
- [Benchmarks](benchmarks.md): run small local smoke tests and understand how
  benchmark scores are calculated.
- [Hardware](hardware.md): discover local CPU/RAM/GPU resources and configure
  hardware/resource profiles.
- [Machines, Stacks, and Orchestrators](machines-and-stacks.md): work with local, shared workstation, Azure, self-managed machines, stack lifecycle, and orchestrator bindings.
- [Integrations](integrations.md): VS Code/Continue setup and IDE/CLI config
  snippets for local or remote model endpoints.
- [Cloud Deployment](cloud-deployment.md): plan and check Azure targets from the
  local CLI.
- [MCP Adapter](mcp.md): run the MCP server for agent/tool access to `aiplane`, including guarded write tools.
- [aiplane skill](../../skills/aiplane/SKILL.md): assistant workflow guidance for Codex-style skill-capable agents.

## Main Commands

```bash
aiplane profiles list
aiplane profiles validate
aiplane environment doctor
aiplane providers list
aiplane models refresh --provider huggingface --query text-generation --limit 25 --dry-run
aiplane tools doctor
aiplane integrations roles continue
```

Project strategy, contributor notes, and roadmap details live under `docs/project/`,
not in the user documentation.

## Profile Selection

Most commands accept `--profile`, but it is optional. `aiplane` resolves the profile in this order:

1. `--profile <name>` on the command.
2. `AIPLANE_PROFILE` if set.
3. `default_profile` in the local `.aiplane/config.yaml`.
4. The only available profile, when exactly one exists.

If no profile exists, start with the local AI quickstart:

```bash
aiplane quickstart local-coding
aiplane quickstart local-coding --dry-run
```

This uses the same lower-level bootstrap path as `aiplane profiles bootstrap-local`: it copies the shipped `local-dev` template into `profiles/local-dev`, validates it, can attempt bounded provider discovery into ignored `models.discovered.yaml`, runs the local doctor when the profile exists, can execute a runtime-helper model pull with `--pull-model` or preview it with `--dry-run --pull-model`, and prints the next safe export commands. Use `aiplane profiles bootstrap-local --no-discovery` when you only want the editable profile files, or `--dry-run` to preview the create/discovery steps.

Use `--profile` only when you need to override the default for one command.
