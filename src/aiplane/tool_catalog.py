from __future__ import annotations

CORE_TOOLCHAIN = ["docker", "openssh-client"]


TOOLCHAIN: dict[str, dict[str, object]] = {
    "azure-cli": {
        "command": "az",
        "description": "Azure CLI for account checks, VM/SKU discovery, quota checks, and Azure resource operations.",
        "category": "cloud",
        "needed_for": [
            "Azure account checks",
            "quota and capacity discovery",
            "VM/AKS/resource operations",
        ],
        "install": {
            "ubuntu": ["curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash"],
            "debian": ["curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash"],
            "fedora": [
                "sudo rpm --import https://packages.microsoft.com/keys/microsoft.asc",
                "sudo dnf install -y azure-cli",
            ],
            "macos": ["brew update", "brew install azure-cli"],
        },
    },
    "opentofu": {
        "command": "tofu",
        "description": "OpenTofu for Terraform-compatible repeatable infrastructure provisioning.",
        "category": "iac",
        "needed_for": [
            "repeatable infrastructure plans",
            "self-managed cloud setup",
            "reviewed VM/AKS provisioning plans",
        ],
        "install": {
            "ubuntu": [
                "follow https://opentofu.org/docs/intro/install/deb/ for the current signed apt repository setup"
            ],
            "debian": [
                "follow https://opentofu.org/docs/intro/install/deb/ for the current signed apt repository setup"
            ],
            "fedora": [
                "follow https://opentofu.org/docs/intro/install/rpm/ for the current signed rpm repository setup"
            ],
            "macos": ["brew install opentofu"],
        },
    },
    "terraform": {
        "command": "terraform",
        "description": "Terraform for users who already standardize on HashiCorp Terraform instead of OpenTofu.",
        "category": "iac",
        "needed_for": [
            "repeatable infrastructure plans",
            "teams standardized on Terraform",
            "reviewed VM/AKS provisioning plans",
        ],
        "install": {
            "ubuntu": [
                "follow https://developer.hashicorp.com/terraform/install for the current signed apt repository setup"
            ],
            "debian": [
                "follow https://developer.hashicorp.com/terraform/install for the current signed apt repository setup"
            ],
            "fedora": ["sudo dnf install -y terraform"],
            "macos": ["brew tap hashicorp/tap", "brew install hashicorp/tap/terraform"],
        },
    },
    "pulumi": {
        "command": "pulumi",
        "description": "Pulumi for provider-agnostic infrastructure as code using general-purpose languages.",
        "category": "iac",
        "needed_for": [
            "multi-cloud infrastructure plans",
            "teams preferring Python/TypeScript/Go IaC",
            "reviewed cloud resource workflows",
        ],
        "install": {
            "ubuntu": ["curl -fsSL https://get.pulumi.com | sh"],
            "debian": ["curl -fsSL https://get.pulumi.com | sh"],
            "fedora": ["curl -fsSL https://get.pulumi.com | sh"],
            "linux": ["curl -fsSL https://get.pulumi.com | sh"],
            "macos": ["brew install pulumi"],
        },
    },
    "vagrant": {
        "command": "vagrant",
        "description": "Vagrant for repeatable local VM development and test environments.",
        "category": "vm",
        "needed_for": [
            "local VM workflows",
            "provider-backed dev boxes",
            "starter Vagrantfile exports",
        ],
        "install": {
            "ubuntu": [
                "follow https://developer.hashicorp.com/vagrant/install for the current signed apt repository setup"
            ],
            "debian": [
                "follow https://developer.hashicorp.com/vagrant/install for the current signed apt repository setup"
            ],
            "fedora": ["follow https://developer.hashicorp.com/vagrant/install for the current rpm repository setup"],
            "macos": [
                "brew tap hashicorp/tap",
                "brew install hashicorp/tap/hashicorp-vagrant",
            ],
        },
    },
    "packer": {
        "command": "packer",
        "description": "Packer for building reusable VM or cloud machine images before provisioning.",
        "category": "image-build",
        "needed_for": [
            "golden VM images",
            "cloud image pipelines",
            "starter Packer template exports",
        ],
        "install": {
            "ubuntu": [
                "follow https://developer.hashicorp.com/packer/install for the current signed apt repository setup"
            ],
            "debian": [
                "follow https://developer.hashicorp.com/packer/install for the current signed apt repository setup"
            ],
            "fedora": ["follow https://developer.hashicorp.com/packer/install for the current rpm repository setup"],
            "macos": ["brew tap hashicorp/tap", "brew install hashicorp/tap/packer"],
        },
    },
    "devcontainer-cli": {
        "command": "devcontainer",
        "description": "Dev Container CLI for reproducible containerized development environments.",
        "category": "container",
        "needed_for": [
            "devcontainer exports",
            "containerized development shells",
            "local dependency setup in containers",
        ],
        "install": {
            "ubuntu": ["npm install -g @devcontainers/cli"],
            "debian": ["npm install -g @devcontainers/cli"],
            "fedora": ["npm install -g @devcontainers/cli"],
            "linux": ["npm install -g @devcontainers/cli"],
            "macos": ["npm install -g @devcontainers/cli"],
        },
    },
    "docker": {
        "command": "docker",
        "description": "Docker Engine/CLI for local and VM-hosted runtime containers.",
        "category": "container",
        "needed_for": [
            "containerized runtimes",
            "TGI/LocalAI serving",
            "runtime bundles and stacks",
        ],
        "install": {
            "ubuntu": [
                "follow https://docs.docker.com/engine/install/ubuntu/ for the current Docker apt repository setup"
            ],
            "debian": [
                "follow https://docs.docker.com/engine/install/debian/ for the current Docker apt repository setup"
            ],
            "fedora": [
                "follow https://docs.docker.com/engine/install/fedora/ for the current Docker dnf repository setup"
            ],
            "macos": ["install Docker Desktop from https://docs.docker.com/desktop/setup/install/mac-install/"],
        },
    },
    "docker-compose": {
        "command": "docker",
        "description": "Docker Compose plugin for reusable multi-runtime stacks.",
        "category": "container",
        "needed_for": [
            "multi-runtime local stacks",
            "compose exports",
            "repeatable single-host runtime setups",
        ],
        "install": {
            "ubuntu": ["sudo apt-get install -y docker-compose-plugin"],
            "debian": ["sudo apt-get install -y docker-compose-plugin"],
            "fedora": ["sudo dnf install -y docker-compose-plugin"],
            "macos": ["Docker Desktop includes Docker Compose"],
        },
    },
    "kubectl": {
        "command": "kubectl",
        "description": "Kubernetes CLI for AKS and existing Kubernetes clusters.",
        "category": "kubernetes",
        "needed_for": [
            "AKS/Kubernetes runtime deployment",
            "cluster inspection",
            "runtime operations on existing clusters",
        ],
        "install": {
            "ubuntu": ["sudo snap install kubectl --classic"],
            "debian": ["follow https://kubernetes.io/docs/tasks/tools/install-kubectl-linux/"],
            "fedora": ["sudo dnf install -y kubernetes-client"],
            "macos": ["brew install kubectl"],
        },
    },
    "helm": {
        "command": "helm",
        "description": "Helm for packaging runtime deployments on Kubernetes/AKS.",
        "category": "kubernetes",
        "needed_for": [
            "Kubernetes runtime packaging",
            "AKS add-ons",
            "chart-based deployment workflows",
        ],
        "install": {
            "ubuntu": ["curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash"],
            "debian": ["curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash"],
            "fedora": ["sudo dnf install -y helm"],
            "macos": ["brew install helm"],
        },
    },
    "openssh-client": {
        "command": "ssh",
        "description": "OpenSSH client for tunnels and remote self-managed workstations/VMs.",
        "category": "remote",
        "needed_for": [
            "SSH tunnels",
            "remote workstation/VM access",
            "machine export/import workflows",
        ],
        "install": {
            "ubuntu": ["sudo apt-get install -y openssh-client"],
            "debian": ["sudo apt-get install -y openssh-client"],
            "fedora": ["sudo dnf install -y openssh-clients"],
            "macos": ["OpenSSH is included with macOS"],
        },
    },
    "ansible": {
        "command": "ansible",
        "description": "Optional agentless host configuration over SSH when shell/cloud-init setup becomes too large.",
        "category": "configuration",
        "needed_for": [
            "optional SSH host configuration",
            "repeatable remote setup steps",
        ],
        "install": {
            "ubuntu": ["python -m pip install --user ansible"],
            "debian": ["python -m pip install --user ansible"],
            "fedora": ["python -m pip install --user ansible"],
            "macos": ["brew install ansible"],
        },
    },
    "ruff": {
        "command": "ruff",
        "description": "Ruff formatter/linter for fast, repeatable Python style checks.",
        "category": "quality",
        "needed_for": [
            "Python formatting",
            "Python lint checks",
            "CI quality gates",
        ],
        "install": {
            "ubuntu": ["python -m pip install -e '.[dev]'"],
            "debian": ["python -m pip install -e '.[dev]'"],
            "fedora": ["python -m pip install -e '.[dev]'"],
            "linux": ["python -m pip install -e '.[dev]'"],
            "macos": ["python -m pip install -e '.[dev]'"],
        },
    },
    "black": {
        "command": "black",
        "description": "Black Python formatter. Ruff is the configured formatter, but Black is tracked for teams that prefer or compare against it.",
        "category": "quality",
        "needed_for": [
            "Python formatting compatibility",
            "local editor formatter setup",
            "style consistency checks",
        ],
        "install": {
            "ubuntu": ["python -m pip install -e '.[dev]'"],
            "debian": ["python -m pip install -e '.[dev]'"],
            "fedora": ["python -m pip install -e '.[dev]'"],
            "linux": ["python -m pip install -e '.[dev]'"],
            "macos": ["python -m pip install -e '.[dev]'"],
        },
    },
    "lm-evaluation-harness": {
        "command": "lm_eval",
        "description": "EleutherAI LM Evaluation Harness for standard and custom model-quality benchmarks.",
        "category": "benchmark",
        "needed_for": [
            "quality benchmarks",
            "standard task evaluation",
            "model comparison",
        ],
        "install": {
            "ubuntu": ['python -m pip install "lm_eval[api,vllm]"'],
            "debian": ['python -m pip install "lm_eval[api,vllm]"'],
            "fedora": ['python -m pip install "lm_eval[api,vllm]"'],
            "linux": ['python -m pip install "lm_eval[api,vllm]"'],
            "macos": ['python -m pip install "lm_eval[api]"'],
        },
    },
    "vllm-benchmark-scripts": {
        "command": "vllm",
        "description": "vLLM CLI including serving benchmark commands for throughput, latency, and concurrency tests.",
        "category": "benchmark",
        "needed_for": ["vLLM serving benchmarks", "runtime parameter sweeps"],
        "install": {
            "ubuntu": ["python -m pip install vllm"],
            "debian": ["python -m pip install vllm"],
            "fedora": ["python -m pip install vllm"],
            "linux": ["python -m pip install vllm"],
            "macos": ["vLLM generally needs Linux/GPU-compatible setup; use a Linux GPU host or container"],
        },
    },
    "locust": {
        "command": "locust",
        "description": "Locust load testing CLI for endpoint and gateway concurrency/rate-limit tests.",
        "category": "benchmark",
        "needed_for": ["multi-user endpoint load tests", "gateway throttling checks"],
        "install": {
            "ubuntu": ["python -m pip install locust"],
            "debian": ["python -m pip install locust"],
            "fedora": ["python -m pip install locust"],
            "linux": ["python -m pip install locust"],
            "macos": ["python -m pip install locust"],
        },
    },
}


