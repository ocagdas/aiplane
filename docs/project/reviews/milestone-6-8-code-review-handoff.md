# Milestones 6–8 Code Review Handoff

## Purpose

This handoff converts the detailed read-only review of deployment rendering, workflow readiness, runtime packaging, stack exports, schemas, and tests into implementable tasks. It does not authorize or begin any code change.

The reviewed worktree passed 652 tests with 3 optional skips and 23 subtests, plus Ruff formatting/lint and profile/CLI smoke checks. Those mechanical gates are healthy, but they do not cover several semantic contradictions described below.

## Guardrails

- Keep Aiplane an environment doctor and configuration compiler. Do not turn these tasks into hidden infrastructure, runtime, or agent execution.
- Preserve render/plan/doctor-first behavior and explicit review before mutation.
- Prefer one authoritative runtime specification over additional copied maps.
- Treat unsupported combinations as explicit validation errors rather than silently ignoring settings.
- Do not add compatibility shims solely for the pre-1.0 interface.
- Keep every behavior change aligned across CLI help, schemas, user documentation, the unified project plan, and focused tests.
- Do not mark the three milestones complete again until the high-priority acceptance criteria below pass.

## Confirmed findings

1. Stack setup and framework export accept incompatible model/runtime pairs. A llama.cpp/GGUF model paired with vLLM was accepted and exported.
2. MLX, Docker Model Runner, and LM Studio bundle settings use port 8000 while their launch manifests use 8080, 12434, and 1234. Stack exports also default MLX and LM Studio to port 8000 instead of their provider endpoints.
3. The `local_runtime` workflow can report `ready` while no selected runner is actually usable. Several prerequisite checks report tools such as Python/pip rather than runtime installation, platform compatibility, or service readiness.
4. Bundle options such as cache volume, environment references, authentication references, GPU selection, context, and tensor parallelism are accepted for modes/runners that do not apply them.
5. The llama.cpp Docker starter builds an image without `llama-server`, a model, or an entrypoint, but emits build/run commands as though it were runnable.
6. Cloud workflow readiness treats OpenTofu, Terraform, and Pulumi as alternatives, but deployment rendering emits only HCL and always recommends `tofu` commands.
7. Model aliases containing spaces or colons are accepted but generate invalid Docker image tags.
8. Runtime recipes are deterministic text but rely on `latest` images and unpinned pip/Conda dependencies, so the current “reproducible” wording is stronger than the implementation.
9. `--required-only` still probes optional tools through workflow readiness, and filtered summaries mix global and workflow-specific requirement labels.
10. Local VM readiness checks Vagrant but not an actual provider, while generated files hardcode VirtualBox. A disposable `vagrant validate` failed when no provider was installed.
11. Cloud artifacts are useful scaffolds but not directly runnable plans: the VM HCL has no resources, Packer has no source/build, and the Ansible inventory has no active host.
12. Bundle and deployment schemas do not enforce cross-field invariants such as checksum/file equality or `selected_file` membership.
13. Native bundle `commands` contains `review runtime-launch.json`, which is an instruction rather than an executable command.
14. The project plan and user documentation currently overstate completion around conventional ports, applied settings, and reproducibility.
15. Runtime facts are duplicated across definitions, launch evidence, bundle code, and stack defaults, directly enabling endpoint/port drift.

## Actionable tasks

### Task 1: Validate stack model/runtime compatibility

Priority: fix first.

Scope:

- Add a single compatibility check used by stack setup and every export path that depends on the primary runtime/model pair.
- Decide whether invalid setup is rejected immediately or may be saved only as an explicitly unresolved plan. Do not silently export it as ready configuration.
- Keep managed-service endpoint ownership distinct from self-managed runtime compatibility.

Acceptance criteria:

- A GGUF/llama.cpp-only model cannot be exported through a vLLM stack without an explicit compatible mapping.
- Valid managed-service and self-managed stacks continue to work.
- Error output names the model alias, requested runtime, and supported alternatives.

Required tests:

- Compatible and incompatible setup cases.
- Framework, Continue, OpenAI-compatible, Dockerfile, Conda, and Compose export behavior for an invalid pair.
- Managed-service role regression coverage.

### Task 2: Establish one authoritative runtime endpoint/port specification

Priority: fix first.

Scope:

- Consolidate conventional endpoint, port, protocol, substrate, cache target, launch renderer, and supported bundle modes into one typed runtime specification or a narrowly composed set of typed records.
- Make runtime launch manifests, bundle settings, stack defaults, provider defaults, and doctors consume that source.
- Remove or mechanically derive duplicated maps.

Acceptance criteria:

- MLX resolves to 8080, Docker Model Runner to 12434, and LM Studio to 1234 everywhere unless the profile explicitly overrides them.
- Bundle settings, launch manifests, stack plan/export, and provider endpoint output agree.
- No self-managed provider default is discarded merely because it is not a managed service.

Required tests:

- Table-driven parity test for all six runners covering endpoint, port, protocol, substrate, and health path.
- Override precedence tests.
- Stack export endpoint assertions for every primary runner.

### Task 3: Redesign local-runtime workflow readiness around a selected or any-of runner

Priority: fix first.

Scope:

- Separate prerequisite availability, runtime installation, platform compatibility, service health, and model availability.
- Allow a focused runner selection, or model the six runners as an explicit any-of group.
- Make workflow readiness consume runtime results rather than tool rows alone.
- Ensure GUI-managed and unsupported-platform runners are not reported ready merely because they have no required CLI checks.

Acceptance criteria:

- `environment doctor --workflow local_runtime` cannot report ready when no usable runner is selected/available.
- MLX on non-Apple platforms is incompatible or plan-only, not ready.
- LM Studio requires detectable/configured server evidence; Docker Model Runner requires a functional `docker model` surface.
- Text and JSON output agree on readiness.

Required tests:

- Zero, one, and multiple available runners.
- Platform-specific MLX behavior.
- Docker installed with and without the `model` command.
- LM Studio absent, installed, and configured endpoint cases.

### Task 4: Make bundle settings mode- and runner-aware

Priority: fix first.

Scope:

- Define which settings each runtime/mode supports.
- Reject unsupported settings with precise errors, or render them into the selected artifact/launch contract.
- Distinguish executable commands, manual review steps, and informational notes structurally.

Acceptance criteria:

- No accepted setting is silently ignored.
- Conda/native environment and authentication references are either represented correctly or rejected.
- Context and tensor-parallel options are accepted only where the runner applies them.
- `commands` contains executable commands only; review instructions have a separate field.

Required tests:

- Table-driven accepted/rejected setting matrix for all six runners and every supported mode.
- CLI tests for `selected-file`, `launch-json`, explicit incompatible formats, and error messages.
- Secret-reference tests confirming values are never embedded.

### Task 5: Resolve llama.cpp Docker support honestly

Priority: fix first.

Scope:

Choose one:

- produce a runnable, pinned llama.cpp container with a defined model mount and entrypoint; or
- remove Docker from llama.cpp supported bundle modes until that recipe exists.

Acceptance criteria:

- A supported llama.cpp Docker bundle starts `llama-server` with the documented model mount and port; or the mode fails before rendering.
- No generated build/run command targets an image that only contains comments and curl.

Required tests:

- Dockerfile semantic assertions.
- Optional build smoke behind an explicit environment flag if a real container build is too heavy for default CI.

### Task 6: Align IaC readiness, renderer selection, and next commands

Priority: fix first.

Scope:

- Add an explicit selected IaC implementation or derive it deterministically from profile configuration.
- Emit `tofu` commands for OpenTofu, `terraform` commands for Terraform, and a genuine Pulumi starter/preview path for Pulumi.
- Do not claim Pulumi satisfies readiness when no Pulumi artifact can be generated.

Acceptance criteria:

- The workflow-selected tool, emitted artifact family, and `next_commands` agree.
- OpenTofu remains the default where no explicit choice exists.
- Terraform-only and Pulumi-only workflows receive usable, tool-appropriate previews.

Required tests:

- OpenTofu, Terraform, and Pulumi selection cases for VM and Kubernetes targets.
- Missing selected tool remediation.
- No apply/up command emitted by default.

### Task 7: Sanitize or derive Docker image tags independently from model aliases

Priority: fix first.

Scope:

- Preserve the original model alias as metadata.
- Generate a validated Docker tag component or reject aliases that cannot be represented.
- Detect collisions if normalization is used.

Acceptance criteria:

- Spaces, colons, uppercase edge cases, and long aliases cannot produce invalid Docker references.
- Shell quoting is not treated as Docker reference validation.

Required tests:

- Valid, invalid, normalized, collision, and length-limit cases.

### Task 8: Correct workflow filtering and summary semantics

Priority: next.

Scope:

- Ensure `--required-only` does not probe optional tools or optional health checks.
- Report alternative groups as satisfied when any member is installed, without counting unselected alternatives as workflow failures.
- Make filtered summary counts use contextual `mandatory`, `alternative`, and `optional` labels.
- Display workflow readiness in human text output.

Acceptance criteria:

- Optional tools are neither probed nor counted under `--required-only`.
- A cloud workflow with OpenTofu installed does not report Terraform and Pulumi as unmet requirements.
- Text and JSON summaries agree.

Required tests:

- Mock call-count assertions proving optional probes are skipped.
- One-of alternative permutations.
- Text presenter golden/contract tests.

### Task 9: Add VM-provider awareness

Priority: next.

Scope:

- Represent the chosen Vagrant provider in the target/workflow contract.
- Check the provider executable/capability, not only Vagrant.
- Render provider-specific Vagrant settings rather than always hardcoding VirtualBox.

Acceptance criteria:

- Vagrant without a usable provider is not reported ready.
- VirtualBox, libvirt, Hyper-V, and other intentionally supported paths are distinguishable.
- `vagrant validate` succeeds in supported synthetic/live environments.

Required tests:

- Vagrant present/provider absent.
- At least two provider render paths.
- Optional live `vagrant validate` test isolated from default CI where necessary.

### Task 10: Separate scaffolds from executable deployment plans

Priority: next.

Scope:

- Add artifact readiness metadata such as `scaffold`, `validate_ready`, or `plan_ready`.
- Do not recommend `tofu plan`, Packer validation/build, or Ansible execution until required placeholders are resolved.
- Surface unresolved variables, hosts, resource blocks, image references, and provider credentials explicitly.

Acceptance criteria:

- Every `next_command` is appropriate for the rendered artifact's readiness level.
- Azure VM inventory does not appear runnable while its host is commented out.
- Required unresolved inputs are machine-readable.

Required tests:

- Readiness and unresolved-input assertions for every deployment workflow branch.
- Ansible inventory/playbook syntax validation in a disposable directory.
- HCL/Packer/Vagrant validation where the relevant external validator is available.

### Task 11: Strengthen bundle and deployment schema contracts

Priority: next.

Scope:

- Require non-empty checksum maps.
- Enforce as much cross-field consistency as JSON Schema supports.
- Add application-level validation for invariants JSON Schema cannot express cleanly.
- Validate representative generated payloads in tests rather than only parsing schema JSON.

Acceptance criteria:

- Missing checksum, incorrect checksum, missing selected file, unsupported mode, and mismatched file/checksum keys are rejected.
- Schema/package discovery works from an installed wheel.

Required tests:

- Positive payload validation for every bundle mode and deployment workflow.
- Negative contract fixtures for each invariant.

### Task 12: Define honest reproducibility levels

Priority: next.

Scope:

- Distinguish deterministic recipe output from reproducible builds and immutable runtime locks.
- Pin image digests/package versions where full reproducibility is claimed.
- Record unresolved runtime versions and dependency locks explicitly when pinning is unavailable.

Acceptance criteria:

- Documentation and JSON state whether evidence is recipe-deterministic, version-pinned, or digest-locked.
- `latest` and unpinned dependencies cannot be described as a reproducible build.
- Runtime and model artifact provenance remain separate.

Required tests:

- Reproducibility-level derivation.
- Complete and incomplete lock examples.
- Documentation contract assertions for terminology.

### Task 13: Replace shallow cross-product tests with behavioral contracts

Priority: next.

Scope:

- Keep useful table-driven coverage, but assert compatibility, endpoint, protocol, artifact content, readiness, and unsupported combinations.
- Avoid proving parity solely by assigning one model every supported runtime and checking metadata round-trips.

Acceptance criteria:

- Each primary runner has at least one realistic compatible fixture.
- Invalid runner/model combinations fail or remain explicitly unresolved.
- Framework exports assert endpoint and role readiness, not only names.

Required tests:

- Six-runner realistic fixture matrix.
- Runner/orchestrator protocol compatibility cases.
- Runtime-specific bundle content and checksum verification.

### Task 14: Reconcile documentation and milestone status after fixes

Priority: final task.

Scope:

- Correct the stale deploy-plan note about runtime manifests.
- Align README, runtime map, tools guide, cloud guide, manual checklist, CLI help, and unified project plan with actual support.
- Keep live-provider/platform evidence separate from deterministic contract completion.

Acceptance criteria:

- No documentation claims that ignored options are applied.
- “Reproducible” is used only at the implemented evidence level.
- Milestone status reflects unresolved live evidence and any deliberately deferred runner modes.

Required tests/checks:

- Documentation command coverage tests.
- Tracked documentation hygiene scan.
- Manual copy/paste smoke for the documented primary paths.

## Recommended execution order

1. Tasks 1–4: compatibility, authoritative runtime facts, readiness, and option semantics.
2. Tasks 5–7: runner/IaC/Docker-tag correctness.
3. Tasks 8–10: workflow summaries, VM providers, and artifact readiness.
4. Tasks 11–13: schemas, reproducibility levels, and stronger behavioral tests.
5. Task 14: documentation and milestone reconciliation after behavior stabilizes.

Tasks 1–7 should be treated as blockers before calling milestones 6–8 implementation-complete.

## Completion gate

When implementation is authorized and finished, run at minimum:

```bash
python -m ruff format --check src tests
python -m ruff check src tests
python -m pytest -q
python -m aiplane profiles validate local-dev
python -m aiplane environment doctor --required-only
python -m aiplane environment doctor --required-only --format json
python -m aiplane environment doctor --workflow local_runtime --format json
python -m aiplane tools matrix --workflow cloud_vm
python -m aiplane deploy render --target azure_gpu_vm
```

Also run disposable syntax validation for generated Ansible, HCL/Packer, and Vagrant artifacts where their external validators are available. Record platform-specific live evidence separately from synthetic contract results.
