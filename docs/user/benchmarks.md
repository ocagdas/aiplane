# Model Benchmarks

`aiplane models benchmark` runs small smoke benchmarks against a configured model. It answers a practical question: does this model work on this setup, and is it fast enough and good enough for the task shape you care about?


## Measurement limits

Each run now reports `server_tokens_per_second`, `client_tokens_per_second` and `average_tokens_per_second` separately. Server rate uses native generation token counts and duration when provided. Client rate uses the endpoint-reported output count divided by client-observed request time through response consumption/parsing; it includes request overhead and does not count stream chunks as tokens. Without an output token count or a positive measured duration, client rate is unavailable.

| Server t/s | Client t/s | Average t/s |
| --- | --- | --- |
| 50 | 40 | 45 |
| 50 | unavailable | 50 |
| unavailable | 40 | 40 |
| unavailable | unavailable | unavailable |
| 0 | 40 | 20 |

The average is the arithmetic mean of available rates, rounded to three decimal places. Missing values are excluded; a measured zero is included. `throughput_average_sources` identifies which values contributed. This is a combined display value across two different intervals, not aggregate inference throughput or whole-agent task throughput.

Repeated-run summaries show the mean server rate, mean client rate and the available-value mean of those two displayed source means, plus each source's sample count. Missing source samples are omitted, not replaced with zero. `median_run_average_tokens_per_second` separately summarizes the per-run averages. Comparisons keep different source-availability combinations in separate groups.

`client_elapsed_ms`, `server_elapsed_ms` and `server_generation_ms` preserve their timing boundaries. `elapsed_ms` equals measured client request time; it stays null without backend timing. `task_elapsed_ms` measures the surrounding model call, including routing and failure handling but excluding grading. It is not complete agent-task time. Previews leave both timings null. Streaming TTFT remains the independently observed first-content time. Native prompt processing throughput remains `prompt_tokens_per_second`.

The old ambiguous per-run `tokens_per_second` field is replaced, not guessed: pre-1.0 measurement imports must label it as server or client. Import rejects that old field, an average inconsistent with the available sources, or an inconsistent source list. Existing files are not deleted; invalid local comparison records produce warnings. Suites can request the three explicit rate metric names.

Suite decoding now travels through the runner/catalog/dispatcher into each provider request. Unknown fields, fractional seeds/token limits, booleans used as numbers and non-finite values are refused. `timeout_seconds` also reaches the provider call. AP2 was removed on 2026-10-18. Run external benchmarks through their own CLI/API, then convert/import useful results through the existing measurement format. Trusted command graders and direct measurement import remain available; no generic wrapper protocol or external launcher is required. See [evaluation boundaries](../project/benchmark-evaluation-boundaries.md).

### Requested and submitted generation settings

| Suite field | Ollama API | OpenAI-compatible / Azure chat completions | Anthropic Messages |
| --- | --- | --- | --- |
| `temperature` | `options.temperature` | `temperature` | `temperature`, range 0–1 |
| `top_p` | `options.top_p` | `top_p` | `top_p` |
| `seed` | `options.seed` | `seed` | Refused before sending |
| `max_output_tokens` | `options.num_predict` | `max_tokens` | `max_tokens` |

Anthropic supplies the existing default `max_tokens: 1024` when no output limit is requested. Its evidence lists that submitted default separately from requested settings. Model-specific restrictions still apply: some current Claude models reject sampling controls; some OpenAI/Azure models require `max_completion_tokens` instead of this adapter's `max_tokens`. A provider rejection records HTTP status and submitted controls, fails that run and never retries with settings removed. This implementation does not infer capabilities from model names. See the official [Claude request fields](https://platform.claude.com/docs/en/api/messages/create), [Azure chat fields](https://learn.microsoft.com/en-us/rest/api/microsoft-foundry/azureopenai/chat) and [Ollama options](https://docs.ollama.com/api/chat).

