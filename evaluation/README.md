# CareerPilot AI Evaluation

This directory is the engineering evaluation surface for CareerPilot AI. It is separate from
`sample_data/`, which exists only for the product demo, and it never writes to the application
database.

The evaluation surface is split into four deliberately non-combinable layers.  The first two are
deterministic matching validation; the third is a semantic integration diagnostic; the fourth is
an offline parsing check.  None is a hiring-success benchmark.

## Regression Validation

`eval-v1` contains 52 manually annotated synthetic resume-job pairs reused from the already
frozen backend matching fixtures, plus 10 controlled semantic diagnostic cases.  It is a
regression-oriented set and its files and first baseline are immutable.  The fixtures begin at
structured resume/job inputs.

Run the first baseline from the project root:

```powershell
python -m evaluation.run
```

The project virtual environment is preferred automatically. To use an explicit backend runtime:

```powershell
backend\.venv\Scripts\python.exe -m evaluation.run
```

Outputs are written to `evaluation/results/`:

- `evaluation_summary.json`: metric summary and run metadata;
- `evaluation_details.json`: labels and per-case predictions;
- `evaluation_report.md`: human-readable methodology and results;
- `FAILURE_ANALYSIS.md`: Expected / Actual / Difference / category for failures;
- `baseline/`: immutable first-run raw outputs.

The runner refuses to overwrite an existing `baseline/`. Use a new output directory for a future
version and record any implementation fix in `EVALUATION_CHANGELOG.md`.

Primary metrics are required-skill precision/recall/F1, missing-skill precision/recall, blocking
risk precision/recall/F1, evidence validity, evidence-backed match rate, unsupported skill claim
rate and structured result validity. Match Band Agreement is secondary and currently `N/A` because
the inherited labels do not contain independent band annotations.

## Independent Synthetic Holdout

`holdout-v1` contains 20 newly authored Resume–Job cases under
`evaluation/dataset/holdout/`.  It is label-first: the annotation log records expected outcomes
before the first execution.  Cases are natural-language job descriptions and include ambiguous
related-but-not-equivalent concepts, required/preferred wording, soft conditions, eligibility,
experience, education and incomplete postings.  It does not reuse `eval-v1`, backend tests,
`sample_data` or demo jobs.

Run it without touching the regression baseline:

```powershell
backend\.venv\Scripts\python.exe -m evaluation.holdout
```

Results are in `evaluation/results/holdout-v1/`.  Holdout metrics and failures are reported on
their own; no overall accuracy combines the two datasets.

## Semantic Diagnostic

The deterministic matcher remains the primary baseline.  The existing fixed fake-embedding
runner is included only as a hybrid semantic diagnostic for integration, ranking and blocking
preservation.  Semantic-only blocking metrics are `N/A` because semantic retrieval has no
blocking policy.  These results are not real-provider semantic quality evidence.

## Parsing Validation

`parsing-v1` evaluates ten new synthetic resumes (five PDF and five DOCX) plus ten natural
language job descriptions.  It measures text extraction, section extraction, dictionary skill
precision/recall, evidence attachment and required-vs-preferred requirement detection through
the deterministic code path only.  It deliberately does not benchmark an unstable real AI
provider or claim OCR/LLM structuring quality.

```powershell
backend\.venv\Scripts\python.exe -m evaluation.parsing
```

Results are in `evaluation/results/parsing-v1/`.  Portfolio-safe wording and prohibited claims
are documented in [PORTFOLIO_METRICS.md](PORTFOLIO_METRICS.md).

## Real Provider Validation

`real-provider-v1` is an opt-in integration check, not a deterministic benchmark.  It prepares
six resume cases (three PDF and three DOCX), ten natural-language job descriptions and ten RAG
questions.  It validates strict structured output, evidence attachment, provider errors,
latency and token-usage metadata when a real provider is explicitly enabled.

```powershell
backend\.venv\Scripts\python.exe -m scripts.validate_real_provider --force
```

Set `RUN_REAL_AI_TESTS=1` and configure local credentials first.  Without them the runner makes
no network request and writes `SKIPPED_OPT_IN_REQUIRED`; it never substitutes Fake output or
overwrites another evaluation layer.
