# Setup

The setup helper creates/configures the environment used to run `aiplane`. It
supports local Python, `venv`, Conda, and Docker CLI images, with either
editable/source-linked installs or static/snapshot installs. This is separate
from provider setup: provider runtimes and API credentials are handled by
`scripts/provider_helper.sh` and documented in `providers.md`.

Platform support: the Bash setup helper and helper-managed runtime install/update commands are currently supported only on Linux hosts. On Windows or macOS, install `aiplane` and runtimes with platform-native Python/Conda/runtime installers, then use `aiplane discover`, `aiplane doctor`, `aiplane recommend`, and `aiplane export` to inspect and generate configuration. If a helper install command is run on an unsupported platform, it terminates with a clear unsupported-platform error.

Install modes:

- `--install-mode editable` or `--editable`: for local/venv/Conda, runs `pip install -e .`; source changes are visible immediately. For Docker, builds a small image and mounts this checkout at `/workspace` when commands run.
- `--install-mode static` or `--static`: for local/venv/Conda, runs `pip install .`; reinstall to pick up later source edits. For Docker, copies this checkout into the image; rebuild the image to update it.

Preview actions without changing anything:

```bash
scripts/setup_env.sh --mode venv --action install --editable --dry-run
scripts/setup_env.sh --mode venv --action install --static --dry-run
scripts/setup_env.sh --mode conda --conda-env aiplane --action install --editable --dry-run
scripts/setup_env.sh --mode conda --conda-env aiplane --action install --static --activate 0 --dry-run
scripts/setup_env.sh --mode local --action install --static --dry-run
scripts/setup_env.sh --mode docker --action install --editable --docker-image aiplane:dev --dry-run
scripts/setup_env.sh --mode docker --action install --static --docker-image aiplane:snapshot --dry-run
```

Fresh Conda install on a new machine:

```bash
# Prerequisites: git and Conda or Miniforge/Miniconda are installed, and conda is on PATH.
git clone https://github.com/ocagdas/aiplane.git
cd aiplane
conda --version

# Recommended: source the helper so the new environment remains active.
source scripts/setup_env.sh --mode conda --conda-env aiplane --action install --editable

# Verify the installed CLI and bootstrapped local profile.
aiplane profiles list
aiplane profiles show local-dev
aiplane environment doctor --required-only
aiplane tools matrix
```

For a snapshot install that is isolated from later source edits, use `--static`
instead of `--editable`. When sourced, the helper returns to the same shell with
the Conda environment active and restores the caller's shell options. If you
execute the setup helper instead of sourcing it, activate afterward with
`source .aiplane/activate-conda-aiplane.sh` or `conda activate aiplane`.

Install into a project-local venv:

```bash
# Development: source-linked to this checkout
scripts/setup_env.sh --mode venv --action install --editable
source .venv/bin/activate
aiplane profiles list

# Snapshot: isolated from later source edits until reinstall
scripts/setup_env.sh --mode venv --action install --static
```

Install into a dedicated Conda environment:

```bash
# Recommended: source the helper so activation persists in this shell.
source scripts/setup_env.sh --mode conda --conda-env aiplane --action install --editable
aiplane profiles list

# Also valid: execute the helper, then activate explicitly.
scripts/setup_env.sh --mode conda --conda-env aiplane --action install --editable
source .aiplane/activate-conda-aiplane.sh
# or: conda activate aiplane

# Snapshot: isolated from later source edits until reinstall, without activation.
scripts/setup_env.sh --mode conda --conda-env aiplane --action install --static --activate 0
conda activate aiplane
```

For Conda installs, `--activate` defaults to `1`. If the setup script is sourced,
it activates the environment before returning to the same shell. If the script is
executed normally,
it cannot activate the parent shell, so it writes `.aiplane/activate-conda-<env>.sh`
and prints activation commands. The helper verifies that the Conda environment
is visible after creation and, during install, repairs an existing Conda
environment that is missing Python by installing `python=3.13` into it. During
install, it also runs
`aiplane profiles bootstrap-local --no-discovery` before the profile-aware sanity
check, so a fresh clone gets an ignored `profiles/local-dev` directory from the
shipped template.

Check Conda environments with:

```bash
conda env list
```

Do not use `conda list env` for this; that lists packages matching `env` in the
current environment. Use `--activate 0` to skip activation/hints.

A Conda environment that also contains runtime dependencies can be replicated with:

```bash
conda env export -n aiplane > environment-aiplane.yaml
```

Install into the current Python environment:

```bash
scripts/setup_env.sh --mode local --action install --editable
scripts/setup_env.sh --mode local --action install --static
aiplane profiles list
```

