# Public Demo Plan

This plan presents `aiplane` as it exists in the developer preview: an environment doctor and configuration compiler for reproducible local and hybrid AI development environments.

The public story is deliberately narrow. `aiplane` turns environment facts and reviewed YAML profiles into readiness findings, hardware-aware recommendations, and deterministic configuration exports. It does not become a model runtime, coding agent, IDE extension, secret manager, or hidden cloud deployment system.

## Recommended video set

Record three self-contained videos. Each must work at normal speaking speed in no more than three minutes; target 2:30-2:50 so command output and small pauses do not force rushed narration.

| Video | New-user outcome | Target |
| --- | --- | --- |
| 1. Local setup | Inspect a laptop, understand blockers, choose a suitable local model, and export Continue config. | 2:45 |
| 2. Safe repeatability | Enforce local-only policy, archive editable YAML, recover from damage, and prove the restored output is identical. | 2:50 |
| 3. Remote GPU | Capture an existing GPU workstation, import it on a laptop, rank it for a workload, plan access, and export endpoint config. | 2:50 |

Do not add a fourth public video yet. MCP, schema automation, Aider, and CI usage can become a fourth “automation and integrations” video after audience or user-testing evidence shows that it clarifies adoption. Until then, show one deterministic integration export in each relevant video and keep advanced surfaces in documentation.

These three videos are also the P0 user-testing demonstrations. A successful recording rehearsal is not a substitute for the independent-user completion gate.

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

## Video 1 — From a new laptop to a usable local setup

**Promise:** “In under three minutes, understand this machine’s AI-development readiness and produce reviewed configuration for an existing coding tool.”

**Prepared state:** `aiplane` is installed. For the live ending, Ollama is already installed and a small reviewed Ollama model is available or can be pulled quickly. The dry-run path must work without either condition.

### 0:00-0:25 — Preview before writing

```bash
aiplane quickstart local-coding --dry-run
aiplane quickstart local-coding
```

Narration:

> Quickstart previews first, then creates the editable local profile. It preserves an existing profile, skips provider catalog communication by default, and reports one exact next action. It does not install a runtime, edit an IDE, or touch cloud resources.

Show `profiles/local-dev/` briefly. Describe it as reviewed environment configuration, not a secret store.

### 0:25-1:15 — Discover and diagnose

```bash
aiplane discover
aiplane doctor
```

Point out:

- detected hardware and installed runtime facts;
- configuration provenance: detected, generated/discovered, profile-supplied, or unresolved;
- blocker versus advisory findings;
- exact remediation and whether it mutates state or supports dry-run.

Narration:

> Doctor is read-only. A blocker explains what is wrong, which resource is affected, and the exact safe next action instead of claiming the machine is ready.

### 1:15-2:05 — Recommend a reviewed local model

```bash
aiplane recommend
aiplane models list --runtime ollama --role chat --enabled-only --sort-by role --limit 3
```

On a prepared profile, select the first rehearsed alias rather than improvising during recording:

```bash
MODEL_ALIAS="REHEARSED_OLLAMA_ALIAS"
aiplane models show "$MODEL_ALIAS"
aiplane quickstart local-coding --dry-run --pull-model "$MODEL_ALIAS"
```

If the recording machine is prepared and the pull is acceptably short, run the same command without `--dry-run`. Otherwise stop at the plan and show `aiplane runtimes status ollama`.

Narration:

> The profile alias is separate from the provider’s model ID and from the runtime that stores or serves the weights. Aiplane records and checks that mapping; Ollama remains the runtime.

### 2:05-2:45 — Compile tool configuration

```bash
aiplane export continue
```

Narration:

> Export is deterministic text for review. It does not install Continue or edit its files. Re-running this export from the same profile produces the same configuration.

End on the core loop:

```text
profile -> discover -> doctor -> recommend -> export
```

## Video 2 — Local-only policy, backup, restore, and deterministic replay

**Promise:** “Treat the setup as reviewable configuration: prove cloud use is blocked, archive it, recover it, and reproduce the same export.”

**Prepared state:** Start with the working `local-dev` profile from video 1. The profile and local config must contain no raw credentials. This video uses ordinary filesystem copies because `aiplane` does not claim to be a backup product.

### 0:00-0:35 — Make policy visible

```bash
aiplane policy explain --action backend:cloud
aiplane policy explain --action provider:ollama
aiplane doctor
```

Use a rehearsed local-only repository policy whose output clearly blocks cloud escalation and allows the selected local provider.

Narration:

> Policy is profile-owned and inspectable. Doctor and policy explanation expose the decision before a model or endpoint is used.

### 0:35-1:10 — Archive editable and canonical forms

