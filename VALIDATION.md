# Current validation

## AP3 completion — 2026-10-18

Final local Python 3.13.14 gate passed formatting, Ruff, repository conformance and **1109 tests, 9 opt-in skips, 44 subtests** (41.15 seconds). Command: `PATH="$PWD/.venv/bin:$PATH" make check PYTHON=.venv/bin/python PYTEST_ARGS='-m pytest -q -n 4 --dist loadfile'`. Log: `/tmp/aiplane-ap3-final.log`. The installed-wheel test executes the shipped evaluator and review CLI from an unrelated workspace with no source import path. Focused benchmark/review/evidence/throughput checks passed 77 tests; log `/tmp/aiplane-ap3-focused.log`. Documentation/security and runtime contract checks passed 37 tests; log `/tmp/aiplane-ap3-docs.log`. Product Markdown links and patch whitespace passed. High-confidence credential-pattern scan found no matches across 62 changed/new product files.

AP3 adds 38 cases: retained full answers across repeats, numeric/pass and pairwise review, source/setup/output/rubric mismatches, duplicate/missing/invalid ratings, preview/write boundaries, external native-result import, malformed/fractional grader scores, timeout/nonzero-exit evidence and secret refusal. Command graders use isolated transient work files. Human review files remain separate from measurement scores and controlled metric leaders.

Actual CLI qualification passed suite validation, a 20-case non-executing preview, independent evaluator v1.0 execution/native result retention, measurement preview/import, numeric review preview/export/import, pairwise review/export/import and changed-source refusal. Log: `/tmp/aiplane-ap3-cli.log`; temporary artifacts: `/tmp/aiplane-ap3-cli-lc6k0ao6`. The supplied answers and entered ratings are synthetic. The fixture produces 18/20 correct category/urgency answers by construction, not by model inference. Request timing/token fields remain unknown. No speculative native-file converter was added because this producer writes the existing contract. Third-party formats remain unqualified until an actual needed file demonstrates a conversion gap.

No live inference, real human-rating study, cloud request, deployment or recovery drill was performed. Those trials remain AP6. AP0/AP1/AP3 are complete locally; AP2 remains removed; AP4 is next. All changes remain uncommitted and publication is owner-only.

## AP2 removal — 2026-10-18

The generic AP2 benchmark wrapper subsystem is removed by owner direction. Deleted its three runtime modules, three protocol schemas, wrapper example/suite, dedicated producer fixture/test module and two protocol-specific guides. Removed wrapper CLI/MCP surfaces, profile/suite selection settings, packaging entries and AP2-only measurement extensions. No local profile/template/config referenced the removed protocol or selection settings. Existing provider clients, native suites/command graders, measurement import and AP1 request/timing/comparison safeguards are preserved.

Final local Python 3.13.14 gate passed formatting, Ruff, repository conformance and **1071 tests, 9 opt-in skips, 44 subtests** (40.00 seconds). Command: `PATH="$PWD/.venv/bin:$PATH" make check PYTHON=.venv/bin/python PYTEST_ARGS='-m pytest -q -n 4 --dist loadfile'`. Log: `/tmp/aiplane-ap2-removal-final.log`. Focused retained-feature/MCP checks passed 93 tests; documentation checks passed 11. Installed-wheel packaging ran in the full gate. The reduced count reflects deleting AP2's 47 dedicated cases, not disabling retained tests.

CLI/MCP checks confirmed native benchmark preview, existing vendor command templates, measurement preview/import and calibration planning remain, while the removed wrapper commands, selection flag and two MCP tools are absent. Log: `/tmp/aiplane-ap2-removal-cli.log`. No external benchmark, live model call, dependency install or deployment ran. AP0/AP1 remain complete; AP2 is removed rather than deferred. AP3 is narrowed to independently produced results and task/manual review, with converters added only for a demonstrated file-format need. All work remains uncommitted.

## Withdrawn experiment — AP2

The AP2 experiment previously passed 1118 tests on October 17, but the owner removed it on October 18 to reduce scope. Its wrapper protocol, process manager, configuration, commands, schemas, examples and 47 dedicated cases are no longer product features. Those earlier test results are historical; the current removal gate above owns present evidence. Existing AP1 model-call and measurement behavior is retained.

## AP0/AP1 completion — 2026-10-17

