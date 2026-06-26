from __future__ import annotations

import shlex
import shutil
import subprocess
from pathlib import Path

from .approvals import ApprovalHandler
from .audit import AuditLogger
from .env import EnvironmentManager
from .models import AuditEvent, Profile
from .policy import PolicyEngine
from .runtime_catalog import RuntimeCatalog


class ToolExecutor:
    def __init__(self, profile: Profile, audit: AuditLogger, approvals: ApprovalHandler | None = None):
        self.profile = profile
        self.audit = audit
        self.policy = PolicyEngine(profile)
        self.approvals = approvals or ApprovalHandler()
        self.environment = EnvironmentManager(profile)

    def run(self, tool_name: str, args: list[str]) -> str:
        decision = self.policy.tool_decision(tool_name)
        action = f"tool:{tool_name}"
        if not decision.allowed:
            self._audit(action, "blocked", {"reason": decision.reason})
            raise PermissionError(decision.reason)
        if not self.approvals.approve(action, decision):
            self._audit(action, "approval_denied", {"reason": decision.reason})
            raise PermissionError("approval denied")

        handler = getattr(self, f"_tool_{tool_name}", None)
        if handler is None:
            self._audit(action, "blocked", {"reason": "unknown tool"})
            raise ValueError(f"unknown tool: {tool_name}")
        try:
            output = handler(args)
            self._audit(action, "allowed", {"args": args, "output": output[-1000:]})
            return output
        except Exception as exc:
            self._audit(action, "failed", {"args": args, "error": str(exc)})
            raise

    def _tool_read_file(self, args: list[str]) -> str:
        path = self._workspace_path(_arg(args, 0, "path"))
        return path.read_text(encoding="utf-8")

    def _tool_write_file(self, args: list[str]) -> str:
        path = self._workspace_path(_arg(args, 0, "path"))
        content = _arg(args, 1, "content")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return f"wrote {path}"

    def _tool_grep(self, args: list[str]) -> str:
        pattern = _arg(args, 0, "pattern")
        target = self._workspace_path(args[1] if len(args) > 1 else ".")
        return self._command(["rg", pattern, str(target)], allow_failure=True)

    def _tool_git_status(self, args: list[str]) -> str:
        return self._command(["git", "status", "--short"], allow_failure=True)

    def _tool_git_diff(self, args: list[str]) -> str:
        return self._command(["git", "diff"], allow_failure=True)

    def _tool_run_tests(self, args: list[str]) -> str:
        command = args or ["python", "-m", "unittest", "discover"]
        return self._command(command, allow_failure=True)

    def _tool_build(self, args: list[str]) -> str:
        command = args or ["python", "-m", "compileall", "src"]
        return self._command(command, allow_failure=True)

    def _tool_lint(self, args: list[str]) -> str:
        command = args or ["python", "-m", "compileall", "src"]
        return self._command(command, allow_failure=True)

    def _tool_docker_exec(self, args: list[str]) -> str:
        if not args:
            raise ValueError("docker_exec requires docker arguments")
        return self._command(["docker", *args], allow_failure=True, use_environment=False)

    def _tool_git_commit(self, args: list[str]) -> str:
        message = " ".join(args).strip()
        if not message:
            raise ValueError("git_commit requires a commit message")
        return self._command(["git", "commit", "-m", message], allow_failure=True)

    def _workspace_path(self, value: str) -> Path:
        path = Path(value)
        if not path.is_absolute():
            path = self.profile.workspace / path
        decision = self.policy.path_decision(path)
        if not decision.allowed:
            raise PermissionError(decision.reason)
        return path.resolve()

    def _command(self, command: list[str], allow_failure: bool = False, use_environment: bool = True) -> str:
        plan = self.environment.plan(command) if use_environment else None
        actual_command = plan.command if plan else command
        cwd = plan.cwd if plan else self.profile.workspace
        result = subprocess.run(
            actual_command,
            cwd=cwd,
            check=False,
            text=True,
            capture_output=True,
        )
        output = (result.stdout + result.stderr).strip()
        if result.returncode and not allow_failure:
            raise RuntimeError(output or f"command failed: {actual_command}")
        return output

    def _audit(self, action: str, decision: str, details: dict[str, object]) -> None:
        self.audit.record(AuditEvent("tool", self.profile.name, action, decision, details))


