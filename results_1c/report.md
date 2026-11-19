# Probe 1c — the replication test of `led_C` vs `app_C` at p = 0.2

**Verdict: `INCONCLUSIVE`.**  The effect is **+3.3 pp, 95% CI [−1.2, +8.0]** (N = 600
seeds).  The preregistered threshold was δ = 5 pp, so the difference is
neither established (point < 5, CI crosses 0) nor ruled out (CI reaches past
+5).  Probe 1's post-hoc observation of +10.0 pp [−2, +22] is **not**
reproduced as an effect of that size: the replication interval does not even
reach +10.

**Stage 3 was not triggered** — it requires a final verdict of `REPLICATED`
(`PREREG_1C.md` §2.5).  The extension was used exactly once, as the rules allow.

| | |
|---|---|
| Model | `minimax-code-global/MiniMax-M3.1-Flash`, temperature 0, local Magpie gateway |
| Code | Probe 1's **frozen** sources (byte-identical to the tag `probe1-final`), `run.py` used as it is |
| Data | 1200 episodes (600 seeds × 2 arms), p = 0.2, 0 infrastructure failures, 0 seeds dropped |
| Statistics | paired bootstrap over seeds, 10,000 resamples, RNG seed 20261119, 95% percentile CI |
| Preregistration | `PREREG_1C.md`, `prereg_1c.lock`, tag `prereg-1c` |
| Reproduce | `uv run python -m dynhouse.analyze_1c --results results_1c` |

---

## 1. Design and preregistration summary

- Environment, memory implementation, prompts and interface: **identical to
  Probe 1**, byte for byte.  `variant=main`; the number of asks left is *not*
  visible in the state; the original `BASE_SYSTEM` + C prompt; the original
  ledger / append views.  The nine frozen sources and `prompts.lock` are
  byte-identical to `probe1-final`, and `prompts.lock` still verifies.
- Arms: `led_C` and `app_C`.  p = 0.2 only.  `n_targets = 2 + seed % 2`.
- Seeds: dev 0–4 (smoke only); Stage 1 = 4000–4299 (N = 300); Stage 2
  extension = 4300–4599 (final N = 600).  1000–1099, 2000–2399 and 3000–3099
  were not reused.
- Primary estimator: Δ = SR(led_C) − SR(app_C) on the seeds where **both**
  arms are complete, paired bootstrap over seeds (10,000 resamples, RNG seed
  20261119), 95% percentile CI.
- Decision rule (δ = 5 pp): `REPLICATED` — point ≥ +5 and CI lower > 0;
  `NOT_REPLICATED` — CI upper < +5; otherwise `INCONCLUSIVE`.
- Extension rule: exactly one extension, allowed only if Stage 1 is
  `INCONCLUSIVE` (it was).  Stage 3: only if the final verdict is
  `REPLICATED` (it was not, so it was skipped).
- The model may have been updated silently since Probe 1, so only the paired
  difference of the two arms, run together on the same seeds, is interpreted;
  `led_C`'s absolute level is never compared with Probe 1's 67%.

## 2. Main result

| arm | n | SR% | SR 95% CI | cost | safety% | budget_exhausted% | invalid | asks | stale_picks | cost of a success | cost of a failure | failures: budget | failures: safety |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **led_C** | 600 | **59.8** | **[55.8, 63.8]** | 44.6 | **5.3** | 35.2 | 1.74 | 0.98 | 0.31 | 35.9 | 57.5 | 211 | 29 |
| **app_C** | 600 | **56.5** | **[52.5, 60.5]** | 44.3 | **10.2** | 34.8 | 1.80 | 0.97 | 0.35 | 36.2 | 54.9 | 209 | 50 |

