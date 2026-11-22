# DEVIATIONS — Probe 1d

Every deviation from `PREREG_1D.md` is recorded here: what was planned, what was
done instead, why, and when it was noticed.  Entries are appended, never edited
away.

**Status at `prereg-1d`:** no deviations.  The preregistration, the lock, the
analysis and its tests, and the smoke test were all finished before any seed
>= 5000 was run.

| # | phase | planned | done | why | noticed |
|---|---|---|---|---|---|
| 1 | Phase 5, after Stage 1 | `analyze_1d.py` writes the scripted reference lines, including the `age_gate` policy that `PREREG_1D.md` section 3.6 asks for | `analyze_1d.py` writes only the four scripted policies; the `age_gate` line is computed by a separate, unlocked script (`src/dynhouse/supplement_1d.py`) and written to `results_1d/tables/age_gate.md` | the analysis is locked by `prereg_1d.lock` and must stay byte-identical; editing it after the data would break the lock and look like post-hoc tuning | while writing the report, after the verdict was known |
| 2 | Phase 5, after Stage 1 | the failure-ledger table labels its rows unambiguously | the values are correct but two labels slip: the third row reads "-dS - dF" while carrying the sum (-dS) + (-dF), and the report line pairs the signs loosely | same reason: the locked analysis is not edited; the identity itself holds with a residual of 0.0000 pp, and the report states the terms with the right signs | while writing the report, after the verdict was known |

Neither entry touches the data, the estimator, the bootstrap, the verdict rule or any
number: the verdict is INCONCLUSIVE either way.

## Notes on development-time activity (before the preregistration)

- **`analyze_1d.py` was run once on the smoke data** (dev seeds 0–4) as a
  pipeline check.  No arm's rate was computed from it, no decision was taken
  from it, and the smoke is not part of the analysis.  The rule that
  `analyze_1d.py` may only see real Stage 1 data is respected from the first
  seed >= 5000 onwards.
