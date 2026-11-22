# age_gate reference line (supplement to `analyze_1d.py`)

`PREREG_1D.md` section 3.6 asks for the `age_gate` policy on the seeds
actually included in the analysis; the locked analysis does not compute it, so it is
computed here.  It involves no LLM and can be recomputed at any time.

| policy | n | success% | cost | unsafe% |
|---|---|---|---|---|
| age_gate (the rule itself, no LLM) | 600 | 73.8 | 38.3 | 5.7% |

## Timestamps

| what | when |
|---|---|
| `prereg-1d` tag (3109d74d) | 2026-11-22 08:19:34 +0800 |
| the run's manifest created (the run started) | 2026-11-22T00:20:19.476878+00:00 |
| the last episode written | 2026-11-22T02:48:06.802006+00:00 |
