# aiplane

`aiplane` is a CLI for setting up and checking AI coding environments. It keeps
the practical bits in one place: Python environment, provider configuration,
approved models, hardware targets, Docker settings, policy checks, and IDE/CLI
integration snippets.

The tool starts with local setups, but the same profile format is intended to
cover shared GPU workstations and cloud-hosted model endpoints. It is not a code
assistant itself; it configures and verifies the tools you already use.

## What This Is

`aiplane` is a control-plane CLI for self-managed AI development environments.
It helps you describe, inspect, prepare, and connect local or remote model
runtimes across laptops, shared GPU workstations, Docker hosts, cloud VMs, and
cluster targets.

The core job is repeatable AI environment setup:

- discover hardware and machine capacity;
- choose model/runtime combinations that fit the target;
- install, start, stop, and check supported runtimes;
- pull or refresh selected models;
- plan/setup/export IDE and CLI configuration for tools such as Continue, Cline,
  Aider, Zed, and MCP-capable clients;
- keep model, provider, runtime, machine, and endpoint choices in profiles.

It is intentionally not a coding agent, chat UI, model marketplace, or production
LLM gateway. Those tools sit above or beside it. `aiplane` focuses on the
operational layer that makes self-managed model environments reproducible and
connectable.

## Core Terms

- **Provider**: a runtime or API that can supply models, such as local Ollama,
  Ollama Cloud, OpenAI, Anthropic, or Azure OpenAI. A provider knows how models
  are discovered, authenticated, and called.
- **Model**: a specific model identifier exposed by a provider, such as
  `qwen2.5-coder:0.5b` on Ollama or an approved cloud model/deployment.
- **Profile**: a YAML configuration set for one workflow or target machine. It
  chooses environment, provider, model, hardware, tools, approvals, and repo
  policy.
- **Doctor**: a readiness check. It explains whether a provider/model/profile is
  usable now by checking services, local models, API keys, and config.

## Installation and Local Setup

Start from the project directory:

```bash
cd aiplane
```

### Option 1: Temporary `PYTHONPATH`

Use this when you want to run the CLI without installing the package:

```bash
PYTHONPATH=src python -m aiplane profiles list
```

If `python -m aiplane ...` fails with `No module named aiplane`, this is the
missing step.

### Helper Script

A setup helper is available at `scripts/setup_env.sh` for local Python, `venv`,
Conda, and Docker CLI-image installation flows. It supports editable/source-linked
installs with `--editable` and static/snapshot installs with `--static`. See
[docs/user/setup.md](docs/user/setup.md) for full usage. Provider/runtime setup can be driven through `aiplane runtimes install/start/stop/pull/...`, backed by `scripts/provider_helper.sh`; see [docs/user/providers.md](docs/user/providers.md) and [docs/user/runtime-model-map.md](docs/user/runtime-model-map.md). Hardware/resource configuration is covered in [docs/user/hardware.md](docs/user/hardware.md), and self-managed machine/stack workflows are covered in [docs/user/machines-and-stacks.md](docs/user/machines-and-stacks.md). Cloud target planning starts in [docs/user/cloud-deployment.md](docs/user/cloud-deployment.md). User documentation starts at [docs/user/index.md](docs/user/index.md), with a practical overview at [docs/user/overview.md](docs/user/overview.md), with practical workflows at [docs/user/workflows.md](docs/user/workflows.md). VS Code/Continue and IDE/CLI config export are covered in [docs/user/integrations.md](docs/user/integrations.md). Project strategy and contributor notes live under `docs/project/`.

### Option 2: Local Python Install

Use this when you want `aiplane` installed into the current Python environment.
Editable mode is best for development; static mode is a package snapshot that only
updates when you reinstall.

```bash
python -m pip install -e .  # source-linked development install
python -m aiplane profiles list
aiplane profiles list

# Static snapshot install instead:
python -m pip install .
```

### Option 3: Python `venv`

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
aiplane profiles list
```

To make tool execution use this venv, set `active: venv` in
`profiles/local-dev/environment.yaml`.

### Option 4: Conda

```bash
# Recommended helper path: source it if you want Conda activation to persist.
source scripts/setup_env.sh --mode conda --conda-env aiplane --action install --editable

