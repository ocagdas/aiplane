from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Callable

from .config import load_profile
from .deploy import DeployManager
from .remote import RemoteManager


def add_deploy_remote_parsers(
    subparsers: Any,
    *,
    command_factory: Callable[..., argparse.ArgumentParser],
    profile_arg: Callable[[argparse.ArgumentParser], None],
    formatter_class: type[argparse.HelpFormatter],
) -> None:
    deploy_cmd = command_factory(
        subparsers,
        "deploy",
        "Plan/check/apply remote deployment targets",
        "Work with configured cloud/shared deployment targets. Apply is guarded and intentionally narrow.",
        "Examples:\n  aiplane deploy list\n  aiplane deploy workflow-plan --target azure_gpu_vm\n  aiplane deploy plan --target aks_gpu_pool\n  aiplane deploy doctor --target aks_gpu_pool\n  aiplane deploy apply --target aks_gpu_pool --yes",
    )
    deploy_sub = deploy_cmd.add_subparsers(dest="deploy_command", required=True, metavar="command")
    deploy_list = deploy_sub.add_parser(
        "list",
        help="List deployment targets",
        description="List targets from profiles/<profile>/targets.yaml.",
        formatter_class=formatter_class,
    )
    profile_arg(deploy_list)
    deploy_show = deploy_sub.add_parser(
        "show",
        help="Show one deployment target",
        description="Show one target config; uses profile default when --target is omitted.",
        formatter_class=formatter_class,
    )
    profile_arg(deploy_show)
    deploy_show.add_argument("--target", help="Target name, such as aks_gpu_pool")
    deploy_workflow = deploy_sub.add_parser(
        "workflow-plan",
        help="Classify a deployment workflow",
        description="Show whether a target is local install, local VM, remote workstation/VM, cloud VM, or Kubernetes/cloud provisioning, and which external tools own each phase.",
        formatter_class=formatter_class,
    )
    profile_arg(deploy_workflow)
    deploy_workflow.add_argument("--target", help="Target name; defaults to profile target default")
    deploy_plan = deploy_sub.add_parser(
        "plan",
        help="Render deployment plan",
        description="Show required tools and commands for a target without applying changes.",
        formatter_class=formatter_class,
    )
    profile_arg(deploy_plan)
    deploy_plan.add_argument("--target", help="Target name; defaults to profile target default")
    deploy_doctor = deploy_sub.add_parser(
        "doctor",
        help="Check target prerequisites",
        description="Check local tools and target prerequisites where implemented.",
        formatter_class=formatter_class,
    )
    profile_arg(deploy_doctor)
    deploy_doctor.add_argument("--target", help="Target name; defaults to profile target default")
    deploy_apply = deploy_sub.add_parser(
        "apply",
        help="Apply guarded bootstrap steps",
        description="Run narrow, planned bootstrap steps for the selected target. Use deploy plan first to preview commands.",
        formatter_class=formatter_class,
    )
    profile_arg(deploy_apply)
    deploy_apply.add_argument("--target", help="Target name; defaults to profile target default")
    deploy_apply.add_argument(
        "--yes",
        action="store_true",
        help="Confirm that mutating target bootstrap commands should run",
    )

    remote_cmd = command_factory(
        subparsers,
        "remote",
        "Plan remote access commands",
        "Render remote access commands such as SSH local port forwards for shared/cloud endpoints.",
        "Example:\n  aiplane remote tunnel plan --target gpu_workstation_ssh",
    )
    remote_sub = remote_cmd.add_subparsers(dest="remote_command", required=True, metavar="command")
    remote_tunnel = remote_sub.add_parser(
        "tunnel",
        help="SSH tunnel planning",
        description="Work with SSH tunnel targets.",
        formatter_class=formatter_class,
    )
    tunnel_sub = remote_tunnel.add_subparsers(dest="tunnel_command", required=True, metavar="command")
    tunnel_plan = tunnel_sub.add_parser(
        "plan",
        help="Render ssh -L command",
        description="Render an SSH local-forward command and endpoint URL. It does not start the tunnel.",
        formatter_class=formatter_class,
    )
    profile_arg(tunnel_plan)
    tunnel_plan.add_argument("--target", required=True, help="ssh_tunnel target name from targets.yaml")
    tunnel_status = tunnel_sub.add_parser(
        "status",
        help="Show tunnel process status",
        description="Show whether a helper-started SSH tunnel is running and which endpoint to use.",
        formatter_class=formatter_class,
    )
    profile_arg(tunnel_status)
    tunnel_status.add_argument("--target", required=True, help="ssh_tunnel target name from targets.yaml")
    tunnel_start = tunnel_sub.add_parser(
        "start",
        help="Start an SSH tunnel",
        description="Start the configured ssh -L tunnel in the background and write PID/log files under .aiplane/remote.",
        formatter_class=formatter_class,
    )
    profile_arg(tunnel_start)
    tunnel_start.add_argument("--target", required=True, help="ssh_tunnel target name from targets.yaml")
    tunnel_stop = tunnel_sub.add_parser(
        "stop",
        help="Stop a helper-started SSH tunnel",
        description="Stop a tunnel process previously started by this CLI.",
        formatter_class=formatter_class,
    )
    profile_arg(tunnel_stop)
    tunnel_stop.add_argument("--target", required=True, help="ssh_tunnel target name from targets.yaml")


def handle_deploy_remote_command(
    args: argparse.Namespace,
    *,
    workspace: Path,
    profiles_dir: Path | None,
    effective_profile: str,
    json_dumps: Callable[..., str],
) -> int | None:
    if args.command == "deploy":
        profile = load_profile(effective_profile, workspace, profiles_dir=profiles_dir)
        manager = DeployManager(profile)
        if args.deploy_command == "list":
            payload = manager.list()
        elif args.deploy_command == "show":
            payload = manager.show(args.target)
        elif args.deploy_command == "workflow-plan":
            payload = manager.workflow_plan(args.target)
        elif args.deploy_command == "plan":
            payload = manager.plan(args.target)
        elif args.deploy_command == "doctor":
            payload = manager.doctor(args.target)
        elif args.deploy_command == "apply":
            payload = manager.apply(args.target, yes=args.yes)
        else:
            raise ValueError(f"unknown deploy command: {args.deploy_command}")
        print(json_dumps(payload, indent=2, sort_keys=True))
        return 0
    if args.command == "remote":
        profile = load_profile(effective_profile, workspace, profiles_dir=profiles_dir)
        manager = RemoteManager(profile)
        if args.tunnel_command == "plan":
            payload = manager.tunnel_plan(args.target)
        elif args.tunnel_command == "status":
            payload = manager.tunnel_status(args.target)
        elif args.tunnel_command == "start":
            payload = manager.tunnel_start(args.target, yes=True)
        elif args.tunnel_command == "stop":
            payload = manager.tunnel_stop(args.target, yes=True)
        else:
            raise ValueError(f"unknown remote tunnel command: {args.tunnel_command}")
        print(json_dumps(payload, indent=2))
        return 0
    return None
