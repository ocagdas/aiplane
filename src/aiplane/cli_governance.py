from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Callable

from .audit import AuditLogger
from .config import load_profile
from .mcp import mcp_manifest, serve_stdio
from .models import AuditEvent
from .policy import PolicyEngine
from .secrets import CredentialStore


def add_governance_parsers(
    subparsers: Any,
    *,
    command_factory: Callable[..., argparse.ArgumentParser],
    profile_arg: Callable[[argparse.ArgumentParser], None],
    formatter_class: type[argparse.HelpFormatter],
) -> None:
    credentials_cmd = command_factory(
        subparsers,
        "credentials",
        "Inspect ignored local credential references",
        "List or show redacted credential accounts from the ignored local credentials file. This never prints raw secrets.",
        "Examples:\n  aiplane credentials list\n  aiplane credentials show openai.personal",
    )
    credentials_sub = credentials_cmd.add_subparsers(dest="credentials_command", required=True, metavar="command")
    credentials_list = credentials_sub.add_parser(
        "list",
        help="List configured credential refs",
        description="List credential account names and metadata without secret values.",
        formatter_class=formatter_class,
    )
    credentials_list.add_argument(
        "--path",
        help="Optional credentials YAML path. Defaults to AIPLANE_CREDENTIALS, local config credentials_path, or .aiplane/credentials.yaml",
    )
    credentials_show = credentials_sub.add_parser(
        "show",
        help="Show one credential ref with secrets redacted",
        description="Show one credential account without printing raw secret values.",
        formatter_class=formatter_class,
    )
    credentials_show.add_argument("ref", help="Credential ref, such as openai.personal or openai/personal")
    credentials_show.add_argument("--path", help="Optional credentials YAML path")

    mcp_cmd = command_factory(
        subparsers,
        "mcp",
        "Expose MCP tools over stdio",
        "Run or inspect the MCP adapter so IDEs/agents can query aiplane configuration and use guarded write tools.",
        "Examples:\n  aiplane mcp manifest\n  aiplane mcp serve",
    )
    mcp_sub = mcp_cmd.add_subparsers(dest="mcp_command", required=True, metavar="command")
    mcp_sub.add_parser(
        "manifest",
        help="Print MCP tool manifest",
        description="Print the MCP tool surface as JSON, including guarded mutating tools.",
        formatter_class=formatter_class,
    )
    mcp_serve = mcp_sub.add_parser(
        "serve",
        help="Start stdio MCP server",
        description="Start the MCP server over stdio for MCP-capable IDEs or agents. It is read-only by default; --allow-writes enables guarded mutations that also require confirm=true per call.",
        formatter_class=formatter_class,
    )
    profile_arg(mcp_serve)
    mcp_serve.add_argument(
        "--allow-writes",
        action="store_true",
        help="Operator opt-in for mutating MCP tools; every mutating call must also pass confirm=true",
    )

    audit = command_factory(
        subparsers,
        "audit",
        "Read local audit logs",
        "Inspect JSONL audit events written under the workspace .aiplane directory.",
        "Example:\n  aiplane audit tail --limit 50",
    )
    audit_sub = audit.add_subparsers(dest="audit_command", required=True, metavar="command")
    tail = audit_sub.add_parser(
        "tail",
        help="Show recent audit events",
        description="Print the last N valid audit events as JSON lines. Malformed records are skipped with metadata-only warnings on stderr.",
        formatter_class=formatter_class,
    )
    profile_arg(tail)
    tail.add_argument("--limit", type=int, default=20, help="Number of events to print")

    policy = command_factory(
        subparsers,
        "policy",
        "Explain policy decisions",
        "Explain how the active profile treats a named action.",
        "Example:\n  aiplane policy explain --action cloud_escalation",
    )
    policy_sub = policy.add_subparsers(dest="policy_command", required=True, metavar="command")
    explain = policy_sub.add_parser(
        "explain",
        help="Explain one action",
        description="Print policy decision details for an action name.",
        formatter_class=formatter_class,
    )
    profile_arg(explain)
    explain.add_argument(
        "--action",
        required=True,
        help="Action name to explain, such as backend:cloud, provider:ollama, model:fixture-chat-small, or write_file",
    )

    policy_list = policy_sub.add_parser(
        "list",
        help="List local temporary approvals and overrides",
        description="List ignored workspace-local policy grants without changing repository policy.",
        formatter_class=formatter_class,
    )
    profile_arg(policy_list)
    policy_list.add_argument("--active-only", action="store_true", help="Hide expired grants")

    grant = policy_sub.add_parser(
        "grant",
        help="Create an expiring local approval or override",
        description="Create an ignored workspace-local policy grant. Approval-required actions become temporary approvals; blocked actions require --override. This never edits profile policy.",
        formatter_class=formatter_class,
    )
    profile_arg(grant)
    grant.add_argument("--action", required=True, help="Canonical action such as tool:write_file or provider:openai")
    grant.add_argument("--reason", required=True, help="Non-secret operator reason recorded in audit")
    grant.add_argument("--expires-in", required=True, help="Positive duration such as 30m, 8h, or 7d")
    grant.add_argument("--override", action="store_true", help="Allow an otherwise blocked action until expiry")
    grant.add_argument("--yes", action="store_true", help="Confirm creation of the local policy grant")

    revoke = policy_sub.add_parser(
        "revoke",
        help="Revoke one local policy grant",
        description="Remove one ignored workspace-local grant by id and record the action in the audit log.",
        formatter_class=formatter_class,
    )
    profile_arg(revoke)
    revoke.add_argument("grant_id", help="Grant id from policy list")
    revoke.add_argument("--yes", action="store_true", help="Confirm revocation")

    drift = policy_sub.add_parser(
        "drift",
        help="Report expired or stale local grants",
        description="Compare local grants with current profile policy without changing either.",
        formatter_class=formatter_class,
    )
    profile_arg(drift)


