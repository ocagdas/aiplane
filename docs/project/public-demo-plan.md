# Public Demo Plan

This plan is for a short public demo of `aiplane` as it exists today. The project is under active development, so individual commands, flags, and output shapes may change. The stable message is the philosophy: make AI development environments explicit, inspectable, repeatable, and safe to rehearse before mutating a host or cloud account.

`aiplane` is a control-plane CLI for self-managed and managed AI development environments. It does not try to replace coding agents, model runtimes, IDE extensions, orchestrator frameworks, or cloud platforms. It organizes the operational layer around them: profiles, providers, model entries, runtimes, machines, stacks, tool readiness, IDE exports, MCP access, orchestrator metadata, and deployment plans.

## Recommended Split

Use two videos rather than one overloaded three-minute recording.

1. **Video 1: Local Control Plane To Coding Tool** - target 2:45-3:00.
   - Tool philosophy and current status.
   - Install `aiplane` itself.
   - Discover/filter models for roles and hardware.
   - Set up a runtime, pull a model, run a simple chat.
   - Export Continue config.
   - Export/start MCP config.

2. **Video 2: Repeatability, Remote Targets, And Roadmap** - target 2:45-3:00.
   - Explain profiles/stacks as a repeatable architecture.
   - Copy/import YAML state and rerun the same commands elsewhere.
   - Show machine/resource discovery for a purpose such as video generation.
   - Touch on LangGraph/orchestrators and current state.
   - Show where Ansible/IaC/runtime packaging fit next.
   - Close with roadmap and active-development caveat.

A single three-minute video can be cut from Video 1 only. Trying to include Azure/media/orchestrators in the same first video will likely make the story feel rushed.

## Demo Thesis

Show that `aiplane` gives a structured path from intent to usable AI environment:

1. Describe the setup in profiles rather than ad hoc shell notes.
2. Discover models from providers for different purposes.
3. Filter by role, runtime, score, and hardware fit.
4. Install/start the runtime deliberately, with dry-runs and doctors available.
5. Pull and use the selected model.
6. Export config for coding tools and MCP-capable clients.
7. Reproduce the same setup locally, on a remote machine, or against a cloud target.

Key points to say explicitly:

- `aiplane` is a control plane, not another agent or runtime.
- The tool is active-development software; commands may change, but the workflow philosophy is the product.
- Providers, models, runtimes, machines, stacks, credentials, and integrations are separate concepts.
- Generated discovery entries are review buffers; profile-owned model entries are deliberate configuration.
- Doctors, dry-runs, plans, and exports come before mutation.
- Model selection can be grouped and filtered by provider, runtime, role, capability/score, RAM/VRAM, and target hardware.
- The longer-term direction includes custom profiling/scoring, richer benchmark data, orchestrator exports, and remote/cloud resource planning.

## Disposable Demo Profile

Complete the Conda install step in Video 1 before running these prep commands, or
run it once before recording. The command blocks below assume the `aiplane`
console script is available from the active Conda environment.

Use a temporary profile directory for recording so machine imports, discovered entries, and stack setup rehearsals do not change `profiles/local-dev`:

```bash
rm -rf /tmp/aiplane-demo-profiles /tmp/demo-local-cpu.machine.yaml
aiplane --profiles-dir /tmp/aiplane-demo-profiles profiles create demo --template local-dev
aiplane --profiles-dir /tmp/aiplane-demo-profiles profiles validate demo
```

Use `--profiles-dir /tmp/aiplane-demo-profiles --profile demo` on commands that intentionally write profile state, such as model refresh, machine import, or stack setup. Keep read-only commands on `local-dev` when you want to show the normal project profile.

## Video 1: Local Control Plane To Coding Tool

### 0:00-0:25 - Tool, Philosophy, Status

On screen:

```bash
aiplane --help
aiplane profiles validate local-dev
```

Voiceover:

> This is aiplane. It is a control-plane CLI for AI development environments. It is not a model runtime, coding agent, IDE extension, or cloud platform. It helps organize the operational pieces around them: profiles, providers, models, runtimes, machines, stacks, tool readiness, integrations, MCP access, and deployment plans.

