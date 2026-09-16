# CareerPilot AI — Phase 4.6 Product Path Closure Report

Completed: 2026-09-16

This report records the Phase 4.6 evidence boundary. Its provisional
`READY_FOR_PORTFOLIO_ENGINEERING = false` was superseded by the intentional Core/Optional scope
decision in [PHASE_4_7_PORTFOLIO_SCOPE_FREEZE.md](PHASE_4_7_PORTFOLIO_SCOPE_FREEZE.md).

## Outcome

Phase 4.6 closed the gap between the standalone real-provider validator and the formal product
API paths. One isolated product smoke used the locally configured DeepSeek-compatible provider for
Resume parsing. Job import and matching were exercised through their real product APIs. Career
Assistant was exercised through its formal API in the current local Fake mode because no Dify
credentials were available.

## Security

- The API key exists only in the local `.env`; `.env` is ignored by `.gitignore`.
- Key status was represented as `configured`; the complete value was never printed.
- Repository text, reports, README, validation JSON and smoke output contain no key value or
  Authorization header.
- No full resume source text was written to reports or usage logs.

## Formal product smoke

| Path | Result | Provider truth |
| --- | --- | --- |
| Resume upload → extract → parse → confirm | Passed for one anonymous PDF; structured result valid, one attempt, 3 technical skills with 3 evidence attachments, confirmed version created | Real `openai_compatible` / `deepseek-v4-flash` |
| Job preview → manual import | Passed; one private job created | Deterministic normalization; **no product AI call** |
| Matching | Passed; `WAITING_REVIEW` with report, then confirmed `SUCCEEDED` | Existing deterministic `deterministic-v1.1` path |
| Career Assistant (3 questions) | Formal API runs succeeded in Fake mode; personal-context questions returned citations, knowledge-only no-context question returned no citations | `FakeKnowledgeQAProvider`; real Dify not configured |

The Job parser and direct OpenAI-compatible Career QA provider remain validation-only contracts;
they must not be presented as formal product AI calls.

## ModelUsageLog verification

The real Resume product parse created an actual `ModelUsageLog` row with:

- provider: `openai_compatible`
- model: `deepseek-v4-flash`
- operation: `resume_structuring`
- prompt version: `resume-parser-v1`
- input/output tokens: `2,287 / 4,261`
- total tokens: `6,548` (computed as input + output; the table stores the two components)
- latency: `13,294 ms`
- success: `true`
- error code: none

The two Career Assistant provider calls made in Fake mode also created rows with provider
`fake`, workflow model `fake-knowledge-qa-v1`, prompt version `career-rag-v1`, and zero token
counts (the Fake provider exposes no token usage). Unsupported/no-context QA runs correctly skip
the provider and therefore do not create a provider usage row.

## Groundedness and citations

The direct Phase 4.5 RAG artifact deliberately retains `PENDING_MANUAL_REVIEW` for groundedness,
citation correctness and unsupported claims. Phase 4.6 product RAG used Fake output, so its
answers are useful for API/citation wiring checks but are not evidence of real-model groundedness.

Manual classification remains:

- `SUPPORTED`: not claimed for a real formal Dify run in this phase.
- `PARTIALLY_SUPPORTED`: not claimed for a real formal Dify run in this phase.
- `UNSUPPORTED`: the knowledge-only no-context smoke question was handled as an unsupported/
  insufficient-evidence response with zero citations.

No LLM judge was introduced.

## Phase 4.5 direct-provider results retained

- Resume: 6/6 structured-valid; 18 skills; 100% evidence attachment; 0 unsupported skills;
  14,142.33 ms average; 13,728 / 23,385 / 37,113 tokens.
- Job contract: 10/10 structured-valid; 26 required entries; 9 preferred entries;
  7,036.80 ms average; 6,940 / 15,572 / 22,512 tokens.
- Direct QA contract: 10 questions, 7 provider calls, 3 deterministic unsupported prechecks;
  2,923.86 ms average; 5,734 / 3,097 / 8,831 tokens. Groundedness/citation correctness remain
  manual-review fields.

## Dify and remaining limitations

The current local configuration uses `DIFY_PROVIDER_MODE=fake` and has no usable Dify knowledge
QA credentials. Per the allowed Phase 4.6 boundary: the direct OpenAI-compatible provider is
validated, while the production Dify Career Assistant remains unvalidated with real credentials.
The product also lacks a real Job parsing endpoint; the current manual Job path is intentionally
deterministic. Hidden Resume Optimization and Chat Interview paths were not expanded.

`READY_FOR_PORTFOLIO_ENGINEERING = false` for a portfolio claim that says the entire product is
real-AI backed. The Resume product path itself is ready to demonstrate, with the above caveats.

## Error handling and privacy checks

Existing no-network unit/contract tests cover invalid configuration, missing-key construction,
authentication failures, timeout/retry behavior and structured-output validation failures. No
additional live calls were made to manufacture errors. The product UI error-state tests and the
full Playwright suite cover bounded error rendering and loading-state transitions.

## Regression gates

The post-smoke regression commands completed successfully:

- Product backend Pytest: **222 passed** (2 existing warnings)
- Evaluation tests: **8 passed**
- Ruff: **all checks passed**
- mypy: **no issues in 111 source files**
- TypeScript type-check: **passed**
- ESLint: **passed**
- Vitest: **25 files / 91 tests passed**
- Playwright: **16 passed**

**No matching algorithm, weights, thresholds, blocking rules or holdout labels were changed.**