| quantity | value |
|---|---|
| Δ = SR(led_C) − SR(app_C), p = 0.2 | **+3.3 pp** |
| 95% CI (paired bootstrap, 10,000 resamples) | **[−1.2, +8.0]** |
| N seeds (both arms complete) | 600 (4000–4599) |
| Verdict | **INCONCLUSIVE** |
| Probe 1's original estimate (post-hoc, different seeds, N = 100) | +10.0 pp, CI [−2, +22] (led_C 67.0 vs app_C 57.0) — **not merged with the replication estimate** |

The two estimates are reported side by side and not combined, as the
preregistration requires.  The replication's point estimate is roughly a third
of Probe 1's, and the replication interval [−1.2, +8.0] does not contain
Probe 1's +10.0; that is a descriptive comparison of two estimates from
different seed ranges, not a second verdict.

## 3. Secondary metrics (pre-declared; point estimate and CI, no verdict)

| metric (led_C − app_C) | difference | 95% CI | led_C | app_C |
|---|---|---|---|---|
| success rate (pp) | +3.33 | [−1.17, +8.00] | 59.83 | 56.50 |
| total cost | +0.26 | [−0.98, +1.51] | 44.59 | 44.33 |
| **safety violation rate (pp)** | **−4.83** | **[−7.33, −2.17]** | 5.33 | 10.17 |
| budget exhausted rate (pp) | +0.33 | [−4.00, +4.83] | 35.17 | 34.83 |
| invalid actions | −0.06 | [−0.19, +0.08] | 1.74 | 1.80 |
| asks | +0.01 | [−0.00, +0.03] | 0.98 | 0.97 |
| competing pick failure (pp) | −3.33 | [−7.17, +0.50] | 15.17 | 18.50 |
| stale pick failure (pp) | −2.00 | [−5.67, +1.83] | 12.50 | 14.50 |
| high-risk pick (pp) | −1.67 | [−3.83, +0.50] | 62.83 | 64.50 |

**One pre-declared secondary metric has an interval that excludes zero: the
safety-violation rate.**  `led_C` violates safety in 5.3% of episodes against
10.2% for `app_C`, a difference of −4.8 pp with a 95% CI of [−7.3, −2.2].
The two arms cost the same, so this is not a trade-off against spending: at
equal cost `led_C` fails fatally for safety about half as often.

## 4. Scripted reference lines (same 600 seeds, p = 0.2, no LLM)

| policy | success% | cost | asks | unsafe% |
|---|---|---|---|---|
| trust_memory | 45.8 | 26.5 | 0.00 | 41.0 |
| observe_pick | 59.2 | 42.4 | 0.00 | 10.8 |
| ask_fetch | 62.3 | 44.3 | 1.00 | 7.2 |
| ledger_gate | 68.5 | 43.7 | 0.98 | 4.8 |
| **age_gate (the rule itself, no LLM)** | **73.5** | 39.5 | — | 6.0 |

Both LLM arms sit between `observe_pick` (59.2%) and `ask_fetch` (62.3%), and
both remain below `ledger_gate` (68.5%) and well below the `age_gate` policy
(73.5%) — the same ordering that Probe 1 found, on a completely different seed
range.

## 5. Figure

`results_1c/figures/replication.png` — the two arms' success rates with their
95% CI, Probe 1's original observation as grey diamonds labelled "post-hoc,
different seeds", and the five scripted reference lines as vertical references.

## 6. Failure analysis (non-exclusive flags, with the successful-episode baseline)