# If you execute the helper normally, activate afterwards.
scripts/setup_env.sh --mode conda --conda-env aiplane --action install --editable
source .aiplane/activate-conda-aiplane.sh
# or: conda activate aiplane

# Manual path:
conda create -n aiplane python=3.13 -y
conda activate aiplane
python -m pip install -e .  # source-linked development install
# or: python -m pip install .  # static snapshot install
aiplane profiles list

# Verify Conda environments with this, not `conda list env`.
conda env list
```

To make tool execution use conda, set `active: conda` and configure the env name
in `profiles/local-dev/environment.yaml`:

```yaml
active: conda
modes:
  conda:
    executable: conda
    name: aiplane
```

### Option 5: Docker CLI Image

The setup helper can also build a Docker image that runs the `aiplane` CLI:

```bash
# Source-linked development image: mounts this checkout when the container runs.
scripts/setup_env.sh --mode docker --action install --editable --docker-image aiplane:dev

# Static snapshot image: copies this checkout into the image; rebuild to update.
scripts/setup_env.sh --mode docker --action install --static --docker-image aiplane:snapshot

# Verify an existing image.
scripts/setup_env.sh --mode docker --action doctor --docker-image aiplane:dev
```

Editable Docker mode keeps source changes visible by mounting the current checkout
at `/workspace` and installing it inside the container command. Static Docker mode
bakes a copy of the checkout into the image under `/opt/aiplane`.

### Option 6: Docker Execution Mode

This is different from installing the CLI inside Docker. Here, the `aiplane` CLI
runs in your current environment, but configured tools execute inside Docker. Set
`active: docker` in `profiles/local-dev/environment.yaml`, then inspect the exact
Docker command before running tools:

```bash
aiplane environment plan python --version
```



## Local Config

Machine/user-specific defaults can live in `.aiplane/config.yaml`, which is
ignored by git. Create it from the checked-in template:

```bash
aiplane config templates
aiplane config init --template local
aiplane config show
```

Use this file for settings such as `profiles_dir`. Command-line flags and
environment variables still take precedence.

## Profiles and Templates

Checked-in defaults live under `profile-templates/`. Editable profiles default to
`profiles/`, which is intended as local/user state. Create a new profile by copying
a template, then customize the copy:

```bash
aiplane profiles templates
aiplane profiles create my-local --template local-dev
aiplane profiles show my-local
aiplane profiles show --selected
```

`profiles show` defaults to the effective default profile when no name is passed.
The full output starts with `name`, `default`, and a `selected` summary. Use
`--selected` when you only want active/enabled/default choices from each block.

This keeps shipped defaults separate from user/team-specific profile changes.

You can store editable profiles elsewhere with either a global CLI option or an
environment variable:

```bash
aiplane --profiles-dir ~/.config/aiplane/profiles profiles create my-local --template local-dev
export AIPLANE_PROFILES_DIR=~/.config/aiplane/profiles
aiplane profiles list
```

Back up that external profiles directory yourself if it contains important local
or team configuration.

Show or set the default profile so commands can omit `--profile`:

```bash
aiplane config default-profile
aiplane config default-profile my-local
aiplane config get profiles_dir
aiplane config set profiles_dir /path/to/profiles
aiplane profiles list
aiplane profiles show
aiplane profiles show --selected
aiplane profiles validate
aiplane models list --group-by provider
aiplane models defaults --group-by provider
```

`profiles list` marks the effective default with `*`. `profiles show` without a
name shows that same effective default. The default profile is
resolved from `AIPLANE_PROFILE`, then local config, then the only available profile when there is exactly one.


## Quick Start

### Profile Selection

Most commands accept `--profile`, but it is optional. `aiplane` resolves the profile in this order:

1. `--profile <name>` on the command.
2. `AIPLANE_PROFILE` if set.
3. `default_profile` in the local `.aiplane/config.yaml`.
4. The only available profile, when exactly one exists.

If no profile exists, create one with:

```bash
aiplane profiles create local-dev --template local-dev
```

Use `--profile` only when you need to override the default for one command.


After one of the setup options above, use this sequence to prove the main pieces
work. Each block is independent; skip the ones you do not need yet.

### 1. Confirm the CLI and active profile

```bash
aiplane profiles list
aiplane profiles show --selected
aiplane profiles validate
```

These commands confirm that `aiplane` can load its profiles, show the effective
default profile, and validate cross-references between providers, models,
hardware, environment modes, and targets.

More detail: [Profiles and setup](docs/user/setup.md), [Practical overview](docs/user/overview.md).

### 2. Check the execution environment

```bash
aiplane environment show
aiplane environment active
aiplane environment plan python --version
```

This shows which execution mode the profile will use, such as system Python,
`venv`, Conda, or Docker execution mode. `environment plan` prints the exact
command wrapper before anything is run.

More detail: [Setup](docs/user/setup.md), [Hardware and Docker resource settings](docs/user/hardware.md).

### 3. Prepare a tiny local Ollama model

```bash
aiplane runtimes install ollama --dry-run
aiplane runtimes start ollama
aiplane runtimes pull ollama --model qwen-tiny
aiplane models doctor
aiplane models test --task analysis --dry-run qwen-tiny
```

This path uses `aiplane` to delegate common Ollama setup tasks: install/check the
runtime, start it, pull the configured tiny model, and verify model readiness. Use
`--dry-run` first when you want to inspect delegated native commands before
changing the machine.

More detail: [Providers and runtime helpers](docs/user/providers.md), [Model sources and runtimes](docs/user/runtime-model-map.md), [Benchmarks](docs/user/benchmarks.md). To refresh later, use `aiplane runtimes update-installed all --dry-run` for runtimes, `aiplane runtimes repull ollama --dry-run` for already-pulled Ollama models, and `aiplane models refresh --provider ollama --dry-run` to refresh source-provider catalog entries in the profile.

### 4. Send a prompt or start provider-native chat

```bash
aiplane run --dry-run "summarize this workspace"
aiplane run --model qwen-tiny "explain this setup"
aiplane chat --dry-run
aiplane chat
```

`aiplane run` sends one prompt through the profile's configured model defaults or
an explicitly selected model. `aiplane chat` is a lightweight wrapper around a
provider-native chat command; today it resolves local Ollama model aliases and
launches `ollama run ...`. This is useful for quick checks, not a full coding
agent session.

Model defaults can be inspected or changed with:

```bash
aiplane models defaults
aiplane models use chat_model llama-8b
aiplane models use autocomplete_model qwen-coder-1.5b-base
aiplane models use embedding_model nomic-embed-text
aiplane models use reasoning_model deepseek-r1-1.5b
```

More detail: [Integrations](docs/user/integrations.md), [Model capabilities](docs/user/model-capabilities.md).

### 5. Connect VS Code through Continue

```bash
aiplane integrations plan continue
aiplane integrations setup continue --dry-run
aiplane integrations export continue
```

`plan` explains which chat, autocomplete, and embedding models will be used.
`setup --dry-run` previews runtime/model preparation, such as starting Ollama or
pulling selected models. `export` prints the Continue config bundle. For local
Ollama, the endpoint is usually `http://localhost:11434/v1`.

