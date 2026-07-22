# Model Benchmarks

`aiplane models benchmark` runs small smoke benchmarks against a configured model. It answers a practical question: does this model work on this setup, and is it fast enough and good enough for the task shape you care about?


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
