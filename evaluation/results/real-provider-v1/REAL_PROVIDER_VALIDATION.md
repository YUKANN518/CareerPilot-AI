# Real Provider Validation — real-provider-v1

- Status: `COMPLETED_WITH_REAL_PROVIDER`
- Resume cases: `6`
- Job cases: `10`
- RAG questions: `10`
- Credentials: never written to this report

## Resume Parsing

Results were produced with `AI_PROVIDER=openai_compatible`, model `deepseek-v4-flash`, and
the opt-in flag enabled. The key itself is not present in this report.
- Cases: `6`; successful cases: `6`
- Structured output validity: `6 / 6`
- Skill extraction: `18` technical/soft skills returned across the six cases
- Evidence attachment: `100.00%` average
- Unsupported/hallucinated skills observed by evidence containment check: `0`
- Average latency: `14,142.33 ms`
- Tokens (input / output / total): `13,728 / 23,385 / 37,113`

## Job Parsing

The real **validation-only** path validates `JobRequirementProfile` with Pydantic and records
required/preferred counts. The formal product Job flow remains deterministic manual import; it has
no AI parser endpoint.
- Cases: `10`; successful cases: `10`
- Structured output validity: `10 / 10`
- Evidence attachment: `100.00%` average
- Required skill entries returned: `26` across 10 cases
- Preferred skill entries returned: `9` across 10 cases
- Experience / education / language / eligibility: structured fields were validated; field-level
  accuracy was not recomputed after the run because the validation artifact intentionally does not
  persist full model output or private source text.
- Average latency: `7,036.80 ms`
- Tokens (input / output / total): `6,940 / 15,572 / 22,512`

## Career Assistant / RAG

RAG used the direct OpenAI-compatible QA contract because `DIFY_PROVIDER_MODE=fake`; no Fake
answers were substituted. This is a provider-contract result, not a formal product Dify run.
- Total questions: `10`
- Provider calls: `7 / 7` (four SUPPORTED + three PERSONAL_CONTEXT)
- Unsupported questions: `3`, handled by evidence precheck without API calls
- Citation present: `4 / 7` provider answers
- Citation correctness: `PENDING_MANUAL_REVIEW`
- Groundedness: `PENDING_MANUAL_REVIEW` using SUPPORTED / PARTIALLY_SUPPORTED / UNSUPPORTED
- Unsupported refusals: `3` expected prechecks; unsupported claims: `PENDING_MANUAL_REVIEW`
- Average latency: `2,923.86 ms`
- Tokens (input / output / total): `5,734 / 3,097 / 8,831`

## Observability

Each attempted real call records feature, provider, model, UTC timestamp, success/error code,
latency, prompt version and usage when the provider returns token counts. All 23 attempted calls
returned token usage. The standalone validation runner stores this metadata in `validation.json`;
it does not create application `ModelUsageLog` rows because it has no user/task transaction.
Product service paths still write `ModelUsageLog` with the same fields.

## Failures and error handling

No real Provider call failed in this run. Invalid configuration, missing-key behavior,
authentication errors, retry semantics and structured-output failures are covered by the
no-network contract tests; no extra live calls were made to manufacture failures.

## Security and limitations

API keys, authorization headers, full prompts and private inputs are excluded. This is a small
opt-in provider validation, not a matching benchmark or a production accuracy claim.
