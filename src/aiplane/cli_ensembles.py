from __future__ import annotations

from pathlib import Path

from .config import dump_yaml, load_profile, resolve_profile_name
from .ensembles import doctor_ensemble, ensemble_template, load_ensemble, plan_ensemble, resolve_role
from .harness_catalog import harness_catalog, harness_record


def add_ensemble_parsers(subparsers, *, command_factory, profile_arg, formatter_class):
    harnesses = command_factory(
        subparsers,
        "harnesses",
        "Inspect harness/model compatibility",
        "Inspect a curated, documentation-backed harness catalog. No live discovery or execution.",
    )
    children = harnesses.add_subparsers(dest="harnesses_command", required=True)
    children.add_parser("list", formatter_class=formatter_class, allow_abbrev=False)
    show = children.add_parser("show", formatter_class=formatter_class, allow_abbrev=False)
    show.add_argument("harness")
    models = children.add_parser("models", formatter_class=formatter_class, allow_abbrev=False)
    models.add_argument("harness")
    models.add_argument("--surface", required=True)
    models.add_argument("--auth", choices=["provider_env", "none"], default="provider_env")
    profile_arg(models)
    ensembles = command_factory(
        subparsers,
        "ensembles",
        "Plan and export role-based ensembles",
        "Compile an offline, neutral handoff manifest. An external runner must implement collaboration and qualify runtime support.",
    )
    children = ensembles.add_subparsers(dest="ensembles_command", required=True)
    children.add_parser("template", formatter_class=formatter_class, allow_abbrev=False)
    for action in ("plan", "doctor", "export"):
        command = children.add_parser(action, formatter_class=formatter_class, allow_abbrev=False)
        command.add_argument("spec", type=Path, help="Standalone restricted YAML or JSON ensemble specification")
        profile_arg(command)


def handle_ensemble_command(args, *, workspace, profiles_dir, json_dumps):
    if args.command not in {"harnesses", "ensembles"}:
        return None
    if args.command == "harnesses" and args.harnesses_command in {"list", "show"}:
        payload = harness_catalog() if args.harnesses_command == "list" else harness_record(args.harness)
    elif args.command == "ensembles" and args.ensembles_command == "template":
        print(dump_yaml(ensemble_template()), end="")
        return 0
    else:
        name = resolve_profile_name(getattr(args, "profile", None), profiles_dir=profiles_dir)
        profile = load_profile(name, workspace, profiles_dir=profiles_dir)
        if args.command == "harnesses":
            harness_record(args.harness)
            rows = []
            for alias in sorted(profile.models.get("models", {}) or {}):
                try:
                    role = resolve_role(
                        "candidate",
                        {"harness": args.harness, "surface": args.surface, "model_alias": alias, "auth": args.auth},
                        profile,
                    )
                    rows.append({"alias": alias, "compatibility": role["compatibility"], "policy": role["policy"]})
                except ValueError:
                    rows.append(
                        {
                            "alias": alias,
                            "compatibility": {
                                "status": "unresolved",
                                "reason": "Binding requires corrected model/provider/auth configuration; use ensembles plan for validation.",
                            },
                        }
                    )
            payload = {
                "harness": args.harness,
                "surface": args.surface,
                "auth": args.auth,
                "models": rows,
                "scope": "reviewed profile aliases; account availability is not checked",
            }
        else:
            payload = plan_ensemble(load_ensemble(args.spec), profile)
            if args.ensembles_command == "doctor":
                payload = doctor_ensemble(payload, profile)
            if args.ensembles_command == "export" and payload["configuration_status"] == "blocked":
                raise ValueError(
                    "ensemble export blocked by policy or unsupported harness binding; inspect ensembles plan"
                )
    print(json_dumps(payload, indent=2, sort_keys=True))
    if args.command == "ensembles" and args.ensembles_command != "template":
        if payload["configuration_status"] == "blocked":
            return 1
        if args.ensembles_command == "doctor":
            return 2
    return 0