def handle_governance_command(
    args: argparse.Namespace,
    *,
    workspace: Path,
    profiles_dir: Path | None,
    effective_profile: str,
    json_dumps: Callable[..., str],
) -> int | None:
    if args.command == "credentials":
        store = CredentialStore(args.path)
        payload = store.list() if args.credentials_command == "list" else store.show(args.ref)
        print(json_dumps(payload, indent=2, sort_keys=True))
        return 0
    if args.command == "mcp":
        if args.mcp_command == "manifest":
            print(json_dumps(mcp_manifest(), indent=2))
            return 0
        load_profile(effective_profile, workspace, profiles_dir=profiles_dir)
        return serve_stdio(
            workspace,
            default_profile=effective_profile,
            profiles_dir=profiles_dir,
            allow_writes=args.allow_writes,
        )
    if args.command == "audit":
        profile = load_profile(effective_profile, workspace, profiles_dir=profiles_dir)
        report = AuditLogger(profile).tail_report(args.limit)
        for warning in report.warnings:
            print(
                f"warning: skipped audit {warning['kind']} at line {warning['line']}",
                file=sys.stderr,
            )
        if report.malformed_records > len(report.warnings):
            print(
                f"warning: skipped {report.malformed_records - len(report.warnings)} additional malformed audit records",
                file=sys.stderr,
            )
        for event in report.events:
            print(json_dumps(event, sort_keys=True))
        return 0
    if args.command == "policy":
        profile = load_profile(effective_profile, workspace, profiles_dir=profiles_dir)
        engine = PolicyEngine(profile)
        if args.policy_command == "explain":
            decision = engine.explain(args.action)
            print(json_dumps(decision.__dict__, indent=2, sort_keys=True))
            return 0
        if args.policy_command == "list":
            payload = {
                "schema_version": "1.0",
                "profile": profile.name,
                "grants": engine.grants.list(include_expired=not args.active_only),
            }
            print(json_dumps(payload, indent=2, sort_keys=True))
            return 0
        if args.policy_command == "drift":
            print(json_dumps(engine.drift(), indent=2, sort_keys=True))
            return 0
        if not args.yes:
            raise ValueError(f"policy {args.policy_command} requires --yes")
        audit = AuditLogger(profile)
        if args.policy_command == "grant":
            base = engine.explain_base(args.action)
            if args.override:
                if base.allowed:
                    raise ValueError("policy override requires an action currently blocked by profile policy")
                kind = "override"
            else:
                if not (base.allowed and base.requires_approval):
                    raise ValueError(
                        "temporary approval requires an action currently marked approval_required; use --override only for blocked actions"
                    )
                kind = "temporary_approval"
            record = engine.grants.grant(args.action, kind=kind, reason=args.reason, duration=args.expires_in)
            audit.record(
                AuditEvent(
                    "policy_grant",
                    profile.name,
                    args.action,
                    "granted",
                    {"id": record["id"], "kind": kind, "expires_at": record["expires_at"], "reason": args.reason},
                )
            )
            print(
                json_dumps(
                    {"schema_version": "1.0", "profile": profile.name, "grant": record}, indent=2, sort_keys=True
                )
            )
            return 0
        record = engine.grants.revoke(args.grant_id)
        audit.record(
            AuditEvent(
                "policy_revoke",
                profile.name,
                str(record["action"]),
                "revoked",
                {"id": record["id"], "kind": record["kind"]},
            )
        )
        print(
            json_dumps({"schema_version": "1.0", "profile": profile.name, "revoked": record}, indent=2, sort_keys=True)
        )
        return 0
    return None