Each run's `decoding_evidence` records protocol, requested values, submitted wire settings, unsupported field names and status (`planned`, `submitted`, `unsupported`, `rejected` or `unverified`). `provider_confirmed` is null: sending a seed proves neither deterministic output nor server compliance. Previews have no submitted settings. Failures keep an error and evidence without inventing throughput.

## Benchmark Frameworks And Installation

`aiplane` has a built-in smoke/custom benchmark runner and can also help you
inspect or install optional external benchmark tools. These tools are optional;
install them only in the environment where you intend to run the benchmark.

List known benchmark frameworks:

```bash
aiplane benchmarks list
```

Check what is available now:

```bash
aiplane benchmarks doctor
aiplane benchmarks doctor lm-evaluation-harness
aiplane benchmarks doctor vllm-serving
```

Preview installs before changing the environment:

```bash
aiplane benchmarks install lm-evaluation-harness --dry-run
aiplane benchmarks install vllm-serving --dry-run
aiplane benchmarks install locust-load --dry-run
```

Render benchmark command templates without executing them:

```bash
aiplane benchmarks plan aiplane-smoke --model MODEL_ALIAS
aiplane benchmarks plan aiplane-smoke --model MODEL_ALIAS --spec benchmarks/simple-python.json
aiplane benchmarks plan lm-evaluation-harness --model MODEL_ALIAS --endpoint http://localhost:8000/v1
aiplane benchmarks plan vllm-serving --model MODEL_ALIAS --endpoint http://localhost:8000/v1
```

Current framework intent:

| Framework | Purpose | Install support |
| --- | --- | --- |
| `aiplane-smoke` | Built-in smoke and custom spec benchmarks. | Built in; no install. |
| `lm-evaluation-harness` | Standard model-quality evaluation tasks. | `pip` helper; GPU/runtime dependencies may still need manual work. |
| `vllm-serving` | vLLM endpoint throughput/latency/concurrency checks. | `pip` helper for `vllm`; CUDA/PyTorch compatibility remains host-specific. |
| `locust-load` | Endpoint/gateway load testing and throttling checks. | `pip` helper; user supplies the Locust test file. |

## Built-In Commands

Preview the built-in benchmark without calling a model:

```bash
aiplane models benchmark MODEL_ALIAS --dry-run
```

Run all built-in benchmark tasks and save the versioned result under `.aiplane/benchmarks/`:

```bash
aiplane models benchmark MODEL_ALIAS
```

Run one built-in task only:

```bash
aiplane models benchmark --task analysis MODEL_ALIAS
aiplane models benchmark --task completion MODEL_ALIAS
aiplane models benchmark --task generation MODEL_ALIAS
aiplane models benchmark --task reasoning MODEL_ALIAS
```

Skip saving:

```bash
aiplane models benchmark --no-save MODEL_ALIAS
```

## Versioned Benchmark Suites

Custom suites use a versioned JSON/YAML contract. Validate and normalize a suite before running it:

```bash
aiplane benchmarks suite-validate benchmarks/simple-python.json
aiplane models benchmark MODEL_ALIAS --spec benchmarks/simple-python.json --task clamp_unit --dry-run
aiplane models benchmark MODEL_ALIAS --spec benchmarks/simple-python.json --repeats 5
```

Example JSON:

```json
{
  "schema_version": "1.0",
  "name": "simple-python-codegen",
  "version": "1.0",
  "kind": "quality",
  "repeats": 5,
  "decoding": {"temperature": 0.0, "seed": 7},
  "comparability": {
    "group": "team-python-v1",
    "protocol": "fixed-prompts-and-settings"
  },
  "metrics": ["quality_score", "elapsed_ms"],
  "tasks": {
    "clamp_unit": {
      "prompt": "Write a Python function clamp(value, low, high). Return only code.",
      "evaluator": {
        "type": "regex",
        "pattern": "def\\s+clamp"
      }
    }
  }
}
```

