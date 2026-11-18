# DEVIATIONS — Probe 1b

Every deviation from `PREREG_1B.md` is recorded here: what was planned, what was
done instead, why, and when it was noticed.  Entries are appended, never edited
away.

**Status at `prereg-1b`:** no deviations.  The preregistration, the lock and the
smoke test were finished before any test seed (3000+) was run.

| # | phase | planned | done | why | noticed |
|---|---|---|---|---|---|
| — | — | — | — | — | — |

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
