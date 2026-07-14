# Practical Threat Model

This document describes the security boundary of the unreleased `aiplane` developer preview. `aiplane` is an environment doctor and configuration compiler, not a sandbox, secret manager, network security boundary, or privilege broker.

## Trust boundary and assets

The local OS account, checked-out repository, operator-selected profiles, and external tools explicitly invoked by the operator are trusted. Profiles are data rather than executable plug-ins, but their paths, endpoints, provider references, remote hosts, and helper selections affect later explicit operations. Validate and render an unfamiliar profile before connecting or mutating:

```bash
aiplane profiles validate <profile>
aiplane profiles render <profile>
```

Assets in scope include credentials and references, private endpoint and host metadata, generated configuration, local files, audit records, runtime state, remote tunnel ownership, and delegated command integrity.

## Threats, controls, evidence, and limits

| Area | Threat and implemented control | Test evidence | Explicit residual limitation |
| --- | --- | --- | --- |
| Credential references | Profiles use named credentials and exports use environment-variable placeholders where supported. Credential display redacts stored secrets. | `tests/test_governance_cli.py::GovernanceCliTests::test_credentials_cli_lists_and_redacts_local_accounts`; `tests/test_integrations_chat.py::IntegrationTests::test_integrations_export_uses_named_credential_ref` | The ignored credentials file and process environment remain readable according to OS permissions. `aiplane` does not encrypt, rotate, or centrally govern credentials. |
| Redaction and errors | Structured sensitive keys, common token forms, command flags, PEM material, CLI failures, and MCP failures are sanitized before normal output or audit storage. | `tests/test_secret_redaction.py`; `tests/test_cli_error_boundary.py` | Redaction is pattern-based, not data-loss prevention. Unknown secret formats or secrets in ordinary fields can escape detection. `--debug` intentionally exposes exception detail. |
| Generated configuration | Tier-1 exports are deterministic and emit credential environment-variable names instead of resolved keys. Output is inspectable before saving. | `tests/test_integrations_chat.py::IntegrationTests::test_integrations_export_uses_named_credential_ref`; `tests/test_integrations_chat.py::IntegrationTests::test_tier1_exports_match_versioned_golden_files` | Exports and caches can reveal model names, paths, private hostnames, endpoints, account aliases, or deployment metadata. Review before committing or sharing. |
| Shell and installer helpers | Python boundaries use argument vectors and injectable runners; network/SSH inputs are validated. Destructive runtime operations require confirmation and unsupported platform helpers fail closed. | `tests/test_network_validation.py`; `tests/test_runtimes_execution.py::RuntimeExecutionTests::test_runtime_remove_and_clear_require_confirmation`; `tests/test_runtimes_execution.py::RuntimeExecutionTests::test_runtime_install_helper_rejects_non_linux_platforms` | Helpers delegate to installed CLIs and some vendor installers. Those programs, downloaded scripts, package repositories, and `PATH` are supply-chain boundaries; `aiplane` does not sandbox them. Review plans and use `--dry-run`. |
| MCP adapter | MCP is read-only by default. Mutation requires both server `--allow-writes` and per-call `confirm: true`; dry-run planning remains read-only. Failures are sanitized and decisions audited. | `tests/test_mcp_guards.py`; `tests/test_secret_redaction.py::test_mcp_error_response_and_failed_audit_do_not_expose_exception_text` | A client can retain data returned by read tools. Guards do not make the client trustworthy; broad shell execution, credential writes, and broad cloud apply are intentionally absent. |
| Tunnel ownership | A live process must match the identity captured at tunnel start before signalling. Reused PIDs are not signalled, invalid state fails closed, and unsupported platforms expose planning only. | `tests/test_remote_state.py`; `tests/test_network_validation.py::test_tunnel_plan_rejects_option_like_host_before_building_command` | OpenSSH owns host-key verification, authentication, encryption, and remote authorization. Local forwarding adds no application authentication. |
| Profile trust | Schema v1, structural validation, deterministic rendering, endpoint checks, workspace boundaries, and policy checks make profile effects inspectable. | `tests/test_profile_schema.py`; `tests/test_network_validation.py`; `tests/test_governance_cli.py::GovernanceCliTests::test_workspace_boundary_blocks_parent_escape` | Profiles are not signed. An untrusted profile can direct later explicit operations toward attacker-controlled but syntactically valid endpoints or paths. Review it like code. |
| Audit sensitivity | Audit details are redacted; tool records minimize arguments and omit command output. Locked persistence is used and readers tolerate malformed records without echoing content. | `tests/test_secret_redaction.py::test_tool_audit_redacts_arguments_and_does_not_store_command_output`; `tests/test_audit_recovery.py`; `tests/test_persistence.py` | Audit JSONL contains operational metadata. `.aiplane/audit/` is ignored by git, but is not encrypted, tamper-evident, or a centralized compliance log. Protect it with OS controls. |

## Safe operating practice

- Keep secrets in ignored local storage or environment variables and only references in tracked profiles.
- Prefer validation, doctor, planning, export, or `--dry-run` before mutation.
- Review generated files and logs before committing, attaching, or sharing.
- Enable MCP writes only for a trusted client and only when required.
- Review helper commands and upstream installation sources.
- Report vulnerabilities through the private process in [`SECURITY.md`](../../SECURITY.md).

A new security claim must cite deterministic regression evidence or be stated as an explicit limitation.
