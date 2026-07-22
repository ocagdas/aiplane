from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Callable

from .config import load_profile
from .providers import ProviderRegistry, SUPPORTED_CATALOG_ADAPTERS, SUPPORTED_ENDPOINT_FAMILIES
from .adapter_protocol import validate_result_file


def add_providers_parser(
    subparsers: Any,
    *,
    command_factory: Callable[..., argparse.ArgumentParser],
    profile_arg: Callable[[argparse.ArgumentParser], None],
    formatter_class: type[argparse.HelpFormatter],
) -> None:
    providers_cmd = command_factory(
        subparsers,
        "providers",
        "List and inspect model catalog providers",
        "Providers are source catalogs such as Ollama library, Hugging Face, GGUF repositories, or local files. Runtimes are handled by aiplane runtimes.",
        "Examples:\n  aiplane providers list\n  aiplane providers list --status disabled\n  aiplane providers list --runtime ollama\n  aiplane providers list --runtime vllm --group-by runtime\n  aiplane providers list --group-by ownership\n  aiplane providers show ollama\n  aiplane providers models ollama",
    )
    providers_sub = providers_cmd.add_subparsers(dest="providers_command", required=True, metavar="command")
    providers_list = providers_sub.add_parser(
        "list",
        help="List model catalog providers",
        description="List model providers that supply downloadable model identifiers or artifacts. Runtimes such as vLLM, TGI, llama.cpp, and Transformers are listed under aiplane runtimes.",
        formatter_class=formatter_class,
        epilog="Examples:\n  aiplane providers list\n  aiplane providers list --status enabled\n  aiplane providers list --status disabled\n  aiplane providers list --runtime ollama\n  aiplane providers list --runtime vllm --group-by runtime\n  aiplane providers list --group-by ownership",
    )
    profile_arg(providers_list)
    providers_list.add_argument(
        "--runtime",
        action="append",
        default=[],
        help="Only show catalog providers whose models are typically served by this runtime; can be repeated",
    )
    providers_list.add_argument(
        "--status",
        choices=["enabled", "disabled", "all"],
        default="all",
        help="Filter providers by enabled state. Defaults to all providers.",
    )
    providers_list.add_argument(
        "--group-by",
        choices=["runtime", "ownership"],
        help="Group catalog providers by typical runtime or ownership",
    )
    providers_show = providers_sub.add_parser(
        "show",
        help="Show one catalog provider",
        description="Show model provider metadata and configured model aliases from that source.",
        formatter_class=formatter_class,
    )
    profile_arg(providers_show)
    providers_show.add_argument("name", help="Provider name, such as ollama, huggingface, or huggingface_gguf")
    providers_diagnose = providers_sub.add_parser(
        "diagnose", help="Explain provider discovery readiness without network access", formatter_class=formatter_class
    )
    profile_arg(providers_diagnose)
    providers_diagnose.add_argument("name", nargs="?", help="Optional provider name")
    providers_endpoint_types = providers_sub.add_parser(
        "endpoint-types",
        help="List supported provider API families and catalog adapters",
        description="List the provider API families and catalog discovery adapters that user-added providers can declare. New API shapes require a code update before they can be used safely.",
        formatter_class=formatter_class,
        epilog=(
            "Examples:\n"
            "  aiplane providers endpoint-types\n"
            "  aiplane providers add my_gateway --ownership managed_service --endpoint-family custom_openai_compatible --catalog-adapter openai --auth-method bearer --api-key-env MY_GATEWAY_API_KEY"
        ),
    )
    profile_arg(providers_endpoint_types)
    providers_adapter_schema = providers_sub.add_parser(
        "adapter-schema",
        help="Show the contributor adapter contract",
        description="Print the versioned, secret-free catalog adapter result contract and schema location.",
        formatter_class=formatter_class,
    )
    profile_arg(providers_adapter_schema)
    providers_adapter_validate = providers_sub.add_parser(
        "adapter-validate",
        help="Validate a catalog adapter result fixture",
        formatter_class=formatter_class,
    )
    profile_arg(providers_adapter_validate)
    providers_adapter_validate.add_argument("path", type=Path)
    providers_models = providers_sub.add_parser(
        "models",
        help="List catalog provider models",
        description="List known model ids for a model provider. With --online, query supported catalog adapters such as Ollama, Hugging Face, OpenAI-compatible /v1/models, Azure OpenAI deployments, and ElevenLabs voices.",
        formatter_class=formatter_class,
    )
    profile_arg(providers_models)
    providers_models.add_argument("name", help="Catalog provider name to query")
    providers_models.add_argument(
        "--online",
        action="store_true",
        help="Query the provider's online catalog API when aiplane has an adapter for it",
    )
    providers_models.add_argument("--query", help="Optional search query for online/catalog model lookup")
    providers_models.add_argument("--limit", type=int, default=500, help="Maximum model ids to return")
    providers_enable = providers_sub.add_parser(
        "enable",
        help="Enable a model provider",
        description="Enable a model provider in this profile. Disabled providers are skipped by refresh/list unless explicitly included.",
        formatter_class=formatter_class,
    )
    profile_arg(providers_enable)
    providers_enable.add_argument("name", help="Provider name, or all")
    providers_disable = providers_sub.add_parser(
        "disable",
        help="Disable a model provider",
        description="Disable a model provider in this profile without removing model aliases.",
        formatter_class=formatter_class,
    )
    profile_arg(providers_disable)
    providers_disable.add_argument("name", help="Provider name, or all")
    providers_remove = providers_sub.add_parser(
        "remove",
        help="Hide/remove a model provider",
        description="Mark a model provider as removed in this profile. Existing model aliases are not deleted; use models clear-cache for aliases.",
        formatter_class=formatter_class,
    )
    profile_arg(providers_remove)
    providers_remove.add_argument("name", help="Provider name to hide/remove from provider discovery")
    providers_add = providers_sub.add_parser(
        "add",
        help="Add a profile model provider",
        description="Add a user-defined model provider to model-providers.user.yaml. This does not edit the shipped defaults file.",
        formatter_class=formatter_class,
    )
    profile_arg(providers_add)
    providers_add.add_argument("name", help="Provider name to add")
    providers_add.add_argument("--description", default="", help="Human-readable provider description")
    providers_add.add_argument(
        "--ownership",
        choices=["self_managed", "managed_service"],
        help="Provider ownership. Defaults to managed_service when --endpoint-family is used, otherwise self_managed.",
    )
    providers_add.add_argument(
        "--runtime",
        action="append",
        default=[],
        help="Self-managed compatible runtime; can be repeated. Do not use for managed-service providers.",
    )
    providers_add.add_argument(
        "--endpoint-family",
        choices=sorted(SUPPORTED_ENDPOINT_FAMILIES),
        help="Managed-service endpoint/API family. If the provider does not match one of these, aiplane needs a code update.",
    )
    providers_add.add_argument(
        "--catalog-adapter",
        choices=sorted(SUPPORTED_CATALOG_ADAPTERS),
        default="profile_catalog",
        help="Catalog discovery adapter/API shape to reuse. Use profile_catalog when the catalog is manually curated.",
    )
    providers_add.add_argument("--endpoint", help="Default endpoint URL for this provider, when applicable")
    providers_add.add_argument("--credential-ref", help="Default credential ref, such as openai.personal")
    providers_add.add_argument("--api-key-env", help="Environment variable that provides the API key/token")
    providers_add.add_argument(
        "--auth-method",
        choices=["none", "api_key", "bearer", "oauth2", "custom"],
        default="none",
        help="Authentication style required by the provider/catalog API",
    )
    providers_add.add_argument(
        "--requires-credentials",
        action="store_true",
        help="Mark this provider/catalog as requiring credentials even if the auth method is custom or configured elsewhere",
    )
    providers_add.add_argument("--disabled", action="store_true", help="Add the provider disabled")
    providers_init = providers_sub.add_parser(
        "init-defaults",
        help="Write built-in provider defaults",
        description="Dump aiplane's hardcoded model-provider defaults into model-providers.yaml for this profile. Use --overwrite to reinitialize an existing defaults file.",
        formatter_class=formatter_class,
    )
    profile_arg(providers_init)
    providers_init.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace an existing model-providers.yaml file",
    )
    providers_update = providers_sub.add_parser(
        "update-defaults",
        help="Refresh profile provider defaults from this aiplane version",
        description="Update model-providers.yaml from built-in defaults while preserving existing enabled/disabled values and leaving model-providers.user.yaml untouched.",
        formatter_class=formatter_class,
    )
    profile_arg(providers_update)
    providers_clear = providers_sub.add_parser(
        "clear",
        help="Clear provider config files",
        description="Clear provider configuration. embedded/all writes an empty model-providers.yaml marker so hardcoded defaults do not silently reappear.",
        formatter_class=formatter_class,
    )
    profile_arg(providers_clear)
    providers_clear.add_argument(
        "--scope",
        choices=["embedded", "user", "all"],
        default="all",
        help="Which provider config to clear. embedded clears model-providers.yaml, user clears model-providers.user.yaml, and all clears both. Bare providers clear defaults to all.",
    )
    providers_doctor = providers_sub.add_parser(
        "doctor",
        help="Check catalog-provider model readiness",
        description="Check configured model aliases from one model provider, or all aliases when omitted.",
        formatter_class=formatter_class,
    )
    profile_arg(providers_doctor)
    providers_doctor.add_argument(
        "name",
        nargs="?",
        help="Optional model provider name to filter readiness checks",
    )
    providers_test = providers_sub.add_parser(
        "test",
        help="Test a managed provider endpoint credential",
        description="Make a small provider-specific API call to verify endpoint and credential configuration. Secrets are never printed.",
        formatter_class=formatter_class,
        epilog="Examples:\n  aiplane providers test openai\n  aiplane providers test azure_openai --credential-ref azure_openai.personal\n  aiplane providers test elevenlabs",
    )
    profile_arg(providers_test)
    providers_test.add_argument(
        "name",
        help="Provider name, such as openai, azure_openai, elevenlabs, or a custom OpenAI-compatible provider",
    )
    providers_test.add_argument(
        "--credential-ref",
        help="Override the provider credential_ref, such as azure_openai.personal",
    )
    providers_test.add_argument("--timeout", type=int, help="HTTP timeout in seconds")