# End-user workflows are separate from tool categories. Required alternatives are
# any-of groups: a user needs one supported IaC implementation, not every one.
WORKFLOW_REQUIREMENTS: dict[str, dict[str, object]] = {
    "local_runtime": {
        "summary": "Run a self-managed model endpoint on the current machine.",
        "required": [],
        "any_of": [],
        "optional": ["docker", "docker-compose"],
        "runtimes": ["ollama", "llamacpp", "mlx", "docker_model_runner", "lmstudio", "vllm"],
    },
    "local_container": {
        "summary": "Use repeatable local containers and development shells.",
        "required": ["docker"],
        "any_of": [],
        "optional": ["docker-compose", "devcontainer-cli"],
        "runtimes": [],
    },
    "local_vm": {
        "summary": "Create a repeatable local VM and configure it after boot.",
        "required": ["vagrant"],
        "any_of": [],
        "optional": ["packer", "ansible", "openssh-client"],
        "runtimes": [],
    },
    "remote_workstation": {
        "summary": "Inspect and configure an existing workstation through SSH.",
        "required": ["openssh-client"],
        "any_of": [],
        "optional": ["ansible"],
        "runtimes": [],
    },
    "cloud_vm": {
        "summary": "Plan an Azure VM, access it through SSH, and optionally configure or image it.",
        "required": ["azure-cli", "openssh-client"],
        "any_of": [["opentofu", "terraform", "pulumi"]],
        "optional": ["packer", "ansible"],
        "runtimes": [],
    },
    "cloud_kubernetes": {
        "summary": "Plan Azure Kubernetes infrastructure and inspect workload prerequisites.",
        "required": ["azure-cli", "kubectl"],
        "any_of": [["opentofu", "terraform", "pulumi"]],
        "optional": ["helm"],
        "runtimes": [],
    },
    "quality": {
        "summary": "Run the repository's configured formatting and lint gates.",
        "required": ["ruff"],
        "any_of": [],
        "optional": ["black"],
        "runtimes": [],
    },
    "benchmark_quality": {
        "summary": "Run optional model-quality evaluation frameworks.",
        "required": [],
        "any_of": [["lm-evaluation-harness"]],
        "optional": [],
        "runtimes": [],
    },
    "benchmark_serving": {
        "summary": "Measure serving throughput, latency, and multi-user load.",
        "required": [],
        "any_of": [["vllm-benchmark-scripts", "locust"]],
        "optional": [],
        "runtimes": [],
    },
}