Final local Python 3.13.14 gate passed formatting, Ruff, repository conformance and **1071 tests, 9 opt-in skips, 44 subtests** (39.50 seconds). Command: `PATH="$PWD/.venv/bin:$PATH" make check PYTHON=.venv/bin/python PYTEST_ARGS='-m pytest -q -n 4 --dist loadfile'`. Log: `/tmp/aiplane-ap1-final.log`. The prior throughput gate had 1032 passing tests; AP1 adds 39 cases covering actual request controls, the full runner/catalog/dispatcher/HTTP chain, timeout propagation, invalid/unsupported settings, rejected requests without retries, saved failure/preview evidence, workload digests and comparison controls/refusals. Installed packaging/schema and documentation coverage ran in the full gate.

All four adapters have captured-request fixtures. Comparison fixtures change workload/rubric, model weights/tokenizer, runtime build/settings, hardware/software, route/cache/concurrency/tools, harness or metric definitions. Missing controls, preview/error runs and incorrect submission evidence cannot produce leaders. Same alias/different weights is distinguished. Malformed runtime settings produce a warning rather than crashing. Built-in smoke records identify the installed measurement code, preserve unknown host/runtime identity and remain uncontrolled.

Representative CLI suite validation, non-executing preview and controlled synthetic comparison passed using temporary fixture profiles; outputs are `/tmp/aiplane-ap1-suite-cli.json`, `/tmp/aiplane-ap1-preview-cli.json` and `/tmp/aiplane-ap1-compare-cli.json`. Root/aiplane handovers validated. Patch whitespace and a high-confidence credential-pattern scan of 48 changed/new product files passed without findings. All changes remain uncommitted.

This closes AP0's selected-venv baseline and AP1's implementation acceptance. Evidence uses deterministic fixtures, not live inference. Server compliance with submitted settings, real external benchmark results, hosted/platform qualification and complete agent-task execution are not established. AP2 was planned at that point and was subsequently removed on October 18; live model trials remain AP6.

## Separate server/client throughput and available-value average — 2026-10-17

Final local Python 3.13.14 gate passed formatting, Ruff, repository conformance and **1032 tests, 9 opt-in skips, 44 subtests** (40.14 seconds). Command: `PATH="$PWD/.venv/bin:$PATH" make check PYTHON=.venv/bin/python PYTEST_ARGS='-m pytest -q -n 4 --dist loadfile'`. Log: `/tmp/aiplane-throughput-final.log`.

Deterministic response/clock fixtures verify server 100 tokens / 2 seconds = 50 t/s, client 100 tokens / 2.5 seconds = 40 t/s, combined average 45 t/s; server-only/client-only fallback; neither present; real zero; invalid/missing duration/count; streamed first-content timing; usage-only endpoints; imported-average rejection; repeat-summary source means/counts; and grouping different available-source combinations separately. The 28 added cases ran in the full suite. Installed wheel/schema coverage ran as part of that gate.

This is local synthetic correctness evidence. No live inference, provider account, model benchmark, cloud service or external harness was exercised. At this earlier gate, submitted decoding and broader setup/metric comparison checks were still pending; the AP1 section above owns their later evidence. The ambiguous old per-run `tokens_per_second` field is refused rather than automatically relabelled; existing files are preserved and invalid local comparison records become warnings.

## Setup refresh — 2026-10-17

Implemented `scripts/setup_env.sh --action refresh` for local/native, existing venv/Conda and Docker image builds. Focused setup/Python/runtime suites passed **80 tests**; the full Python 3.13.14 gate passed format, Ruff, repository conformance and **1004 tests, 9 opt-in skips, 44 subtests**. Full command: `PATH="$PWD/.venv/bin:$PATH" make check PYTHON=.venv/bin/python PYTEST_ARGS='-m pytest -q -n 4 --dist loadfile'`. Logs: `/tmp/aiplane-refresh-focused.log`, `/tmp/aiplane-refresh-full.log`. Final documentation contracts passed 39 tests after docs synchronization.

Actual `--mode venv --action refresh --dev` completed against the local venv and `pip check` passed (`/tmp/aiplane-refresh-venv-live.log`). Actual editable/source-linked Docker dependency-image refresh with `--dev --docker-image aiplane:refresh-check-20261017` built successfully, including declared dev pins and `pip check` (`/tmp/aiplane-refresh-docker-live.log`). Source CLI `--version` then passed in that image with the checkout mounted read-only, no network and a non-root user (`/tmp/aiplane-refresh-docker-cli.log`). The image is retained under that test tag; normal image tags/containers were not restarted or replaced.

