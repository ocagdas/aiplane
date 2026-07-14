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

Core config is declarative YAML. Profiles, providers, models, machines, stacks, and policy files can be committed and reviewed like any other environment contract. Secrets stay in ignored local files or environment variables while profile structure stays explicit and diff-friendly.

`aiplane` exposes a practical command API that is easy to automate. Commands support both human-readable output and machine-readable output (`--format json`) for CI/CD and external DevOps hooks, so you can keep setup and checks in existing pipelines.

A core goal is avoiding lock-in to one provider stack. With aiplane, teams can shift between managed endpoints, self-hosted runtimes, remote workstations, and mixed stacks using the same profile model. This is useful when teams want to optimise cost, move to regions with required data controls, or go fully on-prem as operational needs change.

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

Because the installer is sourced, it activates the `aiplane` Conda environment
in the current shell after installation. Conda is the recommended flow here;
local Python, `venv`, Docker CLI images, and static installs are also supported.
Static installs include the shipped templates and runtime helper scripts.
Use `scripts/setup_env.sh --help` for those modes.

After installation, create the editable `profiles/local-dev/` profile used by
the CLI. It contains the local hardware, provider, model, runtime, tool, policy,
and environment configuration. This safe first-run form keeps an existing
profile, detects local hardware, validates the profile, and skips provider model
catalog queries:

```bash
aiplane profiles bootstrap-local --no-overwrite --no-discovery
```

To run that same command directly from a repository checkout without installing
the package, expose the `src/` directory to Python explicitly:

```bash
PYTHONPATH=src python -m aiplane profiles bootstrap-local --no-overwrite --no-discovery
```

Local CLI preferences are separate and optional. The following creates the
ignored `.aiplane/config.yaml`, where you can set the default profile, output
format, verbosity, and custom paths; it does not create a profile or discover
hardware or models:

```bash
aiplane config init --template local
aiplane config show
```

## Core onboarding flow

Use this when you want the first useful flow with minimal complexity:

```bash
aiplane discover
aiplane doctor
aiplane recommend
aiplane export
```

The single-command equivalent is:

```bash
aiplane quickstart local-coding
aiplane quickstart local-coding --dry-run
aiplane quickstart local-coding --dry-run --pull-model MODEL_ALIAS
aiplane quickstart local-coding --pull-model MODEL_ALIAS
```

This path is designed to detect local hardware, runtimes, model catalog state,
endpoint setup status, and role mappings, report configuration sources (detected, built-in, provider-discovered cache, profile-configured, and unresolved records), and then print the next concrete export commands. Doctor findings include severity, impact, remediation command metadata, mutability, and dry-run support where action is needed.

Command categories are explicit in [command coverage](docs/project/command-coverage.md): core commands lead onboarding, supporting commands troubleshoot specific subsystems, and deferred commands stay out of the public beta path unless a scope review moves them.

### Extended common workflow
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
# Full format, lint, and test gate
scripts/check.sh

# Fast format, lint, contract, and smoke checks
scripts/check.sh quick
```

Run the scripts from an environment where the project development dependencies
are installed, such as the activated Conda environment or `venv`. The scripts
use that environment's `python` executable. The full gate uses four file-scheduled pytest workers by default; set `AIPLANE_TEST_WORKERS=0` for serial execution or choose another worker count. If you do not want to activate a
Conda environment first, you can select it explicitly with
`conda run --no-capture-output -n aiplane scripts/check.sh`. Use
`scripts/format.sh check` to check formatting only, or `scripts/format.sh fix`
to apply formatting fixes.

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
