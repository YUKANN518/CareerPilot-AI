# Technical interview Q&A

## 1. Why is the hybrid split 70/30?

It is the frozen product policy chosen to keep deterministic requirements primary while allowing
semantic retrieval to help with wording differences. It is not presented as a learned optimum; any
future tuning should be evaluated as a new version.

## 2. Why can semantic similarity not prove a skill?

Similarity says that texts are related. It does not prove the candidate performed the task, met the
required level, or has current eligibility. Confirmed source evidence and deterministic rules are
needed for that claim.

## 3. What does Blocking Risk mean?

Blocking Risk is a separate policy result for explicit or unresolved hard conditions such as
education, language, location, or work eligibility. It is not the same thing as a missing skill.

## 4. Why is holdout Blocking Risk recall only 40%?

The 20-case synthetic holdout contains long-tail qualification and eligibility scenarios. The
failures show that rule coverage and ambiguity handling are not general-purpose hiring logic. They
remain visible rather than being removed or tuned away.

## 5. How is hallucination reduced?

Resume fields carry evidence text and source locations, skills must contain evidence, and the user
confirms the immutable version. Unsupported claims are classified as missing or unknown instead of
being silently promoted to a match.

## 6. How is evidence generated?

The resume provider returns a strict Pydantic profile plus evidence metadata. The service validates
the schema, stores the parsed result, and exposes the evidence in the confirmation and report paths.

## 7. What did the real provider test prove?

The opt-in DeepSeek run produced schema-valid output for 6/6 resumes and 10/10 job descriptions,
with 100% resume evidence attachment and no unsupported skill claims in the tested set. It is not a
general model-accuracy benchmark.

## 8. Why is the production Job Parser deterministic?

The matcher only needs a normalized job representation. Structured/manual input is reproducible and
avoids adding hallucination risk to the core path. The real provider Job Parser is validated as a
capability contract, not advertised as a product dependency.

## 9. Why SQLite?

SQLite keeps the portfolio demo self-contained, easy to reset, and easy to run in Docker. It is an
explicit scope choice, not a claim that SQLite is the final store for high-concurrency production.

## 10. Why FAISS?

The project needs local vector retrieval for supporting evidence. FAISS is lightweight, offline,
and sufficient for the portfolio-sized corpus; the interface can be replaced by a managed vector
store if scale requirements change.

## 11. Why Sentence Transformers?

It supplies local multilingual embeddings for the supporting semantic signal. Demo mode uses a
deterministic fake embedding provider for reproducible tests and does not pretend that fake vectors
measure real semantic quality.

## 12. What does LangGraph do here?

It orchestrates the match-run nodes, event stream, retries, human-review checkpoint, and final
report persistence. It is workflow control, not a collection of autonomous agents deciding the
score.

## 13. Why include Dify?

Dify is an optional Career Assistant integration boundary for knowledge-grounded Q&A. The public
Core Demo does not require real Dify credentials; Fake mode and the product contract remain tested.

## 14. How are evaluation datasets separated?

`eval-v1` is regression-oriented and frozen. `holdout-v1` is label-first and independently authored.
Parsing validation and real-provider validation are separate again, so a single number cannot hide
which behavior was actually measured.

## 15. Why is the holdout recommendation agreement 65%?

Recommendation labels combine broad human-authored intervals and hard-policy outcomes. The lower
agreement shows calibration and rule-coverage limitations, especially in sparse or ambiguous jobs.

## 16. Why CPU-only PyTorch in Docker?

The portfolio container runs `EMBEDDING_DEVICE=cpu` and has no GPU inference requirement. Pinning
the official CPU index avoids shipping unnecessary NVIDIA CUDA runtime packages while keeping
`pyproject.toml` and `uv.lock` reproducible.

## 17. How would you scale to 100,000 users?

I would separate API workers from background match jobs, move from SQLite to PostgreSQL, store files
in object storage, use a managed or sharded vector index, add a queue, and introduce tenant-aware
observability. Those are future architecture steps, not hidden capabilities of this demo.

## 18. How are secrets protected?

`.env` is ignored, `.env.example` contains placeholders, Demo/Fake mode needs no provider key, and
the publication checklist scans tracked files and reports. Real validation records key status as
`configured` without persisting the key or Authorization header.
