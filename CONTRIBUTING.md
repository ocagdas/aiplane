# Contributing to aiplane

  Thanks for considering a contribution.

  `aiplane` is a control-plane CLI for AI development environments. It plans,
  checks, prepares, and exports configuration for providers, models, runtimes,
  machines, stacks, tools, integrations, and MCP. It is not a coding agent, model
  runtime, model proxy, IDE extension, or hidden cloud deployment engine.

  ## Before You Start

  Please read:

  - [README.md](README.md)
  - [Security Policy](SECURITY.md)
  - [Code of Conduct](CODE_OF_CONDUCT.md)
  - [Agent Guidance](docs/project/agent-guidance.md)
  - [Roadmap](docs/project/roadmap.md)

  ## Development Setup

  Use the project setup helper:

  ```bash
  scripts/setup_env.sh --mode conda --conda-env aiplane --action install
  conda activate aiplane

  Or, if you need the setup script to update your current shell:

  source scripts/setup_env.sh --mode conda --conda-env aiplane --action install --install-mode editable

  Check the environment:

  aiplane environment doctor --required-only

  ## Running Tests

  Run focused tests for the area you changed, then run the full check before
  opening a PR:

  conda run -n aiplane python -m pytest tests/test_contracts.py -q
  conda run -n aiplane python -m pytest tests/test_mvp.py -k "keyword_for_your_change" -q
  conda run -n aiplane scripts/check.sh

  The full check runs formatting, linting, and tests.

  Tests should cover real behavior, contracts, and regressions. Do not add tests
  only to increase counts. Keep tests deterministic and avoid depending on local
  cloud credentials, running runtimes, or machine-specific state unless the test
  mocks those dependencies.

  ## Documentation

  When behavior changes, update relevant docs in the same change:

  - docs/user/
  - docs/project/roadmap.md
  - docs/project/session-handoff.md
  - docs/project/command-coverage.md
  - tests in tests/test_mvp.py or a focused test file

  Keep CLI help, docs, MCP surfaces, and tests aligned.

  ## Security and Secrets

  Do not commit secrets, tokens, API keys, private keys, account identifiers, local
  runtime state, generated model caches, or .aiplane/ files.

  Use environment variables or ignored local credentials files for secrets. CLI
  output and tests must redact secrets.

  Report vulnerabilities privately. See SECURITY.md (SECURITY.md).

  ## Pull Requests

  A good PR should include:

  - a clear description of the change;
  - focused tests for behavior or regressions;
  - documentation updates when user-facing behavior changes;
  - the result of conda run -n aiplane scripts/check.sh;
  - notes about any intentionally deferred work.

  Keep changes scoped. Avoid unrelated refactors in the same PR.

  ## MCP and Skills

  Do not expose risky operations through MCP by default. Runtime installs, model
  pulls, cloud apply, secret writes, and arbitrary shell execution need explicit
  guardrails before they can be exposed.

  MCP and future agent-skill support are synchronized at periodic checkpoints and
  pre-PR cleanup, not after every small feature.

  ## Compatibility

  aiplane has not reached a stable public release yet. Until maintainers say
  otherwise, prefer the clean current interface over backward-compatibility shims.
  Keep documentation and tests up to date with the current interface.
