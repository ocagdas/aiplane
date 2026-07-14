from __future__ import annotations

from pathlib import Path
import argparse
import json
import os
import sys
import threading
import uuid

from .boundaries import CommandRunner, SubprocessCommandRunner
from .config import (
    create_profile,
    local_config_path,
    load_profile,
    profiles_root,
    resolve_profile_name,
    resolve_output_format,
    resolve_output_verbosity,
)
from .hardware import HardwareManager
from .cli_config import add_config_parser, handle_config_command
from .cli_deploy_remote import add_deploy_remote_parsers, handle_deploy_remote_command
from .cli_hardware import add_hardware_machine_parsers, handle_hardware_machine_command
from .cli_governance import add_governance_parsers, handle_governance_command
from .cli_integrations import add_integrations_parser, handle_integrations_command
from .cli_stacks import add_stack_parsers, handle_stack_command
from .cli_setup import add_setup_parsers, handle_setup_command
from .cli_providers import add_providers_parser, handle_providers_command
from .cli_runtimes import (
    _run_provider_helper,
    _runtime_helper_substrate,
    add_runtimes_parser,
    handle_runtimes_command,
)
from .cli_execution import add_execution_parsers, handle_execution_command
from .cli_public import add_public_parsers, handle_public_command
from .cli_profiles import add_profiles_parser, handle_profiles_command
from .cli_models import add_models_parser, handle_models_command, refresh_cli_payload
from .cli_support import (
    parse_provider_limits as _parse_provider_limits,
    parse_setting_value as _parse_setting_value,
    parse_settings as _parse_settings,
    refresh_progress as _refresh_progress,
)
from .integrations import IntegrationManager
from .integration_contracts import ALL_INTEGRATION_TOOLS
from .local_doctor import local_coding_doctor
from .model_catalog import ModelCatalog
from .output import json_dumps as _json
from .policy import PolicyEngine
from .runtime_catalog import RuntimeCatalog


_COMMAND_RUNNER: CommandRunner = SubprocessCommandRunner()


class HelpFormatter(argparse.ArgumentDefaultsHelpFormatter, argparse.RawDescriptionHelpFormatter):
    pass


def _command(subparsers, name: str, help_text: str, description: str, epilog: str | None = None):
    return subparsers.add_parser(
        name,
        help=help_text,
        description=description,
        epilog=epilog,
        formatter_class=HelpFormatter,
        allow_abbrev=False,
    )


def _profile_arg(parser) -> None:
    parser.add_argument(
        "--profile",
        help="Profile name. Optional: defaults to AIPLANE_PROFILE, local config default_profile, or the only available profile",
    )


def _profiles_dir_from_env() -> Path | None:
    env_path = os.environ.get("AIPLANE_PROFILES_DIR")
    if env_path:
        return Path(env_path).expanduser().resolve()
    return None


_BRIDGE_ACTIONS: dict[str, dict[str, object]] = {
    "ollama-launch": {
        "description": "Launch Ollama native app flow",
        "base_command": ["ollama", "launch"],
        "requires_model": False,
        "supports_prompt": False,
    },
    "ollama-list": {
        "description": "List local Ollama models",
        "base_command": ["ollama", "list"],
        "requires_model": False,
        "supports_prompt": False,
    },
    "ollama-ps": {
        "description": "List running Ollama models",
        "base_command": ["ollama", "ps"],
        "requires_model": False,
        "supports_prompt": False,
    },
    "ollama-run": {
        "description": "Run Ollama model by id/alias",
        "base_command": ["ollama", "run"],
        "requires_model": True,
        "supports_prompt": True,
    },
}

_LAUNCH_TOOLS = ("aider", "continue", "ollama")


def _integration_selection_args(parser) -> None:
    parser.add_argument(
        "--provider",
        help="Constrain model selection to a provider/source, such as ollama or vllm",
    )
    parser.add_argument(
        "--runtime",
        help="Constrain model selection to a compatible runtime, such as ollama, vllm, or tgi",
    )
    parser.add_argument(
        "--capability",
        action="append",
        default=[],
        help="Capability threshold used for selection, e.g. code_analysis>=3 or tool_use>=2; can be repeated",
    )
    parser.add_argument(
        "--select-best",
        action="store_true",
        help="Select best-fit catalog models instead of using profile defaults",
    )
    parser.add_argument("--chat", help="Force a model alias for Continue chat/edit/apply")
    parser.add_argument("--autocomplete", help="Force a model alias for Continue autocomplete")
    parser.add_argument("--embedding", help="Force a model alias for Continue embeddings/retrieval")


