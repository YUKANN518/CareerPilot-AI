# CareerPilot AI — Two-minute demo script

Use the Docker Demo with the synthetic account from the README. Keep the browser at 1440×1000
or similar and use the generated screenshots in `docs/images/` as optional cutaways.

## 0:00–0:15 — The problem

“Many LLM job matchers return an impressive score but cannot show which resume evidence supports a
claim. CareerPilot separates verified evidence, deterministic requirements, semantic relevance,
and hard eligibility risks.”

## 0:15–0:35 — Resume evidence

Open **我的简历** and the anonymous Demo resume. Show the structured status, immutable version,
and field-level evidence. Explain that parsing can use the real OpenAI-compatible DeepSeek provider,
while the public Docker Demo uses Mock mode.

## 0:35–0:50 — Structured job input

Open **目标岗位** and select **AI Product Intern**. Point out that the matching path consumes a
structured job representation: required skills, preferred skills, education, language, and
eligibility. The production path does not depend on an AI Job Parser.

## 0:50–1:15 — Matching workflow

Choose the confirmed resume version and **混合匹配**. Start the run and show the LangGraph nodes:
input validation, deterministic matching, semantic retrieval, blocking-risk checks, report saving,
and human confirmation. Explain the frozen 70/30 policy: rules remain primary and semantic
relevance is only a supporting signal.

## 1:15–1:45 — Explainable report

Open the report and show, in order:

1. Overall match and recommendation cap.
2. Rule, semantic, and hybrid scores.
3. Evidence coverage and semantic supporting evidence.
4. Six scoring dimensions.
5. Matched skills and skill gaps with source evidence.
6. Blocking Risk, kept separate from ordinary skill gaps.

Use the sentence: “A semantic hit can prioritize a requirement, but it cannot prove a capability
or override a blocking conflict.”

## 1:45–2:00 — Close

“The project is intentionally honest about scope: the core is real resume parsing, structured job
input, deterministic and hybrid matching, explainable reports, and application tracking. Dify is
optional, evaluation data is synthetic, and the holdout limitations remain visible.”

Do not show `.env`, API keys, private uploads, debug logs, hidden experimental modules, or Docker
installation details during the portfolio demo.