```bash
mkdir -p demo-backup
cp -a profiles/local-dev demo-backup/local-dev
aiplane profiles render local-dev > demo-backup/local-dev.profile.json
aiplane export continue > demo-backup/continue.before.yaml
```

If local CLI defaults are part of the demonstration:

```bash
aiplane config init --template local
aiplane config show
cp -a .aiplane/config.yaml demo-backup/config.yaml
```

Narration:

> The editable source is the directory of focused YAML files. Render produces one canonical, read-only JSON document for validation, comparison, or archival. Local CLI preferences are separate. Credentials and discovered caches are intentionally not part of this portable profile backup.

Before sharing any archive, review it for private endpoints, machine names, account aliases, or other operational metadata.

### 1:10-1:45 — Demonstrate failure and template repair

Remove one file only after the backup exists:

```bash
mv profiles/local-dev/models.yaml profiles/local-dev/models.yaml.broken
aiplane profiles validate local-dev
aiplane profiles repair local-dev --file models.yaml --dry-run
```

Narration:

> Validation fails closed when a required profile file is missing. Repair can restore a missing structural file from the shipped template, but it cannot reconstruct user customizations. That is why the real profile backup matters.

Do not run repair without `--dry-run` in this sequence; restoring the blank template would not recover the reviewed model choices.

### 1:45-2:30 — Restore and prove equivalence

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

If the optional local config was not created, omit its two copy commands.

Narration:

> Validation proves the references are coherent; byte-for-byte comparison proves the canonical profile and generated Continue configuration replay exactly. Runtime model weights and credentials remain machine-local and are restored through their owning tools, not copied in this YAML bundle.

### 2:30-2:50 — Close with portability boundaries

Show the backup contents:

```bash
find demo-backup -maxdepth 2 -type f -print
```

State explicitly:

- portable: reviewed profile YAML, canonical render, non-secret local defaults when desired, and generated integration text;
- not portable by default: credentials, model weights, provider caches, audit logs, PID/tunnel state, and machine-specific runtime data.

## Video 3 — Reuse the setup with an existing remote GPU workstation

**Promise:** “Describe a real GPU machine once, import that fact on a laptop, plan safe access, and compile client configuration without provisioning infrastructure.”

**Prepared state:** A sanitized existing GPU workstation is reachable through normal OpenSSH. Its runtime endpoint and model alias are already prepared. This demo does not create a VM, bypass SSH authentication, or copy credentials.

### 0:00-0:40 — Capture the GPU machine

Run on the GPU workstation:

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

Back in the laptop demo workspace:

```bash
aiplane machines import gpu-workstation.machine.yaml
aiplane machines show gpu-workstation
aiplane machines recommend --workload inference_large --limit 3
```

If the laptop profile already contains the rehearsed remote model alias:

```bash
REMOTE_MODEL="REHEARSED_REMOTE_ALIAS"
aiplane machines recommend --model "$REMOTE_MODEL" --limit 3
```

Narration:

> The machine, model alias, runtime, and endpoint remain separate facts. Recommendation explains placement; it does not start the remote service.

### 1:20-2:05 — Plan access without opening it

Use a sanitized `ssh_tunnel` target already reviewed in `profiles/local-dev/targets.yaml`:

```bash
aiplane remote tunnel plan --target gpu_workstation_ssh
aiplane remote tunnel status --target gpu_workstation_ssh
```

Narration:

> Plan prints the OpenSSH local-forward command and resulting endpoint. It does not start a process. OpenSSH still owns host-key verification, authentication, and encryption; the remote service still owns application authentication.

If lifecycle support is unavailable on the recording platform, show the explicit `unsupported_platform` result and manage the planned command with the platform-native SSH client.

### 2:05-2:40 — Compile endpoint configuration

With the tunnel or approved endpoint already running:

```bash
aiplane doctor
aiplane export openai-compatible --model "$REMOTE_MODEL" --endpoint http://127.0.0.1:8000/v1
aiplane export continue --chat "$REMOTE_MODEL"
```

Narration:

> The same laptop profile now compiles configuration for an existing remote runtime. Export still only prints reviewable text; it does not create the workstation, start the model server, edit the IDE, or weaken authentication.

### 2:40-2:50 — Close

> Local laptop or remote GPU, the workflow stays the same: describe facts, diagnose readiness, choose placement, plan access, and export deterministic configuration.

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

For each independent user, record:

- operating system and installation channel;
- start/end timestamps and whether the video stayed under three minutes;
- whether help was required beyond the video;
- first failed command and failure category;
- whether the user could explain what files were written;
- whether the user understood that export does not edit the target tool;
- whether backup/restore reproduced canonical render and export byte-for-byte;
- whether remote planning was understood as planning rather than provisioning.

The P0 demonstration gate closes only after independent users reproduce all three flows from clean environments and the final README/documentation sweep is repeated afterward.
