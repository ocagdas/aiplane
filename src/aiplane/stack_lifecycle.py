from __future__ import annotations

import time
from typing import Any

from .boundaries import CommandRunner
from .config import project_root, provider_helper_path
from .env import EnvironmentManager
from .machines import MachineManager
from .models import Profile
from .orchestrators import OrchestratorCatalog
from .runtime_catalog import RuntimeCatalog


class StackLifecycle:
    """Plan and execute guarded stack lifecycle operations."""

    def __init__(self, manager: Any):
        self.manager = manager
        self.profile: Profile = manager.profile
        self.command_runner: CommandRunner = manager.command_runner

    def _stack(self, name: str) -> dict[str, Any]:
        return self.manager._stack(name)

    def endpoint_plan(self, name: str) -> dict[str, Any]:
        return self.manager.endpoint_plan(name)

    def plan(self, name: str) -> dict[str, Any]:
        return self.manager.plan(name)

    def _lifecycle(self, name: str, action: str, dry_run: bool = False) -> dict[str, Any]:
        stack = self._stack(name)
        runtime = str(stack.get("runtime") or "")
        model = str(stack.get("model") or "")
        orchestrator = str(stack.get("orchestrator") or "")
        commands = self._lifecycle_commands(name, action, runtime, model, orchestrator)
        executable, reason = self._lifecycle_executable(stack)
        if dry_run or not executable:
            return {
                "name": name,
                "action": action,
                "dry_run": dry_run,
                "status": "planned" if dry_run else "planned_not_executed",
                "reason": None if executable else reason,
                "execution_mode": "same_host" if executable else "planned_remote",
                "endpoint_security": self.endpoint_plan(name),
                "commands": commands,
            }
        results = []
        failed_step = None
        runtime_status_before = RuntimeCatalog(self.profile).runtime_available(runtime)
        started_at = time.time()
        for item in commands:
            completed = self.command_runner.run(
                item["command"],
                cwd=item.get("cwd") or self.profile.workspace,
                text=True,
                capture_output=True,
                check=False,
            )
            row = {
                "name": item["name"],
                "command": item["command"],
                "returncode": completed.returncode,
                "stdout": completed.stdout[-4000:],
                "stderr": completed.stderr[-4000:],
            }
            results.append(row)
            if completed.returncode != 0:
                failed_step = row
                break
        finished_at = time.time()
        runtime_status_after = RuntimeCatalog(self.profile).runtime_available(runtime)
        outcome = "completed" if failed_step is None and len(results) == len(commands) else "failed"
        return {
            "name": name,
            "action": action,
            "dry_run": False,
            "status": "executed",
            "outcome": outcome,
            "steps_total": len(commands),
            "steps_executed": len(results),
            "failed_step": failed_step,
            "execution_mode": "same_host",
            "started_at": round(started_at, 3),
            "finished_at": round(finished_at, 3),
            "duration_seconds": round(max(0.0, finished_at - started_at), 3),
            "runtime_status_before": runtime_status_before,
            "runtime_status_after": runtime_status_after,
            "results": results,
            "notes": [
                "Same-host lifecycle execution ran local helper commands directly; runtime_status_after is a best-effort post-action readiness snapshot."
            ],
        }

    def _lifecycle_commands(
        self, stack_name: str, action: str, runtime: str, model: str, orchestrator: str
    ) -> list[dict[str, Any]]:
        if action == "prepare":
            commands = [
                self._runtime_helper_command("install runtime", runtime, "install", model),
                self._runtime_helper_command("pull model", runtime, "pull", model),
            ]
            if orchestrator:
                packages = OrchestratorCatalog(self.profile).show(orchestrator).get("packages", [])
                if packages:
                    plan = EnvironmentManager(self.profile).plan(
                        [
                            "python",
                            "-m",
                            "pip",
                            "install",
                            *[str(package) for package in packages],
                        ]
                    )
                    commands.append(
                        {
                            "name": "install orchestrator packages",
                            "command": plan.command,
                            "cwd": str(plan.cwd),
                            "environment_mode": plan.mode,
                        }
                    )
            return commands
        if action in {"start", "stop", "restart"}:
            return [self._runtime_helper_command(f"{action} runtime", runtime, action, model)]
        raise ValueError(f"unknown stack lifecycle action: {action}")

    def _runtime_helper_command(self, name: str, runtime: str, action: str, model: str) -> dict[str, Any]:
        helper = provider_helper_path()
        return {
            "name": name,
            "command": [
                str(helper),
                "--provider",
                runtime,
                "--action",
                action,
                "--profile",
                self.profile.name,
                "--model",
                model,
            ],
            "cwd": str(project_root()),
        }

    def _lifecycle_executable(self, stack: dict[str, Any]) -> tuple[bool, str | None]:
        access = str(stack.get("access") or "")
        machine_name = str(stack.get("machine") or "")
        try:
            machine = MachineManager(self.profile).show(machine_name)["machine"]
        except Exception as exc:  # noqa: BLE001 - report as lifecycle planning reason.
            return False, f"machine lookup failed: {exc}"
        placement = str(machine.get("placement") or "") if isinstance(machine, dict) else ""
        if access in {"same_host", "local"} or placement == "same_host":
            return True, None
        return (
            False,
            "automatic stack lifecycle execution is currently limited to same-host/local stacks; use --dry-run output for remote/SSH/Azure/AKS targets",
        )

    def deploy(self, name: str, yes: bool = False) -> dict[str, Any]:
        if not yes:
            raise PermissionError("stack deploy is mutating; run stacks plan and stacks doctor first")
        plan = self.plan(name)
        access = str(plan.get("access") or "")
        machine = plan.get("machine_config", {})
        placement = str(machine.get("placement") or "") if isinstance(machine, dict) else ""
        if access not in {"same_host", "local"} and placement != "same_host":
            return {
                "name": name,
                "status": "planned_not_executed",
                "reason": "automatic stack execution is currently limited to same-host/local stacks; use the rendered plan for SSH/Azure targets",
                "next_manual_steps": plan["steps"],
            }
        results = []
        for step in plan["steps"]:
            command = step.get("command") if isinstance(step, dict) else None
            if not command or not step.get("mutates"):
                continue
            completed = self.command_runner.run(command, text=True, capture_output=True, check=False)
            results.append(
                {
                    "name": step.get("name"),
                    "command": command,
                    "returncode": completed.returncode,
                    "stdout": completed.stdout[-2000:],
                    "stderr": completed.stderr[-2000:],
                }
            )
            if completed.returncode != 0:
                break
        return {"name": name, "status": "executed_same_host_steps", "results": results}