def main(argv: list[str] | None = None) -> int:
    try:
        return _main(argv)
    except (FileNotFoundError, PermissionError, RuntimeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="aiplane",
        description=(
            "Configure, check, and connect local/cloud AI coding environments.\n\n"
            "aiplane is an environment-doctor and configuration compiler: it manages profiles, providers, models, hardware fit,\n"
            "IDE/CLI exports, remote endpoint plans, and MCP access. It does not replace IDE agents."
        ),
        epilog=(
            "Primary workflow:\n"
            "  aiplane discover\n"
            "  aiplane doctor\n"
            "  aiplane recommend\n"
            "  aiplane export continue\n"
            "  aiplane quickstart local-coding\n\n"
            "Advanced command categories are documented in docs/project/command-coverage.md.\n"
            "Docs: docs/user/index.md"
        ),
        formatter_class=HelpFormatter,
        allow_abbrev=False,
    )
    parser.add_argument(
        "--workspace",
        default=".",
        help="Workspace root for path checks, audit logs, benchmarks, and tool execution",
    )
    parser.add_argument(
        "--profiles-dir",
        help="Directory containing editable profiles. Defaults to AIPLANE_PROFILES_DIR when set, otherwise the repo-local profiles/ directory",
    )
    subparsers = parser.add_subparsers(dest="command", required=True, metavar="command")

    add_public_parsers(
        subparsers,
        command_factory=_command,
        profile_arg=_profile_arg,
        integration_selection_args=_integration_selection_args,
        formatter_class=HelpFormatter,
        integration_tools=ALL_INTEGRATION_TOOLS,
    )

    add_config_parser(
        subparsers,
        command_factory=_command,
        formatter_class=HelpFormatter,
    )

    add_profiles_parser(
        subparsers,
        command_factory=_command,
        profile_arg=_profile_arg,
        formatter_class=HelpFormatter,
    )

    add_execution_parsers(
        subparsers,
        command_factory=_command,
        profile_arg=_profile_arg,
        formatter_class=HelpFormatter,
        launch_tools=_LAUNCH_TOOLS,
        bridge_actions=_BRIDGE_ACTIONS,
    )

    add_hardware_machine_parsers(
        subparsers,
        command_factory=_command,
        profile_arg=_profile_arg,
        formatter_class=HelpFormatter,
    )
    add_stack_parsers(
        subparsers,
        command_factory=_command,
        profile_arg=_profile_arg,
        formatter_class=HelpFormatter,
    )
    add_models_parser(
        subparsers,
        command_factory=_command,
        profile_arg=_profile_arg,
        formatter_class=HelpFormatter,
    )

    add_integrations_parser(
        subparsers,
        command_factory=_command,
        profile_arg=_profile_arg,
        selection_args=_integration_selection_args,
        formatter_class=HelpFormatter,
    )

    add_deploy_remote_parsers(
        subparsers,
        command_factory=_command,
        profile_arg=_profile_arg,
        formatter_class=HelpFormatter,
    )

    add_runtimes_parser(
        subparsers,
        command_factory=_command,
        profile_arg=_profile_arg,
        formatter_class=HelpFormatter,
    )

    add_providers_parser(
        subparsers,
        command_factory=_command,
        profile_arg=_profile_arg,
        formatter_class=HelpFormatter,
    )

    add_setup_parsers(
        subparsers,
        command_factory=_command,
        profile_arg=_profile_arg,
        formatter_class=HelpFormatter,
    )
    add_governance_parsers(
        subparsers,
        command_factory=_command,
        profile_arg=_profile_arg,
        formatter_class=HelpFormatter,
    )
    args = parser.parse_args(argv)
    workspace = Path(args.workspace).resolve()
    profiles_dir = Path(args.profiles_dir).expanduser().resolve() if args.profiles_dir else None
    if profiles_dir is None and args.command != "config":
        profiles_dir = _profiles_dir_from_env()
    requested_profile = getattr(args, "profile", None)

    config_result = handle_config_command(
        args,
        profiles_dir=profiles_dir,
        requested_profile=requested_profile,
        json_dumps=_json,
        parse_setting_value=_parse_setting_value,
    )
    if config_result is not None:
        return config_result

    profile_result = handle_profiles_command(
        args,
        workspace=workspace,
        profiles_dir=profiles_dir,
        requested_profile=requested_profile,
        json_dumps=_json,
        bootstrap_profile=_bootstrap_local_profile,
        validate_profile=_validate_profile,
        profile_selected=_profile_selected,
        profile_summary=_profile_summary,
    )
    if profile_result is not None:
        return profile_result

    public_result = handle_public_command(
        args,
        workspace=workspace,
        profiles_dir=profiles_dir,
        requested_profile=requested_profile,
        json_dumps=_json,
        quickstart=_quickstart_local_coding,
        quickstart_text=_quickstart_local_coding_text,
        discover=_public_discover,
        discover_text=_public_discover_text,
        recommend_text=_public_recommend_text,
        print_export=_print_public_export,
        doctor_exit_code=_doctor_exit_code,
    )
    if public_result is not None:
        return public_result

    effective_profile = resolve_profile_name(requested_profile, profiles_dir=profiles_dir)

    governance_result = handle_governance_command(
        args,
        workspace=workspace,
        profiles_dir=profiles_dir,
        effective_profile=effective_profile,
        json_dumps=_json,
    )
    if governance_result is not None:
        return governance_result

    execution_result = handle_execution_command(
        args,
        workspace=workspace,
        profiles_dir=profiles_dir,
        effective_profile=effective_profile,
        json_dumps=_json,
        bridge_actions=_BRIDGE_ACTIONS,
        launch_plan=_launch_plan,
        new_session_id=_new_session_id,
        default_transcript=_default_session_transcript,
        session_metadata_path=_session_metadata_path,
        command_runner=_COMMAND_RUNNER,
    )
    if execution_result is not None:
        return execution_result

    setup_result = handle_setup_command(
        args,
        workspace=workspace,
        profiles_dir=profiles_dir,
        effective_profile=effective_profile,
        json_dumps=_json,
        progress_factory=_stderr_line_progress,
        resolve_format=resolve_output_format,
        config_path=local_config_path(),
        environment_doctor_text=_environment_doctor_text,
    )
    if setup_result is not None:
        return setup_result

    hardware_result = handle_hardware_machine_command(
        args,
        workspace=workspace,
        profiles_dir=profiles_dir,
        effective_profile=effective_profile,
        json_dumps=_json,
        parse_settings=_parse_settings,
        reporter_factory=_AzCommandReporter,
        resolve_format=resolve_output_format,
        config_path=local_config_path(),
        hardware_show_text=_hardware_show_text,
    )
    if hardware_result is not None:
        return hardware_result
    stack_result = handle_stack_command(
        args,
        workspace=workspace,
        profiles_dir=profiles_dir,
        effective_profile=effective_profile,
        json_dumps=_json,
        parse_settings=_parse_settings,
    )
    if stack_result is not None:
        return stack_result
    if args.command == "models":
        profile = load_profile(effective_profile, workspace, profiles_dir=profiles_dir)
        output_format = None
        output_verbosity = None
        if args.models_command == "list":
            output_format = resolve_output_format(
                args.format,
                profile=effective_profile,
                command="models list",
                path=local_config_path(),
                default="json",
            )
            output_verbosity = resolve_output_verbosity(
                args.verbosity,
                profile=effective_profile,
                command="models list",
                path=local_config_path(),
                default=0,
            )
        return handle_models_command(
            args,
            profile=profile,
            json_dumps=_json,
            output_format=output_format,
            output_verbosity=output_verbosity,
        )

    if args.command == "integrations":
        profile = load_profile(effective_profile, workspace, profiles_dir=profiles_dir)
        return handle_integrations_command(args, profile, _json)

    runtime_result = handle_runtimes_command(
        args,
        workspace=workspace,
        profiles_dir=profiles_dir,
        effective_profile=effective_profile,
        json_dumps=_json,
    )
    if runtime_result is not None:
        return runtime_result

    provider_result = handle_providers_command(
        args,
        workspace=workspace,
        profiles_dir=profiles_dir,
        effective_profile=effective_profile,
        json_dumps=_json,
    )
    if provider_result is not None:
        return provider_result

    deploy_remote_result = handle_deploy_remote_command(
        args,
        workspace=workspace,
        profiles_dir=profiles_dir,
        effective_profile=effective_profile,
        json_dumps=_json,
    )
    if deploy_remote_result is not None:
        return deploy_remote_result

    return 1


