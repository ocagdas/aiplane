# Self-Managed Machines and Stacks

`aiplane` can treat local PCs, on-prem/shared workstations, and self-managed cloud VMs as machine candidates. A machine is a normalized hardware/OS/runtime profile. A stack binds an optional orchestrator, runtime, primary model, machine, and access policy.

## Import vs Provision

Importing a machine does **not** create a VM, workstation, container, or AKS node pool. It only registers a machine profile in `profiles/<profile>/hardware.yaml` under `self_managed_machines`.

Think of an imported machine as one of these:

- a real machine you already profiled with `aiplane hardware export-machine`;
- a manually described on-prem/shared workstation;
- an Azure VM SKU candidate selected from discovery;
- a planned machine shape that still needs to be provisioned.

Provisioning is a separate step. For Azure, provisioning means creating the VM, AKS node pool, networking, disks, identity, and access rules with `az`/`kubectl`/Docker/SSH. Today `aiplane` can plan and check these flows, run a guarded Azure VM create path, and run narrow same-host stack runtime steps. Broad SSH/AKS model-serving automation remains planned.

## Export a Machine Profile

Run this on the machine you want to profile:

```bash
aiplane hardware export-machine --name gpu_box_01 > gpu_box_01.machine.yaml
```

The export includes CPU, RAM, GPU, VRAM, unified memory, accelerator APIs, OS, hostname/platform metadata, and basic runtime hints such as Docker/Ollama/NVIDIA tool availability.

For JSON instead of YAML:

```bash
aiplane hardware export-machine --name gpu_box_01 --format json
```

## Import on the Control Machine

Move the exported file to your main PC/control-plane checkout and import it:

```bash
aiplane machines import gpu_box_01.machine.yaml
aiplane machines list
aiplane machines show gpu_box_01
aiplane machines validate gpu_box_01
```

Override values when the raw machine facts need allocation-specific changes:

```bash
aiplane machines import gpu_box_01.machine.yaml \
  --set memory_gb=128 \
  --set vram_gb=48 \
  --set gpu_count=1
```

## First Local Stack Prerequisite

For a first same-host stack, register the current machine before running `stacks setup`. Hardware templates such as `local_auto` describe capacity patterns, but stack setup expects a named machine entry from `aiplane machines list`.

```bash
aiplane hardware export-machine --name local_box > local_box.machine.yaml
aiplane machines import local_box.machine.yaml
aiplane machines list
aiplane machines validate local_box
```

Preview the stack binding first:

```bash
aiplane stacks setup local_ollama_stack \
  --runtime ollama \
  --model qwen-tiny \
  --machine local_box \
  --access same_host \
  --endpoint http://localhost:11434/v1 \
  --dry-run
```

Persist the stack only after the preview names the intended runtime, model, machine, access mode, and endpoint:

```bash
aiplane stacks setup local_ollama_stack \
  --runtime ollama \
  --model qwen-tiny \
  --machine local_box \
  --access same_host \
  --endpoint http://localhost:11434/v1

aiplane stacks plan local_ollama_stack
aiplane stacks doctor local_ollama_stack
```

## Remote Profiling Plan

You can plan remote profiling over SSH. This does not run SSH yet; it renders the commands to execute:

```bash
aiplane machines profile-remote-plan \
  --name gpu_box_01 \
  --host gpu-box.example.com \
  --user dev
```

The same pattern applies to a self-managed Azure VM or any Linux machine where `aiplane` can be installed and run once.

## Recommend Machines

Rank imported machines for a model/runtime/workload:

```bash
aiplane machines recommend --model qwen-coder-32b --runtime vllm
aiplane machines recommend --workload inference_large
```

Workload classes include `inference_tiny`, `inference_small`, `inference_medium`, `inference_large`, `training_finetune`, `batch_embedding_indexing`, `compile_build`, and `media_generation`.

## Azure Candidate Discovery

Azure discovery starts with live Azure CLI SKU discovery when `az` is installed and reachable. If live discovery is unavailable, it falls back to built-in offline SKU hints:

Check Azure CLI status before discovery:

```bash
aiplane machines azure-status
aiplane machines azure-status --region uksouth --sku-query
```

`azure-status` reports three separate facts: whether `az` is installed, whether `az account show` works, and whether the VM SKU query works for the requested region. A valid account session does not always mean the compute SKU query is usable; subscription/tenant context, permissions, or login scope can still block the live query.


```bash
aiplane machines discover azure --region uksouth --workload inference_large
aiplane machines discover azure --region uksouth --model qwen-coder-32b --runtime vllm
```

Import a selected SKU into the same self-managed machine inventory:

```bash
aiplane machines import-azure-sku Standard_NC40ads_H100_v5 \
  \
  --region uksouth \
  --name azure_h100_test
```


