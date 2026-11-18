# PREREG_1C — Probe 1c: replication test (led_C vs app_C, p = 0.2)

**Status** frozen before any seed ≥ 4000 was run.
**Tag** `prereg-1c` · **Lock** `prereg_1c.lock` (sha256 of `analyze_1c.py` and
`age_gate_reference.py`, with CRLF normalised to LF before hashing).

Probe 1 found `led_C` at 67% at p = 0.2 while the other three core arms
(`app_N`, `led_N`, `app_C`) were at 56–57%.  That difference was seen
afterwards, among twelve secondary contrasts, and was never confirmed
(`led_C − app_C` = +10.0 pp [−2, +22], N = 100, post-hoc).  Probe 1b's `base`
(= `led_C` plus a visible ask budget) scored 68% on new seeds, but that is a
different interface and does not count as a replication.

**Probe 1c runs Probe 1's frozen code and interface on fresh seeds and tests
the difference properly, once, in advance.**

---

## 1. Design

- Environment, memory implementation, prompts and interface: **identical to
  Probe 1**, byte for byte.  `variant=main`; the number of asks left is *not*
  visible in the state; the original `BASE_SYSTEM` + C prompt; the original
  ledger / append views.
  The frozen sources (`src/dynhouse/{env,memory,prompts,agent,gateway,run,analyze,scripted}.py`
  and `prompts.lock`) are byte-identical to the tag `probe1-final`, and
  `run.py` is used as it is.
- Arms: **`led_C` and `app_C`**.  Disturbance rate: **p = 0.2 only**.
  `n_targets = 2 + seed % 2`, as in Probe 1.
- Seeds: dev 0–4 for the smoke test only (~10 episodes, pipeline check);
  test seeds **4000–4299** (N = 300, Stage 1); extension seeds **4300–4599**
  (Stage 2).  Seeds 1000–1099, 2000–2399 and 3000–3099 have been used before and
  are not reused.
- Running: in blocks of 50 seeds (`--seed-start` incremented), both arms in the
  same invocation, so an interruption always leaves complete seeds behind.
  Stage 1 = 600 episodes, about 1.5 hours.
- The model may have been updated silently by the gateway over the past two
  days, so **`led_C`'s absolute level is not compared with Probe 1's 67%**;
  only the paired difference of the two arms, run together on the same seeds,
  is.

## 2. Estimators and decision rules

### 2.1 Primary (the only confirmatory) estimator

Δ = SR(led_C) − SR(app_C), p = 0.2; only the seeds where **both arms are
complete**; paired bootstrap over seeds, 10,000 resamples, RNG seed 20261119,
95% percentile CI.  Infrastructure failures are re-run first (Probe 1's rules,
at most 2 attempts); seeds still missing are dropped **for both arms** and
reported honestly.

### 2.2 Decision rule (δ = 5 pp)

`REPLICATED`: point estimate ≥ +5 and the CI's lower bound > 0;
`NOT_REPLICATED`: the CI's upper bound < +5; otherwise `INCONCLUSIVE`.

### 2.3 Background (does not enter any verdict)

Probe 1's original estimate +10.0 [−2, +22] (N = 100, post-hoc, different
seeds).  The replication estimate is reported next to it for comparison; the
two are **never merged into one verdict**.  A combined descriptive estimate may
be given, but it must be marked exploratory.

### 2.4 Extension rule

Only if Stage 1 is judged `INCONCLUSIVE`, exactly one extension is allowed:
seeds **4300–4599** are added for both arms, and the final decision uses 600
seeds.  If Stage 1 has to be stopped for time, only the wall clock may decide
it; the analysis uses the seeds that are complete, the verdict follows the same
rule, and N is reported honestly.

### 2.5 Stage 3

Only if the final verdict is `REPLICATED`, and **descriptive only, no verdict**:
run `app_N` and `led_N` (p = 0.2) on seeds 4000–4299, to see whether
`led_C`'s advantage is an interaction between the ledger and the prompt or
just `led_C` being high on its own.  Stop afterwards; nothing else is done.

### 2.6 Secondary / descriptive

Pre-declared (everything else is exploratory): success rate, total cost,
safety-violation rate, the `failure_reason` composition (budget exhausted vs
safety violation), `invalid_count`, `ask_count`, the pick-failure rate split
by `evidence_age <= 1` and `>= 2`, and the cost of successful vs failed
episodes.  For every metric: the difference between the two arms and its CI.

The failure analysis uses **non-exclusive flags** and gives the rate of the
same flag in the **successful** episodes next to it; co-occurrence must not be
written as causation.

### 2.7 Scripted reference lines

With the frozen `scripted.py` on seeds 4000–4299 at p = 0.2 (main version):
`trust_memory` / `observe_pick` / `ask_fetch` / `ledger_gate`; and with
`age_gate_reference.py` (taken from the `probe1b` branch:
`git show probe1b:age_gate_reference.py > age_gate_reference.py`) the
`age_gate` policy.  They go into the report as reference lines; they involve no
LLM and can be computed at any time.

## 3. Implementation notes (fixed at preregistration time)

- `analyze_1c.py` reproduces every table and figure from
  `results_1c/episodes.jsonl` and `results_1c/traces.jsonl`; it is locked
  together with `age_gate_reference.py` in `prereg_1c.lock`, and it refuses to
  run when they drift.  The lock hashes the file bytes with CRLF normalised to
  LF, so it is stable on Windows and against the tag.
- The first-step prompts of both arms are pinned by hash at seed 4000, and a
  test rebuilds Probe 1's own first-step prompt from the frozen code and
  compares it with the transcript Probe 1 actually sent.
- The runner is Probe 1's `run.py`, unchanged: per-episode flushing, resume,
  exponential backoff on infrastructure failures, a repair pass at the end.
- The run manifest records the model string, the time and the git hash.

## 4. Known limitations (declared before the data)

1. One model family, one prompt pair, one disturbance rate, one environment.
2. The comparison is a replication of a **post-hoc** observation: Probe 1's
   +10.0 pp came from twelve secondary contrasts, so it is a selected
   hypothesis, and this test has one shot.
3. The model may have changed under the same name since Probe 1; only the
   paired difference on the same seeds is interpretable, not the levels.
4. A non-replication would not show that Probe 1 was wrong — it would show that
   the effect does not reproduce on fresh seeds, which is a weaker (and
   cheaper) claim than "it was an artefact".
5. `δ = 5 pp` is a choice; it is the same threshold as Probe 1b and half of
   Probe 1's.  With N = 300 seeds the resolution of the CI is roughly ±10 pp,
   so a true effect of 5–10 pp would be hard to separate from zero.
6. The scripted reference lines are computed on the same seeds, so they inherit
   the seed difficulty of this particular seed range.

## 5. Freeze statement

δ = 5 pp, 10,000 bootstrap resamples, RNG seed 20261119, the "complete seed"
rule, the verdict boundaries and the extension rule are fixed here and may not
be changed after the first test seed.  If a change is unavoidable, the original
version is kept and the change is recorded in `DEVIATIONS_1C.md` with its
reason.
