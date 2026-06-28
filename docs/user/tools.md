# External Toolchain

`aiplane tools` checks and installs prerequisite command-line tools that support cloud, container, Kubernetes, and remote-machine operations. These are not model runtimes. For example, Docker helps run runtime containers, Azure CLI helps inspect Azure resources, and SSH helps expose a remote Ollama/vLLM endpoint to your local IDE.

## Recommended Tool Set

`aiplane` keeps this intentionally small:

- `azure-cli`: Azure account, quota, VM/SKU, and resource checks.
- `opentofu`: default infrastructure-as-code target for repeatable self-managed cloud setup.
- `terraform`: supported alternative when a team already standardizes on Terraform.
- `pulumi`: provider-agnostic infrastructure as code using Python, TypeScript, Go, or other supported languages.
- `vagrant`: repeatable local VM development and test environments.
- `packer`: reusable VM or cloud machine images.
- `docker`: local or VM-hosted runtime containers.
- `docker-compose`: reusable multi-runtime stacks on one machine.
- `devcontainer-cli`: reproducible containerized development shells.
- `kubectl`: Kubernetes/AKS inspection and deployment operations.
- `helm`: Kubernetes packaging for runtime deployments.
- `openssh-client`: SSH tunnels and remote workstation/VM access.
- `ansible`: optional later-stage host configuration over SSH.
- `lm-evaluation-harness`: optional model-quality benchmark framework.
- `vllm-benchmark-scripts`: optional vLLM serving benchmark commands.
- `locust`: optional endpoint/gateway load-testing framework.

## Tool Task Matrix

| Task | Primary tool | Required? | Why it is used | Current `aiplane` support |
| --- | --- | --- | --- | --- |
| Minimal container runtime path | Docker | Mandatory for container workflows | Runs local or VM-hosted runtime containers such as TGI, LocalAI, and exported stack images. | Doctor, health check, install hint, stack/runtime export integration. |
| Remote access and tunnels | OpenSSH client | Mandatory for remote workflows | Connects to remote PCs/VMs and exposes remote model endpoints locally. | Doctor, install helper where safe, tunnel plan/start/status/stop. |
| Azure account/resource operations | Azure CLI | Optional | Checks account state, quotas, VM/SKU data, and Azure resources. | Doctor, install hint, Azure machine/deploy planning, narrow VM apply. |
| Provider-agnostic cloud provisioning | OpenTofu | Optional | Default IaC target for repeatable cloud resources across providers. | Doctor and install hint; export/apply workflows planned. |
| Terraform-standardized teams | Terraform | Optional | Terraform-compatible IaC for teams already committed to HashiCorp Terraform. | Doctor and install hint; export/apply workflows planned. |
| Language-native cloud provisioning | Pulumi | Optional | IaC using Python, TypeScript, Go, and other supported languages. | Doctor and install hint; project export workflows planned. |
| Local VM development | Vagrant | Optional | Creates repeatable local VM dev/test environments using a provider such as VirtualBox, libvirt, Hyper-V, or VMware. | Doctor and install hint; Vagrantfile export planned. |
| Reusable VM/cloud images | Packer | Optional | Builds golden machine images before provisioning local or cloud VMs. | Doctor and install hint; template export planned. |
| Containerized dev shell | Dev Container CLI | Optional | Opens reproducible development shells backed by Docker-compatible containers. | Doctor and install hint; devcontainer export planned. |
| Multi-container local stack | Docker Compose | Optional | Starts multiple local services/runtimes together. | Doctor, service health check, compose stack export. |
| Kubernetes/AKS operations | kubectl | Optional | Inspects and operates Kubernetes resources. | Doctor and install hint; guarded AKS workflows planned. |
| Kubernetes packaging | Helm | Optional | Installs packaged Kubernetes runtime charts. | Doctor and install hint; chart-driven runtime deployment planned. |
| Remote host configuration | Ansible | Optional | Applies repeatable package/service configuration to local VMs, remote VMs, and remote PCs over SSH. | Doctor and install hint; inventory/playbook workflows planned. |
| Model quality benchmark suite | lm-evaluation-harness | Optional | Runs external evaluation harness tasks. | Benchmark doctor/install/plan. |
| vLLM serving benchmark | vLLM benchmark scripts | Optional | Measures vLLM endpoint serving behavior. | Benchmark doctor/install/plan. |
| Endpoint load testing | Locust | Optional | Load-tests model endpoints and gateways. | Benchmark doctor/install/plan. |

