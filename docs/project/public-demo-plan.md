# Public Demo Plan

This plan is for a short public demo of `aiplane` as it exists today. The project is under active development, so individual commands, flags, and output shapes may change. The stable message is the philosophy: make AI development environments explicit, inspectable, repeatable, and safe to rehearse before mutating a host or cloud account.

`aiplane` is primarily a control-plane CLI for self-managed and managed AI development environments. It is also a thin runner where that helps validate the configured environment: endpoint-backed `chat`, single-prompt `run`, code-task commands, and runtime helper delegation. It does not try to become a model runtime, full chat product, IDE extension, autonomous coding agent, orchestrator platform, or cloud platform. It organizes the operational layer around those tools: profiles, providers, model entries, runtimes, machines, stacks, tool readiness, IDE exports, MCP access, orchestrator metadata, runner smoke checks, and deployment plans.

## Demo Target After `mvp_0.2`

The `mvp_0.2` demo goals should remain the spine: install/validate `aiplane`, discover and filter models, set up a runtime, pull a model, run chat/tasks, export Continue config, expose MCP, and explain repeatability across local, remote, and cloud-adjacent targets.

The `mvp_0.3` enhancement is not a different product story. It makes that original story safer and easier to follow:

- `quickstart local-coding` creates or previews the first local profile flow.
- Top-level `doctor` gives one local/hybrid AI workflow readiness summary.
- Model/runtime/provider/hardware/integration/MCP checks are more explicit.
- `chat`, `run`, and code-task operations are runtime-agnostic endpoint runners where possible, while Ollama still has an optional native CLI path.
- `--pull-model` now means execute the runtime-helper pull; `--dry-run --pull-model` means preview it.
- MCP has a documented read surface and narrow guarded writes, while broad installs, model pulls, cloud apply, secret writes, and arbitrary shell stay out of MCP.

Use a three-part demo rather than two overloaded videos.

1. **Section 1: Local AI Workflow Stack Readiness** - target 2:45-3:00.
   - Install or validate the CLI.
   - Run `quickstart local-coding` in dry-run and real disposable-profile modes.
   - Show `aiplane doctor` as the local/hybrid AI workflow summary: profile files, required tools, model defaults, endpoints, hardware fit, Continue/Aider readiness, and MCP read-surface readiness.
   - Show that an empty structural template reports missing model defaults clearly rather than pretending it is ready.

2. **Section 2: Model To Runtime To Runner** - target 2:45-3:00.
   - Preserve the `mvp_0.2` live path: discover/filter a local Ollama-capable model, add/promote a reviewed alias, preview setup/pull, execute pull when prepared, then run `chat`, `run`, and code-task smoke checks.
   - Add a second runtime track with a vLLM/OpenAI-compatible endpoint: plan/bundle/start dry-run, export endpoint config, and run dry-run chat/task checks; run live only if the endpoint is already prepared.
   - Explain the runner boundary precisely: `aiplane` can route single prompts and task prompts through configured endpoints or delegated runtime helpers; it is not a full chat UI, model server, or autonomous coding agent.
   - Export Continue/Aider/OpenAI-compatible config only after aliases/defaults exist.

3. **Section 3: Portability, MCP, Skills, And Roadmap** - target 2:45-3:00.
   - Show profile/machine/stack repeatability, remote endpoint/tunnel planning, MCP manifest/config export, the `skills/aiplane` assistant guidance package, orchestrator metadata, and tool/deploy planning.
   - Keep Azure/media/orchestrator items as planning/readiness demos unless a prepared sanitized environment exists.
   - Close with the scope anchor: control plane plus thin runner smoke checks, not a runtime/platform replacement.

A single three-minute cut should be Section 1 plus a short runner clip from Section 2. The full public walkthrough should use all three sections.

## Demo Freeze Readiness

A clean PR-ready demo cut is at this point when all of these are true:

- `scripts/check.sh` is passing on the same branch that will be recorded.
- `aiplane quickstart local-coding`, `quickstart local-coding`, and `doctor` flows are demonstrated with dry-runs before any live runtime mutation.
- `stacks doctor` includes stack role policy checks (`role_model_policy:<role>`) for both provider allow-list and cloud-policy outcomes, and these are visible in a rehearsal run.
- `chat`, `run`, and `code` commands are demonstrated in dry-run and live/recorded-live only where runtime endpoint prerequisites are already met.
- A second runtime track is shown through vLLM/OpenAI-compatible planning/export (dry-run at minimum).
- MCP manifest export and skills handoff are shown, and credentials are kept out of screen recordings.

