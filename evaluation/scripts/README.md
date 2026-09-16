# Evaluation Scripts

Supported entrypoints are:

- `python -m evaluation.run` for the immutable `eval-v1` regression baseline;
- `python -m evaluation.holdout` for the independent `holdout-v1` set;
- `python -m evaluation.parsing` for deterministic PDF/DOCX and job-text parsing validation;
- `python evaluation/scripts/generate_parsing_fixtures.py` to reproduce the synthetic parsing
  documents and manifest.

Scripts remain offline, read-only with respect to product data, and write only to a selected
`evaluation/results/` directory or the versioned synthetic fixture directory.
