# Hardware and Resource Configuration

`aiplane` can describe and inspect local/shared/cloud hardware so model choices
are repeatable. The goal is to make CPU, RAM, GPU, VRAM, unified memory, Docker
resource limits, and remote target capacity explicit in profiles.

## Commands

```bash
aiplane hardware discover
aiplane hardware discover --select-closest --dry-run
aiplane hardware discover --select-closest
aiplane hardware clear
aiplane hardware active
aiplane hardware show
aiplane hardware show --format text
aiplane hardware show --format json
aiplane hardware show --verbosity 0
aiplane hardware show --list-types
aiplane hardware templates
aiplane hardware schema
aiplane hardware use nvidia_consumer_gpu --set vram_gb=16
aiplane hardware set memory_gb=64 gpu_index=0
aiplane hardware doctor
aiplane hardware doctor --model MODEL_ALIAS
aiplane hardware recommend
aiplane hardware recommend --runtime ollama --context-tokens 32768
aiplane hardware recommend --score-profile throughput --include-not-recommended
aiplane hardware assess MODEL_ALIAS --runtime ollama --context-tokens 32768
aiplane hardware scoring
aiplane hardware export-machine --name local_box > local_box.machine.yaml
```

- `discover`: probes the current machine for CPU count, RAM, visible
  NVIDIA/AMD GPUs where local tools are available, and closest matching
  hardware templates. Use this when you want to dump what `aiplane` can see on
  the current host without changing profile config. Add `--select-closest` to
  update the active hardware template, or combine it with `--dry-run` to preview
  that write first.
- `clear`: resets selected hardware state back to `local_auto`. Raw discovery is
  not cached, so there is no separate discovery cache to clear.
- `active`: prints only the selected hardware config, including template origin,
  custom status, current values, and the normalized effective machine used for
  recommendations.
- `show`: prints the selected hardware summary (`active_selection` and
  `effective_machine`). Use `--format text` for compact output and `--format json`
  for scripts; output is still scoped by `--verbosity`.
  `--verbosity 0` omits template-catalog rows and keeps the summary terse.
- `templates`: prints immutable hardware templates.
- `schema`: prints the editable machine fields used for recommendation and fit checks.
- `use`: copies a template into the selected config and optionally applies
  `--set key=value` overrides without changing the template.
- `set`: updates the selected config values and marks it customized.
- `doctor`: compares discovered hardware against model fit metadata such as
  minimum RAM and VRAM.
- `recommend`: groups configured models into `recommended`, `usable`, and
  `remote_or_cloud` for the current hardware. Local rows include resource
  estimates, feasible placement modes, blockers, and a versioned placement-
  readiness score. Use `--runtime`, `--context-tokens`, and
  `--score-profile` to make those assumptions explicit. Models that fail a
  hard policy, runtime, or placement gate are hidden by default; use
  `--include-not-recommended` for the full diagnostic list.
  JSON output retains versioned provenance for model, machine, discovery,
  runtime, policy, benchmark sample count, and unresolved evidence.
- `assess`: explains one model's weight, KV-cache and workspace estimates,
  per-mode device capacity, runtime constraints, score components, normalized
  weights, evidence coverage, and assumptions.
- `scoring`: prints the available scoring profiles and the safe data-only
  extension contract. It does not load plugins or execute hook commands.
- `export-machine`: writes the normalized active machine as a portable machine
  profile that can be imported elsewhere with `aiplane machines import`.

Quick ways to show the current host:

```bash
aiplane hardware discover
aiplane hardware discover --select-closest --dry-run
aiplane hardware discover --select-closest
aiplane hardware clear
aiplane hardware active
aiplane hardware show
```

## Supported Hardware Shapes

The profile can represent normal PCs, shared workstations, cloud VMs, and
unified-memory AI workstations. Example profile names include:

- `local_auto`: discover this machine automatically.
- `cpu_laptop`: CPU-only laptop or small desktop.
- `nvidia_consumer_gpu`: RTX-class local GPU workstation.
- `nvidia_workstation_gpu`: workstation/datacenter NVIDIA GPU.
- `nvidia_dgx_spark_style`: NVIDIA unified-memory AI workstation style.
- `amd_consumer_gpu`: Radeon-class local GPU workstation.
- `amd_ryzen_ai_max_halo_style`: AMD Ryzen AI Max/Halo unified-memory style.
- `cloud_gpu_vm`: shared/cloud GPU VM endpoint.
- `aks_gpu_pool`: Kubernetes GPU node pool.

These are configuration shapes, not hard dependencies. The same model catalog
and provider setup can point at a local laptop, shared workstation, Azure GPU VM,
Container Apps endpoint, or AKS node pool.


## Machine Properties

The selected hardware config is a mutable copy of a template. It can include a
stock tag/SKU and the actual resources available to the runtime. This lets you
start from something recognizable, such as an Azure VM size or a workstation
class, then override the real RAM, GPU count, VRAM, or accelerator settings.

Show the fillable structure:

```bash
aiplane hardware schema
```

Core fields:

- `machine_tag`: friendly label, for example `my_4090_box` or `azure_h100_test`.
- `provider`: `local`, `onprem`, `azure`, `aws`, `gcp`, or another owner/source.
- `stock_sku`: vendor or cloud SKU, for example `Standard_NC40ads_H100_v5`.
- `placement`: where it runs, such as `same_host`, `workstation`, `vm`,
  `container`, or `kubernetes`.
- `substrate`: execution substrate, such as `native`, `venv`, `conda`, `docker`,
  `compose`, `kubernetes`, or `vm`.
- `cpu_cores` and `cpu_threads`: allocated CPU capacity.
- `memory_gb`: RAM available to the model runtime.
- `gpu_vendor`, `gpu_model`, `gpu_count`, `gpu_indices`: visible or allocated GPU
  resources.
- `vram_gb`: usable VRAM on the main GPU for a single model load.
- `total_vram_gb`: total visible VRAM across GPUs; useful when model parallelism
  is configured.
- `unified_memory_gb`: shared CPU/GPU memory for unified-memory systems.
- `accelerator_apis`: runtime acceleration APIs such as `cuda`, `rocm`, `metal`,
  `vulkan`, `openvino`, or `cpu`.
- `os`: operating system expected by the runtime.

The schema can record several GPUs, their selected indices, and total VRAM, but
the current recommendation engine deliberately compares a model with the largest
single visible GPU. It does not add VRAM across devices unless a future placement
assessment can prove that the selected runtime, model format, and parallelism
mode support that layout. This avoids presenting an eight-GPU inventory as one
large interchangeable memory pool.

Live discovery is normalized into individual devices and homogeneous groups:

| Capability | Current status |
| --- | --- |
| NVIDIA on Linux | Per-device index, name, total/free VRAM, UUID, PCI bus, compute capability and driver through `nvidia-smi`; multi-device topology is captured when available |
| AMD on Linux | Per-device ROCm JSON evidence where available, with PCI identity fallback |
| Intel on Linux | Per-device PCI identity and OpenVINO backend evidence; memory may remain unresolved |
| Apple Silicon | Unified memory through `sysctl` and Metal GPU identity through `system_profiler` |
| Windows | System/free memory and display-adapter identity, capacity and driver through PowerShell CIM |
| Several visible GPUs | Preserved individually and grouped only when vendor, model and backend match; topology is evidence, not an automatic sharding claim |
| MIG/partitions and full NUMA fabrics | Still partial; unresolved fields remain visible instead of being guessed |

Placement estimation uses configured artifact size when available, otherwise
parameter count and quantization with a documented overhead. KV cache is exact
only when layer, attention-head, KV-head and head-dimension metadata are known.
Without those fields it is marked unresolved. Runtime rules distinguish
single-GPU, homogeneous tensor parallel/split, CPU offload and CPU-only modes.
Total VRAM is never treated as one interchangeable pool merely because several
devices are visible.

Example Azure GPU VM selection:

```bash
aiplane hardware use cloud_gpu_vm \
  --set machine_tag=azure_h100_test \
  --set provider=azure \
  --set stock_sku=Standard_NC40ads_H100_v5 \
  --set placement=vm \
  --set substrate=docker \
  --set memory_gb=320 \
  --set gpu_vendor=nvidia \
  --set gpu_model='H100 NVL' \
  --set gpu_count=1 \
  --set vram_gb=94 \
  --set accelerator_apis=cuda
```

`aiplane hardware recommend` uses this normalized active machine when it is
configured. With `local_auto`, unresolved `auto` values are filled from local
discovery. With a stock VM/workstation template, explicit overrides take
precedence over the template range. The shipped templates intentionally avoid
duplicate descriptive fields such as `type`, `vendor`, and `gpu`; use
`placement`, `substrate`, `gpu_vendor`, `gpu_model`, and accelerator fields
instead.

## Selecting a Hardware Template

Select a template with the CLI:

```bash
aiplane hardware templates
aiplane hardware use nvidia_consumer_gpu --set vram_gb=16
aiplane hardware active
```

`use` copies the template into `selected.values`; it does not mutate the template
under `hardware_profiles`. Additional changes go into the selected copy:

```bash
aiplane hardware set memory_gb=64 gpu_index=0
```

`active` shows the selected config, the template it originated from, whether it
has been customized, the current values, and the normalized `machine` object used
by recommendation. If a profile is hand-edited into a shape that no longer comes
from a template, it should be treated as custom.

Use `local_auto` when you want discovery to describe the current machine and
report the closest matching templates without committing to a fixed shape. Use
`aiplane hardware discover --select-closest` when you want discovery to update
the selected template to the nearest match. Use a
named template when you want runs, deployment plans, or integration exports to
be tied to an intended target such as a CPU laptop, NVIDIA workstation, AMD
unified-memory workstation, cloud GPU VM, or AKS GPU pool.

## Model Recommendation Criteria

`aiplane hardware recommend` first applies hard policy, runtime and placement
eligibility. Scoring cannot override a blocker. Eligible local models are then
ordered by a versioned placement-readiness score whose components remain
separate:

- resource headroom for the selected feasible execution mode;
- runtime readiness;
- requested versus native context fit;
- configured task-suitability metadata;
- measured performance or quality only when a benchmark explicitly declares a
  comparable evidence kind;
- resource-estimate confidence.

Missing components are excluded by renormalizing the available weights, and
`coverage` reports how much of the configured evidence was present. Ordinary
smoke-test pass counts and catalog capability metadata are never relabeled as
measured quality. The shipped `balanced`, `quality_evidence`, and
`throughput` profiles live under `placement_scoring` in `hardware.yaml`.

Teams can add reviewed external results without executable plugins:

```yaml
placement_scoring:
  extensions:
    - name: team_validation
      source_key: team_validation
      weight: 0.20
      description: fixed internal evaluation

# In one model entry in models.yaml:
score_contributions:
  team_validation:
    value: 92
    source: reviewed_eval_v2
    basis: fixed internal suite
```

Extension values must be between 0 and 100. They are explicit model data, are
shown in the component breakdown, and cannot run shell commands or import code.

## Resource Controls

Resource controls live in `profiles/<profile>/hardware.yaml` and
`profiles/<profile>/environment.yaml`. Examples:

```yaml
resource_controls:
  docker:
    cpus: 8
    memory: 32g
    gpus: all
    devices: []
```

Docker resource limits are included in stack export metadata. Runtime endpoints,
ports, and provider credentials belong in runtime/provider configuration, not in
the hardware template. Docker-specific execution settings live in
`environment.yaml`; hardware profiles describe what capacity is available or
intended.

## Local and Remote Access

A local IDE or CLI can use either local or remote model endpoints. The code does
not have to live on the remote machine if the local tool sends selected context
to the model endpoint, similar to cloud model workflows.

Common patterns:

- Local code + local model endpoint.
- Local code + shared workstation/cloud model endpoint.
- Remote dev workspace where code and model endpoint both live remotely.
- Remote job runner where code/artifacts are submitted intentionally.

`aiplane` should make the endpoint, auth, policy, and hardware target explicit
so users know when context leaves their machine.
