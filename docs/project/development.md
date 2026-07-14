# Development Guide

This guide is for contributors working on the `aiplane` codebase. End-user
installation and usage stays in the top-level `README.md`.

## Python Dependencies

The MVP currently has no third-party Python package dependencies; it uses only
the Python standard library. Installing with `python -m pip install -e .` is still
recommended because it registers the `aiplane` command and package metadata in
your active environment.

### Install Dependencies Locally

Use this when you are working directly in your current Python or Anaconda base
environment:

```bash
cd aiplane
python -m pip install --upgrade pip
python -m pip install -e .
```

Verify the package is installed in that same environment:

```bash
python -m aiplane profiles bootstrap-local --no-discovery
python -m aiplane profiles list
python -m pip show aiplane
```

### Install Dependencies in `venv`

```bash
cd aiplane
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
aiplane profiles bootstrap-local --no-discovery
aiplane profiles list
```

When new dependencies are added to `pyproject.toml`, update the venv with:

```bash
source .venv/bin/activate
python -m pip install -e .
```

### Install Dependencies in Conda

For a fresh system with Git and Conda or Miniforge/Miniconda installed:

```bash
git clone https://github.com/ocagdas/aiplane.git
cd aiplane
source scripts/setup_env.sh --mode conda --conda-env aiplane --action install --editable
aiplane profiles list
aiplane environment doctor --required-only
```

The helper creates the Conda environment when missing, installs this checkout in
editable mode, bootstraps ignored `profiles/local-dev`, and returns to the same
shell with the environment active when sourced. Manual equivalent:

```bash
cd aiplane
conda create -n aiplane python=3.13 -y
conda activate aiplane
python -m pip install --upgrade pip
python -m pip install -e .
aiplane profiles bootstrap-local --no-discovery
aiplane profiles list
```

When new dependencies are added, update the active conda environment with:

```bash
conda activate aiplane
python -m pip install -e .
```

### Development and Test Dependencies

The test suite uses the `pytest` runner for local development checks. Keep
dependencies in `pyproject.toml` so local Python, `venv`, Conda, and Docker
install the same environment surface.

```bash
python -m pip install -e .[dev]
```

If future dependencies are added, keep them in `pyproject.toml` so all
workflows use the same source of truth.

## Running Tests

`make test` runs the suite in your current working environment. Pytest uses a
session-scoped copy of the shipped profile templates plus synthetic model data;
it does not load ignored local discovery caches, and external network access is
blocked.

```bash
make test
```

`make test-clean` is the clean-mode runner. It creates a temporary profile root
and runs tests from that isolated copy so local profile edits do not leak into the
suite and local/CI behavior stays in sync.

```bash
make test-clean
```

You can tune clean-mode inputs with these variables:

```bash
make test-clean TEST_PROFILE_TEMPLATE=local-dev TEST_PROFILE_NAME=ci-test
```

### Make Targets and Test Coverage

- `make format`: format only (no tests)
- `make lint`: lint only (no tests)
- `make test`: run tests in the current environment
- `make test-clean`: run tests in isolated temp profiles
- `make check`: `format + lint + test-clean` (full local gate)

The equivalent environment helper commands are:

```bash
scripts/setup_env.sh --mode venv --action test
scripts/setup_env.sh --mode conda --conda-env aiplane --action test
scripts/setup_env.sh --mode local --action test
scripts/setup_env.sh --mode docker --action test
```

The Conda form uses the named environment and streams pytest output. The simpler
`scripts/check.sh` uses the currently active Python environment; run
`conda run --no-capture-output -n aiplane scripts/check.sh` to select Conda
explicitly. The full gate uses four pytest workers with file-level scheduling by default; set `AIPLANE_TEST_WORKERS=0` for serial execution or another worker count for the host. Use `scripts/check.sh quick` for formatting, linting, eight contract checks, and intentional smoke coverage for profile loading, CLI dispatch, dry-run planning, and JSON serialization. The quick gate is a narrow feedback loop, not a substitute for the full suite.

