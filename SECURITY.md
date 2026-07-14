# Security Policy

## Supported Versions

`aiplane` is pre-release software and has not yet published a stable public version. Until the first stable release, security fixes are provided for the active `main` branch only.

| Version | Supported |
| ------- | --------- |
| `main` / unreleased pre-release builds | Yes |
| Tagged releases before `1.0.0` | Best effort only |
| Forks or locally modified copies | No |

After stable releases begin, this table will be updated to identify which release lines receive security updates.

## Reporting a Vulnerability

Please do not report security vulnerabilities in public GitHub issues, discussions, demo recordings, or shared logs.

Preferred reporting path:

1. Use GitHub private vulnerability reporting for this repository if it is enabled.
2. If private reporting is not enabled, contact the project maintainer directly and include `aiplane security report` in the subject.

When reporting, include as much of the following as you safely can:

- affected command, file, or workflow;
- the version, commit, or branch tested;
- steps to reproduce the issue;
- expected and actual behavior;
- impact assessment, including whether secrets, credentials, local files, runtime state, cloud resources, or remote hosts can be exposed or modified;
- logs or output with secrets, tokens, account ids, tenant ids, hostnames, and personal data redacted.

Do not include real API keys, tokens, passwords, private keys, cloud credentials, customer data, or private model weights in the report. If a proof of concept needs credentials, describe the required shape using placeholders or environment-variable names.

## What to Expect

For a valid report, maintainers will aim to:

- acknowledge receipt within 3 business days;
- provide an initial triage result within 10 business days;
- keep the reporter updated when the status materially changes;
- coordinate disclosure timing for confirmed vulnerabilities;
- credit the reporter if they want credit and disclosure is appropriate.

If the report is accepted, maintainers will work on a fix, tests, and documentation updates before public disclosure where practical. If the report is declined, maintainers will explain the reason, such as out-of-scope behavior, a duplicate report, unsupported deployment conditions, or insufficient security impact.

## Security Scope

Security-sensitive areas include:

- credential loading, credential references, redaction, and secret detection;
- profile, provider, model, runtime, machine, stack, and local config file handling;
- MCP tool exposure, especially guarded writes and blocked operations;
- helper scripts that install, start, stop, pull, remove, or clear runtime/model state;
- cloud, SSH, Docker, Kubernetes, and deployment planning/apply paths;
- audit logs and command output that might expose sensitive local or account data.

The [practical threat model](docs/project/threat-model.md) maps these areas to current regression evidence and states the residual limitations that operators must account for.

Known intentional boundaries:

- `aiplane` is an environment doctor and configuration compiler, not a production secret manager, model proxy, runtime sandbox, or cloud security product.
- Local credentials belong in ignored local files or environment variables, not in tracked profile templates.
- Broad shell execution, secret writes through MCP, and broad cloud apply are intentionally out of scope unless explicit guardrails are implemented and documented.