TOOL_WORKFLOWS: dict[str, dict[str, object]] = {
    "vagrant": {
        "task": "local VM lifecycle",
        "summary": "Create and manage repeatable local development VMs from a base box.",
        "prerequisites": [
            "Vagrant",
            "a VM provider such as VirtualBox, libvirt, Hyper-V, or VMware",
            "optional Packer-built box",
        ],
        "commands": [
            "vagrant init aiplane/ubuntu-dev",
            "vagrant up",
            "vagrant ssh",
            "vagrant halt",
        ],
        "artifacts": ["Vagrantfile"],
        "next_steps": [
            "Use Packer first if you need a custom base image.",
            "Run aiplane environment doctor inside the VM or against a configured remote endpoint.",
        ],
    },
    "packer": {
        "task": "machine image build",
        "summary": "Build reusable VM or cloud images before Vagrant or cloud provisioning uses them.",
        "prerequisites": [
            "Packer",
            "builder plugin/provider credentials",
            "OS installer/base image access",
        ],
        "commands": [
            "packer init .",
            "packer validate aiplane.pkr.hcl",
            "packer build aiplane.pkr.hcl",
        ],
        "artifacts": ["aiplane.pkr.hcl"],
        "next_steps": ["Use the resulting box/image from Vagrant, OpenTofu/Terraform, Pulumi, or a cloud CLI."],
    },
    "opentofu": {
        "task": "provider-agnostic infrastructure provisioning",
        "summary": "Default Terraform-compatible IaC target for repeatable cloud resources.",
        "prerequisites": [
            "OpenTofu",
            "provider credentials",
            "selected provider module/resources",
        ],
        "commands": ["tofu init", "tofu plan", "tofu apply"],
        "artifacts": ["main.tf", "variables.tf"],
        "next_steps": [
            "Fill in the provider block and resources for Azure, AWS, GCP, or another supported provider.",
            "Keep apply behind explicit review.",
        ],
    },
    "terraform": {
        "task": "Terraform-standardized infrastructure provisioning",
        "summary": "Terraform-compatible IaC for teams already standardized on HashiCorp Terraform.",
        "prerequisites": [
            "Terraform",
            "provider credentials",
            "selected provider module/resources",
        ],
        "commands": ["terraform init", "terraform plan", "terraform apply"],
        "artifacts": ["main.tf", "variables.tf"],
        "next_steps": [
            "Use the same module shape as OpenTofu unless a team policy requires Terraform-specific behavior."
        ],
    },
    "pulumi": {
        "task": "language-native infrastructure provisioning",
        "summary": "Provider-agnostic IaC using Python, TypeScript, Go, or other supported languages.",
        "prerequisites": [
            "Pulumi",
            "language runtime",
            "provider credentials",
            "Pulumi stack configuration",
        ],
        "commands": ["pulumi stack init dev", "pulumi preview", "pulumi up"],
        "artifacts": ["Pulumi.yaml", "__main__.py"],
        "next_steps": ["Choose Pulumi when the team wants normal programming-language abstractions for IaC."],
    },
    "devcontainer-cli": {
        "task": "containerized development shell",
        "summary": "Open a reproducible development environment backed by Docker-compatible containers.",
        "prerequisites": ["Docker", "Dev Container CLI"],
        "commands": [
            "devcontainer up --workspace-folder .",
            "devcontainer exec --workspace-folder . bash",
        ],
        "artifacts": [".devcontainer/devcontainer.json"],
        "next_steps": ["Use this for local dependency isolation; use Docker/Compose for runtime services."],
    },
    "ansible": {
        "task": "remote host configuration",
        "summary": "Configure local VMs, remote VMs, or remote PCs over SSH after they exist.",
        "prerequisites": ["OpenSSH", "Ansible", "SSH credentials/inventory"],
        "commands": [
            "ansible-inventory -i inventory.ini --list",
            "ansible-playbook -i inventory.ini playbook.yml --check",
            "ansible-playbook -i inventory.ini playbook.yml",
        ],
        "artifacts": ["inventory.ini", "playbook.yml"],
        "next_steps": ["Use Ansible after Vagrant/cloud provisioning when shell bootstrap steps become too large."],
    },
}