> The project is under active development, so flags and exact output can change. The important idea is stable: inspect first, plan and dry-run where possible, then make repeatable changes deliberately.

What to highlight:

- `profiles validate` gives a quick current-status check.
- Mention that doctors, dry-runs, and exports are core workflow primitives.

### 0:25-0:55 - Install `aiplane`

Fresh-system Conda option, recommended for the demo. Start from a shell where
Git and Conda or Miniforge/Miniconda are installed and `conda` is on `PATH`:

```bash
git clone https://github.com/ocagdas/aiplane.git
cd aiplane
conda --version

# Regular installer flow.
scripts/setup_env.sh --mode conda --conda-env aiplane --action install --editable
conda activate aiplane

# Convenience flow: source the setup helper if you want activation to persist automatically.
# source scripts/setup_env.sh --mode conda --conda-env aiplane --action install --editable

aiplane profiles list
aiplane environment doctor --required-only
aiplane tools matrix
```

The setup helper creates the Conda environment if it is missing, upgrades pip,
installs this checkout, bootstraps ignored `profiles/local-dev` from the shipped
template with discovery disabled, runs the profile-aware sanity check, and prints
activation commands. Executing it like a regular installer is the clearest demo
path; sourcing it is a convenience option when you want the Conda environment to
remain active in the same shell automatically.

`--editable` means a source-linked development install. For Conda, venv, or the current Python environment, it runs `pip install -e .`, so changes in this checkout are visible immediately without reinstalling. For a snapshot-style install, use `--static`; that runs a normal install and later source edits require reinstalling.

Optional quick cuts for alternate `aiplane` CLI install modes:

```bash
scripts/setup_env.sh --mode conda --conda-env aiplane --action install --static --activate 0 --dry-run
scripts/setup_env.sh --mode venv --action install --editable --dry-run
scripts/setup_env.sh --mode local --action install --editable --dry-run
scripts/setup_env.sh --mode docker --action install --editable --docker-image aiplane:dev --dry-run
```

Voiceover:

> The CLI itself can be installed into Conda, venv, the current Python environment, or a small Docker CLI image. The setup doctor keeps mandatory checks separate from optional workflows, and the tool matrix shows which workflow categories are ready on this machine.

### 0:55-1:30 - Top-Down Architecture And Model Discovery

On screen:

```bash
aiplane providers list --group-by ownership
aiplane providers list --group-by runtime
aiplane --profiles-dir /tmp/aiplane-demo-profiles models refresh --profile demo --provider ollama --query chat --dry-run --limit 5
aiplane --profiles-dir /tmp/aiplane-demo-profiles models refresh --profile demo --provider ollama --query chat --limit 10
aiplane --profiles-dir /tmp/aiplane-demo-profiles models refresh --profile demo --provider ollama --query code --limit 10
aiplane --profiles-dir /tmp/aiplane-demo-profiles models refresh --profile demo --provider ollama --query embed --limit 10
aiplane --profiles-dir /tmp/aiplane-demo-profiles models list --profile demo --group-by runtime --limit 10
aiplane --profiles-dir /tmp/aiplane-demo-profiles models list --profile demo --runtime ollama --role chat --ram-gb 16 --vram-gb 0 --sort-by role --limit 5
DISCOVERED_CHAT=$(aiplane --profiles-dir /tmp/aiplane-demo-profiles models list --profile demo --runtime ollama --role chat --enabled-only --sort-by role --limit 1 | python -c 'import json,sys; print(json.load(sys.stdin)[0]["name"])')
printf 'reviewed discovered chat candidate=%s\n' "$DISCOVERED_CHAT"
aiplane --profiles-dir /tmp/aiplane-demo-profiles models add --profile demo local_chat --alias "$DISCOVERED_CHAT" --role chat --runtime ollama
aiplane --profiles-dir /tmp/aiplane-demo-profiles models clone --profile demo local_chat local_fast_draft --role completion --notes "Fast draft model for local coding tasks." --dry-run
aiplane --profiles-dir /tmp/aiplane-demo-profiles hardware recommend --profile demo
```

