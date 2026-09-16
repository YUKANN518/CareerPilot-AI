# Anonymous demo fixtures

Every person, school, company, URL and role in this directory is fictional. The reserved
`.test` domain prevents accidental email or web traffic. These files may be committed and
shared; files under `data/` must be treated as private runtime data instead.

`python -m scripts.seed_demo` reads these fixtures and adds them only to the database selected
by `DATABASE_URL`. The recommended `scripts/start-demo.ps1` command selects the isolated
`data/runtime/demo/` location automatically.
