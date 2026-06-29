# Public Demo Plan

This plan is for a short public demo of `aiplane` as it exists today. It is intentionally command-first, non-mutating by default, and structured around repeatable setup rather than one-off terminal tricks.

## Intro Voiceover

`aiplane` is a control-plane CLI for AI development environments. It does not try to replace coding agents, model runtimes, IDE extensions, or cloud platforms. Instead, it keeps the operational pieces organized: profiles, providers, model aliases, runtimes, machines, stacks, tool readiness, IDE exports, MCP access, and deployment plans.

The goal is repeatability. A developer should be able to describe the local machine, a remote workstation, or an Azure target; see which models and runtimes fit; generate config for tools like Continue or MCP-capable clients; and review plans before anything mutates a host or cloud account.

## Demo Thesis

Show that `aiplane` is useful because it gives a structured, inspectable path from setup to model selection to tool configuration to local/remote deployment planning.

Key points to say explicitly:

- `aiplane` is a control plane, not another agent.
- Profiles make setups repeatable locally and remotely.
- Discovery and generated aliases are separate from curated model aliases.
- Plans, doctors, exports, and dry runs come before mutation.
- The same model/runtime can be exposed natively, through Docker/Compose-style artifacts, or through an OpenAI-compatible endpoint.

## Three-Minute Cut

### 0:00-0:20 - What It Is

Show the README headline or terminal help:

```bash
PYTHONPATH=src python -m aiplane --help
```

Voiceover:

> This is aiplane: a control-plane CLI for self-managed and managed AI development environments. It keeps profiles, models, runtimes, machines, IDE exports, MCP tools, and deployment plans in one repeatable workflow.

### 0:20-0:45 - Install And Readiness

Show install/setup and doctors:

```bash
python -m pip install -e .
PYTHONPATH=src python -m aiplane profiles validate local-dev
PYTHONPATH=src python -m aiplane environment doctor --required-only
PYTHONPATH=src python -m aiplane tools matrix
```

What to highlight:

- mandatory local prerequisites are checked separately from optional workflow tools;
- `tools matrix` shows complete, partial, and needs-setup workflow categories;
- nothing is provisioned just by inspecting readiness.

### 0:45-1:15 - Provider Discovery And Model Filtering

Show provider discovery and safe generated-alias flow:

```bash
PYTHONPATH=src python -m aiplane models refresh --provider ollama --dry-run --limit 3
PYTHONPATH=src python -m aiplane models list --runtime ollama --role chat --ram-gb 16 --vram-gb 0 --sort-by role --limit 5
PYTHONPATH=src python -m aiplane hardware recommend
```

What to highlight:

- refresh output includes `next_steps`;
- `models.generated.yaml` is a review buffer, while `models.yaml` is curated profile state;
- model filtering can use runtime, role, capability, RAM, and VRAM constraints;
- hardware recommendations use the active hardware profile.

### 1:15-1:45 - Continue Config And Endpoint Flexibility

Plan and export Continue config:

```bash
PYTHONPATH=src python -m aiplane integrations plan continue --select-best --runtime ollama
PYTHONPATH=src python -m aiplane integrations export continue --model qwen-tiny
PYTHONPATH=src python -m aiplane integrations export openai-compatible --model qwen-tiny --endpoint http://localhost:11434/v1
```

Optional endpoint variation to show in voiceover or split screen:

```bash
PYTHONPATH=src python -m aiplane integrations export openai-compatible --model qwen-tiny --endpoint https://llm.example.com/v1 --api-key-env AIPLANE_GATEWAY_API_KEY
```

What to highlight:

- `aiplane` prints config; it does not edit Continue automatically;
- the same profile alias can target a local native runtime, a Docker-hosted endpoint, an SSH tunnel, or a gateway endpoint when configured;
- exports are repeatable and reviewable.

### 1:45-2:05 - MCP For VS Code Or Agent Tools

Show MCP manifest and VS Code config export:

```bash
PYTHONPATH=src python -m aiplane mcp manifest
PYTHONPATH=src python -m aiplane integrations export vscode-mcp
```

Optional live server shot:

```bash
PYTHONPATH=src python -m aiplane mcp serve
```

What to highlight:

- MCP exposes structured `aiplane` inspection to compatible tools;
- writes are narrow and guarded;
- broad shell, secret writes, and cloud apply are intentionally blocked.

### 2:05-2:30 - Two Repeatable CPU-Oriented Environments

First create/import a local machine profile in a temporary demo location, then plan stack bindings. For the real recording, use a temp profile copy or pre-created demo profile so the repository profile is not polluted.

```bash
PYTHONPATH=src python -m aiplane hardware export-machine --name demo-local-cpu > /tmp/demo-local-cpu.machine.yaml
PYTHONPATH=src python -m aiplane machines import /tmp/demo-local-cpu.machine.yaml --name demo-local-cpu
PYTHONPATH=src python -m aiplane stacks setup cpu_chat --runtime ollama --model qwen-tiny --machine demo-local-cpu --access same_host --dry-run
PYTHONPATH=src python -m aiplane stacks plan cpu_chat
```