def _launch_plan(
    profile,
    tool: str,
    model: str | None = None,
    app: str | None = None,
) -> dict[str, object]:
    if app and tool != "ollama":
        raise ValueError("--app is only supported with --tool ollama")
    manager = IntegrationManager(profile)
    plan_args: dict[str, object] = {}
    if tool == "continue":
        if model:
            plan_args["chat"] = model
    elif tool == "ollama":
        if model:
            plan_args["model_name"] = model
        plan_args["runtime"] = "ollama"
    else:
        if model:
            plan_args["model_name"] = model
    plan = manager.plan("openai-compatible" if tool == "ollama" else tool, **plan_args)
    selections = plan.get("selection", {})
    if not isinstance(selections, dict):
        raise ValueError("integration plan did not include a selection map")
    if tool == "continue":
        selected = selections.get("chat")
        if not isinstance(selected, dict):
            raise ValueError("integration plan is missing continue chat selection")
    else:
        selected = selections.get("primary")
        if not isinstance(selected, dict):
            raise ValueError("integration plan is missing primary selection")

    model_name = str(selected.get("name") or "")
    if not model_name:
        raise ValueError("selected model name is missing")

    decision = PolicyEngine(profile).model_decision(model_name)
    if not decision.allowed:
        raise ValueError(f"launch blocked: {decision.reason}")

    if tool == "ollama":
        model_id = str(selected.get("model") or "")
        command = ["ollama", "launch", model_id]
        if app:
            command.extend(["--app", app])
        return {
            "tool": tool,
            "selection": selected,
            "command": command,
        }

    if tool == "aider":
        api_key_env = str(selected.get("api_key_env") or "")
        model_id = str(selected.get("model") or "")
        if not model_id:
            raise ValueError("selected model has no model id")
        command = ["aider", "--model", f"openai/{model_id}"]
        launch_env: dict[str, str] = os.environ.copy()
        launch_env["OPENAI_API_BASE"] = str(selected.get("endpoint") or "")
        if api_key_env:
            if api_key_env not in launch_env:
                raise ValueError(f"required environment variable {api_key_env} for aider is not set")
            launch_env[api_key_env] = os.environ.get(api_key_env, "")
        return {
            "tool": tool,
            "selection": selected,
            "command": command,
            "env": launch_env,
        }

    if tool == "continue":
        return {
            "tool": tool,
            "selection": selected,
            "command": ["continue"],
        }

    raise ValueError(f"unsupported launch tool: {tool}")


def _new_session_id() -> str:
    return uuid.uuid4().hex


def _default_session_transcript(transcript_arg: str | Path | None, workspace: Path, session_id: str) -> Path:
    if transcript_arg:
        return Path(transcript_arg).expanduser()
    return workspace / ".aiplane" / "sessions" / f"{session_id}.log"


def _session_metadata_path(workspace: Path, session_id: str) -> Path:
    return workspace / ".aiplane" / "sessions" / f"{session_id}.json"


def _profile_summary(profile, default_name: str | None = None) -> dict[str, object]:
    return {
        "name": profile.name,
        "default": profile.name == default_name,
        "root": str(profile.root),
        "workspace": str(profile.workspace),
        "selected": _profile_selected(profile, default_name),
        "environment": profile.environment,
        "hardware": profile.hardware,
        "models": profile.models,
        "targets": profile.targets,
        "repository": profile.repository,
        "tools": profile.tools,
        "approvals": profile.approvals,
        "backends": profile.backends,
    }


def _profile_selected(profile, default_name: str | None = None) -> dict[str, object]:
    providers = ModelCatalog(profile).providers()
    models = profile.models.get("models", {}) if isinstance(profile.models, dict) else {}
    targets = profile.targets.get("targets", {}) if isinstance(profile.targets, dict) else {}
    hardware_selected = profile.hardware.get("selected", {}) if isinstance(profile.hardware, dict) else {}
    return {
        "name": profile.name,
        "default": profile.name == default_name,
        "root": str(profile.root),
        "environment": {
            "active": profile.environment.get("active"),
            "config": _dict_value(profile.environment.get("modes", {})).get(str(profile.environment.get("active")), {}),
        },
        "hardware": {
            "origin": hardware_selected.get("origin"),
            "custom": hardware_selected.get("custom"),
            "values": hardware_selected.get("values", {}),
        },
        "providers": [
            {"name": name, **provider}
            for name, provider in _dict_value(providers).items()
            if bool(provider.get("enabled", True))
        ],
        "model_defaults": (profile.models.get("defaults", {}) if isinstance(profile.models, dict) else {}),
        "models": [
            {"name": name, **model} for name, model in _dict_value(models).items() if bool(model.get("enabled", True))
        ],
        "targets": {
            "default": (profile.targets.get("default") if isinstance(profile.targets, dict) else None),
            "config": (
                _dict_value(targets).get(str(profile.targets.get("default")), {})
                if isinstance(profile.targets, dict)
                else {}
            ),
        },
        "repository": profile.repository,
    }


def _validate_profile(profile) -> dict[str, object]:
    checks: list[dict[str, object]] = []
    for filename in [
        "hardware.yaml",
        "backends.yaml",
        "repository.yaml",
        "tools.yaml",
        "approvals.yaml",
        "environment.yaml",
        "models.yaml",
        "targets.yaml",
        "orchestrators.yaml",
    ]:
        path = profile.root / filename
        checks.append({"name": f"file:{filename}", "ok": path.exists(), "detail": str(path)})

    active_env = profile.environment.get("active") if isinstance(profile.environment, dict) else None
    modes = _dict_value(profile.environment.get("modes", {})) if isinstance(profile.environment, dict) else {}
    checks.append(
        {
            "name": "environment:active_mode",
            "ok": bool(active_env in modes),
            "detail": active_env,
        }
    )

    providers = ModelCatalog(profile).providers()
    models = _dict_value(profile.models.get("models", {})) if isinstance(profile.models, dict) else {}
    defaults = _dict_value(profile.models.get("defaults", {})) if isinstance(profile.models, dict) else {}
    for role, name in defaults.items():
        model = models.get(str(name))
        checks.append(
            {
                "name": f"model_default:{role}",
                "ok": isinstance(model, dict),
                "detail": name,
            }
        )
        if isinstance(model, dict) and not bool(model.get("enabled", True)):
            checks.append(
                {
                    "name": f"model_default_enabled:{role}",
                    "ok": True,
                    "warning": True,
                    "detail": f"{name} is configured but disabled",
                }
            )
    for name, model in models.items():
        provider = str(model.get("provider", "")) if isinstance(model, dict) else ""
        checks.append(
            {
                "name": f"model_provider:{name}",
                "ok": provider in providers,
                "detail": provider,
            }
        )
        if (
            provider in providers
            and bool(model.get("enabled", True))
            and not bool(providers[provider].get("enabled", True))
        ):
            checks.append(
                {
                    "name": f"provider_enabled:{provider}",
                    "ok": True,
                    "warning": True,
                    "detail": f"{name} is catalogued, but runtime endpoint {provider} is disabled",
                }
            )

    targets = _dict_value(profile.targets.get("targets", {})) if isinstance(profile.targets, dict) else {}
    default_target = profile.targets.get("default") if isinstance(profile.targets, dict) else None
    checks.append(
        {
            "name": "target:default",
            "ok": bool(default_target in targets),
            "detail": default_target,
        }
    )

    return {
        "name": profile.name,
        "ok": all(bool(check["ok"]) for check in checks if not check.get("warning")),
        "checks": checks,
    }