Safe built-in evaluator types are `expected_terms`, `exact_match`, `regex`, and `json`. A command evaluator is also available for trusted local suites, but the suite must explicitly set `allow_command_evaluators: true`. Command evaluators are not a sandbox: review the command and use `--dry-run` before execution. They receive `{output_file}` and `{prompt_file}` placeholders and may print `{"score": 82, "passed": true}`.

The `json` evaluator checks that the answer is a JSON object with required keys; it does not check the values. Use a command grader for domain-specific correctness, such as whether `category` equals the expected category. The default keyword smoke score includes time and output length and should not be treated as task-specific accuracy.

Native requests support Ollama, OpenAI-compatible, Azure OpenAI and Anthropic interfaces. Unsupported interfaces produce a failed call, not automatic translation. Use an external evaluator with the provider's interface and convert its result to the measurement contract for import. Arbitrary native result files are not automatically understood, and missing protocol evidence can block controlled ranking. See [evaluation boundaries](../project/benchmark-evaluation-boundaries.md#unsupported-interfaces).

Saved native results retain full prompt/answer artifacts and hashes for each completed call/repeat. Grader files are transient and isolated per invocation; grader failures retain the answer and an error, and later cases continue. `--no-save` avoids saving native result JSON. Saved results and review exports contain task text; keep sensitive workloads private.

[Manual review](benchmark-review.md) uses `benchmarks review-export` and `review-import` with original measurement records and a versioned rubric. Numeric/pass judgments and pairwise preferences stay separate from automatic scores. The importer rejects changed source/output/rubric identities and missing or invalid ratings. The [20-case task example](../examples/task-evaluation/README.md) demonstrates value checking, independent evaluation/import and manual review without model calls. Actual model trials are separate.

Suite results record the suite version, repeat index, decoding settings, runtime/environment context, pass rate, means, medians, standard deviation, and standard error when enough samples exist. Smoke, quality, and performance evidence remain separately typed.

## End-User Measurements and Scoring Hooks

You can import measurements produced by your own harness without giving Aiplane executable code. The import contract is versioned, requires provenance, validates score ranges and environment/runtime metadata, and rejects secret-bearing fields.

Preview first:

```bash
aiplane benchmarks import results/my-measurements.json
```

Write the validated record to the ignored `.aiplane/benchmarks/` cache:

```bash
aiplane benchmarks import results/my-measurements.json --yes
```

The record must use `contract_version: "1.0"`, `record_type: "benchmark_measurements"`, a model alias, suite identity, one or more runs, and `provenance.source`. Each run can supply quality/performance scores, elapsed time, TTFT, token counts, throughput, pass/fail, seed, and metadata. Imported records retain their provenance and feed the materialized catalog after confirmed import.

For organization-specific placement signals, `hardware.yaml` can declare weighted `placement_scoring.extensions`, while a model supplies matching values under `score_contributions`. These hooks are data-only, bounded to `0-100`, inspectable in score components, and cannot execute plugins. Use:

```bash
aiplane hardware scoring
aiplane models route --role chat --candidate MODEL_A --candidate MODEL_B
```

Only evidence with declared comparability affects measured quality/performance components. Local smoke results and arbitrary scores remain visible context, not universal quality claims.

## Controlled Real-Machine Calibration

A smoke run is useful local evidence, but it is not automatically comparable
performance evidence. Generate a read-only protocol before collecting a
cross-model or cross-runtime comparison:

```bash
aiplane benchmarks calibration-plan --model MODEL_ALIAS --runtime ollama --repeats 5
```

Record the exact model revision/quantization, runtime version, host fingerprint,
GPU/VRAM state, context length, concurrency, warm-up policy, and power mode.
Hold prompts, decoding, context, concurrency, thermal state, and power mode
steady across candidates. The plan prints the dry-run, measured-run, preview
import, and confirmed-import commands; it does not execute them.

