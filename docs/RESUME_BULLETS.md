# Resume bullets

These bullets describe the frozen implementation without turning synthetic validation into a
general accuracy claim.

## Chinese

- 设计并实现证据约束的 AI 人岗匹配平台：将 PDF/DOCX 简历解析为严格结构化字段，绑定原文位置并引入 Human Verification，只允许可追溯的正式版本进入匹配。
- 构建六维确定性匹配引擎与 70/30 混合评分流程，独立展示 Skill Gap、Evidence Coverage 与 Blocking Risk，生成包含输入快照和评分版本的可解释报告。
- 集成 OpenAI-compatible DeepSeek Resume Provider 并完成 6 份匿名简历真实验证（结构化输出 6/6、证据附着率 100%）；保留 Mock/Fake Demo 模式，避免 CI 和公开演示依赖密钥。
- 建立 eval-v1 回归集、holdout-v1 独立留出集、parsing-v1 解析验证、Docker Compose、CI 与隐私扫描，覆盖 222 个后端测试、91 个前端测试和 16 个 E2E 测试。

## English

- Built an evidence-grounded AI job-matching platform that parses PDF/DOCX resumes into a strict schema, attaches source locations, and requires human verification before matching.
- Implemented a six-dimension deterministic matcher with a frozen 70/30 hybrid mode, separate skill gaps and blocking risks, and persisted explainable reports with input and scoring snapshots.
- Integrated an OpenAI-compatible DeepSeek resume provider and validated 6/6 anonymous resume cases with 100% evidence attachment in the opt-in real-provider run; kept Demo/Fake mode secret-free.
- Established regression, independent holdout, parsing, Docker, CI, and privacy gates across 222 backend tests, 91 frontend tests, and 16 E2E tests.

## Tech stack line

`Python 3.12 · FastAPI · Vue 3 · TypeScript · SQLAlchemy · SQLite · FAISS · Sentence Transformers · LangGraph · Docker Compose · Pytest · Vitest`
