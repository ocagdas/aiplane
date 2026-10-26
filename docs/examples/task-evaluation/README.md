# A fixed task, an automatic grader and human review

These 20 support messages are synthetic. `answers-fixture.json` deliberately contains 18 correct answers, one wrong category and one invalid JSON answer. They are not model outputs or model-performance evidence. The grader checks category values and boolean urgency against the expected answers; explanation quality is left to human review. It does not merely check whether a category key exists.

Copy this directory's files into `evaluation/` inside your workspace. Use your environment's Python. From that workspace:

```bash
python evaluation/evaluate.py evaluation/answers-fixture.json --model MODEL_ALIAS --output-dir evaluation/fixture-run
aiplane benchmarks import evaluation/fixture-run/measurements.json
aiplane benchmarks import evaluation/fixture-run/measurements.json --yes
```

The evaluator writes its native report and an existing measurement record. It refuses to overwrite an existing output directory. Its version, grader hash, native-result hash and supplied answers are retained. Timing/token values are absent because the script only grades supplied answers. Fixture import demonstrates data handling, not real-model qualification or comparable model ranking. Use an existing configured model alias for import; the alias identifies the source you declare, it does not verify that source independently.

For actual model calls using an existing supported endpoint:

```bash
aiplane benchmarks suite-validate evaluation/suite.json
aiplane models benchmark MODEL_ALIAS --spec evaluation/suite.json --dry-run
aiplane models benchmark MODEL_ALIAS --spec evaluation/suite.json --environment system
```

This executes the explicitly enabled local grader. Substitute your actual suite/expected answers and review the command before running it. The grader is not a sandbox. For code tasks, your grader should invoke a disposable test environment rather than execute generated code on the host. A custom grader may call a marking API and translate its response into the existing score/pass JSON; no API connector or asynchronous queue is supplied by this example. A nonzero grader exit is a failure; an exception/timeout is recorded and other cases continue.

For outputs from an unsupported model API, your own SDK/harness supplies an answers mapping keyed by case ID. Run the same offline evaluator against that file. For real use, retain the producer's actual model/version/settings and request measurements alongside the output. This example does not invent those facts or promote uncontrolled evidence to controlled.

## Score a saved result manually

Replace `RESULT.json` with the exact saved or imported measurement file:

```bash
aiplane benchmarks review-export evaluation/review.json --record RESULT.json --rubric evaluation/rubric.json
aiplane benchmarks review-export evaluation/review.json --record RESULT.json --rubric evaluation/rubric.json --yes
```

The preview writes nothing. The confirmed export refuses an existing file. It includes full prompts/answers and visible model aliases: this is not a blind-review interface. Edit only `reviewer`, `reviewed_at` (ISO timestamp with timezone) and the judgment values/notes. Each score judgment needs a numeric score within rubric bounds or a boolean pass decision. Keep IDs and item order unchanged. Then:

```bash
aiplane benchmarks review-import evaluation/review.json --record RESULT.json --rubric evaluation/rubric.json
aiplane benchmarks review-import evaluation/review.json --record RESULT.json --rubric evaluation/rubric.json --yes
```

Human judgments are stored under ignored `.aiplane/reviews/`, separately from automatic scores. Edited source files, outputs or rubrics, duplicate/missing judgments, previews and failed calls are refused. Hashes detect changes relative to supplied files; they do not authenticate reviewers or prove the declared model produced an answer. Keep source records and the rubric to revalidate a review.

## Compare two outputs manually

Export with `--mode pairwise --record LEFT.json --record RIGHT.json`. The two records must have matching suite/task/repeat identities and identical prompts. Fill each preference with `left`, `right`, `tie` or `abstain`. Import using both original `--record` arguments in the same order. Pairwise preference is not converted into a numeric quality score or added to controlled metric leaders.

Saved measurement/review files contain full task text. Keep sensitive tasks and outputs in private storage; do not publish them with the fixture. `--no-save` avoids native result persistence, though graders still receive transient input files while running. File operations do not call a model, start a service or install a tool. Live endpoint and whole-harness trials remain separate qualification.