def handle_providers_command(
    args: argparse.Namespace,
    *,
    workspace: Path,
    profiles_dir: Path | None,
    effective_profile: str,
    json_dumps: Callable[..., str],
) -> int | None:
    if args.command == "providers":
        profile = load_profile(effective_profile, workspace, profiles_dir=profiles_dir)
        registry = ProviderRegistry(profile)
        if args.providers_command == "list":
            print(
                json_dumps(
                    registry.list(
                        runtimes=args.runtime,
                        group_by=args.group_by,
                        status=args.status,
                    ),
                    indent=2,
                )
            )
            return 0
        if args.providers_command == "show":
            print(json_dumps(registry.show(args.name), indent=2, sort_keys=True))
            return 0
        if args.providers_command == "diagnose":
            print(json_dumps(registry.diagnose(args.name), indent=2, sort_keys=True))
            return 0
        if args.providers_command == "endpoint-types":
            print(json_dumps(registry.endpoint_families(), indent=2, sort_keys=True))
            return 0
        if args.providers_command == "adapter-schema":
            print(
                json_dumps(
                    {
                        "contract_version": "1.0",
                        "schema": "schemas/aiplane-adapter-v1.schema.json",
                        "fixture": "tests/fixtures/adapter-v1.json",
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0
        if args.providers_command == "adapter-validate":
            result = validate_result_file(args.path)
            print(json_dumps({"valid": True, "result": result.to_dict()}, indent=2, sort_keys=True))
            return 0
        if args.providers_command == "models":
            result = registry.models(args.name, query=args.query, limit=args.limit, online=args.online)
            print(json_dumps(result.__dict__, indent=2, sort_keys=True))
            return 0
        if args.providers_command == "enable":
            result = registry.set_all_enabled(True) if args.name == "all" else registry.set_enabled(args.name, True)
            print(json_dumps(result, indent=2))
            return 0
        if args.providers_command == "disable":
            result = registry.set_all_enabled(False) if args.name == "all" else registry.set_enabled(args.name, False)
            print(json_dumps(result, indent=2))
            return 0
        if args.providers_command == "remove":
            print(json_dumps(registry.remove(args.name), indent=2))
            return 0
        if args.providers_command == "add":
            print(
                json_dumps(
                    registry.add(
                        args.name,
                        description=args.description,
                        typical_runtimes=args.runtime,
                        catalog_adapter=args.catalog_adapter,
                        enabled=not args.disabled,
                        ownership=args.ownership,
                        endpoint_family=args.endpoint_family,
                        endpoint=args.endpoint,
                        credential_ref=args.credential_ref,
                        api_key_env=args.api_key_env,
                        auth_method=args.auth_method,
                        requires_credentials=args.requires_credentials,
                    ),
                    indent=2,
                )
            )
            return 0
        if args.providers_command == "init-defaults":
            print(json_dumps(registry.init_defaults(overwrite=args.overwrite), indent=2))
            return 0
        if args.providers_command == "update-defaults":
            print(json_dumps(registry.update_defaults(), indent=2, sort_keys=True))
            return 0
        if args.providers_command == "clear":
            print(json_dumps(registry.clear_config(args.scope), indent=2))
            return 0
        if args.providers_command == "test":
            payload = registry.test_connection(args.name, credential_ref=args.credential_ref, timeout=args.timeout)
            print(json_dumps(payload, indent=2, sort_keys=True))
            return 0 if payload.get("ok") else 2
        print(
            json_dumps(
                [status.__dict__ for status in registry.doctor(args.name)],
                indent=2,
                sort_keys=True,
            )
        )
        return 0

    return None
