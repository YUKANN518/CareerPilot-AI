# CareerPilot AI Phase 4 — Real Provider Validation Report

Completed on 2026-09-16.  This phase adds an auditable, opt-in real-provider validation
surface without changing the matching engine or presenting offline fixtures as live-model
results.

## Outcome

The Phase 4.5 opt-in run completed with `COMPLETED_WITH_REAL_PROVIDER`.  It used the configured
OpenAI-compatible DeepSeek provider and made exactly 23 provider calls: 6 resume, 10 job and 7
RAG calls.  The three UNSUPPORTED RAG questions were stopped by deterministic evidence precheck,
so they did not consume API calls.  No API Key value was printed or persisted.

To run locally with a disposable credential, configure `AI_PROVIDER=openai_compatible`, the
OpenAI-compatible base URL/model/key, and explicitly set `RUN_REAL_AI_TESTS=1`.  The command is:

```powershell
backend\.venv\Scripts\python.exe -m scripts.validate_real_provider --force
```

The runner refuses to overwrite an existing result directory unless `--force` is provided and
never writes keys, Authorization headers, full prompts or private input text to its reports.

## Phase 4.5 real results

### Provider

- Provider: `openai_compatible`
- Model: `deepseek-v4-flash`
- Key status: `configured` (the value is not included anywhere in the reports)

### Resume Parsing

- Cases: `6` (3 PDF, 3 DOCX)
- Successful: `6 / 6`
- Structured validity: `6 / 6`
- Skills returned: `18`
- Evidence attachment: `100.00%` average
- Unsupported/hallucinated skills observed by evidence containment check: `0`
- Average latency: `14,142.33 ms`
- Tokens input/output/total: `13,728 / 23,385 / 37,113`

### Job Parsing

- Cases: `10`
- Successful: `10 / 10`
- Structured validity: `10 / 10`
- Required skill entries returned: `26` across 10 cases
- Preferred skill entries returned: `9` across 10 cases
- Evidence attachment: `100.00%` average
- Experience, education, language and eligibility fields were structurally validated.  Their
  field-level accuracy was not recomputed because the secure result artifact does not persist
  full model output or private source text.
- Average latency: `7,036.80 ms`
- Tokens input/output/total: `6,940 / 15,572 / 22,512`

### Career Assistant / RAG

- Questions: `10`
- Direct provider calls: `7 / 7` (4 SUPPORTED and 3 PERSONAL_CONTEXT)
- Unsupported questions: `3`, deterministic precheck refusal without API calls
- Citation present: `4 / 7` provider answers
- Citation correctness: `PENDING_MANUAL_REVIEW`
- Groundedness: `PENDING_MANUAL_REVIEW` using SUPPORTED / PARTIALLY_SUPPORTED / UNSUPPORTED
- Unsupported refusals: 3 expected prechecks; unsupported claims remain `PENDING_MANUAL_REVIEW`
- Average latency: `2,923.86 ms`
- Tokens input/output/total: `5,734 / 3,097 / 8,831`

### Failures

No provider call failed in this run.  The result intentionally retains the RAG manual-review
fields instead of treating citation presence as citation correctness or groundedness.
Invalid configuration, missing-key behavior, authentication errors, retry semantics and
structured-output failures are covered by the no-network contract tests; no extra live calls were
made to manufacture failures.

### Observability

All 23 attempted calls returned provider usage metadata. The standalone validation runner stores
provider/model/feature/prompt version, latency, token counts, success and error code in
`validation.json`. It does not create application `ModelUsageLog` rows because it has no user/task
transaction; the product service paths write those rows with the same fields. No API Key,
Authorization header or full resume text is present in the artifact.

## Provider and feature scope

| Feature | Phase 4 status | Contract |
| --- | --- | --- |
| Resume Parsing | Ready for opt-in validation; 6 cases (3 PDF, 3 DOCX) | `OpenAICompatibleProvider` + strict `ResumeProfile` validation |
| Job Requirement Parsing | Ready for opt-in **contract** validation; 10 natural-language JDs | Same OpenAI-compatible provider + strict `JobRequirementProfile`; no formal product parse endpoint |
| Career Assistant / RAG | 10 questions prepared; Dify or direct OpenAI-compatible validation | Existing backend retrieval/citation contract; strict `KnowledgeQAWorkflowOutput` |
| Matching | Frozen and untouched | Existing deterministic/hybrid implementation |
| Fake embeddings | Retained for semantic diagnostics | No silent substitution in a configured real path |
| Resume Optimization / Chat Interview | Hidden optional scope only | Not restored to primary navigation or validation |

The DeepSeek endpoint is the documented OpenAI-compatible target through the existing default
base URL/model settings.  The provider abstraction is shared by resume parsing, job parsing and
the direct QA validation contract.  In the product, Career Assistant generation continues to use
the formal Dify contract because that is the existing grounded RAG integration; the validation
script uses Dify when explicitly configured, otherwise the real OpenAI-compatible QA provider,
and never substitutes Fake answers.

Phase 4.6 source audit confirms that the product's current Job flow is deterministic manual
normalization, so the ten live Job cases above must not be presented as product Job AI calls.

## Reliability and safety changes

- Explicit connect/read/write/pool timeouts are applied to every OpenAI-compatible call.
- Only timeout, 408, 429 and selected 5xx responses are retried, with at most three total
  attempts. Invalid credentials and non-retryable 4xx responses fail immediately with bounded
  error codes.
- Structured JSON is validated with Pydantic models using `extra="forbid"`; skill evidence must
  be present and traceable to the supplied source text.
- Prompt versions are recorded (`resume-parser-v1`, `job-parser-v1`, `career-rag-v1`).
- `ModelUsageLog` now records prompt version together with provider/model, latency, success and
  error code. Token counts remain explicitly unknown when a provider omits usage data; no
  unreliable cost estimate is invented.
- Real-mode provider construction raises an explicit configuration error and never falls back to
  Mock/Fake output.

## UI and Dify audit

The existing frontend already surfaces bounded provider error codes for resume, matching and QA
run failures.  `/api/health` exposes the non-secret `ai_mode`, provider and Dify mode for an
operator-facing diagnostic, while the normal product navigation does not restore hidden optional
features.  Dify knowledge QA remains a referenced formal integration; resume optimization and
interview workflows stay outside the primary portfolio scope.

## Quality gates

- New provider contract tests pass without network access.
- Backend full suite: 222 tests passed; evaluation contract suite: 8 tests passed.
- Frontend type-check and ESLint pass; Vitest remains 25 files / 91 tests passed.
- Ruff passes for all Phase 4 Python files.
- Mypy passes for the entire backend application (111 source files).
- The opt-in runner defaults to a no-network blocked report and has a separate output directory
  from the frozen `eval-v1`, `holdout-v1` and `parsing-v1` results.

The live run validates connectivity, structured output, evidence containment and usage telemetry.
No groundedness or citation-correctness score is claimed until the bounded manual review is
completed. Token totals are reported from the provider; no cost estimate is invented.

**No matching algorithm, weights, thresholds, blocking rules or holdout labels were changed.**

Phase 4 ends here.  Docker packaging and GitHub Engineering are intentionally out of scope for
this phase.
