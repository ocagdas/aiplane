# Field Evidence Collection Runbook

Use this copy-paste runbook to collect reviewable output for every open P0 workflow and the current replay, hardware, benchmark, and optional Docker Model Runner evidence milestones. Use the [Manual Test Checklist](manual-test-checklist.md) for exhaustive feature acceptance.

Raw evidence can contain private paths, hosts, endpoints, device identifiers, and account aliases. Never share credentials, tokens, environment values, private infrastructure facts, or personal information.

## 1. Capture setup

POSIX shell:

~~~bash
mkdir aiplane-field-evidence
cd aiplane-field-evidence
mkdir -p evidence/raw evidence/share
export AIPLANE_PROFILE=evidence-local
run_capture() {
  label="$1"; shift
  printf '%s\n' "$*" > "evidence/raw/$label.command.txt"
  date -u +%Y-%m-%dT%H:%M:%SZ > "evidence/raw/$label.started.txt"
  "$@" > "evidence/raw/$label.output.txt" 2>&1
  code=$?
  date -u +%Y-%m-%dT%H:%M:%SZ > "evidence/raw/$label.ended.txt"
  printf '%s\n' "$code" > "evidence/raw/$label.exit.txt"
  printf '%s exit=%s\n' "$label" "$code"
  return 0
}
~~~

PowerShell:

~~~powershell
New-Item -ItemType Directory -Force evidence/raw, evidence/share | Out-Null
$env:AIPLANE_PROFILE = "evidence-local"
function Invoke-Capture {
  param([string]$Name, [string]$Command, [string[]]$Arguments)
  ($Command + " " + ($Arguments -join " ")) | Set-Content "evidence/raw/$Name.command.txt"
  (Get-Date).ToUniversalTime().ToString("o") | Set-Content "evidence/raw/$Name.started.txt"
  & $Command @Arguments *> "evidence/raw/$Name.output.txt"
  $Code = $LASTEXITCODE
  (Get-Date).ToUniversalTime().ToString("o") | Set-Content "evidence/raw/$Name.ended.txt"
  $Code | Set-Content "evidence/raw/$Name.exit.txt"
}
~~~

The helper preserves failures and continues so later diagnostics can be captured.

## 2. P0 install and hosted proof

A no-clone participant installs exactly one immutable release artifact:

~~~bash
sha256sum --check SHA256SUMS
gh attestation verify aiplane-*.whl --repo ocagdas/aiplane
uv tool install ./aiplane-VERSION-py3-none-any.whl
run_capture 00-version aiplane --version
run_capture 01-help aiplane --help
run_capture 02-templates aiplane profiles templates
~~~

Use pipx instead of uv when that is the selected channel. On Windows, compare Get-FileHash -Algorithm SHA256 with SHA256SUMS. Maintainers running this procedure from a source checkout can temporarily return to its root and verify every isolated channel:

~~~bash
cd ..
python scripts/verify_install_channels.py dist/aiplane-VERSION-py3-none-any.whl --channel all
cd aiplane-field-evidence
~~~

A maintainer source checkout should also capture the repository gates. These commands assume the evidence directory was created directly under the checkout:

~~~bash
run_capture 03-format-check bash -lc 'cd .. && python -m ruff format --check src tests'
run_capture 04-lint bash -lc 'cd .. && python -m ruff check src tests'
run_capture 05-full-suite bash -lc 'cd .. && python -m pytest -q'
run_capture 06-clean-gate bash -lc 'cd .. && ./scripts/test-clean.sh'
run_capture 07-profile bash -lc 'cd .. && python -m aiplane profiles validate local-dev'
run_capture 08-required-text bash -lc 'cd .. && AIPLANE_PROFILE=local-dev python -m aiplane environment doctor --required-only'
run_capture 09-required-json bash -lc 'cd .. && AIPLANE_PROFILE=local-dev python -m aiplane environment doctor --required-only --format json'
~~~

PowerShell maintainers can run the same Python commands from the checkout root with Invoke-Capture; the POSIX clean-gate script remains a CI/Linux contributor check.

Public release URLs, immutable tags, hosted Linux/macOS/Windows jobs, attestations, and branch protection require reviewed public links; local commands cannot prove them. Never share tokens or private CI logs.

## 3. P0 primary adoption

~~~bash
run_capture 10-create aiplane profiles create evidence-local --template local-dev
run_capture 11-validate aiplane profiles validate evidence-local
run_capture 12-runtime-doctor aiplane runtimes doctor ollama
run_capture 12-provider-ollama aiplane providers test ollama
run_capture 13-refresh aiplane models refresh --provider ollama
run_capture 14-models aiplane models list --runtime ollama --role chat --identity both
~~~

Replace SELECTED_ALIAS with a compatible alias from step 14. Pull and promotion are preparation, not part of the seven-command public cut.

