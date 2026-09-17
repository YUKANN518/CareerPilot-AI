# Interview pitch

## 30 seconds

CareerPilot AI is an evidence-grounded job-matching platform. Instead of asking an LLM to invent a
match score, it requires a human-verified resume version, represents job requirements
structurally, scores six dimensions with deterministic rules, and uses local semantic retrieval
only as a supporting signal. The report shows the score, source evidence, skill gaps, and blocking
risks. I also built regression, holdout, real-provider, Docker, and privacy validation around it.

## One minute

I built CareerPilot because a fluent LLM recommendation is difficult to audit. The resume service
parses PDF/DOCX documents into a strict schema and stores field-level evidence. A user confirms a
version before it can be used. The matching path intentionally starts from manual or structured job
input, so the core result is reproducible and does not depend on an AI Job Parser. The deterministic
engine scores six dimensions and identifies hard conflicts separately. Hybrid mode combines the
frozen rule score with a local semantic supporting signal at 70/30, but semantic similarity cannot
prove a skill. A LangGraph workflow records each step and produces an explainable report. Demo mode
is offline and Dockerized; real DeepSeek resume parsing is validated separately.

## Three minutes

The key design decision is to treat evidence as a first-class object. Every parsed field can carry
the extracted value, confidence, source text, and source location. A skill without verified source
evidence cannot be presented as a confirmed match. This lets the UI distinguish MATCHED, PARTIAL,
MISSING, and UNKNOWN rather than collapsing uncertainty into a score.

The job side is intentionally deterministic. A structured input or CSV import becomes a normalized
job representation with required/preferred skills and qualification fields. The matcher evaluates
six dimensions, applies explicit blocking policy, and persists a scoring-version snapshot. The
optional semantic step uses local FAISS retrieval to find relevant project or work evidence; it is a
prioritization hint and never overrides a hard conflict. LangGraph orchestrates the long-running
workflow and human confirmation, while SQLite stores the portfolio-scale state.

I validated the system in layers: a frozen 52-case regression set, a separate 20-case holdout, a
small parsing set, and an opt-in DeepSeek run covering six resumes and ten job descriptions. The
holdout is intentionally not perfect—blocking-risk recall is 40% and recommendation agreement is
65%—so I can explain where the current policy fails. Docker uses CPU-only PyTorch because the
portfolio demo does not require GPU inference. Dify remains an optional Career Assistant
integration, not a hidden claim of a fully validated external deployment.

## Questions I answer explicitly

### Why not let an LLM score the candidate directly?

It would make hard constraints, evidence provenance, and regressions difficult to inspect. The LLM
can structure resume evidence, but the released matching decision is driven by versioned rules and
explicit policy.

### What is Evidence Grounding?

It is the contract that a parsed claim carries source text and location, and that only a confirmed
resume version is eligible for matching or report evidence.

### Why combine deterministic and semantic signals?

Rules are precise for requirements and conflicts; semantic retrieval helps find relevant evidence
when wording differs. The semantic signal is supporting context, not proof.

### What would you improve next?

I would improve long-tail aliases and eligibility calibration using more independently labeled data,
then re-run evaluation without changing labels to fit the model. I would not add features before
addressing those measurement limitations.
