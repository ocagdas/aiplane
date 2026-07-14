# User Documentation

These docs are split by user maturity. Start with the first workflow, then move into common recipes, then advanced concepts only when you need to customize providers, runtimes, machines, stacks, policy, or MCP.

## Start here

Use this path for first onboarding. It avoids advanced concepts and keeps every command inspect-first.

1. [Install](setup.md)
   Mutates state: yes, only when you run installer commands without `--dry-run`.
   Verifiable outcome: `aiplane --help` and `aiplane profiles list` run successfully.
2. [Quickstart](overview.md#core-onboarding-flow)
   Mutates state: `aiplane quickstart local-coding --dry-run` is read-only; `aiplane quickstart local-coding` can create or refresh the local profile scaffold but does not install runtimes, edit IDE config, or touch cloud resources.
   Verifiable outcome: the command prints the next `doctor`, `recommend`, and `export` commands.
3. [Doctor](overview.md#ai-workflow-stack-doctor)
   Mutates state: no.
   Verifiable outcome: findings include severity, impact, remediation command metadata, and next commands.
4. [Recommend](hardware.md#hardware-aware-model-recommendations)
   Mutates state: no.
   Verifiable outcome: model rows are grouped into recommended, usable, remote/cloud, or not recommended with rationale.
5. [Export](integrations.md)
   Mutates state: no; exports print configuration snippets and do not edit IDE files.
   Verifiable outcome: Continue, Aider, Cline, Zed, OpenAI-compatible, or MCP config is printed.

Primary workflow:

```bash
aiplane quickstart local-coding --dry-run
aiplane quickstart local-coding
aiplane discover
aiplane doctor
aiplane recommend
aiplane export continue
```

## Common workflows

Use these after the first workflow succeeds.

1. [Local Ollama workflow](workflows.md)
   Mutates state: runtime install/start/pull commands mutate when run without `--dry-run`; discovery, doctor, recommend, and export are read-only.
   Verifiable outcome: `aiplane doctor`, `aiplane recommend`, and `aiplane export continue` produce useful output.
2. [Local vLLM or OpenAI-compatible endpoint workflow](runtime-model-map.md)
   Mutates state: bundle and export commands are read-only; starting a runtime is explicit and helper-backed.
   Verifiable outcome: endpoint config exports with the expected base URL.
3. [Remote GPU workstation workflow](machines-and-stacks.md)
   Mutates state: machine import changes the local profile; remote tunnel start mutates local SSH tunnel state; planning commands are read-only.
   Verifiable outcome: machine profile imports, endpoint/tunnel plan renders, and model recommendations use the remote machine facts.
4. [Managed provider workflow](providers.md)
   Mutates state: provider enable/add commands update profile config; provider tests and exports are read-only.
   Verifiable outcome: provider policy and credentials are explained without printing secrets.
5. [Privacy-restricted repository workflow](overview.md#ai-workflow-stack-doctor)
   Mutates state: policy/profile edits are explicit; doctor and recommend are read-only.
   Verifiable outcome: doctor and recommendation output explain blocked providers, cloud usage, or approval requirements.

## Advanced concepts

Read these when you need to customize the environment model or automate team workflows.

- [Providers and credentials](providers.md): provider/source configuration, endpoint families, managed services, and credential references.
- [Model sources and runtimes](runtime-model-map.md): runtime compatibility, lifecycle helpers, source/runtime mapping, and OpenAI-compatible endpoints.
- [Hardware](hardware.md): CPU/RAM/GPU detection, hardware templates, and fit checks.
- [Machines, stacks, and orchestrators](machines-and-stacks.md): machine inventory, stack planning, remote workstation plans, and orchestrator bindings.
- [Policy, approvals, and audit](overview.md#ai-workflow-stack-doctor): repository policy effects surfaced through doctor, recommend, and policy explain.
- [MCP adapter](mcp.md): structured read/planning access for compatible clients and guarded write surfaces.
- [Benchmarks](benchmarks.md): smoke checks and practical model/runtime evaluation notes.
- [External toolchain](tools.md): prerequisite CLIs for runtime, provisioning, and benchmark workflows.
- [Cloud deployment planning](cloud-deployment.md): guarded planning and checks for Azure targets.
- [Model capabilities](model-capabilities.md): capability scores used by model selection and recommendations.
- [aiplane skill](../../skills/aiplane/SKILL.md): assistant workflow guidance for Codex-style skill-capable agents.

## Main commands

```bash
aiplane discover
aiplane doctor
aiplane recommend
aiplane export continue
aiplane quickstart local-coding
```

Project strategy, developer policy, and future roadmap details live under [docs/project](../project/README.md), not in the user documentation.

## Profile selection

Most commands accept `--profile`, but it is optional. `aiplane` resolves the profile in this order:

1. `--profile <name>` on the command.
2. `AIPLANE_PROFILE` if set.
3. `default_profile` in the local `.aiplane/config.yaml`.
4. The only available profile, when exactly one exists.

If no profile exists, run the onboarding flow directly:

```bash
aiplane quickstart local-coding
aiplane discover
aiplane doctor
aiplane recommend
```

Use `--profile` only when you need to override the default for one command.