_AZ_SENSITIVE_FLAGS = {
    "--subscription",
    "--tenant",
    "--tenant-id",
    "--account-name",
    "--username",
    "--password",
    "--token",
    "--access-token",
    "--api-key",
    "--client-id",
    "--client-secret",
    "--sas-token",
    "--connection-string",
}

_AZ_SENSITIVE_JSON_KEYS = {
    "id",
    "tenantid",
    "subscriptionid",
    "userid",
    "username",
    "principalid",
    "clientid",
    "objectid",
    "accesstoken",
    "refreshtoken",
    "token",
    "password",
    "secret",
    "connectionstring",
}


def _redact_command_for_stderr(command: list[str]) -> str:
    parts: list[str] = []
    redact_next = False
    for item in command:
        token = str(item)
        lowered = token.lower()
        if redact_next:
            parts.append("[redacted]")
            redact_next = False
            continue
        if "=" in token:
            key, value = token.split("=", 1)
            key_lower = key.lower()
            if key_lower in _AZ_SENSITIVE_FLAGS or _looks_sensitive_assignment(key):
                parts.append(f"{key}=[redacted]")
                continue
            parts.append(token if value else key)
            continue
        if lowered in _AZ_SENSITIVE_FLAGS:
            parts.append(token)
            redact_next = True
            continue
        parts.append(token)
    return " ".join(parts)


def _looks_sensitive_assignment(key: str) -> bool:
    key_lower = key.lower()
    return any(marker in key_lower for marker in ("token", "secret", "password", "apikey", "api_key", "key"))


def _redact_az_output_text(value: str) -> str:
    stripped = value.strip()
    if not stripped:
        return value
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        return value
    redacted = _redact_json_payload(payload)
    return json.dumps(redacted, indent=2, ensure_ascii=False)


def _redact_json_payload(value):
    if isinstance(value, dict):
        redacted = {}
        for key, item in value.items():
            key_lower = str(key).lower()
            if key_lower in _AZ_SENSITIVE_JSON_KEYS:
                redacted[key] = "[redacted]"
                continue
            if key_lower == "user" and isinstance(item, dict):
                user_redacted = dict(item)
                if "name" in user_redacted and user_redacted["name"]:
                    user_redacted["name"] = "[redacted]"
                redacted[key] = _redact_json_payload(user_redacted)
                continue
            redacted[key] = _redact_json_payload(item)
        return redacted
    if isinstance(value, list):
        return [_redact_json_payload(item) for item in value]
    return value


class _AzCommandReporter:
    def __init__(self, verbosity: int):
        self.verbosity = max(int(verbosity), 0)
        self._lock = threading.Lock()
        self._has_running_line = False
        self._dot_thread: threading.Thread | None = None
        self._dot_stop: threading.Event | None = None

    def report(self, event: dict[str, object]) -> None:
        phase = str(event.get("phase") or "")
        command = event.get("command")
        command_parts = [str(part) for part in command] if isinstance(command, list) else [str(command or "")]
        command_text = _redact_command_for_stderr(command_parts)
        if phase == "start":
            self._start_command_line(command_text)
            return
        if phase == "complete":
            self._stop_dot_line(clear_line=True)
            if self.verbosity >= 1:
                returncode = event.get("returncode", "?")
                self._write(f"[az] completed (exit {returncode}): {command_text}\n")
                stdout = event.get("stdout")
                stderr = event.get("stderr")
                if isinstance(stdout, str) and stdout.strip():
                    self._write(f"[az] stdout:\n{_redact_az_output_text(stdout).rstrip()}\n")
                if isinstance(stderr, str) and stderr.strip():
                    self._write(f"[az] stderr:\n{_redact_az_output_text(stderr).rstrip()}\n")

    def close(self) -> None:
        self._stop_dot_line(clear_line=True)

    def _start_command_line(self, command_text: str) -> None:
        self._stop_dot_line(clear_line=True)
        if self.verbosity <= 0 and self._has_running_line:
            self._write("\x1b[1A\r\x1b[2K")
        self._write(f"[az] running: {command_text}\n")
        self._has_running_line = True
        self._start_dot_line()

    def _start_dot_line(self) -> None:
        stop = threading.Event()
        self._dot_stop = stop
        thread = threading.Thread(target=self._dot_worker, args=(stop,), daemon=True)
        self._dot_thread = thread
        thread.start()

    def _dot_worker(self, stop: threading.Event) -> None:
        while not stop.wait(2):
            self._write(".")

    def _stop_dot_line(self, clear_line: bool) -> None:
        stop = self._dot_stop
        thread = self._dot_thread
        self._dot_stop = None
        self._dot_thread = None
        if stop:
            stop.set()
        if thread:
            thread.join(timeout=3)
        if clear_line:
            self._write("\r\x1b[2K\r")

    def _write(self, text: str) -> None:
        with self._lock:
            sys.stderr.write(text)
            sys.stderr.flush()


def _stderr_line_progress():
    longest = 0

    def progress(message: str) -> None:
        nonlocal longest
        if not message:
            if longest:
                sys.stderr.write("\r" + " " * longest + "\r")
                sys.stderr.flush()
                longest = 0
            return
        text = f"{message}..."
        longest = max(longest, len(text))
        sys.stderr.write("\r" + text.ljust(longest))
        sys.stderr.flush()

    return progress


