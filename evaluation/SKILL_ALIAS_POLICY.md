# Skill Alias Policy

The evaluation set follows the released `skill-dictionary-v1`. Only common, unambiguous aliases
are treated as the same skill:

| Alias | Canonical skill |
| --- | --- |
| `JS`, `js` | JavaScript |
| `TS`, `ts` | TypeScript |
| `Postgres`, `postgres` | PostgreSQL |
| `Fast API`, `fast api` | FastAPI |
| `Vue 3` | Vue |
| `REST API`, `rest api` | RESTful API |
| `CI CD`, `ci cd` | CI/CD |
| `机器学习` | Machine Learning |
| `自然语言处理` | NLP |

The policy is intentionally narrow. Related concepts are not aliases:

```text
containerization ≠ Docker
container orchestration ≠ Kubernetes
AI ≠ PyTorch
database ≠ MySQL
cloud ≠ AWS
```

If an alias is added to the production dictionary after the baseline, record the issue, before/
after behavior, rationale and metric impact in `EVALUATION_CHANGELOG.md`; do not silently rewrite
the frozen baseline.