### Git Pre-Push Hook

Install the local hook:

```bash
make install-hooks
```

By default, the hook runs:
- `make check` (format + lint + `test-clean`)

You can override behavior when you need speed or need to bypass checks for
backup-only/local-only pushes:

```bash
# fast path (tests only)
AIPLANE_PREPUSH_MODE=fast git push

# skip checks (use only when intended, e.g. backup-only workflows)
AIPLANE_PREPUSH_MODE=backup git push
```

You can always bypass all hooks with git's built-in flag:

```bash
git push --no-verify
```

Through the setup helper:

```bash
scripts/setup_env.sh --mode venv --action test
scripts/setup_env.sh --mode conda --conda-env aiplane --action test
scripts/setup_env.sh --mode local --action test
scripts/setup_env.sh --mode docker --action test
```

Unit tests must stay hermetic and fast. Do not call real cloud CLIs, Docker,
SSH, provider APIs, model runtimes, or long-running local services from normal
suite runs. Mock those boundaries and assert planned commands, parser behavior,
failure handling, and contracts. Keep real checks as explicit manual or
integration smoke commands.

Test profiles are materialized on disk under a temporary `AIPLANE_PROFILES_DIR` using shipped templates and synthetic model data. Tests must call the real production profile loader; do not replace loader functions globally in CLI or MCP modules. CI runs the full gate on Python 3.11 and a focused contract plus clean-wheel installation check on Python 3.12 and 3.13.

All external command and HTTP calls use injectable `CommandRunner` and `HttpTransport` boundaries. Production uses `subprocess` and `urllib`; focused tests should use the recording fakes in `tests/boundary_fakes.py` instead of patching implementation modules. CLI tests that only need in-process dispatch and output capture should use `tests/cli_fixtures.py`; isolated profile materialization remains in `tests/profile_fixtures.py`.

CLI command families should colocate parser registration and dispatch in `cli_<domain>.py` modules behind the single `aiplane` entrypoint. The entrypoint owns shared argument resolution and cross-family orchestration; domain modules own their command grammar, manager calls, and output routing.

Large domain managers should delegate coherent workflows to collaborators rather than accumulating mutation, execution, readiness, and rendering in one class. `ModelCatalog` owns catalog state while `ModelExecution` owns pull/execution/endpoint readiness; `StackManager` owns stack configuration while `StackRolePlanner` and `StackLifecycle` own role policy and lifecycle behavior.

## JSON Output Conventions

User-facing JSON-like output should be predictable and easy to scan. Use the
shared helpers in `src/aiplane/output.py` instead of calling
`json.dumps(..., sort_keys=True)` directly from CLI, MCP, or integration-output
code.

Rules:

- Put `name` first whenever the object has a name.
- For model-like objects, prefer `name`, `provider`, `model`, then runtime/source/type/status fields.
- For profile-like objects, prefer `name`, `default`, `root`, `workspace`, then `selected`.
- Do not alphabetically sort keys for user-facing JSON; alphabetical order often hides the most important fields.
- Group output when it improves scanning, for example by provider, source, runtime, or model id.
- Keep raw JSONL audit/event storage compact, but format displayed CLI output through the shared ordering helper.

When adding a new command, test at least one representative JSON output shape if field
order matters to users.

## Useful Smoke Checks

```bash
python -m aiplane profiles bootstrap-local --no-discovery
python -m aiplane profiles list
python -m aiplane providers list --profile local-dev
python -m aiplane providers models --profile local-dev ollama
python -m aiplane environment doctor --required-only
python -m aiplane integrations plan continue --select-best --runtime ollama
```

## Documentation Split

- `README.md`: end-user setup and usage.
- `docs/user/setup.md`: end-user setup helper details.
- `docs/user/providers.md`: provider setup/discovery helpers.
- `docs/project/development.md`: dependency, test, and contributor workflows.
- `docs/project/strategy.md`: product strategy and roadmap.