def _hardware_show_text(payload: dict[str, object]) -> str:
    if not isinstance(payload, dict):
        return "hardware show\n(no data)"

    active = payload.get("active_selection", {})
    if not isinstance(active, dict):
        active = {}
    machine = payload.get("effective_machine", {})
    if not isinstance(machine, dict):
        machine = {}
    cpu = machine.get("cpu", {})
    memory = machine.get("memory", {})
    gpu = machine.get("gpu", {})
    stock = machine.get("stock", {})
    if not isinstance(cpu, dict):
        cpu = {}
    if not isinstance(memory, dict):
        memory = {}
    if not isinstance(gpu, dict):
        gpu = {}
    if not isinstance(stock, dict):
        stock = {}

    def _to_text(value: object) -> str:
        if value is None:
            return ""
        if isinstance(value, bool):
            return "yes" if value else "no"
        if isinstance(value, (list, tuple)):
            return ", ".join(str(item) for item in value)
        return str(value)

    def _single_row_table(headers: dict[str, str], row: dict[str, str]) -> str:
        keys = list(headers)
        widths = {key: len(headers[key]) for key in keys}
        for key in keys:
            widths[key] = max(widths[key], len(row.get(key, "")))
        lines = [
            "".join(headers[key].ljust(widths[key] + 2) for key in keys),
            "".join(row[key].ljust(widths[key] + 2) for key in keys),
        ]
        return "\n".join(lines)

    active_row = {
        "name": _to_text(active.get("name")),
        "origin": _to_text(active.get("origin")),
        "custom": _to_text(active.get("custom")),
    }
    active_lines = _single_row_table(
        {"name": "NAME", "origin": "ORIGIN", "custom": "CUSTOM"},
        active_row,
    )

    effective_row = {
        "name": _to_text(machine.get("name")),
        "provider": _to_text(stock.get("provider")),
        "placement": _to_text(machine.get("placement")),
        "substrate": _to_text(machine.get("substrate")),
        "cpu_cores": _to_text(cpu.get("cores")),
        "cpu_threads": _to_text(cpu.get("threads")),
        "ram_gb": _to_text(memory.get("ram_gb")),
        "vram_gb": _to_text(gpu.get("vram_gb")),
        "total_vram_gb": _to_text(gpu.get("total_vram_gb")),
        "gpu_vendor": _to_text(gpu.get("vendor")),
        "gpu_model": _to_text(gpu.get("model")),
    }
    effective_lines = _single_row_table(
        {
            "name": "NAME",
            "provider": "PROVIDER",
            "placement": "PLACEMENT",
            "substrate": "SUBSTRATE",
            "cpu_cores": "CPU_CORES",
            "cpu_threads": "CPU_THREADS",
            "ram_gb": "RAM_GB",
            "vram_gb": "VRAM_GB",
            "total_vram_gb": "TOTAL_VRAM_GB",
            "gpu_vendor": "GPU_VENDOR",
            "gpu_model": "GPU_MODEL",
        },
        effective_row,
    )

    return "\n".join(
        [
            "hardware show",
            "active_selection",
            active_lines,
            "",
            "effective_machine",
            effective_lines,
        ]
    )


def _environment_doctor_text(payload: dict[str, object]) -> str:
    summary = payload.get("summary", {}) if isinstance(payload.get("summary"), dict) else {}
    rows: list[dict[str, str]] = []
    tool_rows: list[dict[str, str]] = []
    for section in [
        "installed",
        "missing_installable_by_aiplane",
        "missing_manual_or_platform_specific",
    ]:
        values = payload.get(section, [])
        for item in values if isinstance(values, list) else []:
            if not isinstance(item, dict):
                continue
            needed_for = item.get("needed_for", [])
            why = (
                ", ".join(str(value) for value in needed_for[:2])
                if isinstance(needed_for, list)
                else str(needed_for or "")
            )
            tool_rows.append(
                {
                    "name": str(item.get("name") or ""),
                    "kind": "tool",
                    "status": "installed" if item.get("installed") else "missing",
                    "required": str(item.get("requirement") or "optional"),
                    "why": why or str(item.get("description") or ""),
                }
            )
    rows.extend(
        sorted(
            tool_rows,
            key=lambda row: (
                0 if row["required"] == "mandatory" else 1,
                row["status"] != "installed",
                row["name"],
            ),
        )
    )
    values = payload.get("runtime_prerequisites", [])
    for item in values if isinstance(values, list) else []:
        if not isinstance(item, dict):
            continue
        purpose = item.get("purpose", [])
        why = ", ".join(str(value) for value in purpose[:2]) if isinstance(purpose, list) else str(purpose or "")
        missing_required = item.get("missing_required", [])
        missing_count = len(missing_required) if isinstance(missing_required, list) else 0
        rows.append(
            {
                "name": str(item.get("runtime") or ""),
                "kind": "runtime",
                "status": (
                    "ready" if item.get("ok") else (f"missing {missing_count}" if missing_count else "needs setup")
                ),
                "required": "optional",
                "why": why,
            }
        )
    headers = {
        "name": "NAME",
        "kind": "TYPE",
        "status": "STATUS",
        "required": "REQUIRED",
        "why": "WHY",
    }
    keys = ["name", "kind", "status", "required", "why"]
    widths = {key: len(value) for key, value in headers.items()}
    for row in rows:
        for key in keys:
            limit = 52 if key == "why" else 24
            widths[key] = min(max(widths[key], len(row.get(key, ""))), limit)

    def clipped(value: str, width: int) -> str:
        return value if len(value) <= width else value[: max(0, width - 3)] + "..."

    lines = [
        f"environment doctor for profile {payload.get('profile', 'unknown')}",
        f"tools: {summary.get('tools_installed', 0)}/{summary.get('tools_checked', 0)} installed; runtime prerequisites missing: {summary.get('runtime_prerequisites_missing', 0)}",
        "",
        "  ".join(headers[key].ljust(widths[key]) for key in keys),
    ]
    for row in rows:
        lines.append("  ".join(clipped(row[key], widths[key]).ljust(widths[key]) for key in keys))
    notes = payload.get("notes", [])
    if isinstance(notes, list) and notes:
        lines.append("")
        lines.append("next steps:")
        lines.extend(f"- {note}" for note in notes[:3])
    return "\n".join(lines)


