from __future__ import annotations

import argparse
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .agents import AgentManager
from .approvals import ApprovalHandler
from .audit import AuditLogger
from .code_tasks import CodeTaskRunner
from .persistence import atomic_write_text
from .config import load_profile
from .integrations import IntegrationManager
from .models import AuditEvent
from .router import Router
from .tools import ToolExecutor


def add_execution_parsers(
    subparsers: Any,
    *,
    command_factory: Callable[..., argparse.ArgumentParser],
    profile_arg: Callable[[argparse.ArgumentParser], None],
    formatter_class: type[argparse.HelpFormatter],
    launch_tools: tuple[str, ...],
    bridge_actions: dict[str, dict[str, object]],
) -> None:
    run = command_factory(
        subparsers,
        "run",
        "Route a simple task through local/cloud policy",
        "Route a task through the profile policy and backend selection logic.",
        "Examples:\n  aiplane run --dry-run 'summarize repo status'\n  aiplane run --model MODEL_ALIAS 'explain this setup'\n  aiplane run --escalate 'needs cloud reasoning'",
    )
    profile_arg(run)
    run.add_argument(
        "--model",
        help="Model alias to use. If omitted, aiplane selects an enabled local model, or an enabled non-local model with --escalate",
    )
    run.add_argument(
        "--escalate",
        action="store_true",
        help="Prefer an enabled non-local/cloud model when policy allows it",
    )
    run.add_argument(
        "--dry-run",
        action="store_true",
        help="Show selected model and prompt without calling the provider",
    )
    run.add_argument(
        "--ignore-hardware-fit",
        action="store_true",
        help="Allow a local model run even when active hardware minimums are not satisfied",
    )
    run.add_argument("task", help="Prompt/task text to send to the selected model")

    tool = command_factory(
        subparsers,
        "tool",
        "Run a configured local tool with approval checks",
        "Execute a configured tool through aiplane policy, workspace, approval, and audit checks. Risky tools prompt on an interactive terminal and fail closed otherwise unless --yes is explicit.",
        "Examples:\n  aiplane tool read_file README.md\n  aiplane tool --yes write_file note.txt hello",
    )
    profile_arg(tool)
    tool.add_argument(
        "--yes",
        action="store_true",
        help="Approve this invocation non-interactively when profile policy requires approval; place before TOOL",
    )
    tool.add_argument("tool_name", help="Configured tool name, such as read_file or write_file")
    tool.add_argument(
        "tool_args",
        nargs=argparse.REMAINDER,
        help="Arguments passed to the configured tool; captures options such as -m or -s",
    )

    code_cmd = command_factory(
        subparsers,
        "code",
        "Run simple code analysis/completion/write prompts",
        "Use a configured model for small code tasks. Use --dry-run to inspect prompts before calling a runtime.",
        "Examples:\n  aiplane code analyze --model MODEL_ALIAS src/aiplane/cli.py --dry-run\n  aiplane code complete --model MODEL_ALIAS --line 20 src/app.py\n  aiplane code write --model MODEL_ALIAS --task 'add email validation' --dry-run",
    )
    code_sub = code_cmd.add_subparsers(dest="code_command", required=True, metavar="command")
    code_analyze = code_sub.add_parser(
        "analyze",
        help="Analyze a code file",
        description="Ask a model to explain a file, identify risk, and suggest an improvement.",
        formatter_class=formatter_class,
    )
    profile_arg(code_analyze)
    code_analyze.add_argument("--model", required=True, help="Model alias to use")
    code_analyze.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the prompt without calling the provider",
    )
    code_analyze.add_argument(
        "--timeout-seconds",
        type=int,
        help="Override provider request timeout for this code task",
    )
    code_analyze.add_argument("target", help="File path inside the workspace")
    code_complete = code_sub.add_parser(
        "complete",
        help="Complete code at a line",
        description="Build a completion prompt using file context around the selected line.",
        formatter_class=formatter_class,
    )
    profile_arg(code_complete)
    code_complete.add_argument("--model", required=True, help="Model alias to use")
    code_complete.add_argument("--line", type=int, required=True, help="1-based cursor line number")
    code_complete.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the prompt without calling the provider",
    )
    code_complete.add_argument(
        "--timeout-seconds",
        type=int,
        help="Override provider request timeout for this code task",
    )
    code_complete.add_argument("target", help="File path inside the workspace")
    code_write = code_sub.add_parser(
        "write",
        help="Generate a small code snippet",
        description="Ask a model to write code for a short task description.",
        formatter_class=formatter_class,
    )
    profile_arg(code_write)
    code_write.add_argument("--model", required=True, help="Model alias to use")
    code_write.add_argument("--task", required=True, help="Code-writing task description")
    code_write.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the prompt without calling the provider",
    )
    code_write.add_argument(
        "--timeout-seconds",
        type=int,
        help="Override provider request timeout for this code task",
    )

    agents_cmd = command_factory(
        subparsers,
        "agents",
        "Plan and export starter agent applications",
        "Create non-mutating plans and scaffold files for small agent applications that use configured aiplane model endpoints.",
        "Examples:\n  aiplane agents templates\n  aiplane agents plan repo-helper --framework langgraph --model MODEL_ALIAS\n  aiplane agents export repo-helper --framework langgraph --model MODEL_ALIAS --file agent.py",
    )
    agents_sub = agents_cmd.add_subparsers(dest="agents_command", required=True, metavar="command")
    agents_templates = agents_sub.add_parser(
        "templates",
        help="List starter agent frameworks",
        description="List agent application scaffold templates supported by aiplane.",
        formatter_class=formatter_class,
    )
    profile_arg(agents_templates)
    agents_plan = agents_sub.add_parser(
        "plan",
        help="Plan an agent application scaffold",
        description="Select a model endpoint and show the files/packages for an agent application scaffold. This does not write files or run the agent.",
        formatter_class=formatter_class,
    )
    profile_arg(agents_plan)
    agents_plan.add_argument("name", help="Agent application name, such as repo-helper")
    agents_plan.add_argument(
        "--framework",
        choices=["langgraph", "simple-openai"],
        default="langgraph",
        help="Agent scaffold framework",
    )
    agents_plan.add_argument(
        "--model",
        help="Model alias to use; if omitted, aiplane selects the best enabled chat model",
    )
    agents_plan.add_argument("--runtime", help="Runtime constraint, such as ollama or vllm")
    agents_plan.add_argument("--provider", help="Provider/source constraint, such as openai or ollama")
    agents_plan.add_argument("--endpoint", help="Endpoint/base URL override")
    agents_plan.add_argument("--api-key-env", help="API-key environment variable override")
    agents_plan.add_argument("--instruction", help="System instruction embedded in the scaffold")
    agents_plan.add_argument(
        "--output-dir",
        help="Agent artifact root. Defaults to AIPLANE_AGENT_ARTIFACTS_DIR, local config agent_artifacts_dir, or .aiplane/agents",
    )
    agents_export = agents_sub.add_parser(
        "export",
        help="Print one starter agent file",
        description="Print one scaffold file for an agent application. Output is not written automatically.",
        formatter_class=formatter_class,
    )
    profile_arg(agents_export)
    agents_export.add_argument("name", help="Agent application name, such as repo-helper")
    agents_export.add_argument(
        "--framework",
        choices=["langgraph", "simple-openai"],
        default="langgraph",
        help="Agent scaffold framework",
    )
    agents_export.add_argument(
        "--model",
        help="Model alias to use; if omitted, aiplane selects the best enabled chat model",
    )
    agents_export.add_argument("--runtime", help="Runtime constraint, such as ollama or vllm")
    agents_export.add_argument("--provider", help="Provider/source constraint, such as openai or ollama")
    agents_export.add_argument("--endpoint", help="Endpoint/base URL override")
    agents_export.add_argument("--api-key-env", help="API-key environment variable override")
    agents_export.add_argument("--instruction", help="System instruction embedded in the scaffold")
    agents_export.add_argument(
        "--output-dir",
        help="Agent artifact root. Defaults to AIPLANE_AGENT_ARTIFACTS_DIR, local config agent_artifacts_dir, or .aiplane/agents",
    )
    agents_export.add_argument(
        "--file",
        choices=["agent.py", "requirements.txt", ".env.example", "README.md"],
        default="agent.py",
        help="Scaffold file to print",
    )

    chat_cmd = command_factory(
        subparsers,
        "chat",
        "Run endpoint-backed chat for a model",
        "Resolve a chat-capable model alias and send prompts through its configured runtime/provider endpoint.",
        "Examples:\n  aiplane chat --model MODEL_ALIAS --prompt 'Say hello'\n  echo 'Say hello' | aiplane chat --model MODEL_ALIAS --stdin\n  aiplane chat --model MODEL_ALIAS --native-ollama",
    )
    profile_arg(chat_cmd)
    chat_cmd.add_argument(
        "--model",
        help="Model alias to launch. If omitted, uses the profile chat_model default",
    )
    chat_cmd.add_argument(
        "--prompt",
        help="Prompt to send through the configured chat endpoint",
    )
    chat_cmd.add_argument(
        "--stdin",
        action="store_true",
        help="Read the chat prompt from standard input",
    )
    chat_cmd.add_argument(
        "--timeout-seconds",
        type=int,
        help="Override provider/runtime request timeout for endpoint chat",
    )
    chat_cmd.add_argument(
        "--native-ollama",
        action="store_true",
        help="Use Ollama's native `ollama run` CLI instead of endpoint-backed chat; only works for Ollama-runnable aliases",
    )
    chat_cmd.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview the endpoint chat plan, or the native Ollama command when --native-ollama is used",
    )

    bridge_cmd = command_factory(
        subparsers,
        "bridge",
        "Run allowlisted external runtime commands",
        "Run selected allowlisted runtime CLI commands without exposing arbitrary shell passthrough.",
        "Examples:\n  aiplane bridge list\n  aiplane bridge exec ollama-launch --dry-run\n  aiplane bridge exec ollama-run --model llama3.1:8b --prompt 'Say hello'",
    )
    bridge_sub = bridge_cmd.add_subparsers(dest="bridge_command", required=True, metavar="command")
    bridge_sub.add_parser(
        "list",
        help="List allowlisted bridge actions",
        description="List shorthand actions that aiplane can delegate to external runtime CLIs.",
        formatter_class=formatter_class,
        allow_abbrev=False,
    )
    bridge_exec = bridge_sub.add_parser(
        "exec",
        help="Execute one allowlisted bridge action",
        description="Run one allowlisted external command by shorthand action.",
        formatter_class=formatter_class,
        allow_abbrev=False,
    )
    bridge_exec.add_argument("action", choices=sorted(bridge_actions), help="Bridge action shorthand")
    bridge_exec.add_argument("--model", help="Model id/alias for actions that require a model")
    bridge_exec.add_argument("--prompt", help="Prompt text for actions that support prompts")
    bridge_exec.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the resolved external command without executing it",
    )

    launch_cmd = command_factory(
        subparsers,
        "launch",
        "Launch a configured assistant tool",
        "Launch a configured assistant tool with profile-driven model selection.",
        "Examples:\n  aiplane launch --tool aider --model fixture-chat-small\n  aiplane launch --tool ollama --app vscode\n  aiplane launch --tool continue --model fixture-chat-small --dry-run",
    )
    launch_cmd.add_argument(
        "--tool",
        choices=sorted(launch_tools),
        required=True,
        help="Target assistant/tool wrapper to launch",
    )
    profile_arg(launch_cmd)
    launch_cmd.add_argument(
        "--model",
        help="Model alias to apply when building launch arguments and endpoint metadata. If omitted, defaults to chat_model.",
    )
    launch_cmd.add_argument(
        "--app",
        help="Target application name for `aiplane launch --tool ollama`",
    )
    launch_cmd.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the launch plan without starting any process",
    )

    session_cmd = command_factory(
        subparsers,
        "session",
        "Track a minimal model session",
        "Create thin, local session metadata for model-facing tooling without implementing a custom chat UI.",
        "Examples:\n  aiplane session start --tool aider --model fixture-chat-small\n  aiplane session start --tool ollama --app vscode --transcript /tmp/session.log\n  aiplane session start --tool continue --model fixture-chat-small --dry-run",
    )
    session_sub = session_cmd.add_subparsers(dest="session_command", required=True, metavar="command")
    session_start = session_sub.add_parser(
        "start",
        help="Start a minimal session metadata record",
        description="Start a minimal session metadata record (model, command, transcript path, audit metadata).",
        formatter_class=formatter_class,
        allow_abbrev=False,
    )
    session_start.add_argument(
        "--tool",
        choices=sorted(launch_tools),
        required=True,
        help="Tool name to launch from aiplane session metadata.",
    )
    profile_arg(session_start)
    session_start.add_argument(
        "--model",
        help="Model alias to apply. If omitted, defaults to chat_model.",
    )
    session_start.add_argument(
        "--app",
        help="Target application name for `aiplane session start --tool ollama`.",
    )
    session_start.add_argument(
        "--transcript",
        help="Optional transcript file path. Defaults to .aiplane/sessions/<session-id>.log under workspace.",
    )
    session_start.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview the session metadata without writing it or emitting an audit event.",
    )


