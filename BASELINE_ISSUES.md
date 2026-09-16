# CareerPilot AI Phase 1A Baseline Issues

This list separates resolved baseline blockers from deliberately deferred engineering work.
Phase 1A did not remove product features or redesign matching, RAG, resume parsing, scoring or
LangGraph orchestration.

## Resolved in Phase 1A

| Severity | Issue | Resolution and evidence |
| --- | --- | --- |
| P0 | Playwright backend failed with `ModuleNotFoundError: app` | E2E now starts `python -m scripts.run_e2e` from `backend/`; 27/27 browser tests pass without a custom `PYTHONPATH`. |
| P0 | Demo startup could accidentally share local runtime paths | Demo scripts force `data/runtime/demo/`; the seed command refuses any database, upload or FAISS path outside that boundary. |
| P1 | UI did not disclose whether output came from fake or real providers | `/api/health` exposes only safe provider/mode metadata and the header shows Demo AI, Mixed AI or Real AI. |
| P1 | Dify answer evaluation silently returned fake output when a real provider was selected but unconfigured | The flow now returns an explicit configuration error; the deterministic local interview-plan path remains documented and tested. |
| P1 | Native FAISS persistence failed under the project's Chinese Windows path with `Illegal byte sequence` | Index bytes are serialized/deserialized in memory and persisted through Python path APIs; a Unicode-path regression test passes. |
| P1 | Demo records and knowledge files were not reproducible or shareable | `sample_data/` contains fictional fixtures; migration, seed, re-seed and reset were verified. |
| P2 | E2E fixtures assumed a retired jobs view and several tests raced or used stale text | Synthetic fixture naming, explicit snapshot selection, exact locators and dialog sequencing now match the existing product contract. |
| P2 | One application module failed strict mypy because a loop variable was reused with incompatible inferred types | Variables were named by knowledge/personal context; `mypy app` passes across 133 files. |

## Open after Phase 1A

| Severity | Issue / risk | Recommended next step |
| --- | --- | --- |
| P1 | `npm audit` reports 10 findings (6 moderate, 4 high), and install warns about deprecated transitive `glob@10.5.0` and `whatwg-encoding`. | In an engineering phase, run a dependency-tree audit, update direct parents selectively, and repeat unit/E2E tests. Do not use `npm audit fix --force` blindly. |
| P1 | Real OpenAI-compatible and Dify paths were not exercised because no credentials were provided. | Add opt-in, redacted contract tests with spending limits and synthetic input; keep them outside the offline default suite. |
| P1 | Existing `data/` contains a private local database, 37 uploaded documents and derived indexes. The directory is ignored but was not moved or deleted. | Follow `DATA_PRIVACY_CHECKLIST.md` before publishing; generate a clean repository/ZIP from source plus `sample_data/`, never from the current runtime tree. |
| P2 | Python dependency ranges are broad and no reproducible lock file exists. | Select pip-tools or uv in a later engineering phase and commit a Python 3.12 lock after compatibility testing. |
| P2 | Demo installation pulls the large sentence-transformers/PyTorch stack even though fake embeddings are used. | Split optional real-embedding dependencies only after mapping imports and validating both installation profiles. |
| P2 | Strict application typing passes, but `mypy app scripts` exposes 31 errors in 10 historical generation/real-Dify diagnostic scripts. | Type or quarantine those scripts when formalizing developer tooling; keep `mypy app` as the current documented application gate. |
| P2 | LangGraph and Starlette emit two backend deprecation warnings. | Pin/test compatible upgrades and replace the deprecated 422 constant in a dependency-maintenance change. |
| P2 | Browser coverage is broad but lacks one concise portfolio-oriented smoke journey. | In Phase 1B or a test-focused phase, add one named resume → job → match → assistant → application demonstration test. |
| P3 | The supplied workspace is not a Git repository, so tracked-file and history-level secret checks cannot be performed here. | Initialize or restore version control before publishing and scan the full Git history for secrets and personal data. |

## Scope decisions deferred to Phase 1B

Learning Plan, Cover Letter, Interview, Job Sources, Admin and Dify remain present. Whether any
of them should be hidden, simplified or removed for the resume version is a product-scope
decision for Phase 1B, after the now-green native baseline is used as the safety net.

