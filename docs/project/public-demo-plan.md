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

### Disposable Demo Profile

Use a temporary profile directory for recording so machine imports and stack setup rehearsals do not change `profiles/local-dev`:

```bash
rm -rf /tmp/aiplane-demo-profiles /tmp/demo-local-cpu.machine.yaml
PYTHONPATH=src python -m aiplane --profiles-dir /tmp/aiplane-demo-profiles profiles create demo --template local-dev
PYTHONPATH=src python -m aiplane --profiles-dir /tmp/aiplane-demo-profiles profiles validate demo
```

Use `--profiles-dir /tmp/aiplane-demo-profiles --profile demo` on demo commands that intentionally write profile state, such as machine import or stack setup. Keep read-only commands on `local-dev` when you want to show the normal project profile.

### 0:00-0:20 - What It Is

Show the README headline or terminal help:

```bash
PYTHONPATH=src python -m aiplane --help
```

Voiceover:

> This is aiplane: a control-plane CLI for self-managed and managed AI development environments. It keeps profiles, models, runtimes, machines, IDE exports, MCP tools, and deployment plans in one repeatable workflow.

### 0:20-0:45 - Install And Readiness

Show install/setup and doctors. Use Conda as the main recording path, then mention venv, native/current-Python, and Docker CLI-image alternatives:

```bash
git clone https://github.com/ocagdas/aiplane.git
cd aiplane
source scripts/setup_env.sh --mode conda --conda-env aiplane --action install --editable
aiplane profiles validate local-dev
aiplane environment doctor --required-only
aiplane tools matrix
aiplane providers test openai --credential-ref openai.personal
```

Optional quick cuts for alternate `aiplane` CLI install modes:

```bash
scripts/setup_env.sh --mode venv --action install --editable --dry-run
scripts/setup_env.sh --mode local --action install --editable --dry-run
scripts/setup_env.sh --mode docker --action install --editable --docker-image aiplane:dev --dry-run
```

Show native and Docker runtime options for Ollama as dry-runs:

```bash
aiplane runtimes install ollama --dry-run
aiplane runtimes install ollama --substrate docker --dry-run
aiplane runtimes start ollama --substrate docker --dry-run
```

What to highlight:

- mandatory local prerequisites are checked separately from optional workflow tools;
- `tools matrix` shows complete, partial, and needs-setup workflow categories;
- `aiplane` itself can run in Conda, venv, native Python, or a local Docker CLI image;
- managed provider credentials can be checked with a small provider-specific API call without printing secrets;
- Ollama can be operated natively or through Docker using the official `ollama/ollama` image;
- nothing is provisioned just by inspecting readiness or running dry-runs.

### 0:45-1:15 - Provider Discovery And Model Filtering

Show provider discovery and safe generated-alias flow in the disposable profile. The first command is a dry run for narration; the next three intentionally write only `/tmp/aiplane-demo-profiles/demo/models.generated.yaml` so later export commands can resolve real aliases.

```bash
PYTHONPATH=src python -m aiplane --profiles-dir /tmp/aiplane-demo-profiles models refresh --profile demo --provider ollama --query chat --dry-run --limit 5
PYTHONPATH=src python -m aiplane --profiles-dir /tmp/aiplane-demo-profiles models refresh --profile demo --provider ollama --query chat --limit 10
PYTHONPATH=src python -m aiplane --profiles-dir /tmp/aiplane-demo-profiles models refresh --profile demo --provider ollama --query code --limit 10
PYTHONPATH=src python -m aiplane --profiles-dir /tmp/aiplane-demo-profiles models refresh --profile demo --provider ollama --query embed --limit 10
PYTHONPATH=src python -m aiplane --profiles-dir /tmp/aiplane-demo-profiles models list --profile demo --runtime ollama --role chat --ram-gb 16 --vram-gb 0 --sort-by role --limit 5
PYTHONPATH=src python -m aiplane --profiles-dir /tmp/aiplane-demo-profiles hardware recommend --profile demo
```

Capture the aliases for the next section:

```bash
CHAT_ALIAS=$(PYTHONPATH=src python -m aiplane --profiles-dir /tmp/aiplane-demo-profiles models list --profile demo --runtime ollama --role chat --enabled-only --sort-by role --limit 1 | python -c 'import json,sys; print(json.load(sys.stdin)[0]["name"])')
AUTOCOMPLETE_ALIAS=$(PYTHONPATH=src python -m aiplane --profiles-dir /tmp/aiplane-demo-profiles models list --profile demo --runtime ollama --role autocomplete --enabled-only --sort-by role --limit 1 | python -c 'import json,sys; print(json.load(sys.stdin)[0]["name"])')
EMBEDDING_ALIAS=$(PYTHONPATH=src python -m aiplane --profiles-dir /tmp/aiplane-demo-profiles models list --profile demo --runtime ollama --role embedding --enabled-only --sort-by role --limit 1 | python -c 'import json,sys; print(json.load(sys.stdin)[0]["name"])')
printf 'chat=%s autocomplete=%s embedding=%s\n' "$CHAT_ALIAS" "$AUTOCOMPLETE_ALIAS" "$EMBEDDING_ALIAS"
```