More detail: [IDE and CLI integrations](docs/user/integrations.md), [MCP adapter](docs/user/mcp.md).

### 6. Expose `aiplane` as MCP tools

```bash
aiplane integrations export vscode-mcp
aiplane integrations export continue-mcp
aiplane mcp manifest
aiplane mcp serve
```

The MCP exports print client config snippets that let an MCP-capable IDE or agent
query `aiplane` for profiles, providers, model recommendations, hardware, tunnel
plans, and guarded write tools. This is separate from the model inference
endpoint used by Continue or another coding assistant.

More detail: [MCP adapter](docs/user/mcp.md).

### 7. Inspect policy and audit output

```bash
aiplane policy explain --action tool:read_file
aiplane audit tail
```

Policy commands explain why an operation is allowed, denied, or requires
approval. Audit output shows recent JSONL events for operations that write or run
through guarded paths.

Tool commands still run through policy and audit checks. Use `aiplane policy explain` and `aiplane audit tail` to inspect decisions and write activity.

If you did not install the package, prefix commands with `PYTHONPATH=src python -m`:

```bash
PYTHONPATH=src python -m aiplane profiles list
```

## Local Code Tasks

Use `aiplane code` to run simple local coding workflows against files in the
workspace. Commands print output only; they do not modify files. Use `--dry-run`
to inspect the prompt without calling a model.

