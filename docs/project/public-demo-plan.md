# Public Demo Plan

This plan presents `aiplane` as it exists in the developer preview: an environment doctor and configuration compiler for reproducible local and hybrid AI development environments.

The public story is deliberately narrow. `aiplane` turns environment facts and reviewed YAML profiles into readiness findings, hardware-aware recommendations, and deterministic configuration exports. It does not become a model runtime, coding agent, IDE extension, secret manager, or hidden cloud deployment system.

## Recording hierarchy

### Primary public adoption cut — one outcome in under three minutes

This is the one introductory product video. It contains exactly five core commands—quickstart dry-run, discover, doctor, recommend, and Continue export—with no advanced command detours.

**Promise:** “Inspect this AI-development environment, understand readiness, choose a suitable configuration, and produce reviewed Continue config without hidden mutation.”

**Prepared state:** `aiplane` is installed from a release wheel in a clean workspace. Use a sanitized, rehearsed local Ollama profile so output is useful and deterministic; preparing the runtime/model is part of trial setup, not this public cut.

**Recording convention:** The quoted narration is the exact script to read. Do not read headings, command labels, or stage directions aloud. Type or paste the exact command, pause on the named output cue, then read the quotation at a normal pace. Keep terminal font and window size fixed so output does not reflow between rehearsals.

#### 0:00-0:25 — Preview without mutation

On screen: begin with an empty prompt, execute the command, then hold on `next_action` and the dry-run/write metadata.

Exact command:

```bash
aiplane quickstart local-coding --dry-run
```

Narration:

> Aiplane is an environment doctor and configuration compiler for repeatable AI development setups. I start with a dry-run, which previews the editable local profile and gives me one exact next action without installing a runtime, editing my IDE, contacting a catalog, or changing cloud resources.

#### 0:25-0:55 — Inspect provenance

On screen: keep the summary visible and point once to detected, generated/discovered, user-supplied, and unresolved counts.

Exact command:

```bash
aiplane discover
```

Narration:

> Discovery inventories this environment and labels where configuration came from: detected machine facts, generated or discovered records, values supplied by my profile, and anything still unresolved.

#### 0:55-1:40 — Diagnose readiness

On screen: pause on one representative finding and its reason, impact, remediation, and mutation metadata.

Exact command:

```bash
aiplane doctor
```

Narration:

> Doctor turns that inventory into actionable findings. Each blocker or advisory identifies the affected resource, explains the impact, and gives a remediation while making any mutation or dry-run requirement explicit.

#### 1:40-2:10 — Choose a suitable configuration

On screen: hold on the recommended model/configuration and the hardware or policy reasons—not the full candidate list.

Exact command:

```bash
aiplane recommend
```

Narration:

> Recommendation combines reviewed profile policy with available hardware. This is a transparent compatibility recommendation, not a benchmark result or performance guarantee.

#### 2:10-2:45 — Compile Continue configuration

On screen: scroll only enough to show the model alias and endpoint fields, then return to the command prompt without saving the output.

Exact command:

```bash
aiplane export continue
```

Narration:

> Export compiles deterministic Continue configuration for review. It prints text to the terminal; it does not install Continue, edit its files, start a model, or bypass authentication.

#### 2:45-2:55 — Close on the repeatable loop

On screen: leave the deterministic export visible and add a small overlay reading `profile → discover → doctor → recommend → export`.

Exact command: none; leave the export visible.

Narration:

> That is the repeatable loop: profile, discover, doctor, recommend, and export. Reviewable inputs produce reproducible configuration when the environment changes.

Do not show model pulls, chat/run/code commands, runtime lifecycle, MCP, stacks, orchestrators, deployment, benchmarks, or cloud discovery in this cut. Link advanced documentation below the video rather than adding another segment.

### P0 workflow-validation recordings

These are evidence workflows for independent user testing, not co-equal introductory product videos.

| Recording | Validation outcome | Target |
| --- | --- | --- |
| Local-only replay | Enforce local-only policy, archive editable YAML, recover from damage, and prove deterministic replay. | 2:50 |
| Existing remote GPU | Capture/import a GPU workstation, rank placement, plan access, and export endpoint configuration. | 2:50 |

A successful internal rehearsal does not satisfy the P0 gate. Independent users must complete all three workflows: the local Ollama adoption flow above, local-only/privacy replay, and laptop-to-remote-GPU.

## Shared recording rules

- Start from an installed wheel, `pipx`, or `uv tool` installation; normal viewers should not need a repository clone.
- Use a disposable working directory and sanitized profile names, hosts, paths, endpoints, and model aliases.
- Rehearse every command from a fresh directory before recording.
- Run inspect, doctor, plan, export, or `--dry-run` before mutation.
- Never show credentials, environment-variable values, private hostnames, tenant/subscription IDs, personal paths, or raw audit logs.
- Explain which command writes files. Exports print text; they do not edit Continue, Aider, or IDE settings.
- Keep provider catalog access explicit. The default quickstart is offline-safe; `--discovery` opts into configured catalog communication.
- Use live model pulls or endpoint calls only on a prepared machine. Otherwise show the exact dry-run plan.
- Keep command output at default verbosity unless one field is the point of the shot.