With current behavior and current test coverage, we are at the feature-freeze point for the **Team Policy and Governance** milestone. The next demo checkpoint should be delayed only for any remaining remote-workstation hardening changes that are still being polished outside this milestone.


## Demo Thesis

Show that `aiplane` gives a structured path from intent to usable AI workflow environment:

1. Describe the setup in profiles rather than ad hoc shell notes.
2. Inspect readiness with doctors before mutating runtime or cloud state.
3. Discover and review model candidates separately from stable profile-owned aliases.
4. Filter by role, runtime/source, capability, RAM/VRAM, score, and target hardware.
5. Pull and start runtime assets deliberately, with dry-runs and clear helper ownership.
6. Run small chat/task smoke checks through configured endpoints or explicit runtime helper paths.
7. Export config for coding tools and MCP-capable clients.
8. Reproduce the same setup locally, on a remote machine, or against a cloud-adjacent target.

## Quick Demo Path

Use this path for a compact rehearsal. It keeps the original `mvp_0.2` execution goals but places the `mvp_0.3` quickstart/doctor checks before live runtime work.

```bash
# Install and validate the CLI/profile.
scripts/setup_env.sh --mode conda --conda-env aiplane --action install --editable
conda activate aiplane
aiplane profiles validate local-dev
aiplane environment doctor --required-only

# Section 1: AI workflow readiness wedge.
aiplane quickstart local-coding --dry-run --no-discovery
aiplane quickstart local-coding --dry-run --no-discovery --format text
aiplane --profiles-dir /tmp/aiplane-demo-profiles quickstart local-coding --name demo --no-discovery --no-hardware-discovery
aiplane --profiles-dir /tmp/aiplane-demo-profiles doctor --profile demo

# Section 2: original MVP execution path, enhanced with clearer dry-run/pull semantics.
aiplane --profiles-dir /tmp/aiplane-demo-profiles models refresh --profile demo --provider ollama --query chat --dry-run --limit 5
aiplane --profiles-dir /tmp/aiplane-demo-profiles models refresh --profile demo --provider ollama --query chat --limit 10
aiplane --profiles-dir /tmp/aiplane-demo-profiles models list --profile demo --runtime ollama --role chat --capability 'general_chat>=2' --fits-hardware --enabled-only --sort-by role --limit 5
CHAT_ALIAS="$(aiplane --profiles-dir /tmp/aiplane-demo-profiles models list --profile demo --runtime ollama --role chat --capability 'general_chat>=2' --fits-hardware --enabled-only --sort-by role --limit 1 --name-only)"
printf 'chat_alias=%s\n' "$CHAT_ALIAS"

# Review/add/promote the chosen alias before exporting or running.
aiplane --profiles-dir /tmp/aiplane-demo-profiles models show --profile demo "$CHAT_ALIAS"
aiplane --profiles-dir /tmp/aiplane-demo-profiles integrations roles continue --profile demo

# Pull preview versus execution. Run the non-dry command only on a prepared recording machine.
aiplane --profiles-dir /tmp/aiplane-demo-profiles quickstart local-coding --name demo --dry-run --no-discovery --pull-model "$CHAT_ALIAS"
aiplane --profiles-dir /tmp/aiplane-demo-profiles quickstart local-coding --name demo --no-discovery --pull-model "$CHAT_ALIAS"

aiplane runtimes status ollama
aiplane --profiles-dir /tmp/aiplane-demo-profiles chat --profile demo --model "$CHAT_ALIAS" --prompt "Say hello from the configured endpoint" --dry-run
aiplane --profiles-dir /tmp/aiplane-demo-profiles chat --profile demo --model "$CHAT_ALIAS" --prompt "Say hello from the configured endpoint" --timeout-seconds 180
aiplane --profiles-dir /tmp/aiplane-demo-profiles run --profile demo --model "$CHAT_ALIAS" --dry-run "Summarize what aiplane is in one sentence."
aiplane --profiles-dir /tmp/aiplane-demo-profiles code write --profile demo --model "$CHAT_ALIAS" --task "write a Python function that validates an email address" --dry-run

# Export after aliases/defaults exist or pass explicit role selections.
aiplane --profiles-dir /tmp/aiplane-demo-profiles integrations export continue --profile demo --chat "$CHAT_ALIAS"
aiplane --profiles-dir /tmp/aiplane-demo-profiles integrations export aider --profile demo --chat "$CHAT_ALIAS"

# Second runtime track: vLLM/OpenAI-compatible endpoint planning and runner dry-runs.
VLLM_ALIAS="vllm_demo_chat"
aiplane --profiles-dir /tmp/aiplane-demo-profiles models add "$VLLM_ALIAS" --profile demo --provider local_file --model /models/TinyLlama-1.1B-Chat-v1.0 --role chat --runtime vllm --preferred-runtime vllm --set min_ram_gb=16 --set min_vram_gb=8 --dry-run
aiplane --profiles-dir /tmp/aiplane-demo-profiles models add "$VLLM_ALIAS" --profile demo --provider local_file --model /models/TinyLlama-1.1B-Chat-v1.0 --role chat --runtime vllm --preferred-runtime vllm --set min_ram_gb=16 --set min_vram_gb=8 --overwrite
aiplane --profiles-dir /tmp/aiplane-demo-profiles models show --profile demo "$VLLM_ALIAS"
aiplane --profiles-dir /tmp/aiplane-demo-profiles runtimes prerequisites vllm
aiplane --profiles-dir /tmp/aiplane-demo-profiles runtimes bundle vllm --profile demo --model "$VLLM_ALIAS" --mode docker --format dockerfile
aiplane --profiles-dir /tmp/aiplane-demo-profiles runtimes start vllm --profile demo --model "$VLLM_ALIAS" --dry-run
aiplane --profiles-dir /tmp/aiplane-demo-profiles integrations export openai-compatible --profile demo --model "$VLLM_ALIAS" --endpoint http://localhost:8000/v1
aiplane --profiles-dir /tmp/aiplane-demo-profiles chat --profile demo --model "$VLLM_ALIAS" --prompt "Say hello from the vLLM endpoint" --dry-run

# Section 3: MCP, skills, and repeatability surfaces.
aiplane --profiles-dir /tmp/aiplane-demo-profiles integrations export vscode-mcp --profile demo
aiplane --profiles-dir /tmp/aiplane-demo-profiles integrations export continue-mcp --profile demo
aiplane mcp manifest
sed -n '1,90p' skills/aiplane/SKILL.md
aiplane --profiles-dir /tmp/aiplane-demo-profiles hardware discover --profile demo --dry-run
aiplane --profiles-dir /tmp/aiplane-demo-profiles hardware recommend --profile demo
aiplane --profiles-dir /tmp/aiplane-demo-profiles stacks setup --profile demo cpu_chat --runtime ollama --model "$CHAT_ALIAS" --access same_host --dry-run
```

