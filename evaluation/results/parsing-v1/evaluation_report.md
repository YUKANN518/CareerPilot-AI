# Parsing Validation — parsing-v1

This validation uses ten new synthetic resume documents (five PDF and five DOCX) and ten
natural-language job description text files. It evaluates the existing deterministic text
extractor and skill/requirement evidence path only; it is not an LLM resume-structuring
benchmark.

## Metrics

| Metric | Result |
| --- | ---: |
| Resume samples | 10 |
| Job description samples | 10 |
| Resume text extraction success | 100.00% |
| Job text extraction success | 100.00% |
| Resume section extraction success | 100.00% |
| Resume skill precision / recall / F1 | 100.00% / 94.74% / 97.30% |
| Resume evidence attachment rate | 100.00% |
| Job requirement precision / recall / F1 | 100.00% / 100.00% / 100.00% |
| Required-vs-preferred accuracy | 100.00% |

The sample is deliberately small and synthetic. The numbers describe extraction behavior on
these fixtures, not general parsing quality or hiring outcomes.
