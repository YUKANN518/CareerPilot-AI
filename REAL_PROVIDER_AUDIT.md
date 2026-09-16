# CareerPilot AI — Real Provider Audit

Audit date: 2026-09-16.  This is a read-only audit completed before Phase 4 implementation.
The existing `eval-v1`, `holdout-v1`, `parsing-v1` datasets and all matching configuration are
out of scope for changes in this phase.

## Feature/provider inventory

| Feature | Current provider | Real / Demo | Required in Phase 4? |
| --- | --- | --- | --- |
| Resume text extraction | `ResumeTextExtractor` (`pypdf` / `python-docx`) | Local deterministic | Yes, as input to parsing |
| Resume structured parsing | `MockAIProvider` by default; `OpenAICompatibleProvider` when `AI_PROVIDER=openai_compatible` | Demo by default; real-capable path exists | Yes |
| Job requirement parsing | `JobRequirementExtractor` + local skill dictionary | Deterministic, not an LLM provider | Yes; a real structured Job parser is currently missing |
| Career Assistant retrieval | Backend FAISS/local embeddings + SQL personal context | Local deterministic retrieval | Yes |
| Career Assistant generation | `FakeKnowledgeQAProvider` by default; `DifyKnowledgeQAProvider` when `DIFY_PROVIDER_MODE=dify` | Demo by default; Dify real path exists | Yes |
| Matching semantic component | `SentenceTransformersEmbeddingProvider` or `FakeEmbeddingProvider` | Local real model if configured; fake in tests/diagnostics | Optional; no external embedding validation required |
| Resume Optimization | `FakeResumeOptimizationProvider` or Dify | Hidden/optional | No; do not restore product scope |
| Chat Interview | Local plan provider plus fake/Dify chat/final providers | Hidden/optional | No; only independent smoke test if core passes |
| Dify workflows | Resume optimization, knowledge QA, interview plan/chat/final | Mixed; mode is global for Dify-backed factories | Audit only; retain only referenced configurations |

## Findings

1. Resume parsing already has a provider abstraction (`ResumeAIProvider`) with Mock and
   OpenAI-compatible implementations.  The service validates the returned JSON with
   `ResumeProfile.model_validate_json` and performs evidence checks before persistence.
2. The OpenAI-compatible resume provider already uses explicit `httpx` connect/read/write/pool
   timeouts and transport retries.  It currently retries at the transport layer without an
   application-level distinction between invalid credentials, 4xx errors and transient 5xx/429
   responses.
3. Provider errors are converted to `AIProviderError`, but the error message currently includes
   the configured base URL.  Credentials are not included; logs and persisted state still need a
   single, bounded observability contract.
4. Resume parsing retries are controlled by `RESUME_PARSE_RETRIES` (default 2).  Validation
   failures eventually enter the explicit manual-confirmation fallback; they do not silently use
   fake content in real mode.
5. Job requirement parsing is deterministic only.  There is no existing real Job-structured
   output schema/provider path, so it cannot yet report real-model schema validity or token usage.
6. Career Assistant retrieval is backend-controlled and citation enrichment is deterministic.
   Generation is fake by default or Dify-backed in real Dify mode.  There is no direct
   OpenAI-compatible Career Assistant generation provider yet.
7. Dify providers have explicit timeouts, bounded retries for selected transient failures,
   Pydantic output validation and masked attempt metadata.  Dify is still referenced by the
   formal Career Assistant path and by hidden optional features.
8. The semantic matching path uses local Sentence Transformers or the explicitly named fake
   provider.  It is not silently substituted by fake embeddings when local model loading fails;
   the configured provider raises an error.  Real external embeddings are not required for this
   phase.
9. `.env.example` documents `AI_PROVIDER`, `OPENAI_*`, `DIFY_*`, embedding and timeout settings.
   At the time of this pre-implementation audit there was no locally configured real key, so live
   provider validation was intentionally deferred. Phase 4.5/4.6 reports record the later local
   validation without exposing the key.
10. `.env` is ignored by the repository rules.  No API key is present in source, tests, reports or
    evaluation results.  The real-validation runner must remain opt-in and must redact secrets.

## Phase 4 boundary

The minimum safe implementation is to extend the existing provider abstraction for real Job
parsing and direct OpenAI-compatible Career Assistant generation, add shared prompt/version,
usage/latency metadata and explicit error handling, and provide an opt-in validation script.
Hidden Resume Optimization and Chat Interview remain out of the product scope.  No matching
weights, blocking rules, recommendation thresholds, skill aliases, hybrid ratio or evaluation
labels should be changed.
