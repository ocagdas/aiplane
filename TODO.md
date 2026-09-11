# Open work

This is the sole actionable backlog. Completed work lives in [STATUS.md](STATUS.md).

## Repository standardization hosted gates

- Run exact-tag reusable release qualification on Linux, macOS and Windows; branch/PR CI has passed for the revision recorded in [VALIDATION.md](VALIDATION.md).
- Once Quality gate exists, migrate the required check from Release gate and prove blocked merges without weakening branch/tag protection.
- Prove the existing GitHub App and exact-tip atomic publication in hosted CI. No credential names were changed.
- Complete public assets, attestations and independent-user evidence below. No publication was performed during this migration.

## Product Adoption Backlog

This is the current product and adoption priority list. Maintain remaining work here and current scope decisions in [adoption decisions](docs/project/adoption-decisions.md).

See [adoption decisions](docs/project/adoption-decisions.md) for scope evaluation.

### Prioritized Engineering and Adoption Backlog

#### P0 — Developer preview coherence

2. **Publish the first complete developer-preview release artifact — selective publication automation implemented; hosted app proof and complete public assets pending.** A dedicated short-lived GitHub App token owns patch commits/tags, PR version edits and non-increasing versions are rejected, patches remain CI artifacts unless manually selected, and intentional minor/major versions publish automatically with complete wheel/source/checksum validation. Completion: a public immutable release URL contains exactly one wheel, one source distribution, `SHA256SUMS`, supported-platform/upgrade/rollback guidance, and metadata matching its tag.
3. **Verify the public no-clone path — cross-platform workflow implemented and automatically dispatched after publication; successful public run pending.** `Verify published release` downloads the actual named release on Linux, macOS, and Windows, verifies the portable manifest, exercises pip/pipx/uv independently, and uploads canonical sanitized evidence. Final evidence still requires a complete P0.2 release and a successful hosted run. Completion: the nine evidence records identify release URL, checksum, tag commit, commands, results, and platform limitations.
4. **Make CI mandatory on the release path — repository implementation and exact settings guide complete; rulesets active; hosted App and blocked-merge proof pending.** The PR UI shows `CI / Quality gate` while the ruleset requires the exact job name `Quality gate`; the guide covers reviews, main-only force/deletion protection, the narrow `aiplane-versioning` bypass, tag immutability, and audit commands. The hosted rulesets are active; completion still requires a blocked-merge test.
5. **Standardize external-trial evidence — standard implemented; trial adoption pending.** The canonical JSON template, recording guidance, sanitizer/shape validator, and regression tests cover one sanitized record format for commit/version, OS, installation channel, Python/runtime/model, start state, commands, elapsed time, first failure, assistance, written files, final outcome, and participant feedback. Completion: every P0 workflow trial uses the same record and distinguishes rehearsal from independent completion.

**P0 completion gate.** P0 closes only when both gate requirements pass:

- **Three reproducible demonstrations:** Local Ollama coding, laptop-to-remote-GPU, and local-only/privacy-policy workflows. Completion: independent users reproduce each from a clean environment.
- **Final README and documentation consistency sweep:** Re-read README, package metadata, top-level and core-command help, user documentation entrypoints, examples, strategy, launch review, and roadmap after all numbered P0 work is complete. Remove stale breadth, maturity drift, duplicated guidance, and any claim not backed by a tested workflow. Completion: one coherent product promise, command hierarchy, installation path, and maturity statement across every public entrypoint. Re-run public example, link, help, and contract checks after the sweep. This sweep was run once after the earlier implementation milestones and must be repeated after the user-testing demonstrations; the interim pass does not close this gate. Current local evidence is recorded in [VALIDATION.md](VALIDATION.md).

#### P1 — Prove repeated value

9. Run the six clean-environment trials defined by the public demo plan and record failures by stage.
10. Recruit external design partners, targeting ten unaided successful onboardings before public beta.
11. Measure opt-in activation and recurrence: first useful export, second integration, profile replay, seven/thirty-day return, and support points.
18. Decide the public future of stacks through observed user tests; simplify, keep advanced, or remove from the public model based on evidence.

#### P2 — Differentiated core after adoption evidence

23. Build evidence-backed model placement after the P0 gate and initial P1 trial evidence. Define versioned model-variant, placement-evidence, YAML/canonical-JSON benchmark-suite, artifact-lock, and external-runner-launch schemas; resolve quantization, format, total/active parameters, configured context, KV-cache assumptions, memory pool, execution/offload mode, headroom, and usable context before ranking; standardize repeated throughput/TTFT/latency/token and stochastic task-quality measurements with decoding settings, robust summaries, uncertainty, runtime settings, and privacy-conscious environment fingerprints; calibrate only from comparable local evidence; keep task-quality, placement, performance, and policy separate; support evidence-backed role-routing comparisons with alternatives; expose source, confidence, sample count, uncertainty, and near-miss remedies; and preserve deterministic behavior when measurements are absent. Record separate go/no-go research decisions for node REST scheduling and community benchmark exchange. Do not promote this work into the primary onboarding cut until the breadth freeze closes.
27. Maintain a neutral, versioned compatibility knowledge base separable from shell execution.
28. Create a maintenance budget for advanced/experimental surfaces and archive those without use or ownership.

#### P3 — Low-risk maintainer hardening


### Monetization Validation Track

#### M0 — Services now, without weakening open source