TOOLCHAIN: dict[str, dict[str, object]] = {
    "azure-cli": {
        "command": "az",
        "description": "Azure CLI for account checks, VM/SKU discovery, quota checks, and Azure resource operations.",
        "category": "cloud",
        "needed_for": ["Azure account checks", "quota and capacity discovery", "VM/AKS/resource operations"],
        "install": {
            "ubuntu": ["curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash"],
            "debian": ["curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash"],
            "fedora": ["sudo rpm --import https://packages.microsoft.com/keys/microsoft.asc", "sudo dnf install -y azure-cli"],
            "macos": ["brew update", "brew install azure-cli"],
        },
    },
    "opentofu": {
        "command": "tofu",
        "description": "OpenTofu for Terraform-compatible repeatable infrastructure provisioning.",
        "category": "iac",
        "needed_for": ["repeatable infrastructure plans", "self-managed cloud setup", "future VM/AKS provisioning"],
        "install": {
            "ubuntu": ["follow https://opentofu.org/docs/intro/install/deb/ for the current signed apt repository setup"],
            "debian": ["follow https://opentofu.org/docs/intro/install/deb/ for the current signed apt repository setup"],
            "fedora": ["follow https://opentofu.org/docs/intro/install/rpm/ for the current signed rpm repository setup"],
            "macos": ["brew install opentofu"],
        },
    },
    "terraform": {
        "command": "terraform",
        "description": "Terraform for users who already standardize on HashiCorp Terraform instead of OpenTofu.",
        "category": "iac",
        "needed_for": ["repeatable infrastructure plans", "teams standardized on Terraform", "future VM/AKS provisioning"],
        "install": {
            "ubuntu": ["follow https://developer.hashicorp.com/terraform/install for the current signed apt repository setup"],
            "debian": ["follow https://developer.hashicorp.com/terraform/install for the current signed apt repository setup"],
            "fedora": ["sudo dnf install -y terraform"],
            "macos": ["brew tap hashicorp/tap", "brew install hashicorp/tap/terraform"],
        },
    },
    "docker": {
        "command": "docker",
        "description": "Docker Engine/CLI for local and VM-hosted runtime containers.",
        "category": "container",
        "needed_for": ["containerized runtimes", "TGI/LocalAI serving", "runtime bundles and stacks"],
        "install": {
            "ubuntu": ["follow https://docs.docker.com/engine/install/ubuntu/ for the current Docker apt repository setup"],
            "debian": ["follow https://docs.docker.com/engine/install/debian/ for the current Docker apt repository setup"],
            "fedora": ["follow https://docs.docker.com/engine/install/fedora/ for the current Docker dnf repository setup"],
            "macos": ["install Docker Desktop from https://docs.docker.com/desktop/setup/install/mac-install/"],
        },
    },
    "docker-compose": {
        "command": "docker",
        "description": "Docker Compose plugin for reusable multi-runtime stacks.",
        "category": "container",
        "needed_for": ["multi-runtime local stacks", "compose exports", "repeatable single-host runtime setups"],
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
        "needed_for": ["AKS/Kubernetes runtime deployment", "cluster inspection", "runtime operations on existing clusters"],
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
        "needed_for": ["Kubernetes runtime packaging", "AKS add-ons", "chart-based deployment workflows"],
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
        "needed_for": ["SSH tunnels", "remote workstation/VM access", "machine export/import workflows"],
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
        "needed_for": ["optional SSH host configuration", "repeatable remote setup steps"],
        "install": {
            "ubuntu": ["python -m pip install --user ansible"],
            "debian": ["python -m pip install --user ansible"],
            "fedora": ["python -m pip install --user ansible"],
            "macos": ["brew install ansible"],
        },
    },

    "lm-evaluation-harness": {
        "command": "lm_eval",
        "description": "EleutherAI LM Evaluation Harness for standard and custom model-quality benchmarks.",
        "category": "benchmark",
        "needed_for": ["quality benchmarks", "standard task evaluation", "model comparison"],
        "install": {
            "ubuntu": ["python -m pip install \"lm_eval[api,vllm]\""],
            "debian": ["python -m pip install \"lm_eval[api,vllm]\""],
            "fedora": ["python -m pip install \"lm_eval[api,vllm]\""],
            "linux": ["python -m pip install \"lm_eval[api,vllm]\""],
            "macos": ["python -m pip install \"lm_eval[api]\""],
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


class ToolchainManager:
    def __init__(self, profile: Profile):
        self.profile = profile

    def list(self) -> list[dict[str, object]]:
        return [self._tool_row(name) for name in sorted(TOOLCHAIN)]

    def tool_status(self, name: str) -> dict[str, object]:
        return self._tool_row(name)

    def environment_doctor(self, include_optional: bool = True) -> dict[str, object]:
        rows = self.list() if include_optional else [self._tool_row(name) for name in ["docker", "openssh-client"]]
        runtime_rows = _runtime_prerequisite_rows(self.profile, include_optional=include_optional)
        installable_missing = [row for row in rows if not row["installed"] and row.get("install_mode") == "automated"]
        manual_missing = [row for row in rows if not row["installed"] and row.get("install_mode") != "automated"]
        installed = [row for row in rows if row["installed"]]
        runtime_missing = [row for row in runtime_rows if row.get("known_runtime") and not row.get("ok")]
        return {
            "name": "environment_doctor",
            "profile": self.profile.name,
            "active_environment": EnvironmentManager(self.profile).show(),
            "platform": _platform_info(),
            "summary": {
                "tools_checked": len(rows),
                "tools_installed": len(installed),
                "tools_missing_installable_by_aiplane": len(installable_missing),
                "tools_missing_manual_or_platform_specific": len(manual_missing),
                "runtime_prerequisites_checked": len(runtime_rows),
                "runtime_prerequisites_missing": len(runtime_missing),
            },
            "installed": installed,
            "missing_installable_by_aiplane": installable_missing,
            "missing_manual_or_platform_specific": manual_missing,
            "runtime_prerequisites": runtime_rows,
            "notes": [
                "Use aiplane tools install NAME --dry-run for installable tools before running a real install.",
                "Use aiplane runtimes prerequisites RUNTIME for a focused runtime setup check with Ubuntu/Debian package hints.",
                "If a runtime is unavailable, try aiplane runtimes install RUNTIME --dry-run or aiplane runtimes start RUNTIME --dry-run where helper support exists.",
                "Manual/platform-specific entries need native vendor instructions, GPU drivers, app-store installers, or organization-specific permissions.",
                "Benchmark frameworks are optional unless you run their benchmark suite; aiplane models benchmark --spec is built in.",
            ],
        }

    def doctor(self, name: str | None = None) -> dict[str, object]:
        names = [name] if name else sorted(TOOLCHAIN)
        rows = [self._tool_row(item) for item in names]
        return {
            "name": "tools_doctor",
            "platform": _platform_info(),
            "ok": all(bool(row["installed"]) for row in rows if row.get("required", True)),
            "tools": rows,
            "notes": [
                "Doctor checks whether prerequisite CLIs are installed and whether selected services are reachable.",
                "Install commands are platform-specific; use aiplane tools install NAME --dry-run to preview before installing.",
            ],
        }

    def install(self, name: str, dry_run: bool = True, yes: bool = False) -> dict[str, object]:
        if name not in TOOLCHAIN:
            raise ValueError(f"unknown tool: {name}")
        row = self._tool_row(name)
        commands = self._install_commands(name)
        payload = {
            "name": name,
            "platform": _platform_info(),
            "installed": row["installed"],
            "dry_run": dry_run or not yes,
            "commands": commands,
            "results": [],
            "notes": ["Commands are predefined for this tool/platform. Review --dry-run output before installing."],
        }
        if dry_run or not yes:
            return payload
        results = []
        for command in commands:
            if _non_executable_install_note(command):
                results.append({"command": command, "executed": False, "returncode": None, "stdout": "", "stderr": "manual step required"})
                continue
            actual_command: str | list[str] = command
            cwd = self.profile.workspace
            use_shell = True
            if command.startswith("python -m pip "):
                plan = EnvironmentManager(self.profile).plan(shlex.split(command))
                actual_command = plan.command
                cwd = plan.cwd
                use_shell = False
            completed = subprocess.run(actual_command, cwd=cwd, shell=use_shell, text=True, capture_output=True, check=False)
            results.append({
                "command": command,
                "executed_command": actual_command,
                "cwd": str(cwd),
                "executed": True,
                "returncode": completed.returncode,
                "stdout": completed.stdout[-4000:],
                "stderr": completed.stderr[-4000:],
            })
            if completed.returncode:
                break
        payload["results"] = results
        payload["installed_after"] = self._tool_row(name)["installed"]
        return payload

    def _tool_row(self, name: str) -> dict[str, object]:
        if name not in TOOLCHAIN:
            raise ValueError(f"unknown tool: {name}")
        spec = TOOLCHAIN[name]
        command = str(spec["command"])
        path = shutil.which(command)
        version = _command_version(command) if path else None
        install_commands = self._install_commands(name)
        install_mode = _install_mode(install_commands)
        row = {
            "name": name,
            "category": spec.get("category"),
            "description": spec.get("description"),
            "needed_for": spec.get("needed_for", []),
            "command": command,
            "installed": bool(path),
            "path": path,
            "version": version,
            "health": self._health(name, command, bool(path)),
            "install_mode": install_mode,
            "installable_by_aiplane": install_mode == "automated",
            "install_commands": install_commands,
        }
        return row

    def _install_commands(self, name: str) -> list[str]:
        spec = TOOLCHAIN[name]
        install = spec.get("install", {}) if isinstance(spec, dict) else {}
        platform_id = _platform_id()
        if isinstance(install, dict):
            commands = install.get(platform_id) or install.get("linux") or []
            return [str(command) for command in commands]
        return []

    def _health(self, name: str, command: str, installed: bool) -> dict[str, object]:
        if not installed:
            return {"ok": False, "reason": "command not found"}
        if name == "azure-cli":
            completed = _checked_command([command, "account", "show"], self.profile.workspace)
            return {"ok": completed.get("returncode") == 0, "reason": "logged in" if completed.get("returncode") == 0 else "not logged in or account query failed"}
        if name == "docker":
            completed = _checked_command([command, "info"], self.profile.workspace)
            return {"ok": completed.get("returncode") == 0, "reason": "daemon reachable" if completed.get("returncode") == 0 else "docker CLI found but daemon is not reachable"}
        if name == "docker-compose":
            completed = _checked_command([command, "compose", "version"], self.profile.workspace)
            return {"ok": completed.get("returncode") == 0, "reason": "compose plugin available" if completed.get("returncode") == 0 else "docker compose plugin not available"}
        return {"ok": True, "reason": "command found"}


def _runtime_prerequisite_rows(profile: Profile, include_optional: bool) -> list[dict[str, object]]:
    catalog = RuntimeCatalog(profile)
    runtimes = ["ollama", "vllm", "tgi", "transformers", "localai"] if include_optional else ["ollama", "vllm"]
    rows: list[dict[str, object]] = []
    for runtime in runtimes:
        payload = catalog.prerequisites(runtime)
        rows.append({
            "runtime": runtime,
            "known_runtime": payload.get("known_runtime"),
            "ok": payload.get("ok"),
            "helper_management": payload.get("helper_management"),
            "install_supported_by_helper": payload.get("install_supported_by_helper"),
            "purpose": RUNTIME_PURPOSES.get(runtime, []),
            "missing_required": payload.get("missing_required", []),
            "missing_optional": payload.get("missing_optional", []),
            "ubuntu_install_hint": payload.get("ubuntu_install_hint"),
            "setup_commands": _runtime_setup_commands(runtime, payload),
            "notes": payload.get("notes", []),
        })
    return rows


RUNTIME_PURPOSES: dict[str, list[str]] = {
    "ollama": ["simple local model serving", "Continue/local IDE endpoint", "CPU or single-user workstation workflows"],
    "vllm": ["GPU OpenAI-compatible serving", "Hugging Face model repos", "throughput and latency benchmarking"],
    "tgi": ["containerized Hugging Face serving", "GPU server inference", "OpenAI-compatible endpoint workflows"],
    "transformers": ["Python library experiments", "training/fine-tuning scripts", "offline evaluation jobs"],
    "localai": ["OpenAI-compatible local service", "GGUF/llama.cpp-style models", "mixed backend experiments"],
}


def _runtime_setup_commands(runtime: str, payload: dict[str, object]) -> list[str]:
    commands = [f"aiplane runtimes prerequisites {runtime}"]
    if payload.get("install_supported_by_helper"):
        commands.append(f"aiplane runtimes install {runtime} --dry-run")
    if runtime in {"ollama", "vllm", "tgi", "localai"}:
        commands.append(f"aiplane runtimes start {runtime} --dry-run")
    return commands


def _checked_command(command: list[str], cwd: Path) -> dict[str, object]:
    try:
        completed = subprocess.run(command, cwd=cwd, text=True, capture_output=True, check=False, timeout=15)
    except subprocess.TimeoutExpired:
        return {"returncode": None, "stdout": "", "stderr": "timeout"}
    except OSError as exc:
        return {"returncode": None, "stdout": "", "stderr": str(exc)}
    return {"returncode": completed.returncode, "stdout": completed.stdout, "stderr": completed.stderr}


def _platform_info() -> dict[str, object]:
    return {"name": _platform_id(), "os_release": _os_release_id(), "package_manager": _package_manager()}


def _platform_id() -> str:
    import platform

    if platform.system() == "Darwin":
        return "macos"
    os_id = _os_release_id()
    if os_id in {"ubuntu", "debian", "fedora"}:
        return os_id
    return "linux"


def _os_release_id() -> str | None:
    path = Path("/etc/os-release")
    if not path.exists():
        return None
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if line.startswith("ID="):
            return line.split("=", 1)[1].strip().strip('"')
    return None


def _package_manager() -> str | None:
    for command in ["apt-get", "dnf", "pacman", "brew", "winget"]:
        if shutil.which(command):
            return command
    return None


def _command_version(command: str) -> str | None:
    candidates = [[command, "--version"], [command, "version"]]
    for candidate in candidates:
        try:
            completed = subprocess.run(candidate, text=True, capture_output=True, check=False, timeout=8)
        except Exception:
            continue
        output = (completed.stdout or completed.stderr).strip().splitlines()
        if completed.returncode == 0 and output:
            return output[0][:200]
    return None


def _non_executable_install_note(command: str) -> bool:
    return command.startswith("follow ") or command.startswith("install ") or command.startswith("OpenSSH is included") or command.startswith("Docker Desktop includes") or "generally needs" in command


def _install_mode(commands: list[str]) -> str:
    if not commands:
        return "unavailable"
    if any(_non_executable_install_note(command) for command in commands):
        return "manual"
    return "automated"


def _arg(args: list[str], index: int, name: str) -> str:
    try:
        return args[index]
    except IndexError as exc:
        raise ValueError(f"missing {name}") from exc
