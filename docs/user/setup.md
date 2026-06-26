# Setup

The setup helper creates/configures the environment used to run `aiplane`. It
supports local Python, `venv`, Conda, and Docker CLI images, with either
editable/source-linked installs or static/snapshot installs. This is separate
from provider setup: provider runtimes and API credentials are handled by
`scripts/provider_helper.sh` and documented in `providers.md`.

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
it activates the environment before returning. If the script is executed normally,
it cannot activate the parent shell, so it writes `.aiplane/activate-conda-<env>.sh`
and prints activation commands. The helper now verifies that the Conda environment
is visible after creation and fails with a clear error if it is not.

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

`setup_env.sh --action install` runs a sanity check automatically and then prints
the matching activation command.


## Local Config

Create an ignored local config file when you want machine/user-specific defaults
without committing them:

```bash
aiplane config templates
aiplane config init --template local
aiplane config show
```

Default path:

```text
.aiplane/config.yaml
```

You can also choose a different config file with `AIPLANE_CONFIG` or
`aiplane config init --path ...`. Precedence for profile location is:

1. `--profiles-dir`
2. `AIPLANE_PROFILES_DIR`
3. `profiles_dir` in local config
4. repo-local `profiles/`

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

Use `--overwrite` only when you want to replace an existing profile with a fresh
copy of the template:

```bash
aiplane profiles create my-local --template local-dev --overwrite
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