Discovery output includes a final `discovery` block with:

- `method`: `live` when `az vm list-skus` supplied usable results, otherwise `offline`.
- `source`: the concrete source, such as `az_vm_list_skus` or `static_hints`.
- `status`: why that method was used.
- `cache`: where the latest discovery result was written.

When live Azure discovery works, output also includes:

- `quota`: live `az vm list-usage` results for the selected region, including current usage, limit, and remaining capacity where Azure returns those values.
- `restrictions`: SKU restriction data from `az vm list-skus`, such as subscription or location restrictions.

Results are cached in `profiles/<profile>/machine-discovery-cache.json`. Offline results create or update the cache only when no live cache exists for the same provider/region/filter. A later live discovery always overwrites the cached offline result for that same key, so Azure data takes precedence over static hints as soon as it is available.

Inspect or clear cached discovery results:

```bash
aiplane machines cache-list
aiplane machines cache-clear
aiplane machines cache-clear --key azure__uksouth__inference_large__any_model__any_runtime
```

Always verify real Azure availability, quota, pricing, and exact GPU memory before provisioning.

## Spinning Up an Azure Machine

Current practical flow:

1. Check Azure CLI state:

```bash
aiplane machines azure-status --region uksouth --sku-query
```

2. Discover candidate machine shapes:

```bash
aiplane machines discover azure --region uksouth --workload inference_large
```

3. Import the selected SKU as a planned/self-managed machine entry:

```bash
aiplane machines import-azure-sku Standard_NC40ads_H100_v5 \
  \
  --region uksouth \
  --name azure_h100_test
```

This still has not created the Azure VM. It only gives the control plane a named target shape.

4. Create or update a deploy target in `profiles/<profile>/targets.yaml`, or use the existing `azure_gpu_vm` target as a starting point. Set the real resource group, region, VM name, image, VM size, SSH key, network, and runtime.

5. Render and check the Azure VM plan:

```bash
aiplane deploy plan --target azure_gpu_vm
aiplane deploy doctor --target azure_gpu_vm
```

6. To create the VM through `aiplane`, review the plan and doctor output first, then run guarded apply:

```bash
aiplane deploy apply --target azure_gpu_vm
```

This runs the mutating Azure CLI steps shown in the plan, such as resource group creation, VM creation, and optional SSH port opening. It can create billable Azure resources.

7. After the VM exists and SSH works, profile the live VM from inside the OS and import that real profile back into the control machine:

```bash
aiplane machines profile-remote-plan \
  --name azure_h100_live \
  --host <vm-ip-or-dns> \
  --user azureuser
```

8. Create a stack that binds optional orchestrator + runtime + model + live machine:

```bash
aiplane stacks setup qwen32b_on_h100 \
  --orchestrator langgraph \
  --runtime vllm \
  --model qwen-coder-32b \
  --machine azure_h100_live \
  --access ssh_tunnel \
  --endpoint http://localhost:8000/v1

aiplane stacks plan qwen32b_on_h100
aiplane stacks doctor qwen32b_on_h100
```

Stack plans include preflight checks for runtime prerequisites, likely port conflicts on local endpoints, endpoint auth policy, and model cache-path hints. Doctor output folds those checks into the normal readiness checks so you can catch missing host tools or risky endpoint settings before running lifecycle commands.

## Stacks

A stack is the operational unit for running or exposing a self-managed AI setup. It binds one optional orchestrator, one runtime, one primary model, one machine, and one access policy.

That one-to-one shape is intentional for now. If you need separate planner/coder/reviewer models, create separate stacks or wait for the planned multi-role stack schema. Keeping the first stack model simple makes fit checks, lifecycle commands, and exports easier to reason about.

Before creating a stack, the machine must exist in `aiplane machines list`. Hardware templates such as `local_auto` are not automatically stack machines. Export/import a real machine profile first, or import an Azure SKU candidate.

Create or update a stack:

```bash
aiplane stacks setup coding_agents \
  --orchestrator langgraph \
  --runtime vllm \
  --model qwen-coder-32b \
  --machine azure_h100_live \
  --access ssh_tunnel \
  --endpoint http://localhost:8000/v1 \
  --limit timeout=30m \
  --limit max_parallel_agents=3 \
  --tool shell=guarded \
  --tool filesystem=workspace_only
```


Stack `--limit` and `--tool` values are structured pass-through metadata. `aiplane` stores and exports them, but enforcement belongs to the runtime, orchestrator, wrapper script, or later workload runner.

Common examples:

```bash
--limit timeout=30m
--limit max_parallel_agents=3
--limit max_tokens=200000
--tool shell=guarded
--tool filesystem=workspace_only
--tool git=read_only
```

Preview without writing:

```bash
aiplane stacks setup coding_agents \
  --orchestrator langgraph \
  --runtime vllm \
  --model qwen-coder-32b \
  --machine azure_h100_live \
  --dry-run
```

Plan and check it:

```bash
aiplane stacks plan coding_agents
aiplane stacks doctor coding_agents
aiplane stacks status coding_agents
```

Prepare the stack. This is the convenience lifecycle command for install/pull/config style actions:

```bash
aiplane stacks prepare coding_agents --dry-run
aiplane stacks prepare coding_agents
```

Start or stop runtime-side services:

```bash
aiplane stacks start coding_agents --dry-run
aiplane stacks start coding_agents
aiplane stacks stop coding_agents
aiplane stacks restart coding_agents
```

`start` does not implicitly install or pull models. Use `prepare` first when you want the higher-level install/pull/config path.

For same-host/local stacks, lifecycle commands return structured execution reporting: `status`, `outcome`, `steps_total`, `steps_executed`, `failed_step`, per-step stdout/stderr tails, and a best-effort `runtime_status_after` snapshot. Remote, SSH, Azure, and AKS stacks still return planned commands instead of executing.

Export IDE or packaging artifacts:

```bash
aiplane stacks export continue coding_agents
aiplane stacks export openai-compatible coding_agents
aiplane stacks export dockerfile coding_agents
aiplane stacks export conda-yaml coding_agents
aiplane stacks export compose coding_agents
```

The Dockerfile, Conda YAML, and Compose exports are starter artifacts for review, CI, or custom packaging. They include profile-aware comments or environment variables for stack name, profile, orchestrator, runtime, model, endpoint, machine, limits, tool policies, and selected Docker resource hints where available. The normal user flow is still `stacks setup`, `stacks prepare`, and `stacks start`.

## Orchestrators

Orchestrators are frameworks that can run agent or workflow logic on top of a configured model endpoint. `aiplane` does not initiate autonomous workloads here. It catalogs orchestrator options and lets stacks bind an orchestrator to a runtime/model/machine target.

Initial orchestrator catalog:

Profile-specific orchestrator selections are stored in `profiles/<profile>/orchestrators.yaml`. The built-in catalog remains in code; the profile file only stores your selected/configured orchestrator settings.

```bash
aiplane orchestrators list
aiplane orchestrators list --provider ollama
aiplane orchestrators list --runtime ollama --runtime vllm
aiplane orchestrators list --provider ollama --group-by provider
aiplane orchestrators list --runtime ollama --runtime vllm --group-by runtime
aiplane orchestrators show langgraph
aiplane orchestrators setup langgraph --runtime ollama --model qwen-tiny --dry-run
aiplane orchestrators setup langgraph --runtime ollama --model qwen-tiny --approval-mode ask
aiplane orchestrators doctor langgraph
```

`orchestrators list` includes `supported_providers` and `supported_runtimes`.
Use `--provider` or repeated `--runtime` filters to find orchestrators that can
work with a specific endpoint/provider or all listed runtimes. `--group-by
provider` and `--group-by runtime` present the same compatibility data grouped
for scanning.

`orchestrators setup` writes the profile-specific orchestrator selection and
hints into `orchestrators.yaml`. It can record a runtime, model, endpoint,
environment mode, approval mode, limits, and tool-policy hints. Use `--dry-run`
to preview the config without writing it.

Initial priorities:

- `langgraph`: structured state/graph workflows and bounded agent trees.
- `crewai`: role/task oriented multi-agent crews.
- `autogen`: Microsoft-origin multi-agent conversation/workflow framework.
- `openhands`: heavier software-engineering agent platform, relevant later for coding workloads.
- `semantic_kernel`: useful later for Azure/Microsoft application SDK patterns.
- `llamaindex_workflows`: useful later for retrieval/data-heavy workflows.

A runnable deployment binding still belongs to stacks. Use stacks when you want
to bind an orchestrator to a runtime, model, machine, and access method:

```bash
aiplane stacks setup coding_agents \
  --orchestrator langgraph \
  --runtime ollama \
  --model qwen-tiny \
  --machine local_box \
  --limit timeout=30m \
  --tool shell=guarded
```

Limits, approval labels, and tool policies for orchestrated workloads are structured pass-through stack fields. `aiplane` stores and exports them, but the orchestrator/runtime decides whether and how to enforce them.

## Current Limits

- Same-host/local stack lifecycle is the first supported execution path. It calls `scripts/provider_helper.sh` directly for runtime install/pull/start/stop/restart actions.
- SSH, Azure VM, and AKS stack lifecycle automation returns planned commands instead of executing until remote execution and audit controls are hardened.
- Stack export artifacts are starter files, not guaranteed production-ready deployment manifests.
