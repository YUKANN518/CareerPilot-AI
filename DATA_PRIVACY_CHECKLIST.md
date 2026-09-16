# CareerPilot AI Data Privacy Checklist

> Baseline inventory date: 2026-09-15. No existing runtime file was deleted or moved in Phase 1A.

## Data boundary

| Location | Classification | Source-controlled? | Notes |
| --- | --- | --- | --- |
| `sample_data/` | Shareable synthetic fixtures | Yes | Fictional persona, companies, roles and guidance documents |
| `data/runtime/` | Generated demo/local runtime | No | Demo database, logs, uploads and vector indexes |
| `data/careerpilot.db` | Existing local user database | No | Treat as private even when its contents appear harmless |
| `data/uploads/` | Existing user uploads | No | May contain resumes, contact details and generated files |
| `data/faiss/` | Derived vector indexes | No | May retain recoverable text fragments and serialized metadata |
| `data/acceptance/` | Existing acceptance artifacts | No | Must be reviewed before any external distribution |
| `data/backups/` | Existing backups | No | Never publish without an explicit content review |

## Current private-runtime inventory

The Phase 1A read-only inventory found 113 files (10,795,016 bytes):

- 1 SQLite database (9,220,096 bytes);
- 37 uploaded PDF/DOCX files;
- 72 FAISS/index metadata files;
- 3 placeholder `.gitkeep` files.

This count is a risk inventory, not a claim that every file contains personal information. All
files under `data/` are treated as private until individually reviewed.

## Controls added in Phase 1A

- `.gitignore` excludes SQLite files, uploads, indexes, backups, acceptance artifacts, runtime
  logs and the complete `data/runtime/` tree.
- Demo startup selects `data/runtime/demo/` explicitly and does not open
  `data/careerpilot.db`.
- Demo AI uses Mock/Fake providers and therefore does not transmit fixture content to an
  external model service.
- Shareable examples live in `sample_data/`, use fictional identities and companies, and use
  reserved `.test` domains.
- E2E uses an isolated directory under the operating system temporary directory.

## Before publishing a repository or ZIP

- [ ] Confirm `.env` and every provider key are absent.
- [ ] Exclude the complete `data/` directory except intentionally empty placeholder files.
- [ ] Exclude `backend/.venv/`, `frontend/node_modules/`, caches, coverage and test reports.
- [ ] Search tracked text for phone numbers, personal email addresses, student IDs and addresses.
- [ ] Check Git history, not only the working tree, for previously committed secrets or resumes.
- [ ] Open every file under `sample_data/` and confirm all people, schools and companies are fictional.
- [ ] Regenerate the demo database from `sample_data/`; do not copy the local user database.
- [ ] Verify screenshots do not expose browser history, file paths, tokens or personal records.
- [ ] Rotate any key that may previously have appeared in a report, shell output or archive.

## Before enabling Real AI Mode

- [ ] Confirm the model provider's retention and training policy is acceptable.
- [ ] Obtain user consent before transmitting resume or interview content.
- [ ] Send only fields required for the requested operation.
- [ ] Avoid logging prompts, raw resumes, authorization headers or provider responses containing PII.
- [ ] Configure timeouts and ensure an error is shown instead of silently returning demo output.

## Safe cleanup policy

No automated cleanup command may target the project root, `data/`, a user profile directory or
an unresolved environment variable recursively. Cleanup must resolve and validate a narrow
generated target such as `data/runtime/demo/` or the E2E temporary directory before removal.
