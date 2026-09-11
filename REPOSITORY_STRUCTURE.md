# Repository structure and document ownership

This file owns repository layout and documentation responsibilities. The versioned
[shared contract](standards/repository/v1/contract.json), its adjacent schemas and
[design](docs/development/repository-standard-design.md) own cross-repository automation
interfaces. `repository-standard.json` supplies aiplane's adapter values; run
`python scripts/check_repository_standard.py` to check them. Shared files are vendored,
with hashes in `standards/repository/v1/bundle.json`; runtime sibling imports are prohibited.

## Layout

| Location | Responsibility |
|---|---|
| `src/aiplane/` | Importable runtime, CLI and MCP tools |
| `configs/`, `schemas/`, `skills/` | Distributable defaults, contracts and agent guidance |
| `tests/` | Isolated product and distribution regressions |
| `scripts/`, `.github/workflows/` | Quality and release automation |
| `standards/repository/v1/` | Pinned shared contract and provenance |
| `docs/user/`, `docs/development/` | User guides and detailed design |

aiplane packages its runtime resources and qualifies pip, pipx and uv installations.
See [architecture](docs/architecture.md) for runtime boundaries. Builds, credentials,
caches, overrides and generated evidence remain ignored local state.

## Documentation ownership

| Owner | Sole responsibility |
|---|---|
| [README.md](README.md) | Product entry point and links to guides |
| [PURPOSE.md](PURPOSE.md) | Mission, scope and non-goals |
| [User guides](docs/user/), [development setup](docs/development/setup.md) | User installation and contributor setup |
| [STATUS.md](STATUS.md) | Current capabilities and functional limitations |
| [VALIDATION.md](VALIDATION.md) | Latest tested revision/delta, commands, results and unverified scope |
| [ROADMAP.md](ROADMAP.md) | Milestones and acceptance criteria |
| [TODO.md](TODO.md) | Open actionable work |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Contributor setup and review expectations |
| [BRANCHING.md](BRANCHING.md) | Shared branch/version convention |
| [CI.md](CI.md) | Local/hosted quality commands, matrix and evidence consumption |
| [VERSIONING.md](VERSIONING.md) | aiplane version mirrors, release commands, App configuration and recovery |
| [GitHub setup](docs/development/github-policy-setup.md) | Hosted rules and activation setup |
| [Agent guidance](docs/project/agent-guidance.md) | Safe resumption and protected inputs |
| [docs/index.md](docs/index.md) | Navigation |
| [Architecture](docs/architecture.md) | Runtime components and resource ownership |

Legal and community procedures remain in LICENSE, NOTICE.md, SECURITY.md,
CODE_OF_CONDUCT.md and SUPPORT.md. Runtime instructions stay at their loader-defined paths.

When policy changes, edit its owner and link from summaries. Do not copy operational
rules, dated test counts or hosted activation state into README, STATUS or HANDOFF.
Replace current validation when requalifying; use Git history for older validation
evidence instead of maintaining a documentation-history directory. Historical review
reports likewise belong in Git history; retain current decisions and tasks in their
authoritative documents.
