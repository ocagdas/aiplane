# Benchmark evaluation boundaries

The owner removed AP2 on 2026-10-18 to keep aiplane small. There is no generic wrapper protocol, external process manager, runner registry, runner-selection configuration, or wrapper execution/import command. Existing profile APIs, native smoke/custom suites, trusted command graders, measurement import and comparison remain.

## Model requests

Use existing OpenAI-compatible or native Ollama connections where the selected evaluator supports them. Aiplane already supports those protocols, plus existing Azure/Anthropic adapters. Do not add a model proxy or force every external tool through aiplane. OpenAI compatibility does not guarantee identical supported parameters or native server timing.

### Unsupported interfaces

The model's hosting runtime/provider determines its request interface; weights alone do not define an API. Native execution currently implements Ollama, OpenAI-compatible, Azure OpenAI and Anthropic requests. An unsupported provider raises an explicit execution error; the benchmark records the failed call. There is no automatic API translation, provider substitution or fabricated measurement.

For another interface, run an evaluator that supports that provider's SDK/API/CLI outside aiplane. Alternatively, use an independently configured translating gateway if it supports the provider and required features; identify that gateway and route in the setup being measured. Aiplane does not supply that gateway. Preserve the evaluator's raw results and convert them to the existing measurement contract for import. Import does not automatically understand arbitrary provider or evaluator JSON. Unknown protocol/submission evidence may be stored but still block controlled comparison; never relabel an unknown protocol to bypass that check. A model available only through a chat UI has no reliable unattended benchmark path in the current implementation.

## External evaluation

Run vLLM benchmarks, Promptfoo, llmfit benchmarking or a user's evaluator through that tool's own CLI/API. Use the endpoint and model binding from the reviewed profile. Retain the native result file and producer version. Convert useful results into the existing measurement record and use `aiplane benchmarks import`; no executable wrapper is required. Command templates are starting points, not execution adapters.

A small format converter is justified only by an actual native result file that the existing import cannot consume. It should read data, preserve units/source/version and produce an existing measurement record. It must not grow into another launcher, protocol or benchmark engine. Add one supported format/version at a time when the user's task needs it.

## Measurements retained from AP1

Server generation rate and client-observed request rate remain separate. Their displayed average uses only available values; missing is unknown and zero is a real value. Surrounding model-call time excludes grading and is not a complete harness-task measurement.

Comparison requires declared input/rubric/prompt/harness, model artifact/tokenizer, runtime/build/settings, hardware/software, route/cache/concurrency/tools, submitted decoding and metric definitions. Unknown essential identity blocks leaders while allowing inspection. Record operational failures per run and do not declare uncontrolled or incomplete measurements controlled. Sending settings does not prove the server honored them.

## Custom and manual checks

A user-defined benchmark needs fixed input cases, expected answers or a written grading rubric, model/setup settings, repeat count and separately named correctness and timing measures. For example, score category values on 20 support messages, then report pass count and request latency separately. A fast wrong answer must remain visible as wrong; do not treat the existing smoke score (which mixes keyword checks, time and output length) as a user-defined quality measure.

Use existing suites and explicit trusted command graders for automatic task checks. Preserve task-specific extra evidence under existing metadata without silently turning it into a universal score. Manual review must identify the task, output and rubric; a file workflow is implemented under the narrowed AP3. No TUI or generic plugin system is required.

See the [benchmark user guide](../user/benchmarks.md) for current commands and the [roadmap](../../ROADMAP.md#current-development-plan--2026-10-17) for remaining work. The current implementation has no first-party vLLM/Promptfoo result converters; manual-rating exchange is implemented through file commands.

### Automatic checks available now

- `exact_match` checks stripped output equality; `regex` checks a pattern; `expected_terms` is a keyword smoke check.
- `json` checks for a JSON object and required keys only. It does not validate expected field values or a complete JSON Schema.
- An explicitly enabled command grader receives prompt/output file paths. The user's program can check field values, run tests, calculate domain scores or call a separate judge, then print a score/pass JSON object. Keep any judge model, prompt and version in the rubric identity. Command graders are trusted execution, not a sandbox.
- An independently run evaluator can submit existing measurement records instead. Extra task evidence belongs in metadata; that does not make every extra field a supported ranking metric.

Native timing measures the model request/call, not grading plus the whole agent workflow. Measure complete agent tasks in the actual harness, including tool calls/retries, and label that interval explicitly. Missing usage, timing or cost stays unknown. Server/client rates and their available-source average remain separate from correctness.

### Manual review implemented under AP3

Native records retain each completed call's full prompt/answer and hashes. Command graders receive isolated transient files, cleaned after invocation; exceptions/timeouts/nonzero exits retain failure evidence and do not erase a completed answer. Unsupported/failed model calls and dry runs do not acquire answer artifacts.

`benchmarks review-export` and `review-import` bind original record contents, task/repeat, answers and rubric. Numeric/pass judgments and pairwise preference remain separate, with reviewer and timezone-bearing timestamp. Changed source records/outputs/rubrics, missing/duplicate ratings and invalid scales are refused. Export refuses overwrite; both commands preview by default. Reviews remain independent of metric leaders. Hashes are integrity checks against supplied inputs, not authenticated model/reviewer provenance. There is no review service, asynchronous queue, MCP file-writing tool or new executable protocol.

The [review guide](../user/benchmark-review.md) defines fields and commands. The [20-case example](../examples/task-evaluation/README.md) provides fixed task inputs/expected categories, category/boolean-urgency value grading and an independent evaluator that writes native results plus the existing import contract. Its retained synthetic answers produce 18 passes out of 20 by construction; no inference timing, model quality claim or controlled ranking is implied. No format converter is needed for that producer. Additional tool-specific converters require an actual unsupported format.