Use `aiplane chat --native-ollama --dry-run --model "$CHAT_ALIAS"` only when you explicitly want to show Ollama's `ollama run` path. The default chat path should demonstrate the endpoint-backed runner.

Key points to say explicitly:

- `aiplane` is a control plane with thin runner/smoke-test surfaces; it is not a model runtime, full chat UI, IDE extension, autonomous coding agent, or cloud platform.
- The narrow public wedge is local/hybrid AI workflow stack readiness from one profile.
- Providers, models, runtimes, machines, stacks, credentials, integrations, MCP tools, assistant skills, and runner commands are separate concepts.
- Ollama is the easiest local live demo path; vLLM/OpenAI-compatible is the second runtime path for endpoint planning, export, and dry-run runner checks unless a prepared endpoint is available.
- Generated discovery entries are review buffers; profile-owned model entries are deliberate configuration.
- Doctors, dry-runs, plans, and exports come before mutation.
- Model pulls are opt-in: `--pull-model` executes, and `--dry-run --pull-model` previews.
- MCP exposes structured inspection/planning/export plus narrow guarded writes; broad shell execution, runtime installs, model pulls, cloud apply, and secret writes remain outside MCP.
- The longer-term direction includes remote GPU workstation profiles, team policy/governance, richer benchmark data, orchestrator exports, and guarded cloud/resource planning.

## Disposable Demo Profile

