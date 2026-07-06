# aiplane

`aiplane` is a control-plane CLI for AI model environments across text, image, audio, video, and reasoning workflows.
It helps teams make local, remote, and cloud-adjacent AI workflows reproducible by organizing the non-model part of AI operations:

- providers and provider credentials references,
- runtime and endpoint selection,
- machine/hardware fit,
- policy constraints,
- model catalogs and aliases,
- IDE/agent/automation exports, and
- run-time readiness checks.

It is not a coding agent, chat UI, inference server, model marketplace, or cloud platform. It sits one layer lower:
it coordinates models, runtimes, and tooling so human operators can keep AI environments understandable and auditable.
The aim is to treat AI environment setup and workflow operations like AIOps for AI operations: taking care of setup, replication, migration, and model/runtime alignment so teams can spend time on model work and experimentation instead.

## Why this exists

Most teams discover that “working AI setup” becomes a pile of one-off shell commands, hidden assumptions, and environment drift:

- one model works locally, another in a remote VM,
- one assistant needs one endpoint format, another needs another,
- local and managed providers require different credentials and auth paths,
- hardware constraints (`RAM`, `VRAM`, GPU type) get implicit and untracked,
- and repeatability depends on tribal knowledge.

`aiplane` reduces this by making setup, checks, and exports profile-first and explicit.

## What `aiplane` is (today)

Current branch focus: **early beta / pre-1.0**, with core value around reproducible AI workflow setup.

### In place now

- Profile loading, validation, config inheritance, and profile selection for local and non-local contexts.
- Provider catalogs for managed and self-managed sources.
- Ignored model discovery cache (`models.discovered.yaml`) and explicit profile-owned model entries in `models.yaml`.
- Provider/model discovery, filtering, and model import paths with RAM/VRAM/capability metadata and provider/source/runtimes separation.
- Runtime helper orchestration for supported self-managed runtimes (with dry-run first-class behavior).
- Hardware discovery, machine imports, and hardware-aware recommendations.
- Stack planning and setup workflows (including role model mapping and policy-aware checks).
- Integration exports for Continue, Cline, Zed, Aider, OpenAI-compatible clients, MCP clients.
- MCP read tooling and narrow audited write tooling.
- External tooling readiness checks (`tools doctor/matrix`, `environment doctor`) for provisioning and benchmark workflows.
- Policy and audit foundations for explicitness in cloud escalation and managed endpoint use.
- Smoke-test command scaffolding and benchmark planning.

### Not in scope yet

- it is not a full coding agent,
- it is not an inference engine,
- it is not a hidden production orchestrator,
- it does not run arbitrary shell actions through MCP,
- and it does not promise turnkey enterprise cloud deployment.

## Install

Fresh Conda install:

```bash
# from a clone
git clone https://github.com/ocagdas/aiplane.git
cd aiplane
source scripts/setup_env.sh --mode conda --conda-env aiplane --action install --editable

aiplane profiles list
aiplane environment doctor --required-only
```

Alternative flows are supported for local Python, venv, Docker CLI images, and static installs; use `scripts/setup_env.sh --help` for supported modes.

If you already have the package installed:

```bash
PYTHONPATH=src python -m aiplane profiles bootstrap-local --no-discovery
```

When you want per-machine local defaults:

```bash
aiplane config init --template local
aiplane config show
```

## Quick start flow

Use this when you want to evaluate the project end-to-end:

```bash
aiplane quickstart local-coding
# preview only

aiplane quickstart local-coding --dry-run
# add a model pull only when you choose one alias
aiplane quickstart local-coding --pull-model MODEL_ALIAS

aiplane doctor
aiplane doctor --format json

aiplane profiles show --selected
```

`quickstart local-coding` builds a local profile baseline, runs a readiness doctor when possible, and prints the next deterministic commands.
Model pulls remain opt-in and can always be previewed with `--dry-run`.