```bash
aiplane code analyze src/aiplane/model_catalog.py
aiplane code analyze --dry-run src/aiplane/model_catalog.py
aiplane code complete --line 20 src/aiplane/model_catalog.py
aiplane code write --task "add a function that validates email"
```

The first implementation executes only local Ollama models. Cloud model execution
for code tasks remains disabled until patch review, stronger redaction, and
escalation policy are in place.

## Execution Environments

The active command environment is configured in `profiles/<profile>/environment.yaml`.
The MVP supports:

- `system`: run commands directly in the local workspace.
- `venv`: rewrite Python commands to use `<workspace>/.venv/bin/python`.
- `conda`: prefix commands with `conda run -n <name>`.
- `docker`: run commands with `docker run --rm -v <workspace>:/workspace -w /workspace <image> ...`.


You can inspect and change the active execution mode through the CLI:

```bash
aiplane environment list
aiplane environment active
aiplane environment use venv
aiplane environment plan python --version
```

`environment use` persists the selected mode in the profile's `environment.yaml`.

Change `active` in the profile to switch execution mode without code changes.
Use `aiplane environment plan ...` to inspect the exact command before running tools.

Docker resource mapping is configured in the same file. Examples:

```yaml
active: docker
modes:
  docker:
    image: nvidia/cuda:12.4.1-runtime-ubuntu22.04
    workdir: /workspace
    cpus: 8
    memory: 24g
    gpus: all
    shm_size: 2g
    env: [NVIDIA_VISIBLE_DEVICES, NVIDIA_DRIVER_CAPABILITIES]
    network: bridge
```

For AMD/Intel GPU or special local devices, use explicit device passthrough:

```yaml
active: docker
modes:
  docker:
    image: python:3.13-slim
    devices: [/dev/dri]
```

GPU support depends on the host Docker runtime: NVIDIA requires the NVIDIA
Container Toolkit; other GPU stacks generally require device mounts and matching
drivers/libraries in the image.

## Model Catalog

Models and providers are configured in `profiles/<profile>/models.yaml`. Local
Ollama models can be listed, checked, pulled, and smoke-tested from the CLI:

```bash
python -m aiplane models list
python -m aiplane models show qwen-tiny
python -m aiplane models doctor
python -m aiplane models pull qwen-tiny
python -m aiplane models test --task analysis --dry-run qwen-tiny
python -m aiplane models test --task write qwen-tiny
```

The default laptop smoke-test model is `qwen2.5-coder:0.5b` via Ollama. Cloud
models are listed but disabled by default. Cloud configuration stores only env var
names, never secret values, for example `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`,
`AZURE_OPENAI_API_KEY`, and `AZURE_OPENAI_ENDPOINT`.

Use `models doctor` to check whether Ollama is reachable, local models are
pulled, and cloud provider key environment variables are present.

## Ollama Setup

Install Ollama from the official download page, then make sure the service is
running on the default endpoint `http://localhost:11434`.

Basic local setup:

```bash
ollama --version
ollama serve
```

In another terminal, pull the tiny coding model used by the default profile:

```bash
ollama pull qwen2.5-coder:0.5b
```

Check the platform can see Ollama and the configured models:

```bash
aiplane models doctor
```

Run dry-run prompts without calling the model:

```bash
aiplane models test --task analysis --dry-run qwen-tiny
aiplane models test --task completion --dry-run qwen-tiny
aiplane models test --task write --dry-run qwen-tiny
```

Run an actual local model smoke test after Ollama is running and the model is
pulled:

```bash
aiplane models test --task write qwen-tiny
```

If you see `Connection refused`, Ollama is not reachable at the configured
endpoint. Start it with `ollama serve`, verify with `aiplane models doctor`, or add `--dry-run` to preview prompts without calling the
model.

To analyze a local file:

```bash
aiplane models test --task analysis --target src/aiplane/model_catalog.py qwen-tiny
```

If Ollama is running somewhere else, change the endpoint in
`profiles/local-dev/models.yaml`:

```yaml
providers:
  ollama:
    endpoint: http://localhost:11434
```

The smallest default model is `qwen-tiny`, mapped to `qwen2.5-coder:0.5b`. For a
slightly stronger laptop model, pull and use `qwen-small`, mapped to
`qwen2.5-coder:1.5b`.
