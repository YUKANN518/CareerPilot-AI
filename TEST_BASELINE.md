# CareerPilot AI Phase 1A Test Baseline

Baseline completed on 2026-09-16. Results below are copied from real local commands; no
network-backed AI provider was invoked.

## Verified environment

| Component | Version / result |
| --- | --- |
| OS | Windows, native PowerShell workflow |
| Python | 3.12.6 |
| Node.js | 24.14.1 |
| npm | 11.11.0 |
| Backend install | `python -m pip install -e ".[dev]"` succeeded in `backend/.venv` |
| Frontend install | `npm ci` succeeded from `package-lock.json` (446 packages installed) |
| Database migration | All 10 Alembic revisions applied from an empty Demo database |
| Standard backend start | `python -m uvicorn app.main:app ...` started and `/api/health` returned 200 |
| Demo wrapper | `scripts/start-demo.ps1` started API and UI; reset and second seed were idempotent |

`uv` was not installed on the test machine, so the supported pip path was used. No Python
lock file was generated as part of this phase.

## Final acceptance matrix

| Test | Command | Result |
| --- | --- | --- |
| Backend pytest | `python -m pytest` | **PASS — 285 passed, 0 failed, 0 skipped; 2 warnings; 84% coverage; 265.52 s** |
| Backend lint | `python -m ruff check app tests scripts` | **PASS** |
| Backend application types | `python -m mypy app` | **PASS — 133 source files** |
| TypeScript | `npm run type-check` | **PASS** |
| ESLint | `npm run lint` | **PASS** |
| Vitest | `npm run test` | **PASS — 30 files, 144 tests; 24.88 s after clean install** |
| Playwright | `npm run test:e2e` | **PASS — 27 tests, 1.3 min after clean install** |

The final matrix was run against Mock/Fake providers and isolated SQLite/upload/FAISS paths.
It did not require OpenAI-compatible or Dify credentials.

## Failure classification and resolution trail

### Backend

The first full run after tightening provider configuration collected 284 tests and produced
282 passes and 2 failures:

1. An interview-plan test still documented the supported deterministic local planner. The
   implementation was restored to that contract; this is not a fake external-model result.
2. A legacy answer-evaluation test expected an implicit Fake-provider fallback while Dify was
   selected without a key. The test was updated to require the explicit
   `DIFY_NOT_CONFIGURED` error.

A Windows regression test for FAISS persistence under a Unicode project path was then added,
bringing the final total to 285. The test proves the byte-serialization workaround without
changing retrieval, embeddings, scoring or matching behavior.

### Browser E2E

The Phase 0 blocker was reproduced first: Playwright's backend process failed with
`ModuleNotFoundError: app`. Starting the backend as a module from `backend/` fixed the import
contract without `PYTHONPATH` manipulation.

Once startup worked, the first complete browser attempt reached the product and produced 6
passes and 21 failures. Those failures were classified as stale fixture/view assumptions:

- the fixture source name was outside the explicit JobsDB/OfferToday public-snapshot view;
- job helpers did not select that public view;
- one reindex assertion expected an obsolete completion message;
- one heading locator was ambiguous.

After aligning the synthetic fixture and tests with the existing UI contract, a complete run
produced 25 passes and 2 interaction failures. The final two fixes were test-only: use the
actual create-source entry on the admin overview, and register the `window.confirm` handler
before clicking the interview completion button. The final 27-test run passed.

## Non-blocking warnings and excluded checks

- Pytest reports a LangGraph pending-deprecation warning for `allowed_objects` and a Starlette
  deprecation warning for the HTTP 422 constant.
- `npm ci` reports deprecated transitive `whatwg-encoding` and `glob@10.5.0` packages.
- `npm audit` reports 10 dependency findings (6 moderate, 4 high). No automatic or breaking
  audit fix was applied in Phase 1A.
- Strict `mypy app` passes. An intentionally broader exploratory `mypy app scripts` scan found
  31 errors in 10 historical data-generation and real-Dify diagnostic scripts. Those scripts
  are outside the application type-check command and are tracked in `BASELINE_ISSUES.md`.
- Real AI connectivity, cost, latency and output quality require credentials and non-sensitive
  test input, so they are not claimed by this offline baseline.
