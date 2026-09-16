# CareerPilot AI — Product AI Path Audit

Audit date: 2026-09-16. This audit traces the formal product API paths in source code. The
standalone real-provider validation runner is intentionally not treated as product evidence.

## Runtime configuration used for the product smoke

- `AI_PROVIDER=openai_compatible` with a locally configured DeepSeek-compatible key: configured.
- `DIFY_PROVIDER_MODE=fake`: configured locally; no Dify credential was used in this smoke.
- Database, uploads and FAISS paths were isolated under `data/runtime/phase4_6_product/`.
- The key value, Authorization header, resume source text and prompt bodies were not written to
  this audit.

## Formal product chains

Key source anchors used for this trace: `backend/app/api/resumes.py`,
`backend/app/services/resumes.py`, `backend/app/api/jobs.py`, `backend/app/services/jobs.py`,
`backend/app/api/career_assistant.py`, `backend/app/services/career_assistant.py`,
`backend/app/integrations/dify/knowledge_qa_providers.py`,
`backend/app/api/dependencies.py`, `backend/app/ai/providers/factory.py`, and
`backend/app/services/match_runs.py`.

### Resume parsing — real product path validated

```text
Frontend Resume pages
  -> POST /api/resumes/upload
  -> ResumeService.upload (private file storage + metadata)
  -> POST /api/resumes/{id}/extract
  -> ResumeService.extract (pypdf/python-docx text + source locations)
  -> POST /api/resumes/{id}/parse
  -> dependencies.get_resume_ai_provider
  -> create_resume_ai_provider(settings)
  -> OpenAICompatibleProvider.structure_resume
     when AI_PROVIDER=openai_compatible
  -> strict ResumeProfile/evidence validation
  -> parse_result persisted + ModelUsageLog
  -> POST /api/resumes/{id}/confirm
  -> ResumeService.confirm -> immutable ResumeVersion
```

Product smoke result: one anonymous PDF completed upload, extraction, real DeepSeek parsing,
structured-result validation and confirmation. The parse was `NEEDS_CONFIRMATION`, with one
attempt and a valid structured result; confirmation created a durable version. The corresponding
database row contains provider, model, operation, prompt version, latency, token counts and
success status.

### Job import — deterministic product path; no real AI call

```text
Frontend Jobs page
  -> POST /api/jobs/manual/preview
  -> JobService.preview_manual
  -> normalize_job_record / local skill normalization
  -> POST /api/jobs/manual
  -> JobService.import_manual -> private Job row
```

There is no formal product `JobAIProvider` injection or `/jobs/{id}/parse` endpoint. The
`create_job_ai_provider` factory and `OpenAICompatibleProvider.parse_job` contract are used by
the Phase 4 validation runner only. Therefore the Phase 4.5 Job results validate the provider
contract, not a real-model product Job path.

### Career Assistant / RAG — formal Dify contract; real Dify not validated

```text
Frontend Career Assistant page
  -> POST /api/career-assistant/qa
  -> CareerAssistantQAService LangGraph
  -> local FAISS/SQL knowledge + personal-context retrieval
  -> create_knowledge_qa_provider(settings)
     -> FakeKnowledgeQAProvider when DIFY_PROVIDER_MODE=fake
     -> DifyKnowledgeQAProvider when DIFY_PROVIDER_MODE=dify
  -> citation enrichment + persisted QA run + ModelUsageLog
```

The current local configuration has no usable Dify credentials, so the product smoke exercised
the formal API in Fake mode only. Direct OpenAI-compatible Career QA was validated by the
standalone Phase 4.5 contract runner, but it is not the provider used by this formal product
path. Production Dify Career Assistant remains unvalidated with real credentials.

### Matching — existing deterministic/hybrid path

The product match-run API consumes a confirmed resume version and imported job, then executes the
existing deterministic/hybrid graph with blocking rules and human review. The Phase 4.6 smoke
reached `WAITING_REVIEW`, produced a report, and confirmed it to `SUCCEEDED`.

No matching algorithm, weights, thresholds, blocking rules or holdout labels were changed.

## Smoke evidence boundary

The product smoke proves the Resume API wiring and DB observability, the deterministic Job import,
the matching state machine, and the formal Career Assistant API mode. It does not upgrade the
standalone Job parser or direct QA validation contracts into product capabilities.