~~~bash
run_capture 15-pull-preview aiplane models pull SELECTED_ALIAS --dry-run
run_capture 16-pull aiplane models pull SELECTED_ALIAS
run_capture 17-promote aiplane models promote SELECTED_ALIAS --as local_chat
run_capture 18-runtime-status aiplane runtimes status ollama
run_capture 20-quickstart aiplane quickstart local-coding --dry-run
run_capture 21-discover aiplane discover
run_capture 22-doctor aiplane doctor
run_capture 23-recommend aiplane recommend
run_capture 24-codex aiplane export codex --model local_chat
run_capture 24-codex-launch aiplane launch --tool codex --model local_chat --dry-run
run_capture 25-copilot-cli aiplane export copilot-cli --model local_chat --format json --offline
run_capture 26-copilot-vscode aiplane export copilot-vscode --model local_chat
~~~

Expect provenance, actionable findings, transparent fit reasons, and alias plus provider model identity. `providers test ollama` reads the local `/api/tags` endpoint without credentials. The Codex launch capture is preview-only and is valid only for a selected Ollama or LM Studio alias at its loopback endpoint; it emits no Codex config changes. Other exports print configuration; they do not edit or launch clients.

## 4. P0 local-only replay

~~~bash
run_capture 30-cloud-policy aiplane policy explain --action backend:cloud
run_capture 31-local-policy aiplane policy explain --action provider:ollama
run_capture 32-doctor aiplane doctor
run_capture 33-archive-preview aiplane profiles archive evidence-local --output evidence/raw/source.archive.json --dry-run
run_capture 34-archive aiplane profiles archive evidence-local --output evidence/raw/source.archive.json
run_capture 35-before aiplane profiles render evidence-local
run_capture 36-export aiplane export continue --chat local_chat
run_capture 37-restore-preview aiplane profiles restore evidence/raw/source.archive.json --as evidence-restored --dry-run
run_capture 38-restore aiplane profiles restore evidence/raw/source.archive.json --as evidence-restored --yes
run_capture 39-validate aiplane profiles validate evidence-restored
run_capture 40-after aiplane profiles render evidence-restored
cmp evidence/raw/35-before.output.txt evidence/raw/40-after.output.txt
printf '%s\n' "$?" > evidence/raw/41-compare.exit.txt
run_capture 42-compare aiplane profiles compare evidence-local evidence-restored
~~~

PowerShell users compare Get-FileHash results instead of cmp. Optional failure and repair preview, only after the archive exists:

~~~bash
mv profiles/evidence-local/models.yaml profiles/evidence-local/models.yaml.field-test
run_capture 43-missing aiplane profiles validate evidence-local
run_capture 44-repair-preview aiplane profiles repair evidence-local --file models.yaml --dry-run
mv profiles/evidence-local/models.yaml.field-test profiles/evidence-local/models.yaml
run_capture 45-recovered aiplane profiles validate evidence-local
~~~

Do not run repair without --dry-run here: a template cannot reconstruct user edits. Keep archives private unless reviewed.

## 5. Two-client replay

Use two genuinely separate client workspaces or machines. Do not label a simulation independent.

~~~bash
# Approved source
aiplane profiles archive evidence-local --output approved-source.archive.json

# Client A
aiplane profiles restore approved-source.archive.json --as replay-a --dry-run
aiplane profiles restore approved-source.archive.json --as replay-a --yes
aiplane profiles validate replay-a
aiplane profiles drift replay-a
aiplane doctor --profile replay-a
aiplane export continue --profile replay-a > continue-a.yaml
aiplane profiles archive replay-a --output client-a.archive.json

# Client B
aiplane profiles restore approved-source.archive.json --as replay-b --dry-run
aiplane profiles restore approved-source.archive.json --as replay-b --yes
aiplane profiles validate replay-b
aiplane profiles drift replay-b
aiplane doctor --profile replay-b
aiplane export continue --profile replay-b > continue-b.yaml
aiplane profiles archive replay-b --output client-b.archive.json

# Evidence-control machine
run_capture 50-replay aiplane profiles replay-check approved-source.archive.json --source archive --client-archive client-a.archive.json --client-archive client-b.archive.json
~~~

Expect two distinct clients, an exact/capability-equivalent/materially-incompatible/unresolved classification, and explicit hardware drift.

## 6. Existing remote GPU

Run on the workstation, then review the YAML before approved transfer:

~~~bash
mkdir -p aiplane-machine-export
cd aiplane-machine-export
aiplane profiles bootstrap-local --no-discovery
aiplane hardware export-machine --name gpu-workstation --origin onprem > gpu-workstation.machine.yaml
aiplane profiles validate local-dev
~~~

Run on the laptop with an existing sanitized gpu_workstation_ssh target:

~~~bash
run_capture 60-import aiplane machines import gpu-workstation.machine.yaml
run_capture 61-show aiplane machines show gpu-workstation
run_capture 62-placement aiplane machines recommend --workload inference_large --limit 3
run_capture 63-model-placement aiplane machines recommend --model local_chat --limit 3
run_capture 64-tunnel-plan aiplane remote tunnel plan --target gpu_workstation_ssh
run_capture 65-tunnel-status aiplane remote tunnel status --target gpu_workstation_ssh
run_capture 66-doctor aiplane doctor
run_capture 67-openai aiplane export openai-compatible --model local_chat --endpoint http://127.0.0.1:8000/v1
run_capture 68-continue aiplane export continue --chat local_chat
~~~