def _bridge_action_command(
    actions: dict[str, dict[str, object]], action: str, model: str | None = None, prompt: str | None = None
) -> list[str]:
    if action not in actions:
        raise ValueError(f"unsupported bridge action: {action}")
    spec = actions[action]
    requires_model = bool(spec.get("requires_model"))
    supports_prompt = bool(spec.get("supports_prompt"))
    if requires_model and not (model or "").strip():
        raise ValueError(f"bridge action {action} requires --model")
    if not requires_model and model:
        raise ValueError(f"bridge action {action} does not accept --model")
    if not supports_prompt and prompt:
        raise ValueError(f"bridge action {action} does not accept --prompt")
    command = [str(part) for part in spec.get("base_command", [])]
    if requires_model:
        command.append(str(model).strip())
    if supports_prompt and prompt is not None:
        command.append(prompt)
    return command


def handle_execution_command(
    args: argparse.Namespace,
    *,
    workspace: Path,
    profiles_dir: Path | None,
    effective_profile: str,
    json_dumps: Callable[..., str],
    bridge_actions: dict[str, dict[str, object]],
    launch_plan: Callable[..., dict[str, object]],
    new_session_id: Callable[[], str],
    default_transcript: Callable[..., Path],
    session_metadata_path: Callable[..., Path],
    command_runner: Any,
) -> int | None:
    if args.command == "run":
        profile = load_profile(effective_profile, workspace, profiles_dir=profiles_dir)
        result = Router(profile, AuditLogger(profile)).route(
            args.task,
            prefer_escalation=args.escalate,
            model_name=args.model,
            dry_run=args.dry_run,
            ignore_hardware_fit=args.ignore_hardware_fit,
        )
        print(result.text)
        return 0

    if args.command == "tool":
        profile = load_profile(effective_profile, workspace, profiles_dir=profiles_dir)
        output = ToolExecutor(
            profile,
            AuditLogger(profile),
            ApprovalHandler(assume_yes=args.yes),
        ).run(args.tool_name, args.tool_args)
        print(output)
        return 0

    if args.command == "code":
        profile = load_profile(effective_profile, workspace, profiles_dir=profiles_dir)
        runner = CodeTaskRunner(profile, AuditLogger(profile))
        if args.code_command == "analyze":
            result = runner.analyze(
                args.model,
                Path(args.target),
                dry_run=args.dry_run,
                timeout_seconds=args.timeout_seconds,
            )
        elif args.code_command == "complete":
            result = runner.complete(
                args.model,
                Path(args.target),
                args.line,
                dry_run=args.dry_run,
                timeout_seconds=args.timeout_seconds,
            )
        else:
            result = runner.write(
                args.model,
                args.task,
                dry_run=args.dry_run,
                timeout_seconds=args.timeout_seconds,
            )
        print(result.output)
        return 0

    if args.command == "agents":
        profile = load_profile(effective_profile, workspace, profiles_dir=profiles_dir)
        manager = AgentManager(profile)
        if args.agents_command == "templates":
            print(json_dumps(manager.templates(), indent=2))
            return 0
        if args.agents_command == "plan":
            print(
                json_dumps(
                    manager.plan(
                        args.name,
                        framework=args.framework,
                        model=args.model,
                        runtime=args.runtime,
                        provider=args.provider,
                        endpoint=args.endpoint,
                        api_key_env=args.api_key_env,
                        instruction=args.instruction,
                        output_dir=args.output_dir,
                    ),
                    indent=2,
                )
            )
            return 0
        exported = manager.export(
            args.name,
            framework=args.framework,
            model=args.model,
            runtime=args.runtime,
            provider=args.provider,
            endpoint=args.endpoint,
            api_key_env=args.api_key_env,
            instruction=args.instruction,
            file=args.file,
            output_dir=args.output_dir,
        )
        print(exported["content"])
        if exported.get("notes"):
            print("\n# Notes")
            for note in exported["notes"]:
                print(f"# - {note}")
        return 0

    if args.command == "agents":
        profile = load_profile(effective_profile, workspace, profiles_dir=profiles_dir)
        manager = AgentManager(profile)
        if args.agents_command == "templates":
            print(json_dumps(manager.templates(), indent=2))
            return 0
        if args.agents_command == "plan":
            print(
                json_dumps(
                    manager.plan(
                        args.name,
                        framework=args.framework,
                        model=args.model,
                        runtime=args.runtime,
                        provider=args.provider,
                        endpoint=args.endpoint,
                        api_key_env=args.api_key_env,
                        instruction=args.instruction,
                        output_dir=args.output_dir,
                    ),
                    indent=2,
                )
            )
            return 0
        exported = manager.export(
            args.name,
            framework=args.framework,
            model=args.model,
            runtime=args.runtime,
            provider=args.provider,
            endpoint=args.endpoint,
            api_key_env=args.api_key_env,
            instruction=args.instruction,
            file=args.file,
            output_dir=args.output_dir,
        )
        print(exported["content"])
        if exported.get("notes"):
            print("\n# Notes")
            for note in exported["notes"]:
                print(f"# - {note}")
        return 0

    if args.command == "chat":
        profile = load_profile(effective_profile, workspace, profiles_dir=profiles_dir)
        manager = IntegrationManager(profile)
        prompt = args.prompt
        if args.stdin:
            prompt = sys.stdin.read()
        if args.native_ollama or args.dry_run or prompt is not None:
            output = manager.run_chat(
                args.model,
                prompt=prompt,
                dry_run=args.dry_run,
                timeout_seconds=args.timeout_seconds,
                native_ollama=args.native_ollama,
            )
            if output:
                print(output)
            return 0
        if not sys.stdin.isatty():
            prompt = sys.stdin.read()
            if not prompt.strip():
                raise ValueError("endpoint chat requires a prompt; pass --prompt, --stdin, or use --native-ollama")
            output = manager.run_chat(args.model, prompt=prompt, timeout_seconds=args.timeout_seconds)
            if output:
                print(output)
            return 0
        print("Endpoint chat. Type /exit to quit.")
        while True:
            try:
                prompt = input("aiplane chat> ")
            except EOFError:
                break
            if prompt.strip() in {"/exit", "/quit"}:
                break
            if not prompt.strip():
                continue
            output = manager.run_chat(args.model, prompt=prompt, timeout_seconds=args.timeout_seconds)
            if output:
                print(output)
        return 0

    if args.command == "bridge":
        if args.bridge_command == "list":
            actions = []
            for action, spec in sorted(bridge_actions.items()):
                actions.append(
                    {
                        "action": action,
                        "description": spec.get("description"),
                        "command": list(spec.get("base_command", [])),
                        "requires_model": bool(spec.get("requires_model")),
                        "supports_prompt": bool(spec.get("supports_prompt")),
                    }
                )
            print(json_dumps({"name": "bridge_actions", "actions": actions}, indent=2))
            return 0
        if args.bridge_command == "exec":
            command = _bridge_action_command(bridge_actions, args.action, model=args.model, prompt=args.prompt)
            payload = {
                "name": "bridge_exec",
                "action": args.action,
                "command": command,
                "dry_run": bool(args.dry_run),
            }
            if args.dry_run:
                payload["ok"] = True
                print(json_dumps(payload, indent=2))
                return 0
            executable = command[0] if command else ""
            if executable and not shutil.which(executable):
                payload["ok"] = False
                payload["reason"] = f"required executable not found on PATH: {executable}"
                print(json_dumps(payload, indent=2))
                return 2
            completed = command_runner.run(command, text=True, capture_output=True, check=False)
            if completed.stdout:
                print(completed.stdout, end="")
            if completed.stderr:
                print(completed.stderr, end="", file=sys.stderr)
            return int(completed.returncode)
        raise ValueError(f"unknown bridge command: {args.bridge_command}")

    if args.command == "launch":
        profile = load_profile(effective_profile, workspace, profiles_dir=profiles_dir)
        plan = launch_plan(profile, args.tool, model=args.model, app=args.app)
        payload = {
            "name": "launch_plan",
            "tool": args.tool,
            "profile": profile.name,
            "dry_run": bool(args.dry_run),
            **plan,
        }
        if args.dry_run:
            payload["ok"] = True
            print(json_dumps(payload, indent=2))
            return 0
        executable = str(plan["command"][0]) if plan.get("command") else ""
        if executable and not shutil.which(executable):
            payload["ok"] = False
            payload["reason"] = f"required executable not found on PATH: {executable}"
            print(json_dumps(payload, indent=2))
            return 2
        completed = command_runner.run(
            [str(part) for part in plan["command"]],
            cwd=workspace,
            env=plan.get("env"),
            text=True,
            capture_output=True,
            check=False,
        )
        if completed.stdout:
            print(completed.stdout, end="")
        if completed.stderr:
            print(completed.stderr, end="", file=sys.stderr)
        payload["returncode"] = int(completed.returncode)
        return int(completed.returncode)

    if args.command == "session":
        profile = load_profile(effective_profile, workspace, profiles_dir=profiles_dir)
        launch_plan = launch_plan(profile, args.tool, model=args.model, app=args.app)
        session_id = new_session_id()
        transcript_path = default_transcript(args.transcript, workspace, session_id)
        payload = {
            "name": "session_start",
            "session_id": session_id,
            "tool": args.tool,
            "profile": profile.name,
            "model": launch_plan["selection"]["name"],
            "dry_run": bool(args.dry_run),
            "transcript": str(transcript_path),
            "launch": launch_plan,
        }
        if args.dry_run:
            print(json_dumps(payload, indent=2))
            return 0
        metadata_path = session_metadata_path(workspace, session_id)
        metadata_path.parent.mkdir(parents=True, exist_ok=True)
        transcript_path.parent.mkdir(parents=True, exist_ok=True)
        session_record = {
            "name": "session_record",
            "session_id": session_id,
            "tool": args.tool,
            "profile": profile.name,
            "model": launch_plan["selection"]["name"],
            "command": launch_plan["command"],
            "transcript": str(transcript_path),
            "created": datetime.now(timezone.utc).isoformat(),
        }
        atomic_write_text(metadata_path, json_dumps(session_record, indent=2, sort_keys=True) + "\n")
        launch_event = AuditEvent(
            event_type="session",
            profile=profile.name,
            action="session.start",
            decision="allowed",
            details={
                "session_id": session_id,
                "tool": args.tool,
                "model": launch_plan["selection"]["name"],
                "transcript": str(transcript_path),
                "command": launch_plan["command"],
                "selection": launch_plan["selection"],
            },
        )
        AuditLogger(profile).record(launch_event)
        payload["record"] = str(metadata_path)
        print(json_dumps(payload, indent=2))
        return 0

    return None