Complete the Conda install step in Section 1 before running these prep commands, or
run it once before recording. The command blocks below assume the `aiplane`
console script is available from the active Conda environment.

Use a temporary profile directory for recording so machine imports, discovered entries, and stack setup rehearsals do not change `profiles/local-dev`:

```bash
rm -rf /tmp/aiplane-demo-profiles /tmp/demo-local-cpu.machine.yaml
aiplane --profiles-dir /tmp/aiplane-demo-profiles profiles create demo --template local-dev
aiplane --profiles-dir /tmp/aiplane-demo-profiles profiles validate demo
```

Use `--profiles-dir /tmp/aiplane-demo-profiles --profile demo` on commands that intentionally write profile state, such as model refresh, machine import, or stack setup. Keep read-only commands on `local-dev` when you want to show the normal project profile.

## Section 1: Local AI Workflow Stack Readiness

### 0:00-0:25 - Tool, Philosophy, Status

On screen:

```bash
aiplane --help
aiplane profiles validate local-dev
```

Voiceover:

> This is aiplane. It is primarily a control-plane CLI for AI development environments, with thin runner commands for validating configured models and endpoints. It is not a model runtime, full chat product, autonomous coding agent, IDE extension, or cloud platform. It helps organize the operational pieces around them: profiles, providers, models, runtimes, machines, stacks, tool readiness, integrations, MCP access, runner smoke checks, and deployment plans.

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
# Requires: profiles/create+validate for demo must have run to create profile
aiplane integrations roles continue  # shows required roles for integrations.
aiplane integrations roles continue --groups
aiplane --profiles-dir /tmp/aiplane-demo-profiles models refresh --profile demo --provider ollama --query chat --dry-run --limit 5
aiplane --profiles-dir /tmp/aiplane-demo-profiles models refresh --profile demo --provider ollama --query chat --limit 10
aiplane --profiles-dir /tmp/aiplane-demo-profiles models refresh --profile demo --provider ollama --query code --limit 10
aiplane --profiles-dir /tmp/aiplane-demo-profiles models refresh --profile demo --provider ollama --query embed --limit 10
aiplane --profiles-dir /tmp/aiplane-demo-profiles models list --profile demo --group-by runtime --limit 10
CHAT_ALIAS="$(aiplane --profiles-dir /tmp/aiplane-demo-profiles models list --profile demo --provider ollama --role chat --enabled-only --sort-by role --limit 1 --name-only)"
AUTOCOMPLETE_ALIAS="$(aiplane --profiles-dir /tmp/aiplane-demo-profiles models list --profile demo --runtime ollama --role autocomplete --enabled-only --sort-by role --limit 1 --name-only)"
EMBEDDING_ALIAS="$(aiplane --profiles-dir /tmp/aiplane-demo-profiles models list --profile demo --runtime ollama --role embedding --enabled-only --sort-by role --limit 1 --name-only)"
aiplane --profiles-dir /tmp/aiplane-demo-profiles models add --profile demo local_chat --alias "$CHAT_ALIAS" --role chat --runtime ollama
aiplane --profiles-dir /tmp/aiplane-demo-profiles models clone --profile demo local_chat local_fast_draft --role completion --notes "Fast draft model for local workflow tasks." --dry-run
aiplane --profiles-dir /tmp/aiplane-demo-profiles hardware recommend --profile demo
```

Voiceover:

> The top-down shape is provider, model purpose, runtime, hardware, then tool integration. Provider ownership separates self-managed sources from managed services. Discovery can pull provider results into an ignored discovery cache, but managed-service providers such as OpenAI, Anthropic, Azure OpenAI, Ollama Cloud, Azure Speech, and ElevenLabs do not have local model weights for aiplane to pull. Then we filter by role, runtime, RAM, VRAM, score signals, and target hardware before adding the reviewed candidate into stable profile-owned model config.

What to highlight:

- `providers list --group-by ownership` separates `self_managed` sources from `managed_service` providers.
- `models refresh --dry-run` shows next steps without writing.
- `integrations roles continue` shows required role names for `plan continue`.
- Discovery imports are written as enabled by default; use `models disable` for entries you want to keep off the default selection.
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
# Optional when a sanitized credential ref is configured:
# aiplane providers test openai --credential-ref openai.personal
aiplane providers test azure_openai --credential-ref azure_openai.business_a
```

