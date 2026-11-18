# DEVIATIONS — Probe 1b

Every deviation from `PREREG_1B.md` is recorded here: what was planned, what was
done instead, why, and when it was noticed.  Entries are appended, never edited
away.

**Status at `prereg-1b`:** no deviations.  The preregistration, the lock and the
smoke test were finished before any test seed (3000+) was run.

**Status at `prereg-1b-v2`:** one deviation, entry 1 below.  `prereg-1b` is left
untouched; the change was made before any test seed was run and the lock was
regenerated.

**Status at `prereg-1b-v3`:** two deviations, entries 1 and 2.  Entry 2 was made
after Stage 1, in the presentation code only: `estimators.md` (every verdict) is
byte-identical before and after the change, which was verified before the change
was committed.

| # | phase | planned | done | why | noticed |
|---|---|---|---|---|---|
| 2 | Phase 5, after Stage 1 | `main_results.md` has no confidence interval, while `PREREG_1B.md` requires the main results table to carry "SR, CI, cost, safety violation, by p" | the per-cell bootstrap CI is now a column of `main_results.md` (it was already computed for the figure); the figure legend moved out of the data area | the preregistered table was not delivered as specified; the change is confined to the table/figure code and **no estimator, verdict or rule was touched** -- `estimators.md` is byte-identical before and after, which was checked before committing | while preparing the report, after seeing the Stage 1 result |
| 1 | Phase 3, before any test seed | `analyze_1b.py` reports `INSTRUMENT_FAILED` whenever PC is not `HELPS` | the instrument check distinguishes `NOT EVALUABLE` (PC has no complete seeds) from `INSTRUMENT_FAILED` (PC is judged something else); the permission-gradient figure now shows the real bootstrap CI per arm instead of a fixed +/-5 pp | a missing or partial data set would have been reported as a failed instrument and could have aborted a valid experiment; the figure's error bars must be the preregistered CI | while running `analyze_1b.py` on the Phase 2 smoke data (dev seeds), before any test seed |

## Notes on development-time fixes (before the preregistration)

These are not deviations from the preregistration -- they happened while the
code was being written, before any test seed was run, and they are listed here
for completeness.

- **Controller mode table keyed wrongly (Phase 1).**  The first version of
  `controller.py` looked up "what the controller announces" in a table keyed by
  arm name, so a mode such as `advice` or `recommend` produced an empty
  announcement and the `auto` arm never received a recommendation.  Caught by
  the unit tests (the recommendation was `None` in every episode), fixed by
  splitting the table into `CONTROLLER_MODE` (arm -> mode) and `ANNOUNCED`
  (mode -> announced list).  No data existed at that point.