def _public_discover(profile) -> dict[str, object]:
    catalog = ModelCatalog(profile)
    models = catalog.models()
    providers = catalog.providers()
    defaults = catalog.defaults()
    hardware = HardwareManager(profile).discover()
    runtimes = RuntimeCatalog(profile).list(include_gui=True)
    integrations = IntegrationManager(profile).list()
    endpoints = [
        {
            "provider": name,
            "endpoint": provider.get("endpoint"),
            "enabled": bool(provider.get("enabled", True)),
            "api_key_env": provider.get("api_key_env"),
            "ownership": provider.get("ownership"),
            "origin": provider.get("origin", "built_in"),
        }
        for name, provider in sorted(providers.items())
        if isinstance(provider, dict) and (provider.get("endpoint") or provider.get("api_key_env"))
    ]
    local_models = [
        {
            "name": name,
            "model": model.get("model"),
            "provider": model.get("provider"),
            "enabled": bool(model.get("enabled", True)),
            "origin": "discovered_cache" if name in catalog.generated_config.get("models", {}) else "profile",
        }
        for name, model in sorted(models.items())
        if isinstance(model, dict) and bool(model.get("local", False))
    ]
    return {
        "name": "environment_discovery",
        "profile": profile.name,
        "read_only": True,
        "hardware": hardware,
        "runtimes": runtimes,
        "local_models": local_models,
        "endpoints": endpoints,
        "coding_tools": integrations,
        "defaults": defaults,
        "provenance": _profile_provenance(
            profile,
            hardware=hardware,
            runtimes=runtimes,
            local_models=local_models,
            endpoints=endpoints,
            integrations=integrations,
        ),
        "next_command": f"aiplane doctor --profile {profile.name}",
    }


def _public_discover_text(payload: dict[str, object]) -> str:
    provenance = payload.get("provenance") if isinstance(payload.get("provenance"), dict) else {}
    summary = provenance.get("summary") if isinstance(provenance.get("summary"), dict) else {}
    hardware = payload.get("hardware") if isinstance(payload.get("hardware"), dict) else {}
    lines = [
        f"aiplane discover for profile {payload.get('profile', 'unknown')}",
        f"hardware: CPU={hardware.get('cpu_count', 'unknown')}; RAM={hardware.get('memory_gb', 'unknown')}GB; GPUs={len(hardware.get('gpus', []) or [])}",
        f"runtimes: {len(payload.get('runtimes', []) or [])}; local_models: {len(payload.get('local_models', []) or [])}; endpoints: {len(payload.get('endpoints', []) or [])}; coding_tools: {len(payload.get('coding_tools', []) or [])}",
        "configuration sources (counted records): "
        f"detected={summary.get('detected_values', 0)}, "
        f"built_in={summary.get('generated_values', 0)}, "
        f"discovered_cache={summary.get('discovered_values', 0)}, "
        f"profile_configured={summary.get('user_supplied_values', 0)}, "
        f"unresolved={summary.get('unresolved_values', 0)}",
        "",
        f"next command: {payload.get('next_command')}",
    ]
    return "\n".join(lines)


def _public_recommend_text(payload: dict[str, object]) -> str:
    models = payload.get("models") if isinstance(payload.get("models"), dict) else {}
    lines = ["aiplane recommend", "recommended:"]
    recommended = models.get("recommended", []) if isinstance(models, dict) else []
    if recommended:
        for row in recommended[:8]:
            if not isinstance(row, dict):
                continue
            lines.append(f"- {row.get('name')}: {row.get('reason')}")
    else:
        lines.append("- none")
    usable = models.get("usable", []) if isinstance(models, dict) else []
    remote = models.get("remote_or_cloud", []) if isinstance(models, dict) else []
    lines.append(f"usable: {len(usable)}; remote_or_cloud: {len(remote)}")
    lines.append("next command: aiplane export continue")
    return "\n".join(lines)


def _print_public_export(args, profile) -> None:
    manager = IntegrationManager(profile)
    if args.from_plan:
        plan = json.loads(Path(args.from_plan).read_text(encoding="utf-8"))
        exported = manager.export_from_plan(plan)
    else:
        exported = manager.export(
            args.tool,
            args.model,
            endpoint=args.endpoint,
            api_key_env=args.api_key_env,
            provider=args.provider,
            runtime=args.runtime,
            capabilities=args.capability,
            select_best=args.select_best,
            chat=args.chat,
            autocomplete=args.autocomplete,
            embedding=args.embedding,
        )
    print(exported.content)
    if exported.notes:
        print("\n# Notes")
        for note in exported.notes:
            print(f"# - {note}")


def _doctor_exit_code(payload: dict[str, object]) -> int:
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    if int(summary.get("blocking", 0) or 0) > 0:
        return 2
    if int(summary.get("warnings", 0) or 0) > 0:
        return 1
    return 0