Synthetic command-boundary tests cover all Python selections, explicit upgrades, snapshots, missing environments, failed dependency checks, old Python refusal, quoted paths/extras, unchanged profiles, Docker options, generated requirement contents and non-writing previews. Native/Conda mutations, live Docker static-snapshot execution, hosted CI and non-Linux setup execution were not qualified. No models, providers, external agent harnesses or benchmark workloads ran. The sdist test verifies Docker build-context exclusions are shipped.

## AP0–AP6 planning update — 2026-10-17

Documentation only: roadmap milestones, task checklist, bounded preview exception and resumption links. Existing documentation contracts passed **39 tests**; changed local Markdown links, workspace/aiplane handovers and patch whitespace passed. No runtime behavior changed, no new benchmark ran, and none of AP0–AP6 is marked complete from this planning work. The full code suite was not repeated for this document-only change.

## Benchmark design follow-up — 2026-10-17

Source/documentation review only; no benchmark runtime change or live inference. Documentation contracts passed **39 tests** after recording timing/decoding limitations and the proposed runner protocol. Local design links, handover validation and `git diff --check` passed. Earlier full-gate evidence below applies to the audit code changes; it does not qualify unimplemented runner adapters.

## Correctness audit — 2026-10-17

Restricted-YAML regressions covered duplicate keys, malformed nesting, quoted comments/URL fragments, numeric round-trip and colon-containing keys. Shared ensemble/profile tests passed (100); documentation contracts passed (39). Final `make check` passed formatting, Ruff, repository conformance and **971 passed, 9 skipped, 44 subtests passed**, using four file-scheduled workers on Linux/Python 3.12.12. Log: `/tmp/toolbox-aiplane-final-20261017.log`. An earlier run failed one purpose-wording consistency test; the wording was corrected before this successful full rerun. No model or cloud calls were made.

[CI.md](CI.md) owns check commands; [STATUS.md](STATUS.md) owns capabilities.

## Pre-commit qualification (8 October 2026)

The ensemble increment and retained CAS naming/ignore updates passed
`PATH=/tmp/aiplane-ensemble-dev/bin:$PATH make check` on Linux/Python 3.12.12:
formatting, Ruff, repository conformance, **960 passed, 9 skipped, 44 subtests passed**.
Log: `/tmp/aiplane-precommit-2026-10-08.log`. Changed/new product files passed a
credential-pattern scan and patch whitespace checks. This is local qualification;
no live provider/agent execution or new hosted/platform result is established.
Package version remains 0.2.26; current main reconciliation and release qualification
remain separate from committing this increment.

## Ensemble configuration validation (4 October 2026)

Uncommitted ensemble changes on the shared checkout (HEAD `ec31867`; branch `dev/mvp_0.2.27` at completion) passed local Linux checks using Python 3.12.12 and Ruff 0.16.10 in the disposable `/tmp/aiplane-ensemble-dev` environment. The owner changed the branch/baseline externally during the session; no assistant Git writes occurred. The repository `.venv` was not changed.

- `PATH=/tmp/aiplane-ensemble-dev/bin:$PATH make check`: formatting, lint and shared repository conformance passed; **960 passed, 9 skipped, 44 subtests passed**. Log: `/tmp/aiplane-ensemble-check.log`.
- Ensemble, governance and contract subset: **88 passed**. The 33 ensemble cases cover role resolution, endpoint isolation, native namespaces, policy, unsafe bindings, duplicate fields, dependency cycles, deterministic manifests, CLI exit codes and schema conformance.
- Documentation/contract verification after final guide clarifications: **48 passed**. Log: `/tmp/aiplane-ensemble-doc-check.log`.
- Installed-wheel regression includes the harness catalog command and packaged ensemble schema. Representative source CLI `harnesses show/models` and `ensembles plan/doctor/export` ran against a synthetic disposable profile, with artifacts under `/tmp/aiplane-ensemble-demo`. Doctor returned the documented qualification-required exit code 2. The demo model ID is synthetic, not a claim of an installed/available model.
- Changed-document local links, patch whitespace and credential-pattern review passed. Catalog sources were reviewed; no external agent process, model call, account entitlement check or real collaboration was exercised.

No runner adapters or native framework exporters are included. Windows/macOS, live cloud/local combinations, harness version compatibility and tool calling remain unqualified for this increment. An initial full run found missing CLI help categorization; that defect was corrected before the successful gate.

## Earlier working-tree validation (12 September 2026)

On 12 September 2026, the review changes based on `9b25137362e079c35371c7aff98998e5acb98bd8` passed local Linux validation:

- `make check`: formatting, Ruff, shared repository conformance, and **927 passed, 9 opt-in skips**, using four file-scheduled workers. Log: `/tmp/aiplane-review-check.log`; JUnit: `/tmp/aiplane-review-tests.xml`.
- Packaging regression builds an sdist, builds its wheel, and installs into an isolated environment. Every published documentation path is listed and readable through MCP from an unrelated workspace; complete skill files are present and private strategy files excluded.
- Real pip, pipx, and uv installation, replacement, and uninstall checks passed, including MCP stdio documentation reads and matching CLI/server versions. Log: `/tmp/aiplane-review-channels.log`; built artifacts: `/tmp/aiplane-review-dist`.
- Profile validation and required-only environment doctor passed in text and JSON with temporary shipped profiles. Logs: `/tmp/aiplane-review-profile.log`, `/tmp/aiplane-review-doctor.log`, `/tmp/aiplane-review-doctor-json.log`.
- Skill validation, changed-document local links, patch whitespace checks, and a credential-pattern scan passed. HTTP metadata tests use synthetic transports; no live provider requests were required.

These are uncommitted working-tree results. Windows/macOS and hosted publication checks have not run on this patch. The existing OS/channel workflow will exercise the expanded installed-help checks when the owner publishes the branch. The earlier hosted results below remain baseline evidence only.

## Earlier qualified revision

On 11 September 2026, commit `b843589b331716fbc7e2f799ebc3c7a40db257f6`
passed local and hosted validation. The working tree was clean when testing began;
the only subsequent changes from this task update validation evidence and the backlog.

- Local Linux/Python 3.13.14: `make check` passed formatting, Ruff, shared conformance
  and the isolated-profile suite: **918 passed, 9 opt-in skips**. Tests used four
  file-scheduled workers. Log: `/tmp/aiplane-current-check.log`; JUnit:
  `/tmp/aiplane-current-tests.xml`. Declared dependencies were installed in the
  disposable `/tmp/aiplane-validation-env` environment. An initial missing Ruff
  executable in that environment was corrected before the successful run.
- [Branch-push CI](https://github.com/ocagdas/aiplane/actions/runs/34653187556)
  and [pull-request CI](https://github.com/ocagdas/aiplane/actions/runs/34653190347)
  both succeeded. The push run's `quality-gate/ci-gate.json` reports `go=true` for
  the exact commit and run ID; `scripts/verify_quality_evidence.py` verified it.
- Hosted Linux/Python 3.11: **917 passed, 10 skipped**, plus formatting, Ruff,
  shared conformance, workflow-pin validation and checksum-pinned actionlint 1.7.12.
  The additional skip requires ripgrep, which was unavailable on that runner;
  that test passed locally. Hosted Python 3.12 and 3.13 compatibility checks each
  passed **40 tests**, including actual wheel packaging checks.
- All **nine OS/channel combinations** passed real wheel installation, replacement
  and uninstall: Linux, macOS and Windows, each using pip, pipx and uv. These are
  CI-built wheel checks, not verification of published release downloads.
- Opt-in synthetic catalog benchmarks at 1k, 10k and 100k entries: **3 passed**.
  Log: `/tmp/aiplane-current-performance.log`; JUnit:
  `/tmp/aiplane-current-performance.xml`.
- Opt-in installed external validators: **1 passed, 5 skipped**. Ansible inventory
  and playbook syntax validation passed. OpenTofu, Terraform, Packer and Pulumi
  were unavailable; VirtualBox's kernel module was not loaded. Log:
  `/tmp/aiplane-external-validators.log`.
- Profile validation and required-only environment doctor in text and JSON formats
  passed with temporary shipped profiles. No live credentials or provider requests
  were needed. Local smoke logs: `/tmp/aiplane-current-profile.log`,
  `/tmp/aiplane-current-doctor.log`, `/tmp/aiplane-current-doctor-json.log`.

## Earlier public baseline

The public [v0.2.0 release](https://github.com/ocagdas/aiplane/releases/tag/v0.2.0) has a wheel, source archive, and checksum manifest. An earlier [published-release verification run](https://github.com/ocagdas/aiplane/actions/runs/29414203549) passed all nine OS/channel jobs. This establishes earlier public-path evidence, not qualification of the current publication implementation or this working tree.

## Unverified scope

Exact-tag reusable release qualification, App version publication, live providers,
published asset attestations and independent-user trials remain separate gates.
The version job was intentionally skipped on the development branch and PR; these
successful runs do not establish publication readiness. The five unavailable external
validators remain unqualified. See [TODO.md](TODO.md) and
[hosted setup](docs/development/github-policy-setup.md).

No commits, pushes, tags or releases were performed by this task.
