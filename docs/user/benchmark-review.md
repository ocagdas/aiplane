# Review saved benchmark answers

`aiplane benchmarks review-export` creates a JSON worksheet from saved measurement files and a rubric. `review-import` validates a completed worksheet and stores it separately from automatic scores. Both preview by default; `--yes` writes files. They do not call models or graders, run a service or install dependencies. These commands are CLI-only; there is no MCP write tool or review UI.

## Inputs

Each source measurement record must contain successful, non-preview runs with unique `(task, repeat_index)` pairs. Runs need an `artifact` containing full `prompt` and `output` strings and their UTF-8 SHA-256 hashes. Native benchmark results now retain those fields for every completed model call, including separate repeats. External producers may supply the same artifact through the existing measurement import. Missing old answers cannot be reconstructed from output length or scores; rerun or supply the original answers with accurate provenance.

The rubric is a JSON object with exactly these fields:

```json
{
  "name": "answer-review",
  "version": "1.0",
  "instructions": "Score correctness from 0 to 5. Explain uncertain cases in notes.",
  "score_min": 0,
  "score_max": 5
}
```

Bounds must be finite numbers, with maximum greater than minimum. This is the human review scale; it does not change automatic scores' 0–100 scale.

## Export, complete and import

```bash
aiplane benchmarks review-export review.json --record result.json --rubric rubric.json
aiplane benchmarks review-export review.json --record result.json --rubric rubric.json --yes
```

Export refuses an existing destination. The worksheet contains visible model aliases, source-record hashes, full prompts/answers, rubric contents/hash and judgment rows. It is not a blind-review interface. Keep sensitive answers in private storage.

Edit only:

- `reviewer`: a non-empty reviewer name or pseudonymous ID.
- `reviewed_at`: an ISO timestamp with a timezone, such as `2026-10-18T10:00:00+00:00`.
- `judgments`: retain order and IDs; fill `score`, `passed` and `notes`. A score row needs a finite in-range score or a boolean pass decision. The unused field can stay null; do not infer one judgment from the other.

```bash
aiplane benchmarks review-import review.json --record result.json --rubric rubric.json
aiplane benchmarks review-import review.json --record result.json --rubric rubric.json --yes
```

The importer rebuilds the expected worksheet from the supplied original records and rubric. Changes to outputs, prompts, setup records, rubric, item IDs/order or required fields refuse import. Missing, extra, duplicate or invalid judgments also refuse before writing. Changing JSON whitespace does not change identity; changing its values does. Hashes detect changes relative to the supplied files, not forgery of the original evidence or reviewer identity. This is not a signature system.

Accepted reviews are stored at `.aiplane/reviews/<review-content-sha256>.json`. Reimporting identical content selects the same destination. It does not overwrite measurement files, turn preferences into numeric scores or add human scores to controlled metric leaders. Retain the original measurement files and rubric to revalidate a review later. There is no asynchronous marking queue or callback endpoint.

## Pairwise review

```bash
aiplane benchmarks review-export pairwise.json --record left.json --record right.json --rubric rubric.json --mode pairwise --yes
```

Exactly two distinct source records are required. Suite identity, task/repeat sets and prompts must match. Fill each `preference` with `left`, `right`, `tie` or `abstain`, plus optional notes. Import with both original `--record` arguments in the same order and the same rubric. Do not add numeric scores to pairwise rows.

The versioned worksheet uses `contract_version: "1.0"` and `record_type: "benchmark_review"`. `mode`, `rubric`, `rubric_sha256`, `records` and `items` are fixed evidence; `reviewer`, `reviewed_at` and permitted judgment values are review input. Unknown fields are refused. The CLI validator enforces cross-file hashes and rubric-dependent score bounds.

See the [20-case example](../examples/task-evaluation/README.md) for native automatic grading, independent evaluation/import and manual review using the same outputs. Its supplied answers are synthetic fixture data, not model results. See [benchmark measurement semantics](benchmarks.md) for timing and comparison limits.