Imported controlled records declare the following metadata. `ttft_ms` in a
controlled record must name its native or harness telemetry source; Aiplane will
not infer TTFT from elapsed time.

```json
"calibration": {
  "status": "controlled",
  "run_mode": "warm",
  "context_tokens": 8192,
  "concurrency": 1,
  "warmup_runs": 1,
  "power_mode": "performance"
}
```

## Evidence-to-Handoff Plan

After reviewing a compatible alias and collecting or importing any available calibration evidence, render one portable decision record for a runtime, client configuration, and optional external-agent starter. This reads existing profile and ignored local evidence only; it neither starts the runtime nor writes target configuration.

```bash
aiplane models handoff-plan \
  --role chat \
  --model MODEL_ALIAS \
  --runtime ollama \
  --context-tokens 8192 \
  --integration continue \
  --framework langgraph > model-handoff.json
aiplane models handoff-validate model-handoff.json
```

The artifact distinguishes unavailable calibration from controlled, runtime-specific evidence. A checksum mismatch, profile mismatch, workspace escape, malformed JSON, or secret-like material fails validation. For agent guardrails and optional local receipts, see [Machines, stacks, and orchestrators](machines-and-stacks.md#portable-agent-guardrails).

## Portable Calibration Bundles

Export only controlled, provenance-bearing records into a checksum-protected JSON
bundle. Preview is the default; neither command contacts a provider or changes a
runtime.

```bash
aiplane benchmarks calibration-export calibration.json
aiplane benchmarks calibration-export calibration.json --yes
aiplane benchmarks calibration-import calibration.json
aiplane benchmarks calibration-import calibration.json --yes
```

Export excludes uncalibrated smoke records and local source paths. Import checks
the bundle checksum and rejects uncontrolled records or secret-bearing material
before writing to the ignored local benchmark cache.

## Compare Saved Measurements

Compare saved or imported records across one dimension while holding the other recorded dimensions and the suite protocol constant:

```bash
aiplane benchmarks compare --by runtime
aiplane benchmarks compare --by model --runtime ollama
aiplane benchmarks compare --by machine --suite simple-python-codegen
aiplane benchmarks compare --by quantization
aiplane benchmarks compare --by context --model MODEL_ALIAS
```

Supported dimensions are `runtime`, `model`, `machine`, `quantization`, and `context`. A group reports leaders only when at least two distinct identities are present, the suite declares explicit comparability metadata, every row declares matching controlled calibration conditions, and essential identities/submission/metric definitions are known. The dimension's identity, rather than its display alias alone, establishes whether two candidates differ. A same-named model with different weights can be compared by model; it cannot silently pass as the same model in a runtime comparison.

Comparison basis includes the selected workload digest/task set, decoding, full non-varied runtime settings/version/build, hardware/software, model artifact/tokenizer, route/cache/concurrency/tools, harness/prompt/rubric identity, metric definitions and available throughput sources. A runtime comparison varies the runtime build/settings together; model, quantization, context, workload and machine remain fixed. A machine comparison varies fingerprint/hardware while software remains fixed. Context comparison allows only the context settings/calibration field to vary. Quantization comparisons retain model artifact controls; do not remove a revision control merely to force unlike records into one group. These are conservative comparisons, not whole-setup causal claims.

### Metadata required for ranking

Imported records may omit these fields and remain inspectable; `comparison_blockers` then lists the missing paths and `leaders` is empty. The built-in smoke runner hashes the actual selected task prompts/graders, supplies metric definitions and submission evidence, but does not discover exact weights, tokenizer, runtime build or host state. Its records remain uncontrolled until an external collection process supplies verified identities and conditions. No label makes an experiment controlled by itself.

The measurement record accepts these additional fields. Values below are illustrative identifiers, not real benchmark evidence:

```json
"comparison_context": {
  "workload": {
    "inputs": "sha256:reviewed-inputs",
    "rubric": "sha256:grader-and-external-grader-code",
    "prompt": "sha256:full-prompt-template",
    "harness": "harness-name-and-build"
  },
  "model": {"artifact": "immutable-weight-revision", "tokenizer": "immutable-tokenizer-revision"},
  "runtime": {"build": "runtime-build-or-image-digest"},
  "execution": {"route": "direct-runtime", "cache": "disabled", "concurrency": 1, "tools": "none"}
}
```

Also provide `suite.content_sha256` (the selected prompt/input/inline-grader digest), `runtime.version`, `runtime.settings.quantization`, `runtime.settings.context_tokens`, environment fingerprint/hardware/software and controlled calibration. External grader command text alone does not identify the executable: declare its version/hash in the rubric identity. `metric_definitions` gives each measured metric its unit and numerator/denominator, interval or method. For example:

```json
"metric_definitions": {
  "server_tokens_per_second": {"unit": "tokens/s", "numerator": "provider_output_tokens", "denominator": "server_generation_seconds"},
  "client_tokens_per_second": {"unit": "tokens/s", "numerator": "provider_output_tokens", "denominator": "client_dispatch_to_body_parsed_seconds"},
  "average_tokens_per_second": {"unit": "tokens/s", "method": "mean_available_source_rates"},
  "elapsed_ms": {"unit": "ms", "interval": "client_dispatch_to_body_parsed"},
  "quality_score": {"unit": "score_0_100", "method": "suite_evaluator"}
}
```

The installed measurement-code digest identifies local implementation edits. Command graders leave rubric identity unknown until their external executable/code is identified. [Measurement definitions](../../src/aiplane/benchmark_identity.py) own the built-in metric meanings. Different definitions produce different groups. Preview records, execution errors, absent/mismatched submitted settings and essential unknowns block ranking even when two records contain the same unknowns.  Quality, performance, throughput, elapsed time, and TTFT remain separate. TTFT leadership uses only runs with a non-empty `telemetry_source`; estimated or provenance-free latency is still displayed as evidence but cannot win an exact-TTFT comparison. Invalid local records become warnings rather than hiding valid groups.

## What The Built-In Suite Measures

The built-in benchmark set includes four small tasks:

- `analysis`: explain a simple Python function and identify an edge case.
- `completion`: complete a small Python function.
- `generation`: write a small Python function.
- `reasoning`: solve a small arithmetic word problem.

For each task, `aiplane` records backend, pass/fail, elapsed time, output length, expected keyword matches, evaluator output, and a 0-100 task score.

## Is It Objective?

Partly. Timings, output length, evaluator exit codes, expected-term checks, and JSON scores are objective for the specific benchmark spec. They are not a universal model-quality score.

The default suite is intentionally small so it can run on a laptop. Custom evaluators are the better path for serious checks because they can compile code, run unit tests, compare expected outputs, or check domain-specific constraints.

Current limitations:

- Built-in expected keyword checks are shallow.
- Generated-code execution exists only through custom evaluator commands.
- Token throughput and time-to-first-token are not available for every backend yet.
- Scores vary with quantization, context size, runtime settings, background load, and provider latency.

## Filtering With Scores

Catalog capability scores use a `0-5` scale:

```bash
aiplane models list --min-capability-avg-score 2.0
aiplane models list --capability coding>=3 --min-capability-avg-score 2.0 --sort-by avg
```

Saved benchmark scores use a `0-100` scale:

```bash
aiplane models list --require-benchmark
aiplane models list --min-benchmark-score 75
aiplane models list --min-benchmark-score 80 --sort-by benchmark --limit 3
```

You can combine provider/runtime/capability filters with benchmark filters:

```bash
aiplane models list --provider ollama --runtime ollama --capability code_generation>=3 --min-benchmark-score 70 --sort-by benchmark
```

Use `--score-source` when you only want catalog entries with a particular capability score source, such as `configured`, `catalog_entry`, or `catalog_heuristic`.