| arm | flag | failed | share of failures | successful | share of successes | relative risk |
|---|---|---|---|---|---|---|
| led_C | competing pick failure | 67/241 | 27.8% | 24/359 | 6.7% | 4.16 |
| led_C | stale pick failure | 74/241 | 30.7% | 1/359 | 0.3% | 110.2 |
| led_C | high-risk pick | 132/241 | 54.8% | 245/359 | 68.2% | 0.80 |
| led_C | **repeat ask** | 229/241 | 95.0% | 197/359 | **54.9%** | 1.73 |
| led_C | budget exhausted | 211/241 | 87.6% | 0/359 | 0.0% | inf |
| led_C | safety violation | 32/241 | 13.3% | 0/359 | 0.0% | inf |
| led_C | never used the ask | 2/241 | 0.8% | 8/359 | 2.2% | 0.37 |
| app_C | competing pick failure | 85/261 | 32.6% | 26/339 | 7.7% | 4.25 |
| app_C | stale pick failure | 83/261 | 31.8% | 4/339 | 1.2% | 27.0 |
| app_C | high-risk pick | 164/261 | 62.8% | 223/339 | 65.8% | 0.96 |
| app_C | **repeat ask** | 241/261 | 92.3% | 224/339 | **66.1%** | 1.40 |
| app_C | budget exhausted | 209/261 | 80.1% | 0/339 | 0.0% | inf |
| app_C | safety violation | 61/261 | 23.4% | 0/339 | 0.0% | inf |
| app_C | never used the ask | 9/261 | 3.4% | 7/339 | 2.1% | 1.67 |

Reading the table against its own baseline (co-occurrence is not causation):

- **The repeat ask is not what separates success from failure.**  It appears in
  55% (`led_C`) and 66% (`app_C`) of the **successful** episodes as well, so it
  is a property of the arm, not a failure mechanism.  Calling it the cause
  would be wrong in both directions.
- **What does separate them** is a miss on evidence: the stale-pick flag has a
  relative risk of 110 (`led_C`) and 27 (`app_C`), the competing-pick flag 4.2
  and 4.3, and the budget exhaustion that follows 88% / 80% of failures against
  0% of successes.
- **High-risk picking is *less* frequent in the failures than in the successes**
  (relative risk 0.80 and 0.96) — a high-risk grasp is not by itself a failure
  signal; it only becomes one when it misses or grabs the wrong item.

## 7. Deviations

`DEVIATIONS_1C.md` (repository root).  Two entries, both before the first test
seed: the `prereg-1c` tag was created once and re-created once because the
first commit of the branch had briefly staged Probe 1b's raw transcripts (the
`.gitignore` of `probe1-final` does not carry the 1b entries) — the commit was
undone, the ignore rules were added and the tag re-created, with no experiment
data in existence at that point; and the frozen files had to be restored to
their `probe1-final` bytes (`core.autocrlf` set to `false`, four files
re-checked out) so that the byte-identity requirement and Probe 1's
`prompts.lock` both hold.  No frozen file was edited, and `analyze_1c.py` was
never touched after `prereg_1c.lock` was written.

## 8. Limitations

1. One model family, one prompt pair, one disturbance rate, one environment.
   Nothing here transfers beyond this text house.
2. The hypothesis was **selected post hoc** in Probe 1 (it came out of twelve
   secondary contrasts), so this is a single test of a selected hypothesis.
   A non-replication is evidence that the effect does not reproduce on fresh
   seeds; it is not proof that Probe 1 was wrong, and the two estimates are not
   merged.
3. The model may have changed under the same name since Probe 1, so only the
   paired difference on the same seeds is interpretable.
4. With N = 600 seeds the resolution of the CI is roughly ±5 pp, so an effect
   of 5–8 pp is not cleanly separable from zero; the verdict `INCONCLUSIVE`
   means exactly that, not "no effect".
5. The scripted reference lines are computed on the same seeds and inherit
   that seed range's difficulty.
6. The safety-violation difference is a pre-declared *secondary* metric: it is
   reported with its interval, and it does not change the primary verdict.
7. The failure flags are co-occurrence statistics with a baseline; they
   describe which episodes differ, not why.

## 9. Files

```
results_1c/
  episodes.jsonl        one row per episode (1200)
  traces.jsonl          one row per step (with the prompts)
  raw.jsonl             one row per episode (the full prompts and replies)
  traces_1c.jsonl.gz    the step traces without the prompts (committed)
  tables/               primary, arms, secondary, scripted_reference,
                        failure_flags, run_overview
  figures/              replication.png
  report.md             this file
  RESUME.md             the hand-off note written at the overnight pause
```
