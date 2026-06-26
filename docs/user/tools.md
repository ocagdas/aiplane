# External Toolchain

`aiplane tools` checks and installs prerequisite command-line tools that support cloud, container, Kubernetes, and remote-machine operations. These are not model runtimes. For example, Docker helps run runtime containers, Azure CLI helps inspect Azure resources, and SSH helps expose a remote Ollama/vLLM endpoint to your local IDE.

## Recommended Tool Set

`aiplane` keeps this intentionally small:

- `azure-cli`: Azure account, quota, VM/SKU, and resource checks.
- `opentofu`: default infrastructure-as-code target for repeatable self-managed cloud setup.
- `terraform`: supported alternative when a team already standardizes on Terraform.
- `docker`: local or VM-hosted runtime containers.
- `docker-compose`: reusable multi-runtime stacks on one machine.
- `kubectl`: Kubernetes/AKS inspection and deployment operations.
- `helm`: Kubernetes packaging for runtime deployments.
- `openssh-client`: SSH tunnels and remote workstation/VM access.
- `ansible`: optional later-stage host configuration over SSH.
- `lm-evaluation-harness`: optional model-quality benchmark framework.
- `vllm-benchmark-scripts`: optional vLLM serving benchmark commands.
- `locust`: optional endpoint/gateway load-testing framework.

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
```

`environment doctor` is the general setup check. It reports:

- the active `aiplane` execution environment;
- installed and missing external CLIs;
- what each CLI is needed for;
- whether `aiplane tools install NAME` can attempt an install;
- runtime prerequisite status for common local runtimes;
- dry-run setup commands to try next, such as `aiplane runtimes install vllm --dry-run`.

Check one tool:

```bash
aiplane tools doctor azure-cli
aiplane tools doctor docker
aiplane tools doctor openssh-client
```

The output reports command path, detected version where available, install hints, purposes, and service checks where they make sense. For example, Docker checks whether the daemon is reachable; Azure CLI checks whether `az account show` works.

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