Build a Docker image that can run the `aiplane` CLI:

```bash
# Development: source-linked through a bind mount of this checkout.
scripts/setup_env.sh --mode docker --action install --editable --docker-image aiplane:dev

# Snapshot: source copied into the image; rebuild when the code changes.
scripts/setup_env.sh --mode docker --action install --static --docker-image aiplane:snapshot

# Verify or test an existing image.
scripts/setup_env.sh --mode docker --action doctor --docker-image aiplane:dev
scripts/setup_env.sh --mode docker --action test --docker-image aiplane:dev
```

Docker CLI install mode is not the same as profile Docker execution mode. In Docker CLI install mode, `aiplane` itself runs inside a container. In profile Docker execution mode, `aiplane` runs on the host and wraps configured tool commands in `docker run`.

Verify or test an existing setup:

```bash
scripts/setup_env.sh --mode venv --action doctor
scripts/setup_env.sh --mode venv --action test
scripts/setup_env.sh --mode conda --conda-env aiplane --action doctor
scripts/setup_env.sh --mode docker --action doctor --docker-image aiplane:dev
```


## Environment Mode Selection

Profiles can define several execution modes, such as `system`, `venv`, `conda`,
and `docker`. List and switch them with:

```bash
aiplane environment list
aiplane environment active
aiplane environment use venv
aiplane environment plan python --version
```

`environment use` updates the selected profile's `environment.yaml`. Use
`environment plan` before running tools when you want to verify the exact command
that will execute.

## Activation

A script cannot permanently activate a `venv` or Conda environment in the parent
shell when it is executed normally. For Conda, source `setup_env.sh` during
install if you want it to activate automatically, or use the source helper after
installation:

```bash
source scripts/activate_env.sh venv
source scripts/activate_env.sh conda aiplane
```

`setup_env.sh --action install` bootstraps `profiles/local-dev` from the shipped
template when needed, runs a sanity check automatically, and then prints the
matching activation command. `scripts/activate_env.sh` performs the same
idempotent no-discovery bootstrap after activation.


## Local Config

Create an ignored local config file when you want machine/user-specific defaults
without committing them:

```bash
aiplane config templates
aiplane config init --template local
aiplane config show
```
```bash
aiplane config format
aiplane config format json
aiplane config format json --profile local-dev
aiplane config format --command "models list"
aiplane config format --clear
aiplane config format --clear --profile local-dev
aiplane config format --clear --command "models list"
```

aiplane config also controls output defaults for commands that support `--format`:

- command-line `--format` always wins
- `--profile` value on `config format` overrides global default for that profile
- `--command` value on `config format` overrides global and profile defaults for that command
- global `config format` is the fallback default
- default when unset is `text`

```bash
aiplane config verbosity
aiplane config verbosity 1
aiplane config verbosity 1 --profile local-dev
aiplane config verbosity 1 --command "models list"
aiplane config verbosity --clear
aiplane config verbosity --clear --profile local-dev
aiplane config verbosity --clear --command "models list"
```

aiplane config also controls output detail for commands that support `--verbosity`:

- command-line `--verbosity` always wins
- `--profile` value on `config verbosity` overrides global default for that profile
- `--command` value on `config verbosity` overrides global and profile defaults for that command
- global `config verbosity` is the fallback default
- default when unset is `0`


Default path:

```text
.aiplane/config.yaml
```

`aiplane config show` prints both the default and active config paths, the default and current profile paths, and the effective credentials and agent artifact paths.

You can also choose a different config file with `AIPLANE_CONFIG` or
`aiplane config init --path ...`. Precedence for profile location is:

1. `--profiles-dir`
2. `AIPLANE_PROFILES_DIR`
3. `profiles_dir` in local config
4. repo-local `profiles/`

Agent application artifacts use a separate local path because they are project outputs, not profile configuration. Precedence for agent artifact roots is:

1. `--output-dir` on agent commands
2. `AIPLANE_AGENT_ARTIFACTS_DIR`
3. `agent_artifacts_dir` in local config
4. `.aiplane/agents`

## Local Credentials

Credentials are local machine/user state, not profile state. Profiles and model aliases should reference credential names such as `openai.personal` or `azure_openai.business_a`; the actual keys live in an ignored credentials file.

Precedence for the credentials file is:

1. `--path` on `aiplane credentials` commands
2. `AIPLANE_CREDENTIALS`
3. `credentials_path` in local config
4. `.aiplane/credentials.yaml`

Example ignored credentials file:

```yaml
providers:
  openai:
    accounts:
      personal:
        api_key_env: OPENAI_PERSONAL_API_KEY
        endpoint: https://api.openai.com/v1
      business_a:
        api_key_env: OPENAI_BUSINESS_A_API_KEY
        endpoint: https://api.openai.com/v1
  custom_openai_compatible:
    accounts:
      lab_gateway:
        api_key_env: AIPLANE_LAB_LLM_KEY
        endpoint: https://llm-gateway.example.com/v1
```

`api_key_env` is preferred because target tools such as Continue and Aider can read environment variables without `aiplane` printing raw secrets. For internal discovery/checks, `aiplane` can also read an `api_key` from the ignored credentials file, but `credentials show` redacts it.

Inspect configured refs without exposing secrets. If no credentials file exists yet, `credentials list` returns an empty list without printing the missing path; `credentials show` still errors for a ref that is not configured:

```bash
aiplane credentials list
aiplane credentials show openai.personal
```

Use provider connection tests to verify that a selected endpoint and credential can make a small provider-specific API call. The command reports whether the credential worked, the method used, and item counts, but it does not print the key or token:

```bash
aiplane providers test openai --credential-ref openai.personal
aiplane providers test azure_openai --credential-ref azure_openai.business_a
aiplane providers test elevenlabs
```

Provider overrides can then refer to credentials without embedding secret values. Keep account-specific endpoint and credential references in ignored local config, not in the shipped profile template.

## Profile Templates

Default profile files are checked in under `profile-templates/`. Editable profiles
default to `profiles/`. That directory is local/user state and is ignored for new
profiles. To create a new profile from a shipped template:

```bash
aiplane profiles templates
aiplane profiles create my-local --template local-dev
aiplane profiles show my-local
aiplane profiles show --selected
```

`profiles show` defaults to the effective default profile when no name is passed.
Use `--selected` to show only active/enabled/default choices such as active
environment, selected hardware, enabled models/providers, and default target.

Customize files under `profiles/my-local/`. Do not edit `profile-templates/` for
local machine or team-specific settings unless you intentionally want to change
the shipped defaults.

Use `profiles repair` when an editable profile exists but one or more template
files are missing. It copies only missing files by default and preserves existing
local files unless `--overwrite` is passed:

```bash
aiplane profiles repair local-dev --file models.yaml
aiplane profiles repair local-dev --dry-run
```

Use `--overwrite` only when you want to replace an existing profile or selected
profile file with a fresh copy of the template:

```bash
aiplane profiles create my-local --template local-dev --overwrite
aiplane profiles repair local-dev --file models.yaml --overwrite
```

Use `profiles remove` to delete an editable profile directory. The command is a
preview unless `--yes` is passed, and it does not delete runtime caches,
credentials, or model weights:

```bash
aiplane profiles remove old-local --dry-run
aiplane profiles remove old-local --yes
```

Hardware discovery is under the `hardware` command family, not `profiles`.
`profiles bootstrap-local` runs hardware discovery by default when the profile
exists or has just been created, and can set the active hardware template to the
closest discovered match:

```bash
aiplane profiles bootstrap-local
aiplane profiles bootstrap-local --select-closest-hardware
aiplane hardware discover
aiplane hardware discover --select-closest --dry-run
aiplane hardware active
aiplane hardware export-machine --name local_box > local_box.machine.yaml
```

### Default Profile

Most commands accept `--profile`, but you can set a default in local config:

```bash
aiplane config default-profile
aiplane config default-profile my-local
aiplane profiles list
aiplane profiles show --selected
aiplane environment active
```

`profiles list` marks the effective default with `*`. `profiles show` without a
name shows that same profile. Precedence for default
profile is:

1. `--profile` on the command
2. `AIPLANE_PROFILE`
3. `default_profile` in local config
4. `local-dev`

### Custom Profile Directory

Use `--profiles-dir` for one command, or `AIPLANE_PROFILES_DIR` as the default
location for editable profiles:

```bash
aiplane --profiles-dir ~/.config/aiplane/profiles profiles create my-local --template local-dev
aiplane --profiles-dir ~/.config/aiplane/profiles profiles list

export AIPLANE_PROFILES_DIR=~/.config/aiplane/profiles
aiplane profiles list
aiplane run --profile my-local --dry-run "explain this setup"
```

`profile-templates/` remains the checked-in source of defaults. The custom
profiles directory is your responsibility to back up.

## Profile Selection

Most commands accept `--profile`, but it is optional. `aiplane` resolves the profile in this order:

1. `--profile <name>` on the command.
2. `AIPLANE_PROFILE` if set.
3. `default_profile` in the local `.aiplane/config.yaml`.
4. The only available profile, when exactly one exists.

If no profile exists, create one with:

```bash
aiplane profiles create local-dev --template local-dev
```

Use `--profile` only when you need to override the default for one command.