### Common workflow

```bash
# 1) discover candidates

aiplane providers list
aiplane models refresh --provider huggingface --query text-generation --dry-run

aiplane models list --group-by ownership --enabled-only

# 2) stage runnable setup (explicitly)
aiplane runtimes install ollama --dry-run
aiplane integrations roles continue

aiplane runtimes pull ollama --model MODEL_ALIAS --dry-run

# 3) export and run
aiplane integrations export continue --model MODEL_ALIAS
aiplane integrations export vscode-mcp
aiplane chat --model MODEL_ALIAS --dry-run
```

## Execution tracks

The current project direction is organized into three execution tracks:

1. **Agentic environments and workflows**
   - profile-driven endpoints,
   - policy-aware role bindings,
   - starter project scaffolds (non-mutating export path first).

2. **Provisioning and automation tooling**
   - clear tool readiness checks,
   - non-mutating plans/exports for Vagrant, Packer, OpenTofu/Terraform, Pulumi, Ansible, Docker/Compose, dev containers, and Kubernetes tooling,
   - explicit guardrails before applying remote changes.

3. **Benchmark and evaluation workflow integration**
   - smoke/custom checks,
   - benchmark tool install/check/plan helpers,
   - explicit placement of benchmark execution (local host, remote endpoint, same host as runtime).

See [Roadmap](docs/project/roadmap.md) for concrete implementation status.

## Safety, governance, and trust model

- credentials and local machine state are intentionally outside git in ignored files,
- secrets are redacted by command output tooling,
- plans/doctor/install previews come before mutation,
- MCP mutations are narrow and audited,
- and policy checks are surfaced before escalation is allowed.

Security reporting is documented in [SECURITY.md](SECURITY.md).

## Helper scripts

- `scripts/setup_env.sh`: bootstrap paths for local execution modes and environment setup.
- `scripts/provider_helper.sh`: thin runtime operation dispatcher used by the CLI.
- `aiplane environment plan`: renders how a command would run under current profile context.
- `aiplane environment doctor` and `aiplane tools doctor`: first checks when setup quality looks off.

More command detail in:
- [setup](docs/user/setup.md)
- [providers and runtime helpers](docs/user/providers.md)
- [tools and provisioning](docs/user/tools.md)
- [runtime map](docs/user/runtime-model-map.md)

## Validation expectations

Before relying on a branch for demos or review, run:

```bash
conda run -n aiplane scripts/check.sh
# and a representative smoke set for your area
PYTHONPATH=src python -m pytest tests/test_* -k "smoke or critical"
```

Use [command coverage](docs/project/command-coverage.md), [strategy](docs/project/strategy.md), and [session handoff](docs/project/session-handoff.md) to keep behavior, docs, and tests synchronized.

## Documentation

- [User docs](docs/user/index.md)
- [Security policy](SECURITY.md)
- [Contributing](CONTRIBUTING.md)
- [Code of conduct](CODE_OF_CONDUCT.md)
- [Setup](docs/user/setup.md)
- [Providers and credentials](docs/user/providers.md)
- [Tools and provisioning](docs/user/tools.md)
- [Integrations](docs/user/integrations.md)
- [Machines and stacks](docs/user/machines-and-stacks.md)
- [Benchmarks](docs/user/benchmarks.md)
- [MCP](docs/user/mcp.md)
- [aiplane skill](skills/aiplane/SKILL.md)
- [Roadmap](docs/project/roadmap.md)
- [Project handoff](docs/project/session-handoff.md)

## Contributing

We want practical contributions from teams that run local models, remote GPUs, or AI workflows that span local + managed services.
Good first areas:

- improve provider/runtime checks,
- harden guardrails and policy behavior,
- improve reproducible setup flows,
- improve benchmark and evaluation ergonomics,
- and tighten docs where commands or terminology still create ambiguity.

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT. See [LICENSE](LICENSE).
