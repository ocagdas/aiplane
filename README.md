# aiplane

AI development setups are difficult to reproduce because model capabilities must fit the intended task, available RAM/VRAM, installed runtimes, endpoints, and development tools. `aiplane` is an environment doctor and configuration compiler: it inventories those facts, diagnoses what is ready or missing (the read-only doctor role), and compiles reviewed profiles into hardware-aware recommendations and deterministic tool configuration.

First outcome: inspect the proposed local setup and receive exact doctor, recommendation, and export steps without changing runtimes, development-tool files, or external services.

```bash
aiplane quickstart local-coding --dry-run
```

Profiles are declarative YAML that can be reviewed like other environment contracts. Secrets remain in ignored local files or environment variables. Human-readable and JSON output support both operators and CI.

`aiplane` is not a coding agent, chat UI, inference server, model marketplace, model proxy, or cloud platform. It configures, checks, plans, and exports the operational layer around those tools.

## Why this exists

Most teams discover that “working AI setup” becomes a pile of one-off shell commands, hidden assumptions, and environment drift:

- one model works on a laptop, another only on a shared GPU workstation,
- one assistant needs one endpoint format, another needs another,
- local runtimes and hosted endpoints use different credentials and connection settings,
- hardware constraints (`RAM`, `VRAM`, GPU type) get implicit and untracked,
- and repeatability depends on tribal knowledge.

`aiplane` reduces this by making setup, checks, and exports profile-first and explicit.

## What `aiplane` does today

Current maturity: **developer preview / pre-1.0 alpha**. The supported public workflow is intentionally narrow:

- create and validate a reviewable environment profile;
- discover local hardware, installed runtimes, configured endpoints, and configuration provenance;
- diagnose readiness problems with impact and remediation;
- recommend reviewed models that fit the selected hardware and policy; and
- export deterministic configuration for existing development tools without editing their files.

The result is an explicit environment contract that can be inspected, compared, and reproduced instead of a collection of machine-specific setup notes.