What to highlight:

- refresh output includes `next_steps`;
- `models.generated.yaml` is an ignored review buffer, while checked-in `models.yaml` stays provider-only unless a user deliberately promotes aliases;
- model filtering can use runtime, role, capability, RAM, and VRAM constraints;
- hardware recommendations use the active hardware profile.

### 1:15-1:45 - Continue Config And Endpoint Flexibility

Plan and export Continue config from the discovered aliases:

```bash
PYTHONPATH=src python -m aiplane --profiles-dir /tmp/aiplane-demo-profiles integrations plan continue --profile demo --chat "$CHAT_ALIAS" --autocomplete "$AUTOCOMPLETE_ALIAS" --embedding "$EMBEDDING_ALIAS"
PYTHONPATH=src python -m aiplane --profiles-dir /tmp/aiplane-demo-profiles integrations export continue --profile demo --chat "$CHAT_ALIAS" --autocomplete "$AUTOCOMPLETE_ALIAS" --embedding "$EMBEDDING_ALIAS"
PYTHONPATH=src python -m aiplane --profiles-dir /tmp/aiplane-demo-profiles integrations export openai-compatible --profile demo --model "$CHAT_ALIAS" --endpoint http://localhost:11434/v1
```

Optional endpoint variation to show in voiceover or split screen:

```bash
PYTHONPATH=src python -m aiplane --profiles-dir /tmp/aiplane-demo-profiles integrations export openai-compatible --profile demo --model "$CHAT_ALIAS" --endpoint https://llm.example.com/v1 --api-key-env AIPLANE_GATEWAY_API_KEY
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

### 2:05-2:30 - Repeatable Local And Media Environments

First create/import a local machine profile into the disposable demo profile, then plan a small local chat stack. These commands write only under `/tmp/aiplane-demo-profiles` and can be rerun for rehearsal.

```bash
PYTHONPATH=src python -m aiplane --profiles-dir /tmp/aiplane-demo-profiles hardware export-machine --profile demo --name demo-local-cpu > /tmp/demo-local-cpu.machine.yaml
PYTHONPATH=src python -m aiplane --profiles-dir /tmp/aiplane-demo-profiles machines import --profile demo /tmp/demo-local-cpu.machine.yaml --name demo-local-cpu
PYTHONPATH=src python -m aiplane --profiles-dir /tmp/aiplane-demo-profiles machines list --profile demo
PYTHONPATH=src python -m aiplane --profiles-dir /tmp/aiplane-demo-profiles stacks setup --profile demo cpu_chat --runtime ollama --model "$CHAT_ALIAS" --machine demo-local-cpu --access same_host --dry-run
```

For the media path, show that audio, image, and video generation are represented as AI model choices with runtime and platform requirements. The demo does not need to run these on CPU. Use a pre-provisioned Azure/GPU target, show the command path used to plan or deploy that resource, kick off the generation job, fast-forward the wait, and show the generated clip at the end.

```bash
PYTHONPATH=src python -m aiplane --profiles-dir /tmp/aiplane-demo-profiles models refresh --profile demo --provider huggingface --query text-to-speech --dry-run --verbose --limit 10
PYTHONPATH=src python -m aiplane --profiles-dir /tmp/aiplane-demo-profiles models refresh --profile demo --provider huggingface --query text-to-image --disable-new --limit 10
PYTHONPATH=src python -m aiplane --profiles-dir /tmp/aiplane-demo-profiles models list --profile demo --role image_generation --runtime diffusers --ram-gb 64 --vram-gb 16 --sort-by role --limit 5
PYTHONPATH=src python -m aiplane --profiles-dir /tmp/aiplane-demo-profiles models refresh --profile demo --provider huggingface --query text-to-video --disable-new --limit 10
PYTHONPATH=src python -m aiplane --profiles-dir /tmp/aiplane-demo-profiles models list --profile demo --role video_generation --runtime diffusers --ram-gb 128 --vram-gb 16 --sort-by role --limit 5
PYTHONPATH=src python -m aiplane --profiles-dir /tmp/aiplane-demo-profiles machines discover azure --profile demo --region uksouth --workload media_generation --runtime diffusers --limit 5
PYTHONPATH=src python -m aiplane --profiles-dir /tmp/aiplane-demo-profiles deploy plan --profile demo --target azure_gpu_vm
```

What to highlight:

- stacks are bindings of machine, runtime, model, and access policy;
- local and remote setups use the same data model;
- media generation is selected through online provider discovery, generated aliases, runtime compatibility, and hardware filters before any alias is promoted into curated profile state.

### 2:30-3:00 - Azure Machine Discovery And Deployment Planning

Show Azure machine discovery by task/runtime, then model/machine fit planning:

```bash
PYTHONPATH=src python -m aiplane --profiles-dir /tmp/aiplane-demo-profiles machines azure-status --profile demo --region uksouth
PYTHONPATH=src python -m aiplane --profiles-dir /tmp/aiplane-demo-profiles machines discover azure --profile demo --region uksouth --workload inference_small --runtime ollama --limit 5
PYTHONPATH=src python -m aiplane --profiles-dir /tmp/aiplane-demo-profiles machines discover azure --profile demo --region uksouth --workload inference_large --runtime vllm --limit 5
PYTHONPATH=src python -m aiplane --profiles-dir /tmp/aiplane-demo-profiles machines import-azure-sku Standard_NC4as_T4_v3 --profile demo --region uksouth --name azure_t4_demo
PYTHONPATH=src python -m aiplane --profiles-dir /tmp/aiplane-demo-profiles machines recommend --profile demo --workload inference_large --runtime vllm --limit 5
PYTHONPATH=src python -m aiplane --profiles-dir /tmp/aiplane-demo-profiles deploy plan --profile demo --target azure_gpu_vm
```

Recording note:

Azure account-identifying fields are redacted by default, but still inspect the terminal before recording or use a sanitized pre-recorded fixture. The live discovery/import commands use the disposable demo profile so Azure discovery cache and imported SKU state stay outside the checked-in `profiles/local-dev` profile. Do not show raw Azure portal pages, subscription ids, tenant ids, or personal account names.

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
PYTHONPATH=src python -m aiplane providers test openai --credential-ref openai.personal
PYTHONPATH=src python -m aiplane --profiles-dir /tmp/aiplane-demo-profiles profiles validate demo
PYTHONPATH=src python -m aiplane --profiles-dir /tmp/aiplane-demo-profiles models refresh --profile demo --provider ollama --query chat --dry-run --limit 5
PYTHONPATH=src python -m aiplane --profiles-dir /tmp/aiplane-demo-profiles models refresh --profile demo --provider ollama --query chat --limit 10
PYTHONPATH=src python -m aiplane --profiles-dir /tmp/aiplane-demo-profiles models refresh --profile demo --provider ollama --query code --limit 10
PYTHONPATH=src python -m aiplane --profiles-dir /tmp/aiplane-demo-profiles models refresh --profile demo --provider ollama --query embed --limit 10
PYTHONPATH=src python -m aiplane --profiles-dir /tmp/aiplane-demo-profiles models list --profile demo --runtime ollama --role chat --ram-gb 16 --vram-gb 0 --sort-by role --limit 5
PYTHONPATH=src python -m aiplane --profiles-dir /tmp/aiplane-demo-profiles integrations plan continue --profile demo --chat "$CHAT_ALIAS" --autocomplete "$AUTOCOMPLETE_ALIAS" --embedding "$EMBEDDING_ALIAS"
PYTHONPATH=src python -m aiplane --profiles-dir /tmp/aiplane-demo-profiles integrations export continue --profile demo --chat "$CHAT_ALIAS" --autocomplete "$AUTOCOMPLETE_ALIAS" --embedding "$EMBEDDING_ALIAS"
PYTHONPATH=src python -m aiplane integrations export vscode-mcp
PYTHONPATH=src python -m aiplane mcp manifest
PYTHONPATH=src python -m aiplane --profiles-dir /tmp/aiplane-demo-profiles machines discover azure --profile demo --region uksouth --workload inference_small --runtime ollama --limit 5
```

## Immediate Next Steps To Mention At The End

Voiceover:

> Next, we are hardening the demo paths into repeatable examples: richer provider discovery, cleaner Azure output redaction, Docker-aware stack lifecycle, endpoint authentication plans, and better benchmark comparisons. The goal is not to hide complexity, but to make local, remote, and cloud AI environments explicit, reviewable, and repeatable.

Project next steps:

1. Add a sanitized Azure discovery example for the public demo.
2. Rehearse the disposable `/tmp/aiplane-demo-profiles` flow once immediately before recording.
3. Add or verify a clean Continue config recording path in VS Code.
4. Keep the media demo discovery-first: show online refresh, generated candidates, runtime/hardware filtering, then fast-forward a pre-provisioned Azure/GPU generation job and play the prepared audio/video clip.
5. Keep Docker/endpoint flexibility in the demo through exports and stack plans unless a live container workflow is fully validated.

## Demo Readiness Gate

The demo is ready to plan in detail when:

- current uncommitted changes are reviewed and committed by the human owner;
- GitHub sensitive SHA cleanup is confirmed;
- all commands in the dry-run list and disposable-profile setup pass on the recording machine;
- Azure output has been reviewed on screen and any account-identifying UI/output is redacted or replaced by a sanitized fixture;
- VS Code/Continue and MCP screenshots are rehearsed once;
- the media segment shows online-discovered AI audio, image, and video candidates and has a prepared, playable final clip generated from the selected media path.
