# Public Launch Review

This is the release-readiness checklist for the initial public version and later public updates.

## Scope

`aiplane` should present itself first as an environment doctor and configuration compiler for reproducible local and hybrid AI development environments. It should not claim to be a coding agent, model runtime, model proxy, marketplace, or production LLM gateway.

## Terminology

Use these terms consistently:

- **Provider / model source / catalog**: where model ids, files, or deployments come from. Examples: Ollama library, Hugging Face Hub, GGUF files, OpenAI, Anthropic, Azure OpenAI.
- **Runtime**: software that loads model weights or serves inference. Examples: Ollama, vLLM, TGI, llama.cpp server, LocalAI, Transformers, LM Studio.
- **Runtime endpoint**: the URL exposed by a runtime, often OpenAI-compatible `/v1`.
- **Model**: a profile-approved alias mapped to a source-native model id or deployment plus metadata.
- **Profile**: editable YAML configuration for one workflow or machine context.
- **Machine**: normalized hardware/OS/runtime capacity description.
- **Stack**: operational binding of machine, runtime, primary model, optional orchestrator, and access policy.
- **Target**: deployment/access target such as Azure VM, AKS, Docker host, or SSH tunnel plan.
- **Integration export**: generated config text for an IDE/CLI. It does not edit the target tool.
- **MCP adapter**: stdio tool surface for structured `aiplane` inspection and guarded mutations.
- **Doctor**: readiness check for profiles, tools, providers, runtimes, models, machines, or stacks.

## Public Quality Gate

Before calling a public release or beta ready, the visible project state should be internally consistent: code behavior, README claims, user docs, roadmap status, command coverage, session handoff, examples, and tests should describe the same product. New features should have focused tests or an explicit documented reason they are smoke-only, and broad future work should stay in roadmap sections rather than being implied as current capability.

## Pre-Release Checks

- Run `aiplane environment doctor` and confirm the setup summary is understandable; text is the default output and `--format json` is only for machine-readable checks.
- Run `aiplane profiles validate local-dev`.
- Run representative smoke commands for profiles, providers, runtimes, integrations, and stacks.
- Run the full test suite.
- Confirm `.aiplane/`, logs, PID files, caches, editor swap files, and generated runtime state are ignored or absent.
- Confirm `pyproject.toml` has a public-safe description, readme, license, build backend, package discovery, and a version matching the proposed `vVERSION` tag.
- Build the wheel and source distribution, then run `python scripts/verify_install_channels.py dist` before publishing artifacts.
- Confirm normal CI validates wheel lifecycles through `pip`, `pipx`, and `uv tool` on Linux, macOS, and Windows.
- Confirm `.aiplane/` and generated model caches are not tracked.
- Confirm `docs/user/tools.md` maps each external tool to the workflows it enables.
- Confirm `docs/project/agent-guidance.md` and tool-specific instruction files point to the current project guidance.
- Scan README and user docs for stale command examples and terminology drift.

## Known Public-Launch Caveats

- The project is developer-preview, pre-1.0 alpha quality and should be marked that way.
- Broad cloud and Kubernetes apply paths remain guarded or planned.
- Runtime helpers delegate to native runtimes and official CLIs where possible; deep runtime tuning remains runtime-native.
- MCP write tools must remain narrow, audited, and guarded.
