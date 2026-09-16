# eval-v1 Dataset

`manifest.json` defines the immutable source contract for the first evaluation set. The 52 case
labels and structured fixtures are the reviewed files under `backend/evaluation/matching`; they
are evaluation inputs, not product demo data. The semantic diagnostic source contains 10 separate
cases, including transferable-skill, unrelated-text, incomplete-posting and blocking-text traps.

Case categories in the deterministic labels are:

- `HIGH_MATCH` — broadly supported required skills and no labelled blocker;
- `MEDIUM_MATCH` — partial support or a bounded qualification risk;
- `SKILL_GAP` — one or more explicit missing/partial skills;
- `BLOCKING` — explicit hard-requirement conflict;
- `INCOMPLETE_JOB` — sparse or unparseable job information;
- `INSUFFICIENT_EVIDENCE` — candidate evidence is absent, unknown or unconfirmed.

The inherited label schema deliberately uses broad score intervals and expected recommendation
sets. Required-skill, missing-skill, blocking-risk and evidence metrics therefore remain the
primary evaluation outputs. Independent `expected_match_band` labels are not present in eval-v1;
the report correctly shows that secondary metric as `N/A` instead of deriving a misleading target
from the score itself.

