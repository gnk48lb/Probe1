# DEVIATIONS — Probe 1d

Every deviation from `PREREG_1D.md` is recorded here: what was planned, what was
done instead, why, and when it was noticed.  Entries are appended, never edited
away.

**Status at `prereg-1d`:** no deviations.  The preregistration, the lock, the
analysis and its tests, and the smoke test were all finished before any seed
>= 5000 was run.

| # | phase | planned | done | why | noticed |
|---|---|---|---|---|---|
| — | — | — | — | — | — |

## Notes on development-time activity (before the preregistration)

- **`analyze_1d.py` was run once on the smoke data** (dev seeds 0–4) as a
  pipeline check.  No arm's rate was computed from it, no decision was taken
  from it, and the smoke is not part of the analysis.  The rule that
  `analyze_1d.py` may only see real Stage 1 data is respected from the first
  seed >= 5000 onwards.