Capture selected aliases for later sections. `local_chat` is profile-owned; autocomplete and embedding can be added the same way or used as reviewed discovered candidates for the demo:

```bash
CHAT_ALIAS=local_chat
AUTOCOMPLETE_ALIAS=$(aiplane --profiles-dir /tmp/aiplane-demo-profiles models list --profile demo --runtime ollama --role autocomplete --enabled-only --sort-by role --limit 1 | python -c 'import json,sys; print(json.load(sys.stdin)[0]["name"])')
EMBEDDING_ALIAS=$(aiplane --profiles-dir /tmp/aiplane-demo-profiles models list --profile demo --runtime ollama --role embedding --enabled-only --sort-by role --limit 1 | python -c 'import json,sys; print(json.load(sys.stdin)[0]["name"])')
printf 'chat=%s autocomplete=%s embedding=%s\n' "$CHAT_ALIAS" "$AUTOCOMPLETE_ALIAS" "$EMBEDDING_ALIAS"
```

Voiceover:

> The top-down shape is provider, model purpose, runtime, hardware, then tool integration. Provider ownership separates self-managed sources from managed services. Discovery can pull provider results into an ignored discovery cache, but managed-service providers such as OpenAI, Anthropic, Azure OpenAI, Ollama Cloud, Azure Speech, and ElevenLabs do not have local model weights for aiplane to pull. Then we filter by role, runtime, RAM, VRAM, score signals, and target hardware before adding the reviewed candidate into stable profile-owned model config.

What to highlight:

- `providers list --group-by ownership` separates `self_managed` sources from `managed_service` providers.
- `models refresh --dry-run` shows next steps without writing.
- `models.discovered.yaml` is ignored review state with a generated-file banner.
- `models add --alias` shows the reviewed path from discovered candidate to stable profile-owned model entry.
- `models clone` shows why a second local entry can point at the same real model for a different purpose.
- `models list --group-by runtime` and role/hardware filters show structure.
- Hardware fit is a recommendation signal, not a hidden install/deploy action.
- Managed-service providers are configured and tested through credentials/endpoints; use provider tests instead of model pull commands.

Managed-provider credential reminder for the demo:

```bash
# Keep this file ignored/local. Do not commit raw API keys.
mkdir -p .aiplane
$EDITOR .aiplane/credentials.yaml

# Example refs inside .aiplane/credentials.yaml:
# providers:
#   openai:
#     accounts:
#       personal:
#         api_key_env: OPENAI_PERSONAL_API_KEY
#         endpoint: https://api.openai.com/v1
#       business_a:
#         api_key_env: OPENAI_BUSINESS_A_API_KEY
#         endpoint: https://api.openai.com/v1
#   azure_openai:
#     accounts:
#       business_a:
#         api_key_env: AZURE_OPENAI_BUSINESS_A_KEY
#         endpoint: https://YOUR-RESOURCE.openai.azure.com
#         api_version: 2024-02-01

aiplane credentials list
aiplane credentials show openai.personal
aiplane providers list --group-by ownership
aiplane credentials list
aiplane providers test openai --credential-ref openai.personal
aiplane providers test azure_openai --credential-ref azure_openai.business_a
```

Recording note: show the redacted `credentials list/show` output, not the editor with real values. Use `api_key_env` and shell/secret-manager environment variables for actual secrets.

### 1:30-2:00 - Runtime Setup, Pull, And Chat

Show native and Docker runtime options first as dry-runs:

```bash
aiplane runtimes install ollama --dry-run
aiplane runtimes install ollama --substrate docker --dry-run
aiplane runtimes start ollama --substrate docker --dry-run
```

Then show the chosen path for the recording. Use native if it is already working locally; use Docker if that is the demo focus:

```bash
aiplane runtimes start ollama --dry-run
aiplane runtimes pull ollama --model "$CHAT_ALIAS" --dry-run
aiplane runtimes status ollama
aiplane --profiles-dir /tmp/aiplane-demo-profiles chat --profile demo --model "$CHAT_ALIAS" --dry-run
aiplane --profiles-dir /tmp/aiplane-demo-profiles chat --profile demo --model "$CHAT_ALIAS"
```

If using Docker for the runtime, use:

```bash
aiplane runtimes start ollama --substrate docker --dry-run
aiplane runtimes pull ollama --substrate docker --model "$CHAT_ALIAS" --dry-run
aiplane runtimes status ollama --substrate docker
```

Voiceover:

> Runtimes are separate from model catalogs. Ollama can run natively or inside Docker. In the containerized case, the model is pulled into the runtime container's mounted Ollama store, and clients talk to the exposed endpoint rather than copying model files around.

Recording note: `aiplane chat` resolves the model entry and delegates to provider-native chat, currently local Ollama. Only run mutating `start` or `pull` live if the machine is prepared. Otherwise keep this as a dry-run and show `status` from an already-running runtime.

### 2:00-2:30 - Continue Config

Plan and export Continue config from the selected model entries:

```bash
aiplane --profiles-dir /tmp/aiplane-demo-profiles integrations plan continue --profile demo --chat "$CHAT_ALIAS" --autocomplete "$AUTOCOMPLETE_ALIAS" --embedding "$EMBEDDING_ALIAS"
aiplane --profiles-dir /tmp/aiplane-demo-profiles integrations export continue --profile demo --chat "$CHAT_ALIAS" --autocomplete "$AUTOCOMPLETE_ALIAS" --embedding "$EMBEDDING_ALIAS"
aiplane --profiles-dir /tmp/aiplane-demo-profiles integrations export openai-compatible --profile demo --model "$CHAT_ALIAS" --endpoint http://localhost:11434/v1
```

Voiceover:

> aiplane does not edit Continue automatically. It resolves the model and endpoint choices, then prints config that can be reviewed and pasted into Continue or another compatible tool.

### 2:30-2:55 - MCP

Show MCP manifest and VS Code config export:

```bash
aiplane mcp manifest
aiplane integrations export vscode-mcp
```

Optional live server shot:

```bash
aiplane mcp serve
```

Voiceover:

> MCP exposes structured aiplane inspection to compatible tools. Read tools cover profiles, providers, models, hardware, recommendations, integrations, and runtime status. Writes are narrow and guarded. Broad shell execution, secret writes, and cloud apply are intentionally not exposed.

### 2:55-3:00 - Video 1 Close

Voiceover:

> That is the local loop: inspect, discover, filter, set up the runtime, use the model, and export tool configuration. Next, we can take the same profile-shaped setup to remote machines and cloud targets.

## Video 2: Repeatability, Remote Targets, And Roadmap

### 0:00-0:30 - Repeatable Architecture

On screen:

```bash
aiplane --profiles-dir /tmp/aiplane-demo-profiles hardware export-machine --profile demo --name demo-local-cpu > /tmp/demo-local-cpu.machine.yaml
aiplane --profiles-dir /tmp/aiplane-demo-profiles machines import --profile demo /tmp/demo-local-cpu.machine.yaml --name demo-local-cpu
aiplane --profiles-dir /tmp/aiplane-demo-profiles machines list --profile demo
aiplane --profiles-dir /tmp/aiplane-demo-profiles stacks setup --profile demo cpu_chat --runtime ollama --model "$CHAT_ALIAS" --machine demo-local-cpu --access same_host --dry-run
```

Voiceover:

> Profiles and YAML make the setup repeatable. Machine profiles can be exported from one host and imported into another control-plane profile. A stack binds model, runtime, machine, and access policy so a setup can be repeated locally, over SSH, or against a cloud VM.

### 0:30-1:10 - Grouping, Best Fit, And Custom Scoring Direction

On screen:

```bash
aiplane --profiles-dir /tmp/aiplane-demo-profiles models list --profile demo --group-by provider-kind --limit 20
aiplane --profiles-dir /tmp/aiplane-demo-profiles models list --profile demo --group-by runtime --limit 20
aiplane --profiles-dir /tmp/aiplane-demo-profiles models list --profile demo --role chat --runtime ollama --ram-gb 16 --vram-gb 0 --sort-by role --limit 5
aiplane --profiles-dir /tmp/aiplane-demo-profiles hardware recommend --profile demo
aiplane --profiles-dir /tmp/aiplane-demo-profiles models benchmark --profile demo --task generation "$CHAT_ALIAS" --dry-run
```

Voiceover:

> Model choice is not just a name in a config file. aiplane can group by provider kind or runtime, filter by purpose and target hardware, and rank candidates using catalog signals. Hardware recommendation and benchmark results are separate inputs. The roadmap is to make scoring more extensible: local benchmark results, custom profiling, and team-specific suitability signals.

### 1:10-1:45 - Remote/Azure Resource Discovery For Media

Show that audio, image, and video generation are represented as AI model choices with runtime and platform requirements. The demo does not need to run these on CPU.

```bash
aiplane --profiles-dir /tmp/aiplane-demo-profiles models refresh --profile demo --provider huggingface --query text-to-image --disable-new --limit 10
aiplane --profiles-dir /tmp/aiplane-demo-profiles models list --profile demo --role image_generation --runtime diffusers --ram-gb 64 --vram-gb 16 --sort-by role --limit 5
aiplane --profiles-dir /tmp/aiplane-demo-profiles models refresh --profile demo --provider huggingface --query text-to-video --disable-new --limit 10
aiplane --profiles-dir /tmp/aiplane-demo-profiles models list --profile demo --role video_generation --runtime diffusers --ram-gb 128 --vram-gb 16 --sort-by role --limit 5
aiplane --profiles-dir /tmp/aiplane-demo-profiles machines azure-status --profile demo --region uksouth
aiplane --profiles-dir /tmp/aiplane-demo-profiles machines discover azure --profile demo --region uksouth --workload media_generation --runtime diffusers --limit 5
aiplane --profiles-dir /tmp/aiplane-demo-profiles machines profile-remote-plan --profile demo --name gpu-box-01 --host gpu-box-01.example.internal --user azureuser
```

Voiceover:

> For heavier workloads like video generation, the same planning shape applies. Discover models by purpose, filter by runtime and hardware needs, then discover machine candidates that fit the workload. Azure discovery can be live or fall back to offline hints. Remote profiling plans show how an existing workstation or VM can be measured and imported without hand-writing inventory.

Recording note: inspect Azure output before publishing. Do not show subscription IDs, tenant IDs, personal account names, or Azure portal pages. Fast-forward live discovery if it takes time.

### 1:45-2:15 - Orchestrators And Current State

On screen:

```bash
aiplane orchestrators list --group-by runtime
aiplane orchestrators show langgraph
aiplane orchestrators setup langgraph --runtime ollama --model "$CHAT_ALIAS" --dry-run
aiplane agents templates
```

Voiceover:

> Orchestrators such as LangGraph, CrewAI, AutoGen, Semantic Kernel, and OpenHands are cataloged as integration targets. Today aiplane can inspect and write starter orchestrator configuration. It does not run autonomous agent-to-agent workflows itself. The direction is role and endpoint metadata, tool policies, approvals, and audit labels for established orchestrator frameworks.

### 2:15-2:40 - Deployment And Configuration Tools Roadmap

On screen:

```bash
aiplane tools matrix
aiplane tools plan ansible
aiplane tools export ansible
aiplane deploy plan --profile demo --target azure_gpu_vm
```

Voiceover:

> aiplane should not hide infrastructure work. It integrates with established tools such as Docker, OpenSSH, Ansible, OpenTofu, Terraform, Pulumi, kubectl, and Helm. The near-term direction is better starter artifacts and guarded plans, so runtime setup can be repeated on local machines, remote workstations, and cloud resources without turning aiplane into a hidden deployment engine.