def _profile_provenance(
    profile,
    *,
    hardware: dict[str, object] | None = None,
    runtimes: list[dict[str, object]] | None = None,
    local_models: list[dict[str, object]] | None = None,
    endpoints: list[dict[str, object]] | None = None,
    integrations: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    values: list[dict[str, object]] = []

    def add(state: str, source: str, name: str, value: object) -> None:
        values.append({"state": state, "source": source, "name": name, "value": value})

    hardware = hardware or {}
    if hardware.get("cpu_count") is not None:
        add("detected", "hardware.discover", "hardware.cpu_count", hardware.get("cpu_count"))
    if hardware.get("memory_gb") is not None:
        add("detected", "hardware.discover", "hardware.memory_gb", hardware.get("memory_gb"))
    for index, gpu in enumerate(hardware.get("gpus", []) or []):
        if isinstance(gpu, dict):
            add("detected", "hardware.discover", f"hardware.gpus.{index}", gpu.get("name") or gpu.get("vendor"))
    for runtime in runtimes or []:
        if isinstance(runtime, dict):
            add("generated", "runtime_catalog", f"runtime.{runtime.get('name')}", runtime.get("protocol"))
    for tool in integrations or []:
        if isinstance(tool, dict):
            add("generated", "integration_contracts", f"integration.{tool.get('name')}", tool.get("description"))
    for model in local_models or []:
        if isinstance(model, dict):
            if model.get("origin") == "discovered_cache":
                add("discovered", "models.discovered.yaml", f"model.{model.get('name')}", model.get("model"))
            else:
                add("user_supplied", "profile.models", f"model.{model.get('name')}", model.get("model"))
    for endpoint in endpoints or []:
        if isinstance(endpoint, dict):
            state = "user_supplied" if endpoint.get("origin") == "profile" else "generated"
            source = "profile.providers" if state == "user_supplied" else "provider_defaults"
            add(state, source, f"endpoint.{endpoint.get('provider')}", endpoint.get("endpoint"))
    defaults = profile.models.get("defaults", {}) if isinstance(profile.models, dict) else {}
    if isinstance(defaults, dict):
        for key, value in sorted(defaults.items()):
            if value:
                add("user_supplied", "profile.defaults", f"defaults.{key}", value)
            else:
                add("unresolved", "profile.defaults", f"defaults.{key}", value)
    if not local_models:
        add("unresolved", "profile.models", "local_models", "no local model aliases discovered or configured")
    summary = {
        "detected_values": sum(1 for row in values if row["state"] == "detected"),
        "generated_values": sum(1 for row in values if row["state"] == "generated"),
        "discovered_values": sum(1 for row in values if row["state"] == "discovered"),
        "user_supplied_values": sum(1 for row in values if row["state"] == "user_supplied"),
        "unresolved_values": sum(1 for row in values if row["state"] == "unresolved"),
    }
    return {"summary": summary, "values": values}


def _bootstrap_local_profile(args, workspace: Path, profiles_dir: Path | None) -> dict[str, object]:
    root = profiles_root(profiles_dir)
    profile_path = root / args.name
    created = False
    would_create = False
    if args.dry_run:
        would_create = args.overwrite or not profile_path.exists()
    elif args.overwrite or not profile_path.exists():
        profile_path = create_profile(
            args.name,
            template=args.template,
            overwrite=args.overwrite,
            profiles_dir=profiles_dir,
        )
        created = True
    profile_exists = profile_path.exists()
    validation = None
    discovery = None
    hardware = None
    provenance = None
    if profile_exists:
        profile = load_profile(args.name, workspace, profiles_dir=profiles_dir)
        validation = _validate_profile(profile)
        verbosity = int(getattr(args, "verbosity", 0))
        if not args.no_hardware_discovery:
            manager = HardwareManager(profile)
            hardware = (
                manager.select_closest_discovered(dry_run=args.dry_run)
                if args.select_closest_hardware
                else manager.discover()
            )
        if not args.no_discovery:
            catalog = ModelCatalog(profile)
            provider_limits = _parse_provider_limits(args.provider_limit)
            progress = _refresh_progress()
            write = not args.dry_run
            try:
                if args.provider == "all":
                    refresh_all_kwargs: dict[str, object] = {
                        "write": write,
                        "enable": not args.disable_new,
                        "query": args.query,
                        "provider_limits": provider_limits,
                        "progress": progress,
                        "verbose": verbosity >= 2,
                    }
                    if args.limit is not None:
                        refresh_all_kwargs["limit"] = args.limit
                    discovery = catalog.refresh_all(**refresh_all_kwargs)
                else:
                    refresh_kwargs: dict[str, object] = {
                        "write": write,
                        "enable": not args.disable_new,
                        "query": args.query,
                        "progress": progress,
                        "verbose": verbosity >= 2,
                    }
                    provider_limit = provider_limits.get(args.provider)
                    if provider_limit is not None:
                        refresh_kwargs["limit"] = int(provider_limit)
                    elif args.limit is not None:
                        refresh_kwargs["limit"] = args.limit
                    discovery = catalog.refresh(args.provider, **refresh_kwargs)
            finally:
                if progress:
                    progress("done", "", "")
            if isinstance(discovery, dict) and "results" in discovery:
                discovery = refresh_cli_payload(discovery, verbosity=verbosity)
        provenance = _public_discover(profile)["provenance"]
    elif not args.no_discovery or not args.no_hardware_discovery:
        skipped = "profile does not exist yet; rerun without --dry-run to create it before discovery"
        if not args.no_discovery:
            discovery = {"skipped": True, "reason": skipped}
        if not args.no_hardware_discovery:
            hardware = {"skipped": True, "reason": skipped}
    return {
        "name": "profiles_bootstrap_local",
        "profile": args.name,
        "template": args.template,
        "path": str(profile_path),
        "created": created,
        "would_create": would_create,
        "overwrite": args.overwrite,
        "dry_run": args.dry_run,
        "discovery_requested": not args.no_discovery,
        "discovery": discovery,
        "hardware_discovery_requested": not args.no_hardware_discovery,
        "hardware": hardware,
        "provenance": provenance,
        "validation": validation,
        "next_steps": _profile_bootstrap_next_steps(args.name, not args.no_discovery, args.dry_run),
    }


def _quickstart_local_coding(args, workspace: Path, profiles_dir: Path | None) -> dict[str, object]:
    bootstrap = _bootstrap_local_profile(args, workspace, profiles_dir)
    doctor_payload = None
    recommendation_payload = None
    pull = None
    profile_path = Path(str(bootstrap.get("path", "")))
    profile = None
    if profile_path.exists():
        profile = load_profile(args.name, workspace, profiles_dir=profiles_dir)
        if args.pull_model:
            pull = _quickstart_pull_model(
                profile,
                args.name,
                args.pull_model,
                runtime=args.pull_runtime,
                substrate=args.pull_substrate,
                execute=not args.dry_run,
                profiles_dir=profiles_dir,
            )
        doctor_payload = local_coding_doctor(profile, include_optional=False)
        recommendation_payload = HardwareManager(profile).recommend()
    elif args.pull_model:
        pull = {
            "name": "quickstart_model_pull",
            "model": args.pull_model,
            "executed": False,
            "dry_run": True,
            "skipped": True,
            "reason": "profile does not exist yet; rerun quickstart without --dry-run before pulling models",
        }
    commands = [
        f"aiplane discover --profile {args.name}",
        f"aiplane doctor --profile {args.name}",
        f"aiplane recommend --profile {args.name}",
        f"aiplane export continue --profile {args.name}",
        f"aiplane export aider --profile {args.name}",
        "aiplane export vscode-mcp",
    ]
    if args.pull_model:
        pull_runtime = (pull.get("runtime") if isinstance(pull, dict) else None) or args.pull_runtime or "RUNTIME"
        commands.insert(
            1,
            f"aiplane runtimes pull {pull_runtime} --model {args.pull_model}" + (" --dry-run" if args.dry_run else ""),
        )
    if args.dry_run and not profile_path.exists():
        commands.insert(0, f"aiplane quickstart local-coding --name {args.name}")
    return {
        "name": "quickstart_local_coding",
        "profile": args.name,
        "dry_run": args.dry_run,
        "bootstrap": bootstrap,
        "pull": pull,
        "doctor": doctor_payload,
        "recommend": recommendation_payload,
        "commands": commands,
        "notes": [
            "This quickstart stays in the environment-doctor workflow lane: it creates or previews a local profile, runs discovery/doctor checks, optionally delegates an explicit model pull, and prints export commands.",
            "Use --dry-run with --pull-model to preview the existing runtime helper pull path without pulling model weights.",
            "It does not install runtimes, edit IDE configuration, start cloud resources, or run an agent conversation.",
        ],
    }


def _quickstart_pull_model(
    profile,
    profile_name: str,
    model_name: str,
    runtime: str | None = None,
    substrate: str | None = None,
    execute: bool = False,
    profiles_dir: Path | str | None = None,
) -> dict[str, object]:
    catalog = ModelCatalog(profile)
    model = catalog.get(model_name)
    provider = catalog.providers().get(str(model.get("provider") or ""), {})
    if str(model.get("ownership") or provider.get("ownership") or "") == "managed_service":
        return {
            "name": "quickstart_model_pull",
            "model": model_name,
            "executed": False,
            "dry_run": True,
            "ok": False,
            "reason": "managed-service model aliases are endpoint-backed and do not use local runtime model pulls",
        }
    selected_runtime = runtime or RuntimeCatalog(profile).select_runtime(model_name).get("selected")
    if not selected_runtime:
        return {
            "name": "quickstart_model_pull",
            "model": model_name,
            "executed": False,
            "dry_run": True,
            "ok": False,
            "reason": "no supported runtime is configured for this model alias",
        }
    resolved_substrate = _runtime_helper_substrate(profile, str(selected_runtime), substrate)
    completed = _run_provider_helper(
        str(selected_runtime),
        "pull",
        profile_name,
        model_name,
        substrate=resolved_substrate,
        dry_run=not execute,
        profiles_dir=profiles_dir,
    )
    return {
        "name": "quickstart_model_pull",
        "model": model_name,
        "runtime": str(selected_runtime),
        "substrate": resolved_substrate,
        "executed": execute,
        "dry_run": not execute,
        "ok": completed.returncode == 0,
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def _quickstart_local_coding_text(payload: dict[str, object]) -> str:
    bootstrap = payload.get("bootstrap") if isinstance(payload.get("bootstrap"), dict) else {}
    doctor = payload.get("doctor") if isinstance(payload.get("doctor"), dict) else None
    lines = [
        f"local coding quickstart for profile {payload.get('profile', 'unknown')}",
        f"profile path: {bootstrap.get('path', '')}",
        f"created: {bootstrap.get('created', False)}; dry_run: {payload.get('dry_run', False)}",
    ]
    validation = bootstrap.get("validation") if isinstance(bootstrap.get("validation"), dict) else None
    if validation is not None:
        lines.append(f"profile validation: {'ok' if validation.get('ok') else 'issues found'}")
    pull = payload.get("pull") if isinstance(payload.get("pull"), dict) else None
    if pull is not None:
        lines.append(
            f"pull: {'executed' if pull.get('executed') else 'preview'}; "
            f"model: {pull.get('model')}; runtime: {pull.get('runtime', 'n/a')}"
        )
    if doctor is not None:
        summary = doctor.get("summary") if isinstance(doctor.get("summary"), dict) else {}
        lines.append(
            f"doctor: {'ok' if doctor.get('ok') else 'issues found'}; "
            f"needs_attention: {summary.get('blocking', 0)}; further_actions: {summary.get('warnings', 0)}"
        )
        # show top blocking checks and simple suggestions
        if doctor is not None:
            blocking: list[tuple[str, str]] = []
            warnings: list[tuple[str, str]] = []
            for section in doctor.get("sections", []) or []:
                if not isinstance(section, dict):
                    continue
                section_name = str(section.get("name") or "general")
                for check in section.get("checks", []) or []:
                    if not isinstance(check, dict):
                        continue
                    reason = check.get("reason") or check.get("detail") or ""
                    # simple suggestion mapping with exact CLI snippets
                    if check.get("name") == "model_catalog":
                        suggestion = (
                            "Try: `aiplane models refresh --dry-run`; "
                            "`aiplane models list --group-by runtime`; "
                            "`aiplane models promote DISCOVERED_ENTRY_NAME --as ALIAS`"
                        )
                    elif section.get("name") == "model_defaults" or str(check.get("name", "")).endswith("_model"):
                        role_arg = check.get("name") or "<role>"
                        suggestion = (
                            "Try: `aiplane models refresh --dry-run`; "
                            "`aiplane models promote DISCOVERED_ENTRY_NAME --as ALIAS`; "
                            f"`aiplane models use {role_arg} ALIAS`"
                        )
                    elif section.get("name") == "environment":
                        suggestion = (
                            "Try: `aiplane environment doctor --required-only` then install missing CLIs listed above."
                        )
                    elif section.get("name") == "endpoints" or str(check.get("name", "")).startswith("endpoint:"):
                        suggestion = "Try: `aiplane runtimes status <runtime>` or `aiplane providers test <provider>`. If provider is disabled, run `aiplane providers enable <provider>`."
                    elif section.get("name") == "integrations":
                        suggestion = "Try: `aiplane integrations list`; `aiplane integrations roles <tool>`; `aiplane integrations plan <tool>`."
                    else:
                        suggestion = "See `aiplane doctor --profile <name>` for details."
                    check_name = str(check.get("name") or "check")
                    if section_name == "integrations" and check_name.startswith("integration:"):
                        check_name = check_name.split(":", 1)[1]
                    item = f"{check_name}: {reason} -> {suggestion}"
                    if not check.get("ok"):
                        blocking.append((section_name, item))
                    elif check.get("warning"):
                        warnings.append((section_name, item))

            if blocking:
                lines.append("")
                lines.append(f"recommended actions ({len(blocking)}):")
                current_root = ""
                for root, item in blocking:
                    if root != current_root:
                        lines.append(f"- {root}:")
                        current_root = root
                    lines.append(f"  - {item}")
            if warnings:
                lines.append("")
                lines.append(f"further actions/status ({len(warnings)}):")
                current_root = ""
                for root, item in warnings:
                    if root != current_root:
                        lines.append(f"- {root}:")
                        current_root = root
                    lines.append(f"  - {item}")
    lines.append("")
    lines.append("next commands:")
    commands = payload.get("commands", [])
    if isinstance(commands, list):
        lines.extend(f"- {command}" for command in commands)
    return "\n".join(lines).rstrip()


def _profile_bootstrap_next_steps(profile: str, discovery_requested: bool, dry_run: bool) -> list[str]:
    if dry_run:
        steps = [
            f"Rerun aiplane profiles bootstrap-local --name {profile} without --dry-run to create or refresh the profile."
        ]
    else:
        steps = [f"Run aiplane profiles validate {profile} after local edits."]
    if discovery_requested:
        steps.append(f"Review discovered candidates with aiplane models list --profile {profile} --group-by runtime.")
        steps.append(
            "Promote a reviewed discovered entry or add a profile-owned entry before setting defaults or exporting IDE config."
        )
    else:
        steps.append(
            f"Run aiplane models refresh --profile {profile} when you want to populate models.discovered.yaml."
        )
    return steps


def _dict_value(value: object) -> dict:
    return value if isinstance(value, dict) else {}