Recording note: show the redacted `credentials list/show` output, not the editor with real values. Use `api_key_env` and shell/secret-manager environment variables for actual secrets.

## Section 2: Model To Runtime To Runner

### 0:00-0:35 - Runtime Setup, Pull, And Chat

Use the integration setup flow as the practical task-level bundle. It reuses the Continue plan, checks the selected runtime/model state, and previews supported install/start/pull helper actions before doing anything live:

```bash
aiplane --profiles-dir /tmp/aiplane-demo-profiles integrations setup continue --profile demo --chat "$CHAT_ALIAS" --autocomplete "$AUTOCOMPLETE_ALIAS" --embedding "$EMBEDDING_ALIAS" --dry-run
# Run without --dry-run only on a prepared recording machine.
aiplane --profiles-dir /tmp/aiplane-demo-profiles integrations setup continue --profile demo --chat "$CHAT_ALIAS" --autocomplete "$AUTOCOMPLETE_ALIAS" --embedding "$EMBEDDING_ALIAS"
aiplane runtimes status ollama

# Confirm the alias is suitable for interactive local chat, then launch it.
aiplane --profiles-dir /tmp/aiplane-demo-profiles models list --profile demo --provider ollama --role chat --enabled-only --name-only --limit 3
aiplane --profiles-dir /tmp/aiplane-demo-profiles models show --profile demo "$CHAT_ALIAS"
aiplane --profiles-dir /tmp/aiplane-demo-profiles chat --profile demo --model "$CHAT_ALIAS" --dry-run
aiplane --profiles-dir /tmp/aiplane-demo-profiles chat --profile demo --model "$CHAT_ALIAS"

# Small one-shot CLI tasks against a model alias.
aiplane --profiles-dir /tmp/aiplane-demo-profiles code write --profile demo --model "$CHAT_ALIAS" --task "write a Python function that validates an email address" --dry-run
aiplane --profiles-dir /tmp/aiplane-demo-profiles code analyze --profile demo --model "$CHAT_ALIAS" src/aiplane/cli.py --dry-run
```

Keep the lower-level runtime commands available as diagnostics or when you want to show native versus Docker explicitly:

```bash
aiplane runtimes install ollama --dry-run
aiplane runtimes start ollama --dry-run
aiplane runtimes pull ollama --model "$CHAT_ALIAS" --dry-run
aiplane runtimes install ollama --substrate docker --dry-run
aiplane runtimes start ollama --substrate docker --dry-run
aiplane runtimes pull ollama --substrate docker --model "$CHAT_ALIAS" --dry-run
```

Voiceover:

> Runtimes are separate from model catalogs. The selected aiplane alias maps to a runtime-native model id, and setup delegates storage to the runtime. Native Ollama uses its normal local model store; Docker Ollama uses the mounted Docker volume at `/root/.ollama` inside the container. aiplane records the alias mapping and endpoint, not a copy of the model weights.

Recording note: `aiplane chat` resolves the model entry and uses the configured endpoint path by default. Only run mutating setup live if the machine is prepared. Otherwise keep this as a dry-run and show `status` from an already-running runtime. Use `--native-ollama` only to demonstrate Ollama's native CLI path.

### 0:35-1:05 - Second Runtime: vLLM/OpenAI-Compatible Endpoint

Use vLLM as the second runtime story. Keep it dry-run unless the recording machine or a remote GPU box already has a reachable OpenAI-compatible endpoint.

