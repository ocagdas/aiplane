# Model Capabilities

`aiplane` shows a capability profile for each configured model. The profile is a
0-5 suitability score, not a benchmark percentage. It is meant to help users pick
a model for a task before running more expensive local or cloud tests.

## Score Scale

- `0`: not supported or not applicable.
- `1`: weak or incidental capability.
- `2`: usable for simple tasks.
- `3`: good for routine work.
- `4`: strong candidate.
- `5`: top-tier candidate for this profile/category.

## Categories

Text/code categories:

- `code_analysis`
- `code_generation`
- `code_completion`
- `debugging_refactor`
- `reasoning`
- `math`
- `tool_use`
- `general_chat`
- `embedding`

Common role labels:

- `chat`: instruction/chat model suitable for conversational IDE or CLI use.
- `autocomplete`: completion-oriented model suitable for code completion/autocomplete.
- `embedding`: vector/embedding model for retrieval; not a chat model.

Multimodal categories:

- `vision_image_understanding`
- `image_generation`
- `audio`
- `video`

Most local Ollama coding models are text-only, so image/audio/video scores are
usually `0` unless the model/provider is explicitly multimodal.


## Roles vs Capabilities

Roles and capabilities are deliberately separate:

- **Role**: how an integration uses a model, such as `chat`, `autocomplete`, `embedding`, `analysis`, or `generation`.
- **Capability**: a scored suitability signal, such as `general_chat`, `code_completion`, `embedding`, `code_analysis`, `tool_use`, or `reasoning`.

Current role-to-capability mapping used by integration planning:

- `chat` -> `general_chat`, `reasoning`, `tool_use`
- `autocomplete` -> `code_completion`
- `embedding` -> `embedding`
- `analysis` -> `code_analysis`, `reasoning`
- `generation` -> `code_generation`, `general_chat`
- `refactor` -> `debugging_refactor`, `code_analysis`

A model can have a capability without being selected for that role. For example, a coding model may have some `general_chat` score but still be better used as `autocomplete`.


## Enabled And Disabled Models

Each model alias in a profile can be enabled or disabled. Disabled entries stay
in `models.yaml`, but automatic selection, recommendations, and integration
planning skip them when `--enabled-only` is used or when a command only considers
active profile models. This is a soft profile-level blacklist/allowlist switch;
it does not delete model files and does not unload a runtime.

```bash
aiplane models disable some-model
aiplane models enable some-model
aiplane models list --enabled-only
```

Use this when a discovered model is too large, broken, unsuitable for policy or
licensing reasons, or simply not wanted in automatic planning.

## Recommendation Sorting

`models list` filters and displays catalog rows. It also ranks them with
`--sort-by name|avg|role|benchmark` and trims the output with `--limit`.

Without `--role`, `--sort-by avg` sorts by overall `capability_avg_score` from
highest to lowest. With one or more `--role` flags, `--sort-by role` sorts by
the role-relevant capability score first, then by overall average score.

```bash
aiplane models list --runtime ollama --enabled-only --sort-by avg --limit 3
aiplane models list --runtime ollama --role chat --enabled-only --sort-by role --limit 3
aiplane models list --runtime ollama --role chat --role autocomplete --enabled-only --sort-by role --limit 3
```

For `--role chat`, the role score is based on `general_chat`, `reasoning`, and
`tool_use`. For multiple roles, aiplane averages each requested role's mapped
capabilities, then averages those role scores so each requested role has equal
weight. The output includes `role_score`, `matched_roles`, and
`role_capabilities` so the ranking is visible.

## Benchmark References

The catalog uses well-known benchmark families as references when assigning or
reviewing scores:

- Coding: HumanEval, MBPP, LiveCodeBench, SWE-bench-style repair tasks.
- Reasoning/math: AIME, MATH, GPQA, Codeforces.
- General instruction following: MMLU/MMLU-Pro, IFEval, Arena-style preference
  evaluations.
- Multimodal, when added later: MMMU, MathVista, VQAv2, TextVQA, ImageNet-style
  vision checks, and task-specific audio/video evaluations.

Current local catalog scores are `catalog_heuristic` values based on model
family, approximate parameter count, and configured roles. Future work should add
measured scores from local smoke tests: load time, time to first token, tokens per
second, code-analysis latency, and pass/fail results on small code tasks.

## Commands

```bash
aiplane models list
aiplane models list --role chat
aiplane models list --role autocomplete
aiplane models list --role embedding
aiplane models list --runtime ollama --role chat --enabled-only --sort-by role --limit 3
aiplane models list --runtime ollama --role chat --role autocomplete --enabled-only --sort-by role --limit 3
aiplane models list --capability code_completion>=3 --sort-by avg
aiplane models disable some-model
aiplane models enable some-model
aiplane models show qwen-coder-32b
aiplane hardware recommend
```
