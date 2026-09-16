# Portfolio-safe metrics and claim boundaries

CareerPilot AI reports measurements from small, synthetic, manually annotated fixtures.  The
numbers are useful for demonstrating engineering discipline in a portfolio, but they are not
evidence of hiring outcomes or population-level model accuracy.

## Safe to claim

- The project has a frozen regression set (`eval-v1`, 52 cases) and a separate independent
  label-first holdout (`holdout-v1`, 20 cases).
- The deterministic matcher returns structured results with traceable evidence on the evaluated
  cases; the reported evidence validity and structured-result validity are dataset metrics.
- The holdout includes explicit tests for required/preferred skills, unknown aliases, soft job
  conditions, experience/education conflicts, language and work-eligibility states, and sparse
  postings.
- Parsing validation covers ten synthetic PDF/DOCX resumes and ten job descriptions using the
  existing deterministic text/evidence path.
- The semantic layer is documented as a controlled diagnostic using fake deterministic vectors;
  it is not presented as real embedding quality.

## Claim only with context

- Quote any precision, recall, F1, recommendation agreement, or parsing number with the dataset
  version, case count, scoring version, and synthetic/manual-label qualifier.
- Describe `deterministic-v1.1` as the frozen implementation evaluated at the time of the run;
  do not imply that the metric generalizes to all resumes or jobs.
- Explain that “required skill” and “missing skill” metrics are label-set metrics, while
  recommendation and match-band agreement depend on broad manually authored intervals.
- Treat fake-embedding hybrid results as integration/ranking/regression diagnostics only.

## Do not claim

- Do not claim “CareerPilot accuracy”, hiring-success prediction, recruiter agreement, fairness,
  or production reliability from these fixtures.
- Do not combine regression and holdout values into one overall accuracy or average score.
- Do not claim a real-provider LLM benchmark, real semantic similarity quality, OCR capability,
  or general PDF/DOCX understanding from the parsing validation.
- Do not imply that a missing skill is a blocking rejection; blocking-policy metrics are a
  separate explicit-conflict measurement.
- Do not hide the retained labelled failures or silently retune the matching algorithm to fit
  the holdout.