```bash
VLLM_ALIAS="vllm_demo_chat"
aiplane --profiles-dir /tmp/aiplane-demo-profiles models add "$VLLM_ALIAS" --profile demo --provider local_file --model /models/TinyLlama-1.1B-Chat-v1.0 --role chat --runtime vllm --preferred-runtime vllm --set min_ram_gb=16 --set min_vram_gb=8 --dry-run
aiplane --profiles-dir /tmp/aiplane-demo-profiles models add "$VLLM_ALIAS" --profile demo --provider local_file --model /models/TinyLlama-1.1B-Chat-v1.0 --role chat --runtime vllm --preferred-runtime vllm --set min_ram_gb=16 --set min_vram_gb=8 --overwrite
aiplane --profiles-dir /tmp/aiplane-demo-profiles models show --profile demo "$VLLM_ALIAS"
aiplane --profiles-dir /tmp/aiplane-demo-profiles runtimes prerequisites vllm
aiplane --profiles-dir /tmp/aiplane-demo-profiles runtimes bundle vllm --profile demo --model "$VLLM_ALIAS" --mode docker --format dockerfile
aiplane --profiles-dir /tmp/aiplane-demo-profiles runtimes start vllm --profile demo --model "$VLLM_ALIAS" --dry-run
aiplane --profiles-dir /tmp/aiplane-demo-profiles integrations export openai-compatible --profile demo --model "$VLLM_ALIAS" --endpoint http://localhost:8000/v1
aiplane --profiles-dir /tmp/aiplane-demo-profiles chat --profile demo --model "$VLLM_ALIAS" --prompt "Say hello from the vLLM endpoint" --dry-run
```

Voiceover:

> Ollama is the easiest local live path, but it should not be the only runtime story. vLLM shows the OpenAI-compatible endpoint path: aiplane can declare a reviewed local or remote artifact path, render runtime packaging/start plans, export endpoint config, and route dry-run chat/task checks against that runtime. Live vLLM execution is a prepared GPU endpoint demo, not a required laptop demo.

### 1:05-1:35 - Continue Config

Plan and export Continue config from the selected model entries:

```bash
aiplane --profiles-dir /tmp/aiplane-demo-profiles integrations plan continue --profile demo --chat "$CHAT_ALIAS" --autocomplete "$AUTOCOMPLETE_ALIAS" --embedding "$EMBEDDING_ALIAS"
aiplane --profiles-dir /tmp/aiplane-demo-profiles integrations export continue --profile demo --chat "$CHAT_ALIAS" --autocomplete "$AUTOCOMPLETE_ALIAS" --embedding "$EMBEDDING_ALIAS"
aiplane --profiles-dir /tmp/aiplane-demo-profiles integrations export openai-compatible --profile demo --model "$CHAT_ALIAS" --endpoint http://localhost:11434/v1
```

Voiceover:

> aiplane does not edit Continue automatically. It resolves the model and endpoint choices, then prints config that can be reviewed and pasted into Continue or another compatible tool.

### 1:35-2:15 - MCP And Skills

Show MCP manifest, client config exports, and the assistant skill package:

```bash
aiplane mcp manifest
aiplane integrations export vscode-mcp
aiplane integrations export continue-mcp
sed -n '1,90p' skills/aiplane/SKILL.md
```

Optional live server shot, only in a separate terminal because it stays attached to stdio:

```bash
aiplane mcp serve
```

Voiceover:

> MCP exposes structured aiplane inspection to compatible tools. Read tools cover profiles, providers, models, hardware, recommendations, integrations, and runtime status. Writes are narrow and guarded. The aiplane skill is different: it is assistant guidance for working safely in this repository and preserving the product boundary. Broad shell execution, runtime installs, model pulls, secret writes, and cloud apply are intentionally not exposed through MCP.

### 2:15-3:00 - Runner Boundary And Close

Voiceover:

> That is the local loop: inspect, discover, filter, set up the runtime, pull deliberately, run small chat/task checks, and export tool configuration. Next, we can take the same profile-shaped setup to remote machines and cloud-adjacent targets.

## Section 3: Portability, MCP, Skills, And Roadmap

### 0:00-0:30 - Repeatable Architecture

On screen:

```bash
aiplane --profiles-dir /tmp/aiplane-demo-profiles hardware export-machine --profile demo --name demo-local-cpu > /tmp/demo-local-cpu.machine.yaml
aiplane --profiles-dir /tmp/aiplane-demo-profiles machines import --profile demo /tmp/demo-local-cpu.machine.yaml --name demo-local-cpu
aiplane --profiles-dir /tmp/aiplane-demo-profiles machines list --profile demo
aiplane --profiles-dir /tmp/aiplane-demo-profiles stacks setup --profile demo cpu_chat --runtime ollama --model "$CHAT_ALIAS" --machine demo-local-cpu --access same_host --dry-run
```

Show the first remote replication path as plain file transfer, not Ansible/Vagrant yet:

```bash
# On the source machine: copy the profile state, not runtime caches or raw secrets.
tar -C /tmp/aiplane-demo-profiles -czf /tmp/aiplane-demo-profile.tgz demo
scp /tmp/aiplane-demo-profile.tgz user@gpu-box-01:/tmp/

# On the remote machine after installing aiplane:
mkdir -p ~/aiplane-profiles
tar -C ~/aiplane-profiles -xzf /tmp/aiplane-demo-profile.tgz
aiplane --profiles-dir ~/aiplane-profiles profiles validate demo
CHAT_ALIAS="$(aiplane --profiles-dir ~/aiplane-profiles models list --profile demo --provider ollama --role chat --enabled-only --sort-by role --limit 1 --name-only)"
AUTOCOMPLETE_ALIAS="$(aiplane --profiles-dir ~/aiplane-profiles models list --profile demo --runtime ollama --role autocomplete --enabled-only --sort-by role --limit 1 --name-only)"
EMBEDDING_ALIAS="$(aiplane --profiles-dir ~/aiplane-profiles models list --profile demo --runtime ollama --role embedding --enabled-only --sort-by role --limit 1 --name-only)"
aiplane --profiles-dir ~/aiplane-profiles integrations setup continue --profile demo --chat "$CHAT_ALIAS" --autocomplete "$AUTOCOMPLETE_ALIAS" --embedding "$EMBEDDING_ALIAS" --dry-run
```

Voiceover:

> Profiles and YAML make the setup repeatable. Machine profiles can be exported from one host and imported into another control-plane profile. A stack binds model, runtime, machine, and access policy so a setup can be repeated locally, over SSH, or against a cloud VM. For the first remote replication demo, copy the profile directory and rerun validate/setup on the remote host. Do not copy `.aiplane` PID/log/runtime state or local model caches; the remote runtime should install/start/pull its own models from the alias mappings. Credentials stay local as environment variables or ignored credential refs, not raw secrets in the profile bundle.

### 0:30-1:10 - Grouping, Best Fit, And Custom Scoring Direction

On screen:

```bash
aiplane --profiles-dir /tmp/aiplane-demo-profiles models list --profile demo --group-by provider-kind --limit 20
aiplane --profiles-dir /tmp/aiplane-demo-profiles models list --profile demo --group-by runtime --limit 20
aiplane --profiles-dir /tmp/aiplane-demo-profiles models list --profile demo --role chat --runtime ollama --capability 'general_chat>=2' --fits-hardware --sort-by role --limit 5
BEST_FIT_ALIAS="$(aiplane --profiles-dir /tmp/aiplane-demo-profiles models list --profile demo --role chat --runtime ollama --capability 'general_chat>=2' --fits-hardware --sort-by role --limit 1 --name-only)"
printf 'best_fit=%s\n' "$BEST_FIT_ALIAS"
# `--sort-by role` is the score sort for the requested role; `avg` is the broad average score.
aiplane --profiles-dir /tmp/aiplane-demo-profiles hardware recommend --profile demo
aiplane --profiles-dir /tmp/aiplane-demo-profiles models benchmark --profile demo --task generation "$CHAT_ALIAS" --dry-run
```

Voiceover:

> Model choice is not just a name in a config file. aiplane can group by provider kind or runtime, filter by purpose, capability threshold, and active hardware, then rank candidates by the requested role score and pick the top result with `--limit 1`. Hardware recommendation and benchmark results are separate inputs. The roadmap is to make scoring more extensible: local benchmark results, custom profiling, and team-specific suitability signals.

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