Planning is read-only. Starting a tunnel needs separate approval. An explicit unsupported_platform result is valid evidence.

## 7. Hardware placement calibration

Repeat on real NVIDIA, AMD, Intel, Apple, Windows, and heterogeneous multi-GPU hosts available to you. Keep catalog, model, quantization, contexts, runtime, and score profiles consistent. Replace MODEL_ALIAS and RUNTIME_NAME:

~~~bash
run_capture 70-discover aiplane hardware discover
run_capture 71-doctor aiplane hardware doctor
run_capture 72-assess-4k aiplane hardware assess MODEL_ALIAS --runtime RUNTIME_NAME --context-tokens 4096
run_capture 73-assess-8k aiplane hardware assess MODEL_ALIAS --runtime RUNTIME_NAME --context-tokens 8192
run_capture 74-assess-32k aiplane hardware assess MODEL_ALIAS --runtime RUNTIME_NAME --context-tokens 32768
run_capture 75-balanced aiplane hardware assess MODEL_ALIAS --runtime RUNTIME_NAME --context-tokens 8192 --score-profile balanced
run_capture 76-throughput aiplane hardware assess MODEL_ALIAS --runtime RUNTIME_NAME --context-tokens 8192 --score-profile throughput
run_capture 77-manifest aiplane runtimes launch-manifest RUNTIME_NAME --model MODEL_ALIAS --context-tokens 8192
~~~

For multi-GPU evidence, add reviewed repeated --gpu-device values and supported --tensor-parallel/--offload values. Do not infer MIG, NUMA, interconnect, or shared-memory facts discovery did not report. In evidence/share/calibration-summary.md record a pseudonymous host label, OS/architecture, accelerator vendor/count, RAM/VRAM, runtime/version, model/quantization/context, expected versus observed placement, and discrepancies.

## 8. Benchmark and runtime calibration

Keep model, quantization, context, suite, runtime/version, host, repeats, warmup, and concurrency identical across comparisons.

~~~bash
run_capture 80-list aiplane benchmarks list
run_capture 81-doctor aiplane benchmarks doctor
run_capture 82-plan aiplane benchmarks plan aiplane-smoke --model local_chat --endpoint http://127.0.0.1:11434/v1
run_capture 83-preview aiplane models benchmark local_chat --task all --repeats 5 --dry-run
run_capture 84-benchmark aiplane models benchmark local_chat --task all --repeats 5 --no-save
run_capture 85-runtime aiplane runtimes benchmark ollama
run_capture 86-balanced aiplane models route --role chat --candidate local_chat --runtime ollama --context-tokens 8192 --score-profile balanced
run_capture 87-throughput aiplane models route --role chat --candidate local_chat --runtime ollama --context-tokens 8192 --score-profile throughput
~~~

Review plans and prepare endpoints before live commands. Preserve nulls when exact telemetry such as TTFT is unavailable; do not estimate. Record cold/warm state and failures. User measurements and scoring extensions must identify provenance; trusted command graders require explicit opt-in.

The optional query benchmark measures catalog performance, not model quality:

~~~bash
AIPLANE_RUN_PERFORMANCE=1 python -m pytest -q tests/performance/test_catalog_query_performance.py
~~~

## 9. Optional Docker Model Runner evidence

~~~bash
run_capture 90-capabilities aiplane runtimes capabilities docker_model_runner
run_capture 91-status aiplane runtimes status docker_model_runner
run_capture 92-models aiplane runtimes list-runtime-models docker_model_runner
run_capture 93-inspect aiplane runtimes inspect docker_model_runner
run_capture 94-benchmark aiplane runtimes benchmark docker_model_runner
~~~

Preserve an unsupported result as compatibility evidence.

## 10. Sanitize, validate, and share

P0 trials use the canonical record:

~~~bash
cp ../docs/project/trial-evidence/template.json evidence/trial.json
python ../scripts/validate_trial_evidence.py evidence/trial.json
~~~

A no-clone participant can return notes privately; the maintainer can prepare the record without requiring a clone. Fill elapsed times from timestamps, preserve the first failure and actual assistance, and use primary-adoption, local-only-replay, remote-gpu, or no-clone-install. A rehearsal never counts as independent.

Before copying selected files to evidence/share, remove names, emails, organizations, home paths, private hosts/IPs/URLs, SSH targets, tenants, subscriptions, accounts, credentials, headers, environment values, and stable device identifiers. Do not share archives, audit logs, or configs by default. Human review remains mandatory.

Share only validated trial records, selected redacted command/output/exit files, the reviewed calibration summary, and needed public release/CI links. Paste those reviewed files into an issue or chat for analysis; keep evidence/raw private.
