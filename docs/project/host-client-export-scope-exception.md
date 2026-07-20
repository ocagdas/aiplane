# P0 Scope Exception: Host-Client Model Exports

Status: approved for implementation and public-demo promotion on 2026-07-19.

## External-user blocker

An evaluator could discover a hardware-suitable model and see its provider-native id, but could not reliably translate the reviewed Aiplane alias into Codex, GitHub Copilot CLI, or Copilot-in-VS-Code configuration. Generic OpenAI-compatible output does not express each host's API, authentication, model-capability, or user-config rules, which made the install-to-agent demo incomplete and encouraged error-prone manual mapping.

## Public promise

Aiplane deterministically plans, prepares, and prints configuration for `codex`, `copilot-cli`, and `copilot-vscode`. Exports show both the Aiplane alias and native model id, retain secrets as environment-variable references, and support reviewed local or managed endpoints when the host's API contract is compatible. They do not install or launch a client, edit client-owned files, copy credentials, or transfer ChatGPT/GitHub subscription entitlements.

Affected commands:

```bash
aiplane integrations plan TARGET --model MODEL_ALIAS
aiplane integrations setup TARGET --model MODEL_ALIAS --dry-run
aiplane integrations export TARGET --model MODEL_ALIAS
aiplane export TARGET --model MODEL_ALIAS
```

Copilot CLI additionally supports `--format json|posix|powershell` and `--offline`; host-client exports accept `--api-type responses|chat-completions|messages` when an endpoint needs an explicit reviewed override.

## Costs and controls

- Security: raw secret values never enter plans or exports; JSON carries `environment_refs`, while VS Code instructs users to enter managed keys through its model-management UI.
- Platform: JSON is canonical and shell-neutral; POSIX and PowerShell are golden-tested renderings of the same payload.
- Compatibility: Codex custom providers require Responses; Copilot CLI requires tool calling and streaming and uses Chat Completions for OpenAI-compatible endpoints; VS Code uses its Custom Endpoint schema.
- Maintenance: upstream client schemas are version-sensitive, so each target has a Tier-1 v1 golden plus release-smoke ownership.
- Documentation: README, public demo, integration guide, roadmap, command coverage, help, and handoff move together.

## Success and removal criteria

Success requires deterministic golden output, Linux/Windows shell coverage, secret-regression coverage, current-client smoke checks against local Ollama and one authenticated Responses-compatible gateway, and an independent user completing the revised demo without manually translating alias to model id.

Demote a target from Tier-1 and remove it from the primary demo if its upstream client removes the documented BYOK/configuration surface, if the output cannot be validated on supported platforms, or if release smoke ownership cannot be maintained. The feature remains print-only unless a separate reviewed exception authorizes client-file mutation or launching.