Use these phrases across all three sections:

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
# Optional when a sanitized credential ref is configured:
# aiplane providers test openai --credential-ref openai.personal
aiplane --profiles-dir /tmp/aiplane-demo-profiles profiles validate demo
aiplane --profiles-dir /tmp/aiplane-demo-profiles models refresh --profile demo --provider ollama --query chat --dry-run --limit 5
aiplane --profiles-dir /tmp/aiplane-demo-profiles models refresh --profile demo --provider ollama --query chat --limit 10
aiplane --profiles-dir /tmp/aiplane-demo-profiles models refresh --profile demo --provider ollama --query code --limit 10
aiplane --profiles-dir /tmp/aiplane-demo-profiles models refresh --profile demo --provider ollama --query embed --limit 10
aiplane --profiles-dir /tmp/aiplane-demo-profiles models list --profile demo --provider ollama --role chat --ram-gb 16 --vram-gb 0 --sort-by role --limit 5
aiplane --profiles-dir /tmp/aiplane-demo-profiles integrations plan continue --profile demo --chat "$CHAT_ALIAS" --autocomplete "$AUTOCOMPLETE_ALIAS" --embedding "$EMBEDDING_ALIAS"
aiplane --profiles-dir /tmp/aiplane-demo-profiles integrations export continue --profile demo --chat "$CHAT_ALIAS" --autocomplete "$AUTOCOMPLETE_ALIAS" --embedding "$EMBEDDING_ALIAS"
aiplane integrations export vscode-mcp
aiplane integrations export continue-mcp
aiplane mcp manifest
sed -n '1,90p' skills/aiplane/SKILL.md
VLLM_ALIAS="vllm_demo_chat"
aiplane --profiles-dir /tmp/aiplane-demo-profiles models add "$VLLM_ALIAS" --profile demo --provider local_file --model /models/TinyLlama-1.1B-Chat-v1.0 --role chat --runtime vllm --preferred-runtime vllm --set min_ram_gb=16 --set min_vram_gb=8 --dry-run
aiplane --profiles-dir /tmp/aiplane-demo-profiles models add "$VLLM_ALIAS" --profile demo --provider local_file --model /models/TinyLlama-1.1B-Chat-v1.0 --role chat --runtime vllm --preferred-runtime vllm --set min_ram_gb=16 --set min_vram_gb=8 --overwrite
aiplane --profiles-dir /tmp/aiplane-demo-profiles runtimes bundle vllm --profile demo --model "$VLLM_ALIAS" --mode docker --format dockerfile
aiplane --profiles-dir /tmp/aiplane-demo-profiles machines discover azure --profile demo --region uksouth --workload inference_small --runtime vllm --limit 5
```

## Quick Local-Dev Runner Checklist

Use this checklist when rehearsing the live execution part of the demo on `local-dev` without the disposable profile flags:

```bash
# Pick an Ollama-runnable alias for endpoint chat and optional native Ollama fallback.
OLLAMA_CHAT_ALIAS="$(aiplane models list --runtime ollama --role chat --enabled-only --max-parameters-b 14 --ram-gb 32 --vram-gb 3 --sort-by role --limit 1 --name-only)"
printf 'ollama_chat=%s\n' "$OLLAMA_CHAT_ALIAS"
aiplane models show "$OLLAMA_CHAT_ALIAS"

# Setup checks/prepares runtime + selected model. Use dry-run first.
aiplane integrations setup openai-compatible --model "$OLLAMA_CHAT_ALIAS" --dry-run
aiplane integrations setup openai-compatible --model "$OLLAMA_CHAT_ALIAS"

# Endpoint chat, plus optional Ollama-native CLI preview.
aiplane chat --model "$OLLAMA_CHAT_ALIAS" --prompt "Say hello from the configured endpoint" --dry-run
aiplane chat --model "$OLLAMA_CHAT_ALIAS" --prompt "Say hello from the configured endpoint"
aiplane chat --model "$OLLAMA_CHAT_ALIAS" --native-ollama --dry-run

# CLI task prompts. Keep dry-run for recording unless the runtime is ready and output timing is rehearsed.
aiplane runtimes status ollama
aiplane runtimes list-runtime-models ollama
aiplane code write --model "$OLLAMA_CHAT_ALIAS" --task "write a Python function that validates an email address" --dry-run
aiplane code write --model "$OLLAMA_CHAT_ALIAS" --task "write a Python function that validates an email address" --timeout-seconds 180
aiplane code analyze --model "$OLLAMA_CHAT_ALIAS" src/aiplane/cli.py --dry-run

# Continue export after setup.
aiplane integrations export continue --chat "$OLLAMA_CHAT_ALIAS"
```

For this checklist, `openai-compatible` is the generic client protocol used by setup planning for a single model endpoint. `aiplane chat` uses configured endpoints by default; Ollama's native CLI path is available with `--native-ollama`.

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
- VS Code/Continue, MCP config/manifest, and the `skills/aiplane` guidance package screenshots are rehearsed once;
- the media/planning segment is either rehearsed with sanitized provider output or omitted from the short cut; do not imply built-in media job running is complete;
- the voiceover states that the project is under active development and commands may evolve.
