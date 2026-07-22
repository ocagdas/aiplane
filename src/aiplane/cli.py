from __future__ import annotations

from pathlib import Path
import os
import sys
import traceback

from .boundaries import CommandRunner, SubprocessCommandRunner
from .secrets import redact
from .config import (
    local_config_path,
    load_profile,
    resolve_profile_name,
    resolve_output_format,
    resolve_output_verbosity,
)
from .cli_config import handle_config_command
from .cli_deploy_remote import handle_deploy_remote_command
from .cli_hardware import handle_hardware_machine_command
from .cli_governance import handle_governance_command
from .cli_integrations import handle_integrations_command, handle_integrations_import
from .cli_launch_support import (
    _default_session_transcript,
    _launch_plan,
    _new_session_id,
    _session_metadata_path,
)
from .cli_presenters import (
    _AzCommandReporter,
    _environment_doctor_text,
    _hardware_show_text,
    _public_discover_text,
    _public_recommend_text,
    _quickstart_local_coding_text,
    _stderr_line_progress,
)
from .cli_profile_support import _profile_selected, _profile_summary, _validate_profile
from .cli_public_workflows import (
    _bootstrap_local_profile,
    _doctor_exit_code,
    _print_public_export,
    _public_discover,
    _quickstart_local_coding,
)
from .cli_stacks import handle_stack_command
from .cli_setup import handle_setup_command
from .cli_support_catalog import handle_support_command
from .cli_providers import handle_providers_command
from .cli_runtimes import handle_runtimes_command
from .cli_execution import handle_execution_command
from .cli_public import handle_public_command
from .cli_profiles import handle_profiles_command
from .cli_models import handle_models_command
from .cli_support import (
    parse_setting_value as _parse_setting_value,
    parse_settings as _parse_settings,
)
from .cli_parser import BRIDGE_ACTIONS, build_parser
from .output import json_dumps as _json
from .cli_version import handle_version_argument


_COMMAND_RUNNER: CommandRunner = SubprocessCommandRunner()


def _profiles_dir_from_env() -> Path | None:
    env_path = os.environ.get("AIPLANE_PROFILES_DIR")
    if env_path:
        return Path(env_path).expanduser().resolve()
    return None


def main(argv: list[str] | None = None) -> int:
    debug = _debug_enabled(argv)
    try:
        return _main(argv)
    except BrokenPipeError:
        _silence_stdout()
        return 0
    except KeyboardInterrupt:
        print("error: interrupted", file=sys.stderr)
        return 130
    except (FileNotFoundError, PermissionError, RuntimeError, ValueError) as exc:
        print(f"error: {redact(str(exc))}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001 - process boundary must sanitize unexpected failures.
        if debug:
            traceback.print_exc()
        else:
            print(
                f"error: unexpected {type(exc).__name__}; rerun with --debug for a traceback",
                file=sys.stderr,
            )
        return 1


def _debug_enabled(argv: list[str] | None) -> bool:
    arguments = sys.argv[1:] if argv is None else argv
    return "--debug" in arguments or os.environ.get("AIPLANE_DEBUG", "").lower() in {"1", "true", "yes"}


def _silence_stdout() -> None:
    if sys.stdout is not sys.__stdout__:
        return
    descriptor: int | None = None
    try:
        descriptor = os.open(os.devnull, os.O_WRONLY)
        os.dup2(descriptor, sys.stdout.fileno())
    except (AttributeError, OSError):
        pass
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    version_result = handle_version_argument(args)
    if version_result is not None:
        return version_result
    if args.command is None:
        parser.error("the following arguments are required: command")
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

    support_result = handle_support_command(args, _json)
    if support_result is not None:
        return support_result

    if args.command == "integrations" and args.integrations_command == "import":
        return handle_integrations_import(args, profiles_dir=profiles_dir, json_dumps=_json)

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
        bridge_actions=BRIDGE_ACTIONS,
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
