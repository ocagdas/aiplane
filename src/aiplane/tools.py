from __future__ import annotations

import shlex
import shutil
from collections.abc import Callable
import subprocess
from pathlib import Path

from .boundaries import CommandRunner, SubprocessCommandRunner
from .approvals import ApprovalHandler
from .audit import AuditLogger
from .env import EnvironmentManager
from .persistence import atomic_write_text
from .models import AuditEvent, Profile
from .policy import PolicyEngine
from .runtime_catalog import RuntimeCatalog
from .tool_catalog import CORE_TOOLCHAIN, TOOLCHAIN, TOOL_WORKFLOWS


class ToolExecutor:
    def __init__(
        self,
        profile: Profile,
        audit: AuditLogger,
        approvals: ApprovalHandler | None = None,
        command_runner: CommandRunner | None = None,
    ):
        self.profile = profile
        self.command_runner = command_runner or SubprocessCommandRunner()
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
            self._audit(action, "allowed", self._audit_details(tool_name, args))
            return output
        except Exception as exc:
            self._audit(action, "failed", {**self._audit_details(tool_name, args), "error_type": type(exc).__name__})
            raise

    def _tool_read_file(self, args: list[str]) -> str:
        path = self._workspace_path(_arg(args, 0, "path"))
        return path.read_text(encoding="utf-8")

    def _tool_write_file(self, args: list[str]) -> str:
        path = self._workspace_path(_arg(args, 0, "path"))
        content = _arg(args, 1, "content")
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(path, content)
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

    def _command(
        self,
        command: list[str],
        allow_failure: bool = False,
        use_environment: bool = True,
    ) -> str:
        plan = self.environment.plan(command) if use_environment else None
        actual_command = plan.command if plan else command
        cwd = plan.cwd if plan else self.profile.workspace
        result = self.command_runner.run(
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

    def _audit_details(self, tool_name: str, args: list[str]) -> dict[str, object]:
        details: dict[str, object] = {"argument_count": len(args)}
        if tool_name in {"read_file", "write_file"} and args:
            details["target"] = args[0]
        return details

    def _audit(self, action: str, decision: str, details: dict[str, object]) -> None:
        self.audit.record(AuditEvent("tool", self.profile.name, action, decision, details))


class ToolchainManager:
    def __init__(self, profile: Profile, command_runner: CommandRunner | None = None):
        self.profile = profile
        self.command_runner = command_runner or SubprocessCommandRunner()

    def list(self) -> list[dict[str, object]]:
        return [self._tool_row(name) for name in sorted(TOOLCHAIN)]

    def matrix(self) -> dict[str, object]:
        rows = []
        for row in self.list():
            name = str(row["name"])
            workflow = TOOL_WORKFLOWS.get(name, {})
            rows.append(
                {
                    "name": name,
                    "category": row.get("category"),
                    "task": workflow.get("task") or row.get("category"),
                    "needed_for": row.get("needed_for", []),
                    "requirement": row.get("requirement"),
                    "installed": row.get("installed"),
                    "install_mode": row.get("install_mode"),
                    "installable_by_aiplane": row.get("installable_by_aiplane"),
                    "plan_available": name in TOOL_WORKFLOWS,
                    "export_available": name in TOOL_WORKFLOWS,
                }
            )
        categories = []
        workflows = []
        for category in sorted({str(row.get("category") or "uncategorized") for row in rows}):
            tools = [row for row in rows if str(row.get("category") or "uncategorized") == category]
            categories.append({"name": category, "tools": tools})
            installed = [row for row in tools if row.get("installed")]
            missing = [row for row in tools if not row.get("installed")]
            missing_installable = [row for row in missing if row.get("installable_by_aiplane")]
            missing_manual = [row for row in missing if not row.get("installable_by_aiplane")]
            readiness = "complete" if not missing else "partial" if installed else "needs_setup"
            workflows.append(
                {
                    "name": category,
                    "readiness": readiness,
                    "tools": len(tools),
                    "installed": len(installed),
                    "missing": len(missing),
                    "mandatory": sum(1 for row in tools if row.get("requirement") == "mandatory"),
                    "optional": sum(1 for row in tools if row.get("requirement") == "optional"),
                    "missing_installable_by_aiplane": len(missing_installable),
                    "missing_manual_or_platform_specific": len(missing_manual),
                    "plans_available": sum(1 for row in tools if row.get("plan_available")),
                    "exports_available": sum(1 for row in tools if row.get("export_available")),
                    "primary_tasks": sorted({str(row.get("task")) for row in tools if row.get("task")}),
                    "missing_tools": [str(row["name"]) for row in missing],
                }
            )
        return {
            "name": "tools_matrix",
            "profile": self.profile.name,
            "summary": {
                "tools": len(rows),
                "mandatory": sum(1 for row in rows if row.get("requirement") == "mandatory"),
                "optional": sum(1 for row in rows if row.get("requirement") == "optional"),
                "installable_by_aiplane": sum(1 for row in rows if row.get("installable_by_aiplane")),
                "exports_available": sum(1 for row in rows if row.get("export_available")),
                "workflows": len(workflows),
                "workflows_complete": sum(1 for row in workflows if row.get("readiness") == "complete"),
                "workflows_partial": sum(1 for row in workflows if row.get("readiness") == "partial"),
                "workflows_needing_setup": sum(1 for row in workflows if row.get("readiness") == "needs_setup"),
            },
            "workflows": workflows,
            "categories": categories,
        }

    def tool_status(self, name: str) -> dict[str, object]:
        return self._tool_row(name)

    def environment_doctor(
        self,
        include_optional: bool = True,
        progress: Callable[[str], None] | None = None,
    ) -> dict[str, object]:
        tool_names = sorted(TOOLCHAIN) if include_optional else CORE_TOOLCHAIN
        rows = []
        for name in tool_names:
            if progress:
                progress(f"checking tool {name}")
            rows.append(self._tool_row(name))
        runtime_rows = _runtime_prerequisite_rows(
            self.profile,
            include_optional=include_optional,
            progress=progress,
        )
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
                results.append(
                    {
                        "command": command,
                        "executed": False,
                        "returncode": None,
                        "stdout": "",
                        "stderr": "manual step required",
                    }
                )
                continue
            actual_command: str | list[str] = command
            cwd = self.profile.workspace
            use_shell = True
            if command.startswith("python -m pip "):
                plan = EnvironmentManager(self.profile).plan(shlex.split(command))
                actual_command = plan.command
                cwd = plan.cwd
                use_shell = False
            completed = self.command_runner.run(
                actual_command,
                cwd=cwd,
                shell=use_shell,
                text=True,
                capture_output=True,
                check=False,
            )
            results.append(
                {
                    "command": command,
                    "executed_command": actual_command,
                    "cwd": str(cwd),
                    "executed": True,
                    "returncode": completed.returncode,
                    "stdout": completed.stdout[-4000:],
                    "stderr": completed.stderr[-4000:],
                }
            )
            if completed.returncode:
                break
        payload["results"] = results
        payload["installed_after"] = self._tool_row(name)["installed"]
        return payload

    def plan(self, name: str) -> dict[str, object]:
        if name not in TOOLCHAIN:
            raise ValueError(f"unknown tool: {name}")
        row = self._tool_row(name)
        workflow = dict(TOOL_WORKFLOWS.get(name, {}))
        return {
            "name": "tools_plan",
            "tool": name,
            "status": row,
            "task": workflow.get("task", row.get("category")),
            "summary": workflow.get("summary", row.get("description")),
            "prerequisites": workflow.get("prerequisites", []),
            "commands": [str(command) for command in workflow.get("commands", [])],
            "artifacts": workflow.get("artifacts", []),
            "next_steps": workflow.get("next_steps", []),
            "notes": [
                "Planning and export commands do not mutate hosts or cloud accounts.",
                "Run tool-specific init/plan/preview commands before any apply/build/up step.",
            ],
        }

    def export(self, name: str) -> dict[str, object]:
        if name not in TOOLCHAIN:
            raise ValueError(f"unknown tool: {name}")
        if name not in TOOL_WORKFLOWS:
            raise ValueError(f"tool export is not available for {name}")
        filename, content = _tool_export_content(name)
        workflow = TOOL_WORKFLOWS[name]
        return {
            "name": "tools_export",
            "tool": name,
            "filename": filename,
            "content": content,
            "notes": [
                str(workflow.get("summary", "Starter artifact.")),
                "Review and adapt this starter artifact before running mutating commands.",
            ],
        }

    def _tool_row(self, name: str) -> dict[str, object]:
        if name not in TOOLCHAIN:
            raise ValueError(f"unknown tool: {name}")
        spec = TOOLCHAIN[name]
        command = str(spec["command"])
        path = shutil.which(command)
        version = _command_version(command, self.command_runner) if path else None
        install_commands = self._install_commands(name)
        install_mode = _install_mode(install_commands)
        row = {
            "name": name,
            "category": spec.get("category"),
            "description": spec.get("description"),
            "needed_for": spec.get("needed_for", []),
            "requirement": "mandatory" if name in CORE_TOOLCHAIN else "optional",
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
            completed = _checked_command([command, "account", "show"], self.profile.workspace, self.command_runner)
            return {
                "ok": completed.get("returncode") == 0,
                "reason": (
                    "logged in" if completed.get("returncode") == 0 else "not logged in or account query failed"
                ),
            }
        if name == "docker":
            completed = _checked_command([command, "info"], self.profile.workspace, self.command_runner)
            return {
                "ok": completed.get("returncode") == 0,
                "reason": (
                    "daemon reachable"
                    if completed.get("returncode") == 0
                    else "docker CLI found but daemon is not reachable"
                ),
            }
        if name == "docker-compose":
            completed = _checked_command([command, "compose", "version"], self.profile.workspace, self.command_runner)
            return {
                "ok": completed.get("returncode") == 0,
                "reason": (
                    "compose plugin available"
                    if completed.get("returncode") == 0
                    else "docker compose plugin not available"
                ),
            }
        return {"ok": True, "reason": "command found"}


def _tool_export_content(name: str) -> tuple[str, str]:
    if name == "vagrant":
        return (
            "Vagrantfile",
            """# Generated starter Vagrantfile from aiplane.
# Use a Packer-built box here when you need a custom CUDA/runtime base image.
Vagrant.configure("2") do |config|
  config.vm.box = ENV.fetch("AIPLANE_VAGRANT_BOX", "ubuntu/jammy64")
  config.vm.hostname = "aiplane-dev"
  config.vm.synced_folder ".", "/workspace"
  config.vm.network "forwarded_port", guest: 11434, host: 11434, auto_correct: true
  config.vm.network "forwarded_port", guest: 8000, host: 8000, auto_correct: true

  config.vm.provider "virtualbox" do |vb|
    vb.cpus = Integer(ENV.fetch("AIPLANE_VM_CPUS", "4"))
    vb.memory = Integer(ENV.fetch("AIPLANE_VM_MEMORY_MB", "8192"))
  end

  config.vm.provision "shell", inline: <<-SHELL
    set -eu
    sudo apt-get update
    sudo apt-get install -y curl git python3 python3-venv openssh-client
  SHELL
end
""",
        )
    if name == "packer":
        return (
            "aiplane.pkr.hcl",
            """packer {
  required_plugins {
    virtualbox = {
      version = ">= 1.0.0"
      source  = "github.com/hashicorp/virtualbox"
    }
  }
}

variable "vm_name" {
  type    = string
  default = "aiplane-ubuntu-dev"
}

source "virtualbox-iso" "ubuntu" {
  vm_name       = var.vm_name
  guest_os_type = "Ubuntu_64"
  # Fill in ISO URL/checksum or replace this builder with azure-arm, amazon-ebs, googlecompute, etc.
  iso_url       = "file:///path/to/ubuntu.iso"
  iso_checksum  = "sha256:replace-me"
  ssh_username  = "ubuntu"
  ssh_password  = "ubuntu"
  shutdown_command = "echo 'ubuntu' | sudo -S shutdown -P now"
}

build {
  sources = ["source.virtualbox-iso.ubuntu"]

  provisioner "shell" {
    inline = [
      "sudo apt-get update",
      "sudo apt-get install -y curl git python3 python3-venv openssh-client",
    ]
  }
}
""",
        )
    if name in {"opentofu", "terraform"}:
        binary = "tofu" if name == "opentofu" else "terraform"
        return (
            "main.tf",
            f"""# Generated starter {name} module from aiplane.
# Fill in the provider and resources for your target cloud before running {binary} apply.

terraform {{
  required_version = ">= 1.6.0"
  required_providers {{
    # Example:
    # azurerm = {{
    #   source  = "hashicorp/azurerm"
    #   version = "~> 4.0"
    # }}
  }}
}}

variable "name" {{
  type    = string
  default = "aiplane-runtime"
}}

variable "region" {{
  type    = string
  default = "uksouth"
}}

# Add provider blocks and VM/container/Kubernetes resources here.
# Keep {binary} plan in review before any {binary} apply.
""",
        )
    if name == "pulumi":
        return (
            "__main__.py",
            '"""Generated starter Pulumi program from aiplane.\n\nInstall the provider package you need, configure credentials, then add resources.\nFor Azure, for example, use pulumi-azure-native and `pulumi config set azure-native:location uksouth`.\n"""\n\nimport pulumi\n\nname = pulumi.Config().get("name") or "aiplane-runtime"\nregion = pulumi.Config().get("region") or "uksouth"\n\npulumi.export("name", name)\npulumi.export("region", region)\n# Add cloud resources here using the provider package selected by your team.\n',
        )
    if name == "devcontainer-cli":
        return (
            ".devcontainer/devcontainer.json",
            """{
  "name": "aiplane-dev",
  "image": "python:3.13-slim",
  "workspaceFolder": "/workspace",
  "features": {},
  "postCreateCommand": "python -m pip install -e .",
  "customizations": {
    "vscode": {
      "extensions": []
    }
  }
}
""",
        )
    if name == "ansible":
        return (
            "playbook.yml",
            """---
- name: Prepare aiplane runtime host
  hosts: aiplane_hosts
  become: true
  tasks:
    - name: Install baseline packages
      ansible.builtin.apt:
        name:
          - curl
          - git
          - python3
          - python3-venv
          - openssh-client
        update_cache: true
      when: ansible_os_family == "Debian"

    - name: Show next manual runtime step
      ansible.builtin.debug:
        msg: "Run aiplane environment doctor and aiplane runtimes prerequisites on this host before starting runtimes."
""",
        )
    raise ValueError(f"tool export is not available for {name}")


def _runtime_prerequisite_rows(
    profile: Profile,
    include_optional: bool,
    progress: Callable[[str], None] | None = None,
) -> list[dict[str, object]]:
    catalog = RuntimeCatalog(profile)
    runtimes = ["ollama", "vllm", "tgi", "transformers", "localai"] if include_optional else ["ollama", "vllm"]
    runtimes = [
        *runtimes,
        *_default_model_runtimes(profile, include_gui=include_optional),
    ]
    rows: list[dict[str, object]] = []
    for runtime in dict.fromkeys(runtimes):
        if progress:
            progress(f"checking runtime prerequisite {runtime}")
        payload = catalog.prerequisites(runtime)
        ok = bool(payload.get("ok"))
        notes = list(payload.get("notes", [])) if isinstance(payload.get("notes"), list) else []
        availability = None
        if runtime == "azure_speech":
            availability = catalog.runtime_available(runtime)
            ok = bool(availability.get("available"))
            reason = availability.get("reason")
            if reason:
                notes.append(f"Azure Speech status: {reason}")
        rows.append(
            {
                "runtime": runtime,
                "known_runtime": payload.get("known_runtime"),
                "ok": ok,
                "helper_management": payload.get("helper_management"),
                "install_supported_by_helper": payload.get("install_supported_by_helper"),
                "purpose": RUNTIME_PURPOSES.get(runtime, []),
                "missing_required": payload.get("missing_required", []),
                "missing_optional": payload.get("missing_optional", []),
                "ubuntu_install_hint": payload.get("ubuntu_install_hint"),
                "setup_commands": _runtime_setup_commands(runtime, payload),
                "notes": notes,
                "availability": availability,
            }
        )
    return rows


def _default_model_runtimes(profile: Profile, include_gui: bool) -> list[str]:
    catalog = RuntimeCatalog(profile)
    defaults = profile.models.get("defaults", {}) if isinstance(profile.models, dict) else {}
    models = profile.models.get("models", {}) if isinstance(profile.models, dict) else {}
    runtimes: list[str] = []
    if isinstance(defaults, dict) and isinstance(models, dict):
        for name in defaults.values():
            model = models.get(str(name))
            if isinstance(model, dict):
                runtimes.extend(catalog.compatible_runtimes_for_entry(model, include_gui=include_gui))
    return runtimes


RUNTIME_PURPOSES: dict[str, list[str]] = {
    "ollama": [
        "simple local model serving",
        "Continue/local IDE endpoint",
        "CPU or single-user workstation workflows",
    ],
    "vllm": [
        "GPU OpenAI-compatible serving",
        "Hugging Face model repos",
        "throughput and latency benchmarking",
    ],
    "tgi": [
        "containerized Hugging Face serving",
        "GPU server inference",
        "OpenAI-compatible endpoint workflows",
    ],
    "transformers": [
        "Python library experiments",
        "training/fine-tuning scripts",
        "offline evaluation jobs",
    ],
    "localai": [
        "OpenAI-compatible local service",
        "GGUF/llama.cpp-style models",
        "mixed backend experiments",
    ],
    "azure_speech": [
        "managed text-to-speech",
        "cloud audio generation",
        "voice output workflows",
    ],
    "diffusers": [
        "AI image/video generation",
        "GPU or remote media jobs",
        "pipeline experiments",
    ],
    "comfyui": [
        "AI image/video workflows",
        "visual generation pipelines",
        "local or remote GPU runtime",
    ],
}


def _runtime_setup_commands(runtime: str, payload: dict[str, object]) -> list[str]:
    commands = [f"aiplane runtimes prerequisites {runtime}"]
    if payload.get("install_supported_by_helper"):
        commands.append(f"aiplane runtimes install {runtime} --dry-run")
    if runtime in {"ollama", "vllm", "tgi", "localai"}:
        commands.append(f"aiplane runtimes start {runtime} --dry-run")
    if runtime == "azure_speech":
        commands.extend(
            [
                "aiplane models list --role text_to_speech",
                "aiplane providers list --status all --runtime azure_speech",
            ]
        )
    if runtime == "diffusers":
        commands.extend(
            [
                "aiplane models list --role image_generation --runtime diffusers",
                "aiplane models list --role video_generation --runtime diffusers",
            ]
        )
    if runtime == "comfyui":
        commands.extend(
            [
                "aiplane models list --role image_generation --runtime comfyui",
                "aiplane models list --role video_generation --runtime comfyui",
            ]
        )
    return commands


def _checked_command(command: list[str], cwd: Path, command_runner: CommandRunner) -> dict[str, object]:
    try:
        completed = command_runner.run(command, cwd=cwd, text=True, capture_output=True, check=False, timeout=15)
    except subprocess.TimeoutExpired:
        return {"returncode": None, "stdout": "", "stderr": "timeout"}
    except OSError as exc:
        return {"returncode": None, "stdout": "", "stderr": str(exc)}
    return {
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def _platform_info() -> dict[str, object]:
    return {
        "name": _platform_id(),
        "os_release": _os_release_id(),
        "package_manager": _package_manager(),
    }


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


def _command_version(command: str, command_runner: CommandRunner) -> str | None:
    candidates = [[command, "--version"], [command, "version"]]
    for candidate in candidates:
        try:
            completed = command_runner.run(candidate, text=True, capture_output=True, check=False, timeout=8)
        except Exception:
            continue
        output = (completed.stdout or completed.stderr).strip().splitlines()
        if completed.returncode == 0 and output:
            return output[0][:200]
    return None


def _non_executable_install_note(command: str) -> bool:
    return (
        command.startswith("follow ")
        or command.startswith("install ")
        or command.startswith("OpenSSH is included")
        or command.startswith("Docker Desktop includes")
        or "generally needs" in command
    )


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