- Package a fixed-scope “Local and Hybrid AI Development Environment Standardisation” engagement: inventory, compatibility report, approved profiles, Continue/Aider exports, remote endpoint plan, repository privacy policy, CI doctor checks, team documentation, and up to two adapters.
- Validate pricing through real proposals and paid discovery, not generic SaaS benchmarks.
- Track whether customers pay for repeatability/governance or only installation help; this determines product direction.
- Keep discovery, profiles, validation, doctor, recommendation, deterministic exports, drift, basic local policy/audit, and community adapters fully useful in open source.

#### M1 — Paid team prototype, gated

Start only after two organizations replay approved profiles across at least three machines and request paid central governance. Candidate scope: central profile registry/history/promotion, shared templates/policy, approvals, fleet/drift reporting, central audit, signed profiles, and integration compatibility management.

Go gate: two paid pilots or signed intent, named budget owners, recurring governance need, and delivery without becoming a gateway or infrastructure platform.

#### M2 — Enterprise, later and evidence-led

Potential self-hosted registry/control service, SSO, SCIM, SIEM export, air-gapped updates, signed policy/profile bundles, retention, compliance evidence, private adapters, and support agreements. None is scheduled until M1 proves demand.

### Product Metrics and Decision Gates

North star: approved profiles successfully replayed on more than one machine and used by more than one external integration.

Developer-preview exit: standard install works; five unaided external users complete the main workflow; one integration is verified on Linux, macOS, and Windows; doctor/export contracts are stable; docs match behavior; no critical unsafe mutation or secret leak is open.

Team-product gate: two teams use the same approved setup across at least three machines, use drift in practice, and explicitly request shared policy, approval, registry, or audit.

Decision outcomes:

- activation plus replay/return supports the profile/compiler thesis;
- activation without return suggests a setup/service product unless drift and CI create recurrence;
- policy/audit demand supports a governance commercial wedge;
- consultancy-only demand supports a professional delivery accelerator;
- installation failures mean market conclusions are premature;
- no cross-tool value means narrow to diagnostics/compatibility or stop broad investment.


## P0 Maintainer Checklist

This checklist contains actions that require GitHub administration, public publication, or independent participants.

### 1. Install and prove the versioning identity

Follow [Repository Protection](docs/project/repository-protection.md).

- [ ] Verify the existing versioning App installation is scoped only to the intended repository.
- [ ] Grant only Contents read/write and Metadata read-only; disable webhooks.
- [x] Confirm `AIPLANE_VERSIONING_APP_ID` is present as an Actions repository variable.
- [x] Confirm `AIPLANE_VERSIONING_APP_PRIVATE_KEY` exists as an Actions repository secret (value not inspected).
- [ ] Merge the app-token workflow before activating protection.
- [ ] Confirm an ordinary merge is patched and tagged by `aiplane-versioning[bot]`.
- [ ] Confirm the patch tag runs the release workflow but does not create a public release.

### 2. Activate repository protection

- [x] Activate the `main`-only branch ruleset.
- [x] Require the exact status-check value `Quality gate` and an up-to-date branch.
- [x] Require PRs, conversation resolution, stale-review dismissal, and one approval when another reviewer exists.
- [x] Restrict updates, force pushes, and deletion of `main`.
- [x] Add only repository administrators and `aiplane-versioning` to bypass.
- [x] Activate immutable `v*` tag rules with the same narrow bypass.
- [ ] Prove a pending/failing gate or missing review blocks a non-bypass merge.
- [ ] Save the ruleset URL or screenshot in private evidence.

Read-only confirmation:

```bash
gh api repos/ocagdas/aiplane/branches/main/protection
gh api repos/ocagdas/aiplane/rulesets --jq '.[] | {id, name, target, enforcement}'
```

### 3. Publish one complete developer-preview release

For an intentional minor or major release, follow [CI and Release Process](VERSIONING.md); publication should start automatically after the app creates the tag. A selected patch may instead be published through **Actions -> Release artifacts -> Run workflow**.

Confirm the release visibly contains:

- [ ] exactly one `aiplane-VERSION-py3-none-any.whl`;
- [ ] exactly one `aiplane-VERSION.tar.gz`;
- [ ] `SHA256SUMS`;
- [ ] metadata matching the immutable tag;
- [ ] platform, upgrade, uninstall, and rollback guidance.

Do not count an empty release page and never replace assets under an existing version.

### 4. Verify actual public assets

Publication dispatches **Verify published release** automatically; it may also be run manually.

- [ ] All nine Linux/macOS/Windows x pip/pipx/uv jobs passed.
- [ ] Every job downloaded public assets rather than rebuilding source.
- [ ] Every manifest and install/replacement/uninstall lifecycle passed.
- [ ] Evidence identifies the same URL, tag commit, version, and wheel digest.
- [ ] Evidence contains no private data and reflects documented platform limitations.

### 5. Run independent demonstrations

Give participants only the installed artifact and the relevant [Public Demo Plan](docs/user/demo.md#public-demo-plan) section. Record first failures and assistance honestly, sanitize every record, and validate it:

```bash
python scripts/validate_trial_evidence.py PATH_TO_RECORD.json
```

Required outcomes:

- [ ] primary local adoption flow reproduced;
- [ ] local-only policy plus backup/restore replay reproduced;
- [ ] existing remote-GPU import/plan/export flow reproduced;
- [ ] participants understand written files and export boundaries.

### 6. Trigger the final documentation gate

Only after public verification and independent demonstrations:

- [ ] compare README, metadata, help, user docs, and demos;
- [ ] remove unsupported claims and maturity drift;
- [ ] run public example, link, help, contract, packaging, and full test gates;
- [ ] update the P0 backlog with evidence paths and final counts.

