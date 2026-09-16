# holdout-v1

This directory is the independent, synthetic, label-first matching holdout.  `cases.json`
contains complete Resume/Job inputs and expected outcomes; `ANNOTATION_LOG.md` records the
annotation date and rationale before execution.  The set is intentionally separate from the
52-case `eval-v1` regression fixtures and from product/demo data.

Run it from the project root with:

```powershell
backend\.venv\Scripts\python.exe -m evaluation.holdout
```

The evaluator uses the released deterministic-v1.1 implementation and writes versioned outputs
under `evaluation/results/holdout-v1/`.  It refuses to overwrite a non-empty output directory.
