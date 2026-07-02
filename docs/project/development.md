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

The current test suite uses `unittest`, so no separate test dependency install is
needed. Run tests with:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python -m unittest discover -s tests
```

Or, after editable install:

```bash
PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s tests
```

If future dependencies are added, keep them in `pyproject.toml` so local, venv,
conda, and Docker setup all use the same source of truth.

## Running Unit Tests

The project currently uses the Python standard-library `unittest` runner.

Without installing the package:

```bash
cd aiplane
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python -m unittest discover -s tests
```

After editable install in local Python, `venv`, or Conda:

```bash
PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s tests
```

Through the setup helper:

```bash
scripts/setup_env.sh --mode venv --action test
scripts/setup_env.sh --mode conda --conda-env aiplane --action test
scripts/setup_env.sh --mode local --action test
```

Unit tests must stay hermetic and fast. Do not call real cloud CLIs, Docker, SSH, provider APIs, model runtimes, or long-running local services from the normal unit suite. Mock those boundaries and assert the planned commands, parsed results, fallback behavior, and error handling. Keep live Azure/Ollama/Docker checks as explicit manual or integration smoke commands so a developer's installed tools do not make `python -m unittest discover -s tests` slow or environment-dependent.


## JSON Output Conventions

User-facing JSON-like output should be predictable and easy to scan. Use the shared helpers in `src/aiplane/output.py` instead of calling `json.dumps(..., sort_keys=True)` directly from CLI, MCP, or integration-output code.

Rules:

- Put `name` first whenever the object has a name.
- For model-like objects, prefer `name`, `provider`, `model`, then runtime/source/type/status fields.
- For profile-like objects, prefer `name`, `default`, `root`, `workspace`, then `selected`.
- Do not alphabetically sort keys for user-facing JSON; alphabetical order often hides the most important fields.
- Group output when it improves scanning, for example by provider, source, runtime, or model id.
- Keep raw JSONL audit/event storage compact, but format displayed CLI output through the shared ordering helper.

When adding a new command, test at least one representative JSON output shape if field order matters to users.

## Useful Smoke Checks

```bash
PYTHONPATH=src python -m aiplane profiles bootstrap-local --no-discovery
PYTHONPATH=src python -m aiplane profiles list
PYTHONPATH=src python -m aiplane providers list --profile local-dev
PYTHONPATH=src python -m aiplane providers models --profile local-dev ollama
PYTHONPATH=src python -m aiplane environment doctor --required-only
PYTHONPATH=src python -m aiplane integrations plan continue --select-best --runtime ollama
```

## Documentation Split

- `README.md`: end-user setup and usage.
- `docs/user/setup.md`: end-user setup helper details.
- `docs/user/providers.md`: provider setup/discovery helpers.
- `docs/project/development.md`: dependency, test, and contributor workflows.
- `docs/project/strategy.md`: product strategy and roadmap.
