# DEVIATIONS — Probe 1c

Every deviation from `PREREG_1C.md` is recorded here: what was planned, what was
done instead, why, and when it was noticed.  Entries are appended, never edited
away.

**Status at `prereg-1c`:** no deviations.  The preregistration, the lock and the
smoke test were finished before any seed >= 4000 was run.

| # | phase | planned | done | why | noticed |
|---|---|---|---|---|---|
| — | — | — | — | — | — |

## Notes on development-time activity (before the preregistration)

- **`analyze_1c.py` was run once on the smoke data** (dev seeds 0–4) as a
  pipeline check; it printed a delta of +0.0 pp with N = 5 seeds.  That number
  is meaningless at that size, no decision was taken from it, and the smoke is
  not part of the analysis.  The rule that `analyze_1c.py` may only see real
  Stage 1 data is respected from the first test seed onwards.
- **The `prereg-1c` tag was created once and re-created once, before any
  seed >= 4000 was run.**  The first commit of this branch had briefly staged
  Probe 1b's raw transcripts (193 MB) because the `.gitignore` of
  `probe1-final` does not carry the 1b entries; the commit was undone, the
  ignore rules were added, and the tag was re-created on the corrected
  commit.  No experiment data existed at that point and the run had not
  started.
- **The frozen files were restored to their `probe1-final` bytes** after the
  branch switch: `core.autocrlf` was set to `false` in this repository and
  four files that had been rewritten with CRLF by an earlier patch script were
  re-checked out, so that all nine frozen files are byte-identical to the tag
  and Probe 1's `prompts.lock` still verifies.  No frozen file was edited.
