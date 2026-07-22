# aiplane

[![CI](https://github.com/ocagdas/aiplane/actions/workflows/ci.yml/badge.svg)](https://github.com/ocagdas/aiplane/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%2B-3776AB.svg)](pyproject.toml)

**Know what fits. See what is missing. Generate the right config.**

Your AI setup worked on one machine. Can you explain why, reproduce it on
another, and configure each supported development tool without rebuilding it from memory?

`aiplane` is an **environment doctor and configuration compiler** for local and
hybrid AI development. It connects the facts that usually drift apart - hardware,
models, runtimes, endpoints, policy, and client configuration - then turns them
into one reviewable workflow.

First outcome: get a read-only assessment and one exact next action without
installing a runtime, pulling weights, editing development-tool files, or
touching an external service.

```bash
aiplane quickstart local-coding --dry-run
```

Profiles are declarative YAML. Output is available as readable text or
deterministic JSON. Secrets stay in ignored local files or environment
variables.

## The problem it solves

Most AI tools run a model, serve an endpoint, or act as an assistant. Aiplane
handles the awkward questions before and around them:

| Question | Aiplane answer |
| --- | --- |
| What can this PC actually run? | Discover the machine and filter reviewed models by RAM, VRAM, GPU, runtime, and role. |
| Why is this setup not ready? | Diagnose missing tools, endpoints, credentials, defaults, and hardware fit with actionable findings. |
| Which model name do I put in the client? | Keep a stable profile alias beside the provider-native model identity. |
| How do I configure another client? | Compile the same reviewed choice into deterministic client-specific configuration. |
| Will this profile still work elsewhere? | Archive, restore, compare, and classify current-machine drift without copying secrets or model weights. |

No more mystery aliases, undocumented ports, or "it works on my GPU" setup
notes.

## What you get

- **Hardware-aware choices** - inspect the current PC, a saved machine profile,
  or explicit RAM/VRAM/GPU constraints.
- **Actionable diagnosis** - findings include impact, provenance, remediation,
  mutability, and dry-run support.
- **One model identity story** - see the Aiplane alias and provider-native model
  name together.
- **Deterministic exports** - generate reviewed configuration for existing
  coding tools and OpenAI-compatible clients without editing their files.
- **Portable profiles** - keep models, endpoints, hardware expectations, and
  policy in inspectable YAML; compare exact, equivalent, incompatible, and
  unresolved destinations.
- **Safe automation** - use stable JSON in scripts and CI while keeping broad
  host, cloud, and secret mutation outside the default workflow.

> [!NOTE]
> Aiplane is a **developer preview / pre-1.0 alpha**. The public path is
> deliberately narrow: discover -> doctor -> recommend -> export. Supporting
> commands are tested, but their maturity varies and is documented in
> [command coverage](docs/project/project-plan.md#command-coverage).


Advanced, review-first workflows are available without turning Aiplane into a model server or cluster controller:

~~~bash
aiplane integrations import continue ~/.continue/config.yaml --as imported-draft
aiplane support list --kind runtime
aiplane providers adapter-validate tests/fixtures/adapter-v1.json
aiplane runtimes pull docker_model_runner --model ai/model-id --dry-run
aiplane stacks render-kubernetes STACK --image IMAGE --device-class DEVICE_CLASS
~~~

Literal credentials are never imported, lifecycle mutations require confirmation, support records do not claim unverified upstream versions, and Kubernetes application remains outside this command surface.

Aiplane does not replace your coding assistant, model runtime, chat interface,
inference server, model registry, gateway, or cloud platform. It makes the
configuration around those systems explicit and reproducible.

## Install

Download the wheel from the
[latest GitHub Release](https://github.com/ocagdas/aiplane/releases/latest),
then install it as an isolated application:

```bash
# Choose one.
uv tool install ./aiplane-0.1.0-py3-none-any.whl
pipx install ./aiplane-0.1.0-py3-none-any.whl

# Or install into an active venv or Conda environment.
python -m pip install ./aiplane-0.1.0-py3-none-any.whl

aiplane --version
```

Use the filename attached to the release; `0.1.0` is illustrative. See
[Installation and setup](docs/user/setup.md#standard-wheel-install-no-repository-clone)
for upgrades, uninstallation, Conda usage, verification, and platform notes.

Create the editable local profile without contacting model-provider catalogs:

```bash
aiplane profiles bootstrap-local --no-overwrite --no-discovery
```

<details>
<summary><strong>Install from a source checkout</strong></summary>

Choose one environment owner from the repository root:

```bash
# Current Python environment
scripts/setup_env.sh --mode local --action install --editable

# Project-local venv
scripts/setup_env.sh --mode venv --action install --editable
source .venv/bin/activate

# Dedicated Conda environment
source scripts/setup_env.sh --mode conda --conda-env aiplane --action install --editable
```

Use `--static` instead of `--editable` for a snapshot installation. To invoke
the source tree without installing it:

```bash
PYTHONPATH=src python -m aiplane profiles bootstrap-local --no-overwrite --no-discovery
```

</details>

Local CLI preferences are optional and separate from profiles:

```bash
aiplane config init --template local
aiplane config show
```

## Core onboarding flow

Four read-only commands take you from "what is here?" to usable configuration:

```bash
aiplane discover
aiplane doctor
aiplane recommend
aiplane export continue
```

Use the selected model alias with another supported client when needed:

```bash
aiplane export codex --model MODEL_ALIAS
aiplane export copilot-cli --model MODEL_ALIAS --format json
aiplane export copilot-vscode --model MODEL_ALIAS
```

`discover` inspects the catalog state already present in the profile; it does
not contact provider catalogs. To update the ignored discovery cache, preview
the network operation first, run it, then review alias/native-model pairs:

```bash
aiplane models refresh --dry-run
aiplane models refresh
aiplane models list --group-by runtime
```

Discovery does not silently turn results into reviewed configuration. Promote
an entry before using it as a stable profile alias. See
[Model catalog refresh](docs/user/providers.md#model-catalog-refresh).

Prefer one command? Quickstart is offline-safe by default, preserves existing
profile files, and reports one exact next action:

```bash
aiplane quickstart local-coding
aiplane quickstart local-coding --dry-run
aiplane quickstart local-coding --dry-run --pull-model MODEL_ALIAS
aiplane quickstart local-coding --pull-model MODEL_ALIAS
aiplane quickstart local-coding --discovery  # explicitly contact configured catalogs
```

## Quick local Ollama demo

This walkthrough goes from a clean directory to a hardware-filtered local model,
reviewed client configuration, and interactive endpoint chat. Catalog refresh
contacts Ollama; promotion writes the profile; setup may install or start Ollama
and pull model weights. Every mutating step has a preview immediately before it.

<details>
<summary><strong>Expand the full install -> discover -> promote -> run walkthrough</strong></summary>

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
aiplane hardware assess DISCOVERED_ALIAS --runtime ollama --context-tokens 32768
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

</details>

`models list` shows the Aiplane `ALIAS` beside the provider-native `MODEL` by
default. Use `--identity alias` or `--identity model` for one value per line, or
`--identity both` for the normal full output. Host-client exports print reviewed
configuration; they do not install, launch, or edit Codex, Copilot CLI, or VS
Code. Type `/exit` to leave chat.

Catalog refresh also builds an ignored query cache, so filters over provider,
runner, parameter size, benchmark score, and exact model properties remain fast
without replacing the reviewable YAML source of truth. Inspect it with
`aiplane models catalog-cache status`; bypass it for comparison with
`aiplane models list --catalog-cache off`.

## Profiles, render, export, and replay

- A **profile** is the editable YAML source of truth for an intended AI development setup: reviewed model aliases, runtimes, endpoints, hardware expectations, tool roles, and policy.
- `aiplane profiles render PROFILE` reads the profile's canonical YAML files and prints one consistently ordered JSON snapshot. Use that snapshot for validation, comparison, CI, or archival evidence; it is not an installable config and cannot currently restore the YAML.
- `aiplane profiles archive PROFILE --output PATH` creates a deterministic, checksummed JSON archive of reviewed profile YAML. Its manifest explicitly excludes raw credentials, ignored discovery/provider overrides, audit/tunnel/session state, model weights, runtime caches, and generated exports.
- `aiplane profiles restore ARCHIVE --as PROFILE` validates and previews restoration. Add `--yes` to create a new profile; existing profiles are never overwritten.
- `aiplane profiles compare LEFT RIGHT` compares two profile names by default; use `--left-source archive` or `--right-source archive` for a validated archive operand.
- `aiplane profiles drift SOURCE` compares explicit active hardware evidence with live discovery on this PC; use `--source archive` to assess an archive before restoration.
- `aiplane export TARGET` compiles the selected profile into configuration text understood by another tool, such as Codex, Copilot CLI, Copilot in VS Code, or Continue. It prints to stdout and does not install the tool, edit its files, start a runtime, or copy credentials.
- A **replay** restores reviewed YAML, validates it, inspects the destination, and compiles fresh target-tool configuration there.

The archive is a reviewable transfer artifact, not a managed backup service. Preview both operations before moving configuration between machines:

```bash
# Source machine: validate the manifest, then write the portable archive.
aiplane profiles archive local-dev --output local-dev.aiplane-profile.json --dry-run
aiplane profiles archive local-dev --output local-dev.aiplane-profile.json
aiplane profiles render local-dev > local-dev.profile.json
aiplane profiles compare local-dev local-dev.aiplane-profile.json --right-source archive
aiplane export continue > continue.expected.yaml

# Destination machine: preview restoration, create a new profile, then assess it.
aiplane profiles restore local-dev.aiplane-profile.json --as restored-local
aiplane profiles restore local-dev.aiplane-profile.json --as restored-local --yes
aiplane profiles validate restored-local
aiplane profiles compare local-dev restored-local
aiplane profiles drift restored-local
aiplane doctor --profile restored-local
aiplane recommend --profile restored-local
aiplane export continue --profile restored-local > continue.actual.yaml
```

Archive and restore validate paths, required files, YAML mappings, file sizes, SHA-256 checksums, and credential safety before writing. The archive includes the nine canonical profile YAML files plus profile-owned `model-providers.yaml` when present. Review it before sharing because endpoints, paths, machine names, and account aliases may still be operationally sensitive.

Identical portable evidence is classified as **exact**. When only active hardware differs, Aiplane reports **capability-equivalent** only if every selected local model still meets its configured minimum RAM, VRAM, GPU-vendor, and accelerator-API requirements. Resource failures are **materially incompatible** and missing model or machine facts are **unresolved**. Other portable configuration changes are conservatively material. Each result includes the changed facts and their provenance; neither command mutates profiles or the current machine. Credentials, model weights, discovery caches, audit logs, tunnel state, and runtime-owned data remain machine-local. See [Profile backup, recovery, and replay](docs/user/profile-schema.md#backup-recovery-and-cross-machine-replay).

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