`aiplane` also retains tested supporting and experimental commands for specialised troubleshooting and planning. They are available to advanced users, but they do not expand the public product promise or block the core workflow. See [command coverage](docs/project/project-plan.md#command-coverage) for their maturity and limitations.

## Install

For evaluation without cloning the repository, download the wheel from the [latest GitHub Release](https://github.com/ocagdas/aiplane/releases/latest), then install it with one of these isolated or environment-specific methods:

```bash
# Recommended isolated application install. Choose one.
uv tool install ./aiplane-0.1.0-py3-none-any.whl
pipx install ./aiplane-0.1.0-py3-none-any.whl

# Or install into the currently active venv or Conda environment.
python -m pip install ./aiplane-0.1.0-py3-none-any.whl
```

Use the filename attached to the release; `0.1.0` is illustrative. All three methods register the `aiplane` command and include the profile/config templates and runtime helper assets. Verify the installed package with `aiplane --version`; it reports the effective version, package metadata version, module version, install type, and module path. See [Setup](docs/user/setup.md#standard-wheel-install-no-repository-clone) for verification, upgrades, uninstallation, index-based commands, Conda usage, and platform limitations.

Contributor and source-checkout installs remain available through `scripts/setup_env.sh`; they are not required for normal evaluation. From the repository root, choose one environment owner:

```bash
# Native/current Python environment (prefer an already isolated environment)
scripts/setup_env.sh --mode local --action install --editable

# Project-local venv; activate it after installation
scripts/setup_env.sh --mode venv --action install --editable
source .venv/bin/activate

# Dedicated Conda environment; sourcing keeps it active in this shell
source scripts/setup_env.sh --mode conda --conda-env aiplane --action install --editable
```

Use only one of these paths. `--editable` keeps the installation linked to the checkout; use `--static` for a snapshot that changes only when reinstalled. See [Source-checkout install modes](docs/user/setup.md#source-checkout-install-modes) for prerequisites, activation behavior, dry-run examples, verification, and platform support.

After installation, create the editable `profiles/local-dev/` profile used by
the CLI. It contains the reviewed hardware, model, runtime, endpoint, and policy
configuration. This safe first-run form keeps an existing
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
aiplane export codex --model MODEL_ALIAS
aiplane export copilot-cli --model MODEL_ALIAS --format json
aiplane export copilot-vscode --model MODEL_ALIAS
```

`discover` inspects the model catalog state already present in the selected
profile; it does not contact provider catalogs. To populate or update the
ignored `models.discovered.yaml` cache, explicitly preview and run a model
catalog refresh, then review the discovered entries:

```bash
aiplane models refresh --dry-run
aiplane models refresh
aiplane models list --group-by runtime
```

Refresh does not add reviewed aliases or defaults to `models.yaml`. Promote a
discovered entry when you want it to become part of the editable profile; see
[Model Catalog Refresh](docs/user/providers.md#model-catalog-refresh).

The single-command equivalent is offline-safe by default:

```bash
aiplane quickstart local-coding
aiplane quickstart local-coding --dry-run
aiplane quickstart local-coding --dry-run --pull-model MODEL_ALIAS
aiplane quickstart local-coding --pull-model MODEL_ALIAS
aiplane quickstart local-coding --discovery  # explicitly contact configured catalogs
```

Quickstart preserves existing profile files on repeat runs and reports one exact next action. When no model alias exists, it offers only two setup paths—local Ollama or an existing managed endpoint—and requires no manual YAML editing. Provider catalog access is opt-in with `--discovery`.

This path is designed to detect local hardware, runtimes, model catalog state,
endpoint setup status, and role mappings, report configuration sources (detected, built-in, provider-discovered cache, profile-configured, and unresolved records), and then report one exact next action. Doctor findings include severity, impact, remediation command metadata, mutability, and dry-run support where action is needed.

## Quick local Ollama demo

The core onboarding flow above is inspect-first. For an end-to-end evaluator demo
that prepares and runs a local model, use this order after downloading the wheel.
The wheel version below is illustrative. Catalog refresh contacts Ollama; promotion
writes the editable profile; integration setup may install/start Ollama and download
model weights.

```bash
# 1. Install and create a clean demo workspace.
uv tool install ./aiplane-0.1.0-py3-none-any.whl
aiplane --version
mkdir aiplane-demo
cd aiplane-demo

# 2. Create the profile, then inspect this machine explicitly.
aiplane profiles bootstrap-local --no-overwrite --no-discovery --no-hardware-discovery
aiplane hardware discover

# 3. Discover Ollama catalog entries and show alias/model pairs that fit this PC.
aiplane models refresh --provider ollama --query chat --limit 25 --dry-run
aiplane models refresh --provider ollama --query chat --limit 25
aiplane models list --provider ollama --runtime ollama --role chat --current-machine --sort-by role --limit 10 --format text
aiplane models list --provider ollama --runtime ollama --role chat --current-machine --sort-by role --limit 10 --identity alias

# 4. Replace DISCOVERED_ALIAS with one alias from the ALIAS column, then review it.
aiplane models show DISCOVERED_ALIAS
aiplane models promote DISCOVERED_ALIAS --as local_chat --dry-run
aiplane models promote DISCOVERED_ALIAS --as local_chat
aiplane models use chat_model local_chat

# 5. Preview and perform supported runtime/model preparation.
aiplane integrations setup codex --model local_chat --runtime ollama --dry-run
aiplane integrations setup codex --model local_chat --runtime ollama
aiplane runtimes status ollama
aiplane runtimes list-runtime-models ollama

# 6. Print host-client configuration, then smoke-test the endpoint interactively.
aiplane export codex --model local_chat
aiplane export copilot-cli --model local_chat --format json --offline
aiplane export copilot-vscode --model local_chat
aiplane chat --model local_chat
```

`models list` shows the Aiplane `ALIAS` beside the provider-native `MODEL` by
default. Use `--identity alias` or `--identity model` for one value per line, or
`--identity both` explicitly for the normal full output. Host-client exports print reviewed configuration; they do not install, launch, or edit Codex, Copilot CLI, or VS Code. Type `/exit` to leave chat.

## Profiles, render, export, and replay

- A **profile** is the editable YAML source of truth for an intended AI development setup: reviewed model aliases, runtimes, endpoints, hardware expectations, tool roles, and policy.
- `aiplane profiles render PROFILE` reads the profile's YAML files and prints one consistently ordered JSON snapshot. Use that snapshot for validation, comparison, CI, or archival evidence; it is not an installable config and cannot currently restore the YAML.
- `aiplane export TARGET` compiles the selected profile into configuration text understood by another tool, such as Codex, Copilot CLI, Copilot in VS Code, or Continue. It prints to stdout and does not install the tool, edit its files, start a runtime, or copy credentials.
- A **replay** copies the reviewed YAML profile to another workspace or machine, validates it, inspects the destination, and compiles fresh target-tool configuration there.

Today, ordinary reviewed filesystem or version-control procedures own backup and transfer:

```bash
# Source machine: preserve the editable source and comparison evidence.
cp -a profiles/local-dev portable-local-dev
aiplane profiles render local-dev > local-dev.profile.json
aiplane export continue > continue.expected.yaml

# Destination machine: restore the YAML source, then evaluate this machine.
cp -a portable-local-dev profiles/local-dev
aiplane profiles validate local-dev
aiplane discover
aiplane doctor
aiplane recommend
aiplane export continue > continue.actual.yaml
```

Identical machines with equivalent resolved inputs should reproduce the same export. Machines with small hardware differences may still be **capability-equivalent** when the reviewed models, runtimes, endpoints, and policy remain suitable; discovery and doctor should expose the variance without forcing a different result. Material differences must remain visible and may legitimately change recommendations or exports. Credentials, model weights, discovery caches, audit logs, tunnel state, and runtime-owned data are machine-local and are not part of the portable profile. See [Profile backup, recovery, and replay](docs/user/profile-schema.md#backup-recovery-and-cross-machine-replay).

Command categories are explicit in [command coverage](docs/project/project-plan.md#command-coverage): core commands lead onboarding, supporting commands troubleshoot specific subsystems, and experimental commands remain outside the developer-preview path.

## Advanced and experimental commands

The repository contains additional tested commands for specialised environment troubleshooting, integration planning, and guarded operations. They remain subordinate to the profile → discover → doctor → recommend → export workflow. They remain implementation details rather than additional product promises. See [command coverage](docs/project/project-plan.md#command-coverage) for the exact maturity boundary and [Roadmap](docs/project/project-plan.md#roadmap) for future decisions.

## Safety, governance, and trust model

- credentials and local machine state are intentionally outside git in ignored files,
- secrets are redacted by command output tooling,
- plans/doctor/install previews come before mutation,
- mutating operations are narrow, guarded, and audited,
- and policy checks are surfaced before escalation is allowed.

Security reporting is documented in [SECURITY.md](SECURITY.md). The tested trust boundaries and residual limitations are in the [practical threat model](docs/project/threat-model.md).

## Helper scripts

- `scripts/setup_env.sh`: bootstrap paths for local execution modes and environment setup.
- `scripts/provider_helper.sh`: thin runtime operation dispatcher used by the CLI.
- `aiplane environment plan`: renders how a command would run under current profile context.
- `aiplane environment doctor` and `aiplane tools doctor`: first checks when setup quality looks off.

More detail:

- [setup and installation](docs/user/setup.md)
- [core user workflow](docs/user/index.md)
- [doctor output contract](docs/user/doctor-contract.md)
- [platform support](docs/user/platform-support.md)
- [advanced command maturity](docs/project/project-plan.md#command-coverage)

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

Use [command coverage](docs/project/project-plan.md#command-coverage) and [strategy](docs/project/strategy.md) to keep behavior, docs, and tests synchronized.

## Documentation

- [Start here](docs/user/index.md)
- [Installation and setup](docs/user/setup.md)
- [Platform support](docs/user/platform-support.md)
- [Security policy](SECURITY.md) and [practical threat model](docs/project/threat-model.md)
- [Advanced command maturity](docs/project/project-plan.md#command-coverage)
- [Contributor guide](CONTRIBUTING.md)

## Contributing

We want practical contributions that make local and hybrid AI development environments easier to diagnose and reproduce. Good first areas:

- improve discovery and actionable doctor findings;
- improve hardware-fit recommendations and deterministic exports;
- harden profile, policy, and secret-safety behavior;
- improve reproducible installation and setup flows; and
- tighten documentation where commands or terminology create ambiguity.

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT. See [LICENSE](LICENSE).
