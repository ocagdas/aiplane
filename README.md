# aiplane

`aiplane` is a control-plane CLI for building and checking managed LLM environments. It helps teams keep model providers, local runtimes, machines, profiles, credentials, IDE exports, automation tools, and benchmark workflows in one understandable place.

It is not a coding agent, chat UI, inference server, model marketplace, or cloud platform. It coordinates those pieces so local, remote, VM, and cloud-adjacent AI development environments can be planned, reproduced, checked, and connected safely.

## Why It Exists

Self-managed AI development setups quickly become a mix of:

- local runtimes such as Ollama, vLLM, TGI, llama.cpp, LocalAI, LM Studio, or Transformers;
- managed providers such as OpenAI, Anthropic, Azure OpenAI, and OpenAI-compatible endpoints;
- IDE and agent tools such as Continue, Cline, Zed, Aider, Codex-like CLIs, and MCP-capable clients;
- machines ranging from laptops to shared GPU boxes, local VMs, remote VMs, and Kubernetes or cloud targets;
- provisioning tools such as Ansible, Vagrant, Packer, OpenTofu/Terraform, Pulumi, Docker, Dev Containers, kubectl, Helm, and Azure CLI;
- benchmark tools that may run locally while targeting a remote endpoint, or directly on the GPU host.

`aiplane` gives that operational layer a profile-driven CLI: inspect what exists, plan what should happen, export config for other tools, and keep risky operations explicit.

## Current Status

`aiplane` is pre-1.0 and suitable for early beta testing by engineers who are comfortable reading plans and generated config before applying changes. The current branch is focused on **agentic environment setup and remote tooling integration**.

Implemented foundations include:

- profile loading, validation, local config, ignored credentials, and selected/default summaries;
- environment planning for system Python, `venv`, Conda, and Docker execution mode;
- `environment doctor` and `tools doctor` readiness checks;
- provider catalogs for local, open-weight, OpenAI-compatible, OpenAI, Anthropic, Azure OpenAI, Ollama Cloud placeholder, Hugging Face, GGUF, and runtime-backed discovery, with no checked-in model aliases;
- ignored generated model caches that are repopulated from provider discovery and can be filtered by role, runtime, capability, RAM/VRAM, benchmark score, and target hardware;
- runtime helper delegation for supported providers such as Ollama;
- machine inventory, hardware discovery, hardware-aware model recommendations, and stack planning;
- integration plan/setup/export for Continue, Cline, Zed, Aider, OpenAI-compatible clients, and MCP client snippets;
- starter agent application scaffolds through `agents templates/plan/export`;
- non-mutating tool plans and starter exports for Vagrant, Packer, OpenTofu/Terraform, Pulumi, Dev Containers, and Ansible;
- benchmark planning helpers for smoke/custom checks, lm-evaluation-harness, vLLM serving benchmarks, and Locust-style load tests.

Still in progress: remote mutation workflows, production service management, provider-specific IaC/playbooks, richer agent templates, distributed benchmark execution, and endpoint authentication/gateway automation.

## Install

From the repository root:

```bash
python -m pip install -e .
aiplane profiles list
```

Without installing the package:

```bash
PYTHONPATH=src python -m aiplane profiles list
```

Create ignored local config when you want machine/user-specific defaults:

```bash
aiplane config init --template local
aiplane config show
```

`config show` reports the active/default config path, profile roots, current/default profile paths, credentials path, and agent artifact path.

## Quick Start

Check the configured profile and environment:

```bash
aiplane profiles list
aiplane profiles show --selected
aiplane profiles validate
aiplane environment doctor
```

Inspect provider state, then populate an ignored local model cache from discovery when needed:

```bash
aiplane providers list
aiplane models refresh --provider huggingface --query text-generation --limit 25 --dry-run
aiplane models list --group-by ownership
aiplane models clear-cache --dry-run
```

Plan a local runtime/model setup before changing the machine. Replace `MODEL_ALIAS` with an alias discovered into `models.generated.yaml` or deliberately promoted into local `models.yaml`:

```bash
aiplane runtimes install ollama --dry-run
aiplane runtimes pull ollama --model MODEL_ALIAS --dry-run
aiplane integrations roles continue
```

Export IDE or agent-tool config after choosing aliases. MCP exports do not need a model alias:

```bash
aiplane integrations export continue --model MODEL_ALIAS
aiplane integrations export vscode-mcp
aiplane mcp manifest
```

Plan an agent application scaffold outside the repo/profile tree:

```bash
aiplane agents templates
aiplane agents plan news-briefing --framework langgraph --model MODEL_ALIAS
aiplane agents export news-briefing --framework langgraph --model MODEL_ALIAS --file agent.py
```

Inspect automation and provisioning tool readiness:

```bash
aiplane tools doctor
aiplane tools plan ansible
aiplane tools export opentofu
aiplane tools export vagrant
```

Plan benchmark tooling:

```bash
aiplane benchmarks list
aiplane benchmarks doctor
aiplane benchmarks plan vllm-serving --model MODEL_ALIAS
```

## The Three Execution Fabric Tracks

The current roadmap is organized around three tracks.

### 1. Agentic Environments and Workflows

Goal: create, configure, and validate external agent applications that use the model endpoints and credentials managed by `aiplane`.

Current capability:

- starter templates for LangGraph and simple OpenAI-compatible Python agents;
- model endpoint selection from configured profile aliases;
- configurable agent artifact root via `--output-dir`, `AIPLANE_AGENT_ARTIFACTS_DIR`, or local config `agent_artifacts_dir`;
- roadmap demo for a news briefing/video agent.

Next work:

- write full agent project directories instead of printing individual files;
- add richer templates for research, news, coding, and multi-agent workflows;
- add run/test lifecycle checks for generated agents;
- define multi-agent coordination across local, network, and cloud targets.

### 2. Provisioning and Automation Tools

Goal: interface cleanly with the tools that prepare machines and environments instead of replacing them.

Current capability:

- readiness checks for Azure CLI, OpenTofu, Terraform, Pulumi, Vagrant, Packer, Docker/Compose, Dev Container CLI, kubectl, Helm, OpenSSH, Ansible, and benchmark helpers;
- non-mutating plans and starter exports for Vagrant, Packer, OpenTofu/Terraform, Pulumi, Dev Containers, and Ansible;
- explicit helper/runtime delegation for supported runtimes.

Next work:

- generate Ansible inventories from known machines;
- harden VM, image, IaC, and Dev Container templates;
- make local install, local VM provisioning, remote VM provisioning, remote PC setup, and cloud provisioning distinct workflows;
- keep remote mutation behind explicit plans, SSH controls, and audit output.

### 3. Benchmarking and Evaluation

Goal: benchmark models and endpoints using the right tool in the right place.

Current capability:

- smoke/custom model checks;
- benchmark tool list/doctor/install/plan helpers;
- initial support for lm-evaluation-harness, vLLM serving benchmarks, and Locust-style load tests.

Benchmark placement depends on the task:

- API/load benchmarks can usually run on the `aiplane` host while targeting a remote endpoint.
- In-process GPU/model benchmarks usually need to run on the remote runtime host.
- Quality/eval benchmarks can run locally or remotely if the model is reachable and datasets/tools are available.

Next work:

- represent `benchmark driver: local | remote | same-host-as-runtime`;
- capture latency, throughput, token metrics, and repeated-run summaries;
- compare benchmark results across models, runtimes, and machines.

## Helper Scripts

The CLI is the normal entry point. Helper scripts exist for bootstrap and runtime operations that are easier to express in shell.

- `scripts/setup_env.sh` prepares ways to run the `aiplane` CLI itself.
  - Supports local Python, `venv`, Conda, and Docker CLI-image flows.
  - Use `--editable` for source-linked development installs.
  - Use `--static` for snapshot installs that update only when rebuilt/reinstalled.
  - Use `--action doctor` to check an existing setup.

- `scripts/provider_helper.sh` performs provider/runtime operations behind CLI wrappers.
  - Used by commands such as `aiplane runtimes install/start/stop/restart/status/pull/list-runtime-models`.
  - Covers supported runtime paths such as Ollama today.
  - Prefer the `aiplane runtimes ... --dry-run` path before direct helper use so profile selection, command rendering, and safety checks stay visible.

- `aiplane environment plan ...` shows how a command would run under the active profile environment.
  - Use it for system, `venv`, Conda, or Docker execution-mode checks.
  - It is non-mutating.

- `aiplane environment doctor` and `aiplane tools doctor` are the first checks to run when setup looks wrong.
  - `environment doctor` checks the current aiplane/profile environment.
  - `tools doctor` checks external tools needed for provisioning, deployment, containers, Kubernetes, remote access, and benchmarks.

More detail: [setup](docs/user/setup.md), [providers and runtime helpers](docs/user/providers.md), [tools](docs/user/tools.md), [runtime map](docs/user/runtime-model-map.md).

## Safety Model

`aiplane` is designed around visible decisions:

- local config and credentials are ignored by git;
- credential commands redact secrets;
- profiles store credential references or environment variable names, not raw keys;
- plans, doctors, exports, and dry runs are preferred before mutation;
- MCP write tools are narrow and audited;
- arbitrary shell/cloud apply through MCP is out of scope.

Project guidance for AI coding tools lives in [docs/project/agent-guidance.md](docs/project/agent-guidance.md). Tools working in this repo must not commit, push, tag, publish, or open PRs.

## Documentation

- [User docs](docs/user/index.md)
- [Setup](docs/user/setup.md)
- [Providers and credentials](docs/user/providers.md)
- [Tools and provisioning](docs/user/tools.md)
- [Integrations](docs/user/integrations.md)
- [Machines and stacks](docs/user/machines-and-stacks.md)
- [Benchmarks](docs/user/benchmarks.md)
- [MCP](docs/user/mcp.md)
- [Roadmap](docs/project/roadmap.md)
- [Project handoff](docs/project/session-handoff.md)

## Contributing

This project is looking for practical contributions from people running local models, remote GPU machines, small team AI environments, or cloud-adjacent agent workflows. Useful areas include:

- testing setup on Ubuntu, macOS, WSL, Conda, Docker, and GPU hosts;
- improving provider/runtime checks;
- adding safe tool plans and starter exports;
- expanding agent templates and benchmark workflows;
- tightening docs when commands or terminology are unclear.

Before opening changes, run:

```bash
PYTHONPATH=src python -m pytest
PYTHONPATH=src python -m aiplane profiles validate local-dev
PYTHONPATH=src python -m aiplane environment doctor --required-only
```

## License

MIT. See [LICENSE](LICENSE).