Prepare a clean workspace:

```bash
mkdir aiplane-demo
cd aiplane-demo
aiplane --help
```

The installed CLI creates editable profiles relative to this workspace. Keep the demo workspace after each rehearsal until the recording has been reviewed.

## P0 validation recording 1 — Local-only policy, backup, restore, and deterministic replay

**Promise:** “Treat the setup as reviewable configuration: prove cloud use is blocked, archive it, recover it, and reproduce the same export.”

**Prepared state:** Start with the working `local-dev` profile from video 1. The profile and local config must contain no raw credentials. This video uses ordinary filesystem copies because `aiplane` does not claim to be a backup product.

### 0:00-0:35 — Make policy visible

On screen: show the blocked cloud decision, allowed Ollama decision, and doctor summary; do not expose the policy file path.

Exact commands:

```bash
aiplane policy explain --action backend:cloud
aiplane policy explain --action provider:ollama
aiplane doctor
```

Use a rehearsed local-only repository policy whose output clearly blocks cloud escalation and allows the selected local provider.

Narration:

> Policy is profile-owned and inspectable. Doctor and policy explanation expose the decision before a model or endpoint is used.

### 0:35-1:10 — Archive editable and canonical forms

On screen: paste commands one at a time and briefly show the backup filenames, not their potentially private contents.

Exact commands:

```bash
mkdir -p demo-backup
cp -a profiles/local-dev demo-backup/local-dev
aiplane profiles render local-dev > demo-backup/local-dev.profile.json
aiplane export continue > demo-backup/continue.before.yaml
```

Continue with these exact commands to include non-secret local CLI defaults:

```bash
aiplane config init --template local
aiplane config show
cp -a .aiplane/config.yaml demo-backup/config.yaml
```

Narration:

> The editable source is the directory of focused YAML files. Render produces one canonical, read-only JSON document for validation, comparison, or archival. Local CLI preferences are separate. Credentials and discovered caches are intentionally not part of this portable profile backup.

Before sharing any archive, review it for private endpoints, machine names, account aliases, or other operational metadata.

### 1:10-1:45 — Demonstrate failure and template repair

On screen: hold on the missing-file validation error and the repair dry-run; make the `dry_run` state visible.

Exact commands; remove one file only after the backup exists:

```bash
mv profiles/local-dev/models.yaml profiles/local-dev/models.yaml.broken
aiplane profiles validate local-dev
aiplane profiles repair local-dev --file models.yaml --dry-run
```

Narration:

> Validation fails closed when a required profile file is missing. Repair can restore a missing structural file from the shipped template, but it cannot reconstruct user customizations. That is why the real profile backup matters.

Do not run repair without `--dry-run` in this sequence; restoring the blank template would not recover the reviewed model choices.

### 1:45-2:30 — Restore and prove equivalence

On screen: keep both silent `cmp` commands and their zero exit status visible, followed by successful validation.

Exact commands:

```bash
cp demo-backup/local-dev/models.yaml profiles/local-dev/models.yaml
rm profiles/local-dev/models.yaml.broken
cp demo-backup/config.yaml .aiplane/config.yaml
aiplane profiles validate local-dev
aiplane profiles render local-dev > demo-backup/local-dev.restored.profile.json
aiplane export continue > demo-backup/continue.after.yaml
cmp demo-backup/local-dev.profile.json demo-backup/local-dev.restored.profile.json
cmp demo-backup/continue.before.yaml demo-backup/continue.after.yaml
```


Narration:

> Validation proves the references are coherent; byte-for-byte comparison proves the canonical profile and generated Continue configuration replay exactly. Runtime model weights and credentials remain machine-local and are restored through their owning tools, not copied in this YAML bundle.

### 2:30-2:50 — Close with portability boundaries

On screen: show only the sanitized relative backup file list while the narration separates portable and machine-owned state.

Exact command:

```bash
find demo-backup -maxdepth 2 -type f -print
```

Narration:

> This backup contains the reviewed profile YAML, canonical render, optional non-secret local defaults, and generated integration text. Credentials, model weights, provider caches, audit logs, tunnel state, and machine-specific runtime data stay with the systems that own them.

## P0 validation recording 2 — Reuse the setup with an existing remote GPU workstation

**Promise:** “Describe a real GPU machine once, import that fact on a laptop, plan safe access, and compile client configuration without provisioning infrastructure.”

**Prepared state:** A sanitized existing GPU workstation is reachable through normal OpenSSH. Its runtime endpoint and model alias are already prepared. This demo does not create a VM, bypass SSH authentication, or copy credentials.

### 0:00-0:40 — Capture the GPU machine

On screen: run on the workstation, then show the exported filename and successful profile validation—not raw private hardware identifiers.

Exact commands to run on the GPU workstation:

```bash
mkdir -p aiplane-machine-export
cd aiplane-machine-export
aiplane profiles bootstrap-local --no-discovery
aiplane hardware export-machine --name gpu-workstation --origin onprem > gpu-workstation.machine.yaml
aiplane profiles validate local-dev
```

Narration:

> Hardware export prints a normalized, reviewable machine description. It contains capacity facts, not runtime weights or SSH credentials. Review the file before transferring it.

Transfer `gpu-workstation.machine.yaml` through the team’s approved file-transfer path.

### 0:40-1:20 — Import and rank on the laptop

On screen: switch clearly to the laptop terminal, show the imported machine summary, then hold on the ranked recommendation reasons.

Exact commands to run in the laptop demo workspace:

```bash
aiplane machines import gpu-workstation.machine.yaml
aiplane machines show gpu-workstation
aiplane machines recommend --workload inference_large --limit 3
```

Set the sanitized alias prepared in the laptop profile, then run the exact recommendation command:

```bash
REMOTE_MODEL="REHEARSED_REMOTE_ALIAS"
aiplane machines recommend --model "$REMOTE_MODEL" --limit 3
```

Narration:

> The machine, model alias, runtime, and endpoint remain separate facts. Recommendation explains placement; it does not start the remote service.

### 1:20-2:05 — Plan access without opening it

On screen: emphasize `plan`, the local forwarded endpoint, and status. Do not run `tunnel start` during this segment.

Use a sanitized `ssh_tunnel` target already reviewed in `profiles/local-dev/targets.yaml`. Exact commands:

```bash
aiplane remote tunnel plan --target gpu_workstation_ssh
aiplane remote tunnel status --target gpu_workstation_ssh
```

Narration:

> Plan prints the OpenSSH local-forward command and resulting endpoint. It does not start a process. OpenSSH still owns host-key verification, authentication, and encryption; the remote service still owns application authentication.

If lifecycle support is unavailable on the recording platform, show the explicit `unsupported_platform` result and manage the planned command with the platform-native SSH client.

### 2:05-2:40 — Compile endpoint configuration

On screen: hold on doctor readiness and sanitized endpoint/model fields in both exports; do not save or open an IDE.

Exact commands, with the tunnel or approved endpoint already running:

```bash
aiplane doctor
aiplane export openai-compatible --model "$REMOTE_MODEL" --endpoint http://127.0.0.1:8000/v1
aiplane export continue --chat "$REMOTE_MODEL"
```

Narration:

> The same laptop profile now compiles configuration for an existing remote runtime. Export still only prints reviewable text; it does not create the workstation, start the model server, edit the IDE, or weaken authentication.

### 2:40-2:50 — Close

On screen: leave the sanitized Continue export visible and overlay `describe → diagnose → choose → plan → export`.

Exact command: none; leave the exported configuration visible.

Narration:

> Local or remote, the loop stays the same: describe, diagnose, choose, plan, and export deterministic configuration.

## Optional fourth video — hold until evidence supports it

Do not record this for the initial set. Candidate scope is “automation and integration contracts”:

- `aiplane profiles schema` and canonical JSON validation;
- Tier-1 Aider, OpenAI-compatible, and generic MCP exports;
- read-only MCP initialize/tools-list demonstration;
- JSON doctor output in CI;
- the security boundary: read-only defaults, explicit write enablement, per-call confirmation, and audit sensitivity.

The video should be approved only if user testing shows that it answers a recurring adoption question and can remain under three minutes without turning advanced features into the main product promise.

## Rehearsal checklist

Before each recording:

```bash
scripts/check.sh quick
aiplane profiles validate local-dev
aiplane doctor
```

For a wheel-installed recording workspace without a repository clone, omit `scripts/check.sh quick`; that command is for contributors.

Verify:

- each video completes in a normal-speed rehearsal under 2:50;
- every alias, target, host, endpoint, and output is sanitized and predetermined;
- every mutation is preceded by its dry-run or plan;
- commands use the installed CLI rather than `PYTHONPATH=src`;
- no command depends on live catalog/cloud communication unless the segment says so;
- expected nonzero validation output is rehearsed and explained;
- integration exports are compared before/after where repeatability is claimed;
- profile backup and template repair are described as different operations;
- platform limitations match `docs/user/platform-support.md`;
- no credentials, audit records, private paths, or account identifiers appear on screen.

## P0 demonstration evidence

Use the canonical [external-trial evidence record](external-trial-evidence.md) and validate it before sharing. For each independent user, record:

- operating system and installation channel;
- start/end timestamps and whether the video stayed under three minutes;
- whether help was required beyond the video;
- first failed command and failure category;
- whether the user could explain what files were written;
- whether the user understood that export does not edit the target tool;
- whether backup/restore reproduced canonical render and export byte-for-byte;
- whether remote planning was understood as planning rather than provisioning.

The P0 demonstration gate closes only after independent users reproduce all three flows from clean environments and the final README/documentation sweep is repeated afterward.
