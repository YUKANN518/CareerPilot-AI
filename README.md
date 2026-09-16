# CareerPilot AI

> 基于证据约束的人岗匹配与 AI 求职决策平台  
> Evidence-Grounded AI Job Matching & Career Decision Platform

CareerPilot AI 不是招聘爬虫或功能堆叠式“AI 工具箱”。它围绕一条可演示、可解释的
求职决策链路工作：

```text
Resume → Parsing → Evidence → Target Job → Requirements
       → Hybrid Matching → Blocking Rules → Match Report
       → Application Tracking
```

系统只把用户确认过、可以回溯到简历原文的内容当作候选人证据。匹配报告同时展示
确定性规则、语义检索证据、硬性条件阻断和缺失信息，AI 助手则基于知识库与个人上下文
回答问题并返回引用。

## Portfolio scope

默认产品导航只包含：

- 工作台（Dashboard）
- 我的简历（Resume）
- 目标岗位（Jobs）
- 匹配任务（Matching）
- AI 职业助手（可选集成，页面明确标记）
- 投递管理（Applications）
- 知识库（仅管理员）

Resume Optimization 与 Chat Interview 的实现、接口和测试仍保留，但不出现在默认
导航或匹配报告主操作中。Learning Plan、Cover Letter、旧版单题面试评分、职位抓取/API
同步和职位源管理已经移除。投递漏斗统一为 `SAVED → APPLIED → INTERVIEW → OFFER`
以及 `REJECTED` 五种状态。

详细范围决策见 [SCOPE_CLEANUP_PLAN.md](SCOPE_CLEANUP_PLAN.md)，Dify 配置变更见
[AI_CONFIG_AFTER_CLEANUP.md](AI_CONFIG_AFTER_CLEANUP.md)。真实的匹配公式、证据边界、
阻断规则与限制见 [MATCHING_METHODOLOGY.md](MATCHING_METHODOLOGY.md)。

## Core capabilities

- PDF/DOCX 简历安全上传、文本提取、结构化解析和人工确认。
- 不可覆盖的正式简历版本与字段级原文证据。
- 手工结构化岗位输入、规范化预览、CSV 批量导入和用户私有岗位 CRUD。匹配引擎使用的
  岗位要求来自结构化岗位输入；真实 LLM Job Parsing 已独立完成 Provider 能力验证，
  但不是生产匹配链路的要求。
- 硬技能、经验、学历、语言等确定性评分与硬性条件阻断。
- FAISS 语义召回与可追溯的混合匹配报告。
- 五状态投递看板、状态历史、备注与下一步时间。

## Optional Integrations

- **Career Assistant / Dify**：保留正式 API、检索、引用和 Fake/Dify Provider；当前默认
  为 Demo/Fake，可在配置 Dify 后作为可选集成验证。它不是 Core Portfolio Feature，
  不宣称真实 Dify 已验证。
- Resume Optimization 与 Chat Interview：保留实现和测试，但属于隐藏的实验性功能，
  不纳入核心作品集演示。

## Evaluation

The project deliberately separates four evaluation layers rather than presenting one misleading
“overall accuracy” number. All numbers below are small, synthetic, manually annotated or
deterministic fixture measurements—not hiring-success or population estimates.

### Regression Validation

`eval-v1` contains 52 resume-job cases covering high/medium matches, skill gaps, blocking
requirements, incomplete postings and insufficient evidence, plus 10 fixed semantic diagnostic
cases. Its first `deterministic-v1.1` baseline is frozen and regression-oriented.

The first frozen baseline runs the released `deterministic-v1.1` matcher without changing its
weights, aliases, thresholds or blocking policy:

| Metric | Result |
| --- | ---: |
| Required Skill F1 | 100.00% |
| Missing Skill F1 | 100.00% |
| Blocking Risk F1 | 100.00% |
| Evidence Validity | 100.00% |
| Unsupported Skill Claim Rate | 0.00% |
| Structured Result Validity | 100.00% |

The controlled hybrid diagnostic preserved blocking in all cases, reported seven semantic-case
improvements and zero new misjudgments. These are project-level validation results on synthetic
fixtures, not an academic benchmark, population estimate or production accuracy claim. Details
and failure analysis are stored under `evaluation/results/`.

### Independent Synthetic Holdout

`holdout-v1` is a separate label-first set of 20 newly authored Resume–Job cases. It covers
related-but-not-equivalent concepts (for example containerized vs Docker, relational database vs
PostgreSQL, AI vs PyTorch and cloud vs AWS), required/preferred wording, experience, education,
language, Hong Kong work eligibility, internship/graduate context, hybrid/on-site work and sparse
postings. Run it with:

```powershell
backend\\.venv\\Scripts\\python.exe -m evaluation.holdout
```

Its metrics are reported separately from `eval-v1`; no aggregate accuracy is calculated.

### Semantic Diagnostic

The existing fixed fake-embedding run is an integration/ranking diagnostic only. It is not a real
embedding or semantic-quality benchmark, and semantic-only blocking metrics are `N/A`.

### Parsing Validation

`parsing-v1` validates deterministic text/evidence extraction on ten synthetic resumes (five PDF,
five DOCX) and ten natural-language job descriptions. It measures section extraction, skill
precision/recall, evidence attachment and required-vs-preferred detection without claiming an LLM
or OCR benchmark. Run it with:

```powershell
backend\\.venv\\Scripts\\python.exe -m evaluation.parsing
```

See [PHASE_3_5_EVALUATION_HARDENING_REPORT.md](PHASE_3_5_EVALUATION_HARDENING_REPORT.md) and
[evaluation/PORTFOLIO_METRICS.md](evaluation/PORTFOLIO_METRICS.md) for the full split and safe
resume wording.

## Technology stack

| Layer | Technology |
| --- | --- |
| Frontend | Vue 3, TypeScript, Vite, Pinia, Vue Router, Tailwind CSS, Axios |
| Backend | Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2, Alembic |
| Data | SQLite, private local file storage |
| AI/RAG | OpenAI-compatible API, Dify workflows/chatflow, LangChain, LangGraph |
| Retrieval | Sentence Transformers, FAISS; deterministic fake embeddings in Demo Mode |
| Quality | Pytest, Ruff, mypy, Vitest, ESLint, Playwright |

## Local setup

Requirements: Python 3.12+, Node.js 20+, npm. SQLite is the supported database.

From the project root in PowerShell:

```powershell
cd backend
py -3.12 -m pip install uv
uv sync --extra dev --locked
cd ..
Copy-Item ..\.env.example .env
cd backend
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

In a second terminal:

```powershell
cd frontend
npm ci
npm run dev
```

Open `http://127.0.0.1:5173`. API health and documentation are available at
`http://127.0.0.1:8000/api/health` and `http://127.0.0.1:8000/docs`.

## Docker Demo

The default Compose stack is an isolated Demo Mode and requires no external API key:

```powershell
docker compose up --build
```

Open `http://localhost:5173`. The API is available at `http://localhost:8000`; demo credentials
are `admin@careerpilot.local / Admin123456!` (**Demo-only local credentials**). Runtime SQLite,
uploads and FAISS files are mounted under `data/runtime/docker-demo/` and are never copied into
the images. Stop the stack with `docker compose down`.

## Demo Mode

Demo Mode needs no external API key:

```powershell
.\scripts\start-demo.ps1
```

The wrapper uses isolated paths under `data/runtime/demo/`, runs migrations, loads fictional
portfolio data and starts the API/UI. It does not overwrite `data/careerpilot.db`.

```text
Email: admin@careerpilot.local
Password: Admin123456!
```

Reset the isolated demo with:

```powershell
.\scripts\reset-demo.ps1
```

演示数据和 AI 风格输出均由确定性的 Mock/Fake Provider 生成，不代表真实模型结果。

## AI configuration

`.env.example` at the repository root is the source of truth. `AI_PROVIDER=mock` and
`DIFY_PROVIDER_MODE=fake` select the offline demo providers; real providers must be selected
and configured explicitly. The normal product UI intentionally does not expose environment or
development-mode labels.

The OpenAI-compatible provider powers resume parsing, the opt-in real Job parser and the direct
QA validation contract. Dify powers product Knowledge QA and the hidden optional generation
features. Every feature has an independent key; missing real-provider configuration fails
explicitly. Secrets are never returned by `/api/health`.

The formal product paths have been audited separately from the validation runner. Resume parsing
is wired to the OpenAI-compatible provider and has an end-to-end real smoke result. The current
product Job flow is deterministic manual import (the real Job parser is validation-only), and the
formal Career Assistant path is Dify-backed; with local `DIFY_PROVIDER_MODE=fake`, it is an
offline smoke path until real Dify credentials are configured. See
[PRODUCT_AI_PATH_AUDIT.md](PRODUCT_AI_PATH_AUDIT.md),
[REAL_AI_CAPABILITY_MATRIX.md](REAL_AI_CAPABILITY_MATRIX.md) and
[PHASE_4_6_PRODUCT_PATH_REPORT.md](PHASE_4_6_PRODUCT_PATH_REPORT.md).
The final portfolio scope is frozen in
[PHASE_4_7_PORTFOLIO_SCOPE_FREEZE.md](PHASE_4_7_PORTFOLIO_SCOPE_FREEZE.md); optional integrations
do not block portfolio engineering.
The frozen system boundary is shown in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## AI Modes