For a CPU media-oriented path, prefer audio via Piper for the short demo. Show readiness and model metadata rather than trying to generate audio live unless a pre-rendered clip is prepared:

```bash
PYTHONPATH=src python -m aiplane models show piper-en-us-lessac-medium
PYTHONPATH=src python -m aiplane runtimes prerequisites piper
PYTHONPATH=src python -m aiplane stacks setup cpu_voice --runtime piper --model piper-en-us-lessac-medium --machine demo-local-cpu --access same_host --dry-run
```

What to highlight:

- stacks are bindings of machine, runtime, model, and access policy;
- local and remote setups use the same data model;
- CPU image/video generation is not a good live demo target yet, but runtime planning can cover future media runtimes.

### 2:30-3:00 - Azure Machine Discovery And Deployment Planning

Show Azure machine discovery by task/runtime, then model/machine fit planning:

```bash
PYTHONPATH=src python -m aiplane machines discover azure --region uksouth --workload inference_small --runtime ollama --limit 5
PYTHONPATH=src python -m aiplane machines discover azure --region uksouth --model qwen-coder-32b --runtime vllm --limit 5
PYTHONPATH=src python -m aiplane machines import-azure-sku Standard_NC4as_T4_v3 --region uksouth --name azure_t4_demo
PYTHONPATH=src python -m aiplane machines recommend --model qwen-coder-32b --runtime vllm --limit 5
PYTHONPATH=src python -m aiplane deploy plan --target azure_gpu_vm
```

Recording note:

Azure discovery may include subscription, tenant, user, or account metadata in JSON output. For the public video, use redacted output or a sanitized pre-recorded fixture. Do not show raw Azure account fields.

What to highlight:

- discovery can be by workload, model, and runtime;
- machine profiles become reusable inputs for recommendations and stack/deploy plans;
- deploy planning is not the same as cloud apply.

## Structured Repeatability Beats

Use these phrases in the voiceover:

- A profile captures policy, providers, model aliases, runtime endpoints, tools, machines, targets, and orchestrators.
- Generated discovery data is reviewable before it becomes curated configuration.
- Machine profiles can be exported from one host and imported into another control-plane profile.
- Stack plans bind a model/runtime to a machine and an access policy, so the setup can be repeated locally, over SSH, or against a cloud VM.
- Integration exports are text artifacts that users review and paste into the target tool's native config.

## Public Demo Commands To Dry-Run Before Recording

```bash
PYTHONPATH=src python -m aiplane profiles validate local-dev
PYTHONPATH=src python -m aiplane environment doctor --required-only
PYTHONPATH=src python -m aiplane tools matrix
PYTHONPATH=src python -m aiplane models refresh --provider ollama --dry-run --limit 3
PYTHONPATH=src python -m aiplane models list --runtime ollama --role chat --ram-gb 16 --vram-gb 0 --sort-by role --limit 5
PYTHONPATH=src python -m aiplane hardware recommend
PYTHONPATH=src python -m aiplane integrations plan continue --select-best --runtime ollama
PYTHONPATH=src python -m aiplane integrations export continue --model qwen-tiny
PYTHONPATH=src python -m aiplane integrations export vscode-mcp
PYTHONPATH=src python -m aiplane mcp manifest
PYTHONPATH=src python -m aiplane machines discover azure --region uksouth --workload inference_small --runtime ollama --limit 5
```

## Immediate Next Steps To Mention At The End

Voiceover:

> Next, we are hardening the demo paths into repeatable examples: richer provider discovery, cleaner Azure output redaction, Docker-aware stack lifecycle, endpoint authentication plans, and better benchmark comparisons. The goal is not to hide complexity, but to make local, remote, and cloud AI environments explicit, reviewable, and repeatable.

Project next steps:

1. Add a sanitized Azure discovery example for the public demo.
2. Create a disposable demo profile so stack/machine import commands can run without changing `local-dev`.
3. Add or verify a clean Continue config recording path in VS Code.
4. Decide whether CPU media is a Piper audio plan only or a pre-rendered audio clip.
5. Keep Docker/endpoint flexibility in the demo through exports and stack plans unless a live container workflow is fully validated.

## Demo Readiness Gate

The demo is ready to plan in detail when:

- current uncommitted changes are reviewed and committed by the human owner;
- GitHub sensitive SHA cleanup is confirmed;
- all commands in the dry-run list pass on the recording machine;
- Azure output is redacted or replaced by a sanitized fixture;
- VS Code/Continue and MCP screenshots are rehearsed once;
- the CPU media segment is either reduced to runtime planning or backed by a pre-rendered artifact.
