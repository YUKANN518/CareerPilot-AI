# Public Repository Security Checklist

This checklist is the final pre-publication review for CareerPilot AI. It records repository
hygiene without reproducing any secret or private resume content.

## Secrets

- [x] Local `.env` exists only in the developer workspace and is ignored by `.gitignore`.
- [x] Root `.env.example` contains placeholders only; it has no live provider credential.
- [x] The configured provider key was checked by status only (`configured`); its value was not
  printed, logged, committed, or copied into a report.
- [x] Exact-key scan of publishable source and documentation files found zero matches.
- [x] Generic `sk-*` and long `Bearer` token scan found zero matches in publishable files.
- [x] CI uses Demo/Fake providers and does not require or print secrets.

## Private and generated data

- [x] Local SQLite databases, uploads, FAISS indexes, runtime directories, logs, caches,
  virtual environments, `node_modules`, and build/test output are ignored.
- [x] `data/` runtime artifacts were not staged for publication.
- [x] Tracked `sample_data/` and evaluation fixtures are synthetic/curated project fixtures and
  should still be reviewed before any public release containing personal-looking text.
- [x] Real-provider output is metadata-only in tracked reports; raw output is ignored.
- [x] Demo credentials are clearly labelled local demo-only credentials in the README.
- [x] DOCX fixture scan found only a synthetic `example.test` email domain in the test fixture;
  no real-looking phone number or government ID was found.

## Review before pushing to a public remote

Run `git status --short --ignored` and inspect the staged file list. Repeat the secret and private
data scans after any future configuration change. Never commit `.env`, real resumes, production
database exports, provider responses, authorization headers, or logs.