CareerPilot has three explicit runtime modes exposed by the non-secret `/api/health` response:

- `demo`: Mock/Fake providers only; deterministic and offline.
- `mixed`: at least one configured real provider and one offline provider.
- `real`: configured real providers are required for the selected feature; a missing key or
  provider failure is surfaced as an error instead of silently returning fake content.

The matching engine and its frozen evaluation fixtures are independent of this mode. Fake
embeddings remain an explicitly named semantic diagnostic, not a hidden replacement for a real
embedding provider.

## Real Provider Validation

Phase 4 provides an opt-in, secret-free validation runner for six resumes (three PDF and three
DOCX), ten natural-language job descriptions and ten Career Assistant/RAG questions. Ordinary
pytest runs never call the network. The runner also refuses to overwrite previous results:

```powershell
cd backend
.\.venv\Scripts\python.exe -m scripts.validate_real_provider --force
```

Before running, set `AI_PROVIDER=openai_compatible`, the OpenAI-compatible endpoint/model/key,
and `RUN_REAL_AI_TESTS=1` in a local `.env`. The latest local run is recorded as a real
DeepSeek result with key status shown only as `configured`; reports do not contain the key. See
[REAL_PROVIDER_AUDIT.md](REAL_PROVIDER_AUDIT.md),
[PHASE_4_REAL_PROVIDER_REPORT.md](PHASE_4_REAL_PROVIDER_REPORT.md), and
[`evaluation/results/real-provider-v1/REAL_PROVIDER_VALIDATION.md`](evaluation/results/real-provider-v1/REAL_PROVIDER_VALIDATION.md).

## Tests

Backend:

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check app tests scripts
.\.venv\Scripts\python.exe -m mypy app
```

Frontend:

```powershell
cd frontend
npm ci
npm run type-check
npm run lint
npm run test
npm run build
npm run test:e2e
```

The Playwright runner creates an isolated database, upload directory and FAISS index. Phase 1A
baseline results are recorded in [TEST_BASELINE.md](TEST_BASELINE.md); Phase 1B results and the
intentional test-count changes are recorded in [PHASE_1B_REPORT.md](PHASE_1B_REPORT.md). The core
flow audit and completed explainability work are recorded in [CORE_FLOW_AUDIT.md](CORE_FLOW_AUDIT.md)
and [PHASE_2_REPORT.md](PHASE_2_REPORT.md).

## Data and privacy

Tracked fixtures under `sample_data/` are fictional. Files under `data/` are runtime artifacts
and must not be published without review. See [DATA_PRIVACY_CHECKLIST.md](DATA_PRIVACY_CHECKLIST.md).

## Engineering and publication

The pre-publication inventory is [PORTFOLIO_ENGINEERING_AUDIT.md](PORTFOLIO_ENGINEERING_AUDIT.md).
Dependency findings from `npm audit` are recorded in
[DEPENDENCY_SECURITY_REPORT.md](DEPENDENCY_SECURITY_REPORT.md), and the public architecture is
shown in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). CI uses Demo/Fake mode and does not require
DeepSeek or Dify secrets. See [LICENSE](LICENSE) for the MIT license.

## Known limitations

- Formal Dify Career Assistant connectivity and real-model groundedness/citation correctness still
  require local Dify credentials and manual review; the current product smoke uses Fake mode.
- The real Job parser is validated as a provider contract only; the formal product Job import is
  deterministic until a product parse endpoint is intentionally added.
- `npm audit` currently reports historical moderate/high advisories, including a production ECharts
  advisory; major upgrades are tracked separately and were not forced into the frozen release.
- The native environment installs the sentence-transformers stack even when Demo Mode uses
  fake embeddings.
- Dependency upgrades for the audited advisories are intentionally deferred until compatibility
  can be verified; they are recorded in `DEPENDENCY_SECURITY_REPORT.md`.
- Hidden Resume Optimization and Chat Interview are not part of the default recruiter demo
  path; expose them only after giving them a separate product decision.