Mandatory means required for the minimal supported path in that workflow, not required to install `aiplane` itself. Most tools are optional until a workflow asks for them.

## Health Checks

Check the full prerequisite set:

```bash
aiplane tools doctor
```

Check the active aiplane execution environment and group missing tools by whether
`aiplane` can attempt an install or whether manual/platform-specific work is
needed:

```bash
aiplane environment doctor
aiplane environment doctor --required-only
aiplane environment doctor --format json
```

`environment doctor` is the general setup check. It reports:

- the active `aiplane` execution environment;
- installed and missing external CLIs;
- whether each checked tool is mandatory for the minimal setup path or optional for specific workflows;
- what each CLI is needed for;
- whether `aiplane tools install NAME` can attempt an install;
- runtime prerequisite status for common local runtimes;
- dry-run setup commands to try next, such as `aiplane runtimes install vllm --dry-run`.

Text output is the default human-readable aligned table with tool/runtime name, type, status, mandatory/optional scope, and a short purpose. Use `--format json` for scripts and tests.

Check one tool:

```bash
aiplane tools doctor azure-cli
aiplane tools doctor docker
aiplane tools doctor openssh-client
```

The output reports command path, detected version where available, install hints, purposes, and service checks where they make sense. For example, Docker checks whether the daemon is reachable; Azure CLI checks whether `az account show` works.

## Provisioning and Setup Layers

Use the smallest layer that matches the target:

- Local machine dependency setup: `environment doctor`, runtime prerequisite checks, and guarded helper commands.
- Local containers: Docker, Docker Compose, and runtime bundle exports.
- Containerized development shells: Dev Container CLI, usually backed by Docker.
- Local VMs: Vagrant, with VirtualBox/libvirt/Hyper-V/VMware providers installed separately where needed.
- Remote VMs or remote PCs: OpenSSH for access and tunnels; Ansible is the natural next layer for repeatable package and service configuration.
- Cloud resources across providers: OpenTofu is the default provider-agnostic IaC target, Terraform is supported for teams already standardized on it, and Pulumi is available for teams that prefer general-purpose language IaC.
- Azure-specific resource operations: Azure CLI remains the direct Azure account, SKU, quota, and resource management integration.
- Reusable machine images: Packer prepares golden VM/cloud images before provisioning them with Vagrant, OpenTofu/Terraform, Pulumi, or cloud CLIs.

`aiplane` should wrap these tools with plans, doctors, dry-runs, and exports before it mutates a host or cloud account. The tool itself should not hide platform prerequisites such as a VM hypervisor, Docker daemon permissions, SSH credentials, or cloud authentication.

Runtime checks are related but separate from external CLI checks:

```bash
aiplane runtimes prerequisites ollama
aiplane runtimes prerequisites vllm
aiplane runtimes prerequisites all
```

Those commands list required and optional host tools, Ubuntu/Debian package hints where known, and helper commands that can be previewed before any install/start action.

## Guarded Installs

`aiplane` should provide install helpers for the crucial tools users normally need
to make self-managed AI stacks repeatable: Azure CLI, OpenTofu/Terraform,
Docker/Compose, kubectl, Helm, OpenSSH, and eventually Ansible. These helpers
are convenience wrappers around official install paths; they are not Python
package dependencies and they may require OS package repositories, services, or
manual permission changes.

Always preview first:

```bash
aiplane tools install azure-cli --dry-run
aiplane tools install opentofu --dry-run
aiplane tools install docker --dry-run
```

Run an install only after reviewing the commands:

```bash
aiplane tools install azure-cli
```

Some tools require manual or OS-specific steps. In those cases `aiplane` prints the official install instruction rather than guessing a risky system mutation.

## Platform Notes

These installs are not pure Python dependencies. Some tools can be installed with Python or Homebrew, but others need OS package repositories, system services, user groups, or a daemon:

- Docker needs an OS-level engine/daemon and permissions to access the Docker socket.
- Azure CLI, OpenTofu, Terraform, kubectl, and Helm are external CLIs.
- Ansible can often be installed with `pip` inside a venv or Conda environment, but using it against remote hosts still depends on SSH.

`aiplane` detects the platform and package manager where possible, currently focusing on Ubuntu/Debian/Fedora/macOS style installs.