### 2:40-3:00 - Roadmap Close

Voiceover:

> The next steps are focused hardening: richer provider discovery, endpoint authentication plans, Docker-aware stack lifecycle, cleaner remote execution, better benchmarks and custom scoring, and test-suite isolation. The goal is not to hide complexity. It is to make local, remote, and cloud AI environments explicit, reviewable, and repeatable.

Optional final shot:

```bash
aplay /tmp/aiplane-demo.wav
```

Voiceover after audio:

> Hello world. This is AI plane.

## Structured Repeatability Beats

Use these phrases across both videos:

- A profile captures policy, model entries, local overrides, tools, machines, targets, and orchestrators; provider discovery and runtime endpoint defaults stay explicit and inspectable.
- Discovered model data is reviewable before it becomes profile-owned configuration.
- Machine profiles can be exported from one host and imported into another control-plane profile.
- Stack plans bind a model/runtime to a machine and an access policy, so setup can be repeated locally, over SSH, or against a cloud VM.
- Integration exports are text artifacts that users review and paste into the target tool's native config.
- Doctors and dry-runs are part of the design, not just debugging aids.

## Public Demo Commands To Dry-Run Before Recording

```bash
aiplane profiles validate local-dev
aiplane environment doctor --required-only
aiplane tools matrix
aiplane providers test openai --credential-ref openai.personal
aiplane --profiles-dir /tmp/aiplane-demo-profiles profiles validate demo
aiplane --profiles-dir /tmp/aiplane-demo-profiles models refresh --profile demo --provider ollama --query chat --dry-run --limit 5
aiplane --profiles-dir /tmp/aiplane-demo-profiles models refresh --profile demo --provider ollama --query chat --limit 10
aiplane --profiles-dir /tmp/aiplane-demo-profiles models refresh --profile demo --provider ollama --query code --limit 10
aiplane --profiles-dir /tmp/aiplane-demo-profiles models refresh --profile demo --provider ollama --query embed --limit 10
aiplane --profiles-dir /tmp/aiplane-demo-profiles models list --profile demo --runtime ollama --role chat --ram-gb 16 --vram-gb 0 --sort-by role --limit 5
aiplane --profiles-dir /tmp/aiplane-demo-profiles integrations plan continue --profile demo --chat "$CHAT_ALIAS" --autocomplete "$AUTOCOMPLETE_ALIAS" --embedding "$EMBEDDING_ALIAS"
aiplane --profiles-dir /tmp/aiplane-demo-profiles integrations export continue --profile demo --chat "$CHAT_ALIAS" --autocomplete "$AUTOCOMPLETE_ALIAS" --embedding "$EMBEDDING_ALIAS"
aiplane integrations export vscode-mcp
aiplane mcp manifest
aiplane --profiles-dir /tmp/aiplane-demo-profiles machines discover azure --profile demo --region uksouth --workload inference_small --runtime ollama --limit 5
```

## What We Are Not Claiming Yet

- No built-in TTS/image/video job runner is complete in this milestone.
- Managed-service endpoint binding in stacks/orchestrator role graphs is planned, not complete.
- Deeper agent-to-agent orchestration is planned config/export work, not runtime execution by `aiplane`.
- Docker-aware stack lifecycle beyond helper/runtime paths is still hardening work.
- Exports do not edit Continue, VS Code, cloud accounts, or runtime configs automatically.

## Demo Readiness Gate

The demo is ready to record when:

- current uncommitted changes are reviewed and committed by the human owner;
- CI format, lint, and test checks are green;
- all commands in the dry-run list and disposable-profile setup pass on the recording machine;
- Azure output has been reviewed on screen and any account-identifying UI/output is redacted or replaced by a sanitized fixture;
- VS Code/Continue and MCP screenshots are rehearsed once;
- the media segment shows online-discovered AI audio, image, and video candidates and has a prepared, playable final clip generated from the selected media path;
- the voiceover states that the project is under active development and commands may evolve.
