# Dependency Security Report

Audit date: 2026-09-16. Command: `npm audit --json` in `frontend/` after `npm ci`.

## Summary

| Severity | Count |
| --- | ---: |
| Critical | 0 |
| High | 4 |
| Moderate | 6 |
| Low / Info | 0 |

Total dependency graph: 496 packages (95 production, 402 development, 54 optional).

## Findings by dependency role

### Production dependency

- `echarts` — direct production dependency, **moderate** XSS advisory, current range `<6.1.0`.
  npm reports `6.1.0` as the available fix, which is a major upgrade and therefore requires a
  separate compatibility review of chart configuration before changing the frozen portfolio
  code.

### Development dependencies

- Direct: `@vitest/coverage-v8` (moderate), `vitest` (moderate) and `postcss` (moderate).
- Transitive: `@vitest/mocker`, `baseline-browser-mapping`, `brace-expansion` (high),
  `browserslist` (high), `js-yaml` (high) and `nanoid` (high).
- npm proposes major Vitest 5.x upgrades for the Vitest findings; the high transitive findings
  are in the development/build toolchain and are not shipped in the runtime image.

## Decision

No `npm audit fix --force` was run. The available fixes include major-version upgrades (Vitest 5
and ECharts 6.1) and were not applied without a dedicated compatibility task. Existing
`npm ci`, type-check, ESLint, Vitest, production build and Playwright gates remain green. The
production `echarts` advisory is an explicit release follow-up, not silently ignored.

## Safe follow-up

Before a dependency-upgrade change, review ECharts 6 migration notes and Vitest 5 compatibility,
apply upgrades in a separate branch, rerun all native/Docker/CI checks, and re-run `npm audit`.
This report intentionally records the current risk state without changing application behavior.

