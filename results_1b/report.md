# Probe 1b — the controller (harness gating) experiment

**Verdict: `INSTRUMENT_FAILED`** — the positive control did not pass, so the
zero results of `hint` / `shield` / `both` **may not** be read as "the
controller does not help".  The required diagnosis is in §6.

| | |
|---|---|
| Model | `minimax-code-global/MiniMax-M3.1-Flash`, temperature 0, via the local Magpie gateway |
| Stage 1 | 1500 episodes (5 arms × p ∈ {0.1, 0.2, 0.4} × seeds 3000–3099), 26,155 LLM calls, 60.7 M tokens |
| Infrastructure | 0 infrastructure failures, 0 format failures (0.000% of 26,155 calls), 5 format re-sends |
| Analysis | paired bootstrap over seeds, 10,000 resamples, RNG seed 20261118; δ = 5 pp |
| Preregistration | `PREREG_1B.md`, `prompts_1b.lock`; tags `prereg-1b`, `prereg-1b-v2`, `prereg-1b-v3` |
| Stage 2 | **not run** — the extension is only allowed when PC = HELPS *and* G_both = INCONCLUSIVE; PC is INCONCLUSIVE |
| Reproduce | `uv run python -m dynhouse.analyze_1b --results results_1b` |

---

## 1. Arms

| arm | controller | what it does | SR p=0.1 | SR p=0.2 | SR p=0.4 |
|---|---|---|---|---|---|
| `base` | `[]` | nothing (the 1b control; the CONTROLLER paragraph is in the prompt but the controller is inert) | 78.0 | 68.0 | 50.0 |
| `hint` | `["advice"]` | every ledger row carries `advice`: "trust" / "verify" | 75.0 | 67.0 | 51.0 |
| `shield` | `["shield"]` | a high-risk grasp whose advice is "verify" is blocked (no world change, 0 budget, 1 step) | 77.0 | 58.0 | 56.0 |
| `both` | `["advice","shield"]` | both | 76.0 | 64.0 | 44.0 |
| `auto` | `["recommend"]` | the state carries `controller_recommendation` (positive control) | 83.0 | 70.0 | 45.0 |

All arms share one system prompt byte for byte (Probe 1's `BASE_SYSTEM` +
`PROMPT_C` + the CONTROLLER paragraph) and one memory representation (the
ledger).  Full table with cost, safety, steps, tokens: `results_1b/tables/arms.md`.

### Scripted reference lines on the same 100 seeds

| policy | p=0.1 | p=0.2 | p=0.4 |
|---|---|---|---|
| trust_memory | 74.0 / 21.2 | 48.0 / 28.9 | 22.0 / 34.7 |
| observe_pick | 84.0 / 34.3 | 60.0 / 42.5 | 31.0 / 49.4 |
| ask_fetch | 83.0 / 37.2 | 61.0 / 42.4 | 43.0 / 49.1 |
| ledger_gate | 87.0 / 34.9 | 64.0 / 41.4 | 44.0 / 48.0 |
| **age_gate (the rule itself, no LLM)** | **90.0 / 32.7** | **72.0 / 38.5** | **54.0 / 43.8** |

The last row is the controller **acting on its own** (no model): the number the
whole experiment is measured against.  It is reproduced by the controller alone
in test T7 on both seed ranges.

## 2. Main results (SR with 95% CI, cost, safety violation, by p)

| p | arm | SR% | SR 95% CI | cost | safety% | blocked | n |
|---|---|---|---|---|---|---|---|
| 0.1 | base | 78.0 | [70.0, 86.0] | 39.7 | 5.0 | 0.00 | 100 |
| 0.1 | hint | 75.0 | [67.0, 83.0] | 39.2 | 4.0 | 0.00 | 100 |
| 0.1 | shield | 77.0 | [68.0, 85.0] | 40.3 | 2.0 | 0.06 | 100 |
| 0.1 | both | 76.0 | [67.0, 84.0] | 38.8 | 3.0 | 0.01 | 100 |
| 0.1 | auto | 83.0 | [75.0, 90.0] | 35.7 | 4.0 | 0.00 | 100 |
| 0.2 | base | 68.0 | [59.0, 77.0] | 43.1 | 8.0 | 0.00 | 100 |
| 0.2 | hint | 67.0 | [58.0, 76.0] | 43.5 | 3.0 | 0.00 | 100 |
| 0.2 | shield | 58.0 | [49.0, 68.0] | 42.9 | 8.0 | 0.03 | 100 |
| 0.2 | both | 64.0 | [55.0, 73.0] | 42.4 | 6.0 | 0.00 | 100 |
| 0.2 | auto | 70.0 | [61.0, 79.0] | 41.3 | 8.0 | 0.00 | 100 |
| 0.4 | base | 50.0 | [40.0, 60.0] | 47.3 | 17.0 | 0.00 | 100 |
| 0.4 | hint | 51.0 | [41.0, 61.0] | 47.8 | 12.0 | 0.00 | 100 |
| 0.4 | shield | 56.0 | [46.0, 66.0] | 46.6 | 12.0 | 0.01 | 100 |
| 0.4 | both | 44.0 | [34.0, 54.0] | 47.8 | 13.0 | 0.00 | 100 |
| 0.4 | auto | 45.0 | [35.0, 55.0] | 47.1 | 12.0 | 0.00 | 100 |

Figure: `results_1b/figures/permission_gradient.png` — the permission gradient,
one panel per p, the LLM arms' SR with their 95% CI, the scripted lines as
vertical references.

## 3. Verdicts

| estimator | contrast | N seeds | effect (pp) | 95% CI | verdict | per p (0.1 / 0.2 / 0.4) |
|---|---|---|---|---|---|---|
| **G_both (primary)** | both − base | 100 | **−4.0** | **[−9.7, +1.7]** | **NOT_NEEDED** | −2.0 / −4.0 / −6.0 |
| **PC (positive control)** | auto − base | 100 | **+0.7** | **[−5.3, +6.7]** | **INCONCLUSIVE** | +5.0 / +2.0 / −5.0 |
| G_hint | hint − base | 100 | −1.0 | [−7.3, +5.3] | INCONCLUSIVE | −3.0 / −1.0 / +1.0 |
| G_shield | shield − base | 100 | −1.7 | [−8.0, +4.7] | NOT_NEEDED | −1.0 / −10.0 / +6.0 |
| both − hint | | 100 | −3.0 | [−9.0, +3.0] | NOT_NEEDED | +1.0 / −3.0 / −7.0 |
| both − shield | | 100 | −2.3 | [−7.7, +3.3] | NOT_NEEDED | −1.0 / +6.0 / −12.0 |
| auto − both | | 100 | +4.7 | [−1.0, +10.3] | INCONCLUSIVE | +7.0 / +6.0 / +1.0 |

**Interpretation table (`PREREG_1B.md` §1.5):**

| PC | G_both | reading |
|---|---|---|
| PC=HELPS | G_both=HELPS | harness gating recovers part of the gap → the paper's main line |
| PC=HELPS | G_both otherwise | the LLM cannot use advice or a shield, only full delegation works → the "controller permission gradient" story |
| **PC not HELPS** | — | **instrument failure → stop, report and diagnose** ← this row |

**The instrument failed.**  PC = +0.7 pp with a CI of [−5.3, +6.7] is neither
"HELPS" nor "NOT_NEEDED" (the CI reaches past δ = 5), so it is INCONCLUSIVE, and
the preregistration forbids reading anything into the zeros of `hint`, `shield`
or `both`.  §6 is the required diagnosis.

Note also that the extension is not allowed: it requires PC = HELPS **and**
G_both = INCONCLUSIVE.  PC is INCONCLUSIVE, so Stage 2 (seeds 3100–3199) was
**not run**.

## 4. Mechanism metrics

| arm | episodes | advice "verify" → checked before the pick | verify picks | high-risk should-verify picks | override rate | recommendations | episodes with a block |
|---|---|---|---|---|---|---|---|
| base | 300 | 41.8% | 79 | 43 | n/a | 0 | 0.0% |
| hint | 300 | 41.7% | 84 | 45 | n/a | 0 | 0.0% |
| shield | 300 | 28.0% | 82 | 33 | n/a | 0 | 3.3% |
| both | 300 | 49.3% | 75 | 38 | n/a | 0 | 0.3% |
| auto | 300 | 81.2% | 48 | 42 | **13.6%** | 5070 | 0.0% |

Budget by action type (successful vs failed episodes): `tables/budget_by_action.md`.

## 5. Failure analysis (non-exclusive flags, with the successful-episode baseline)

Each failed episode gets several flags; the same flag's rate in the **successful**
episodes is reported next to it, with the relative risk.  Full table:
`tables/failure_flags.md`.  Two findings that survive the baseline:

* **`repeat_ask` is 0 in every arm** — in Probe 1, 93.7% of the failed episodes
  asked again after their one allowed ask was spent, because the ask budget was
  not in the public state.  The `asks_remaining` field (present in all five 1b
  arms, absent in `base_old`) removes that failure mode completely: the
  effective-action waste it caused is gone.  This is a change to the
  environment's *observability*, not to any rule, and it is the one Probe 1
  defect this experiment repairs by construction.
* **`high_risk_should_verify_pick` is not specific to failures**: it appears in
  9–14% of the *successful* episodes of every arm (relative risk 1.3–2.1).  A
  high-risk grasp on stale evidence is common; it is only fatal when it misses.

First fatal event (`tables/first_fatal_event.md`, definition frozen in the
preregistration):

| arm | failed | safety_violation | stale_pick_fail | controller_block | budget_exhausted | none |
|---|---|---|---|---|---|---|
| base | 104 | 30 | 25 | 0 | 49 | 0 |
| hint | 107 | 19 | 30 | 0 | 58 | 0 |
| shield | 109 | 22 | 41 | 0 | 46 | 0 |
| both | 116 | 21 | 30 | 0 | 65 | 0 |
| auto | 102 | 17 | 45 | 0 | 40 | 0 |

Budget exhaustion is the most common terminal event in every arm, and it is
much more frequent in the failed episodes than in the successful ones (e.g. base:
74.0% of failures, 0% of successes).  The controller blocked **no** pick in any
failed episode — it fired 11 times in 1500 episodes, all in episodes that
recovered anyway.

## 6. Diagnosis of the instrument failure

The preregistration names three things to check: the compliance rate, the
format failures and the interception loops.

**Compliance: high, but not exact, and the substitutions are the problem.**
`auto` followed the recommendation exactly in 86.4% of 5070 steps (687
overrides).  What the model does instead:

| override | count |
|---|---|
| a different action of the same type (a different destination) | 148 |
| a different action type (e.g. "observe" where the controller said "pick", or "move" where it said "observe") | 539 |

The second kind is the damaging one: where the controller said *pick* (the item
was seen in this room on the previous step), the model often inserted an
*observe* first.  That widens the window in which the roommate can move the
item, and it shows up in the data — the `auto` arm misses far more grasps than
`base` (51.0% vs 39.0% of episodes at p = 0.4) while scoring slightly *worse*
(45.0% vs 50.0%).

**Format failures: none.**  0 of 26,155 calls failed to parse (5 re-sends, all
successful).  The pipeline is not what broke the positive control.

**Interception loops: none.**  11 blocked grasps in 1500 episodes, at most one
per episode, every one in an episode that recovered.  The shield fires so rarely
that it cannot move the result either way.

**The decisive comparison.**  The controller acting on its own, on the very same
100 seeds, with no model in the loop:

| p | base (LLM alone) | auto (LLM executing the recommendation) | age_gate (no LLM) |
|---|---|---|---|
| 0.1 | 78.0 | 83.0 | **90.0** |
| 0.2 | 68.0 | 70.0 | **72.0** |
| 0.4 | 50.0 | 45.0 | **54.0** |

The plan is worth 12 / 4 / 4 pp when the harness executes it, and 5 / 2 / −5 pp
when the model executes it.  The gap between those two columns is the positive
control's failure: **the recommendation is a good plan, and the model does not
follow it exactly enough for the harness to enforce it.**  The model substitutes
its own navigation and its own extra verification, and those substitutions cost
more than the plan saves.

Consistent with that reading, the `auto` episodes in which the model never
overrode anything score far better than the ones where it did — but the sample
is tiny and this is **exploratory**, not a verdict: at p = 0.4, 4 episodes
without an override score 75.0% against 43.8% for the 96 with at least one
override; at p = 0.1, 9 episodes without an override score 88.9% against 82.4%
for the 91 with one.

### What may and may not be concluded

**May** (operational, about the harness and the model, not about the gate):
the gate rule itself is a strong policy in this environment (90 / 72 / 54 with no
model at all, against 78 / 68 / 50 for the model alone); handing that policy to
the model as a *recommendation* does not deliver it, because the model replaces
14% of the actions and those replacements are systematically harmful.

**May not**: that advice (`hint`), interception (`shield`) or their combination
(`both`) "do not help".  Their estimates are indistinguishable from zero, but the
instrument that was supposed to make a *positive* effect visible failed, so the
zeros are uninterpretable in the direction the preregistration forbids.

## 7. Deviations

`DEVIATIONS.md` (root).  Two entries: one from before the test seeds (the
analysis distinguished "no data" from "failed instrument") and one after Stage 1
(the main results table now carries the preregistered CI; the change is confined
to the table/figure code and `estimators.md` — every verdict — is byte-identical
before and after, which was checked before committing).  Tags `prereg-1b`,
`prereg-1b-v2`, `prereg-1b-v3` keep the three lock states apart.

## 8. Limitations

1. One model family (MiniMax-M3.1-Flash).  The positive control may fail
   because a small model cannot follow a recommendation, which says nothing
   about the gate rule.
2. One gate rule (τ_low = 20, τ_high = 1), written before this experiment and
   not tuned here.  The experiment does not compare gate rules.
3. `both` bundles two interventions; `both − hint` and `both − shield` separate
   them only partially, and both are inconclusive anyway.
4. `auto` measures whether the model *follows* a recommendation, not whether a
   controller is optimal.  A low override rate can also mean a compliant but
   unhelpful recommendation.
5. The controller's recommendation is computed from the agent's visible
   information *before* the model acts; when the model overrides, the
   controller's next recommendation is computed from the diverged trajectory.
   The permission gradient therefore mixes "the model obeyed" with "the model
   took over".
6. The shield is nearly inert in this environment (11 blocks in 1500 episodes),
   so `shield` and `both` mostly measure "a controller that does not fire".
   That is a property of the gate rule and the LLM's behaviour, not evidence
   about interception as a technique.
7. The environment is the Probe 1 text house; nothing here transfers to
   anything else.
8. The `auto` override split (no-override vs override episodes) has n = 4 to 11
   in the no-override cells and is exploratory.
9. Stage 2 was not run, so every number here rests on 100 seeds; the bootstrap
   covers the seed sampling only.

## 9. Files

```
results_1b/
  episodes.jsonl        one row per episode (1500)
  traces.jsonl          one row per step (26150, with the prompts)
  raw.jsonl             one row per episode (the full prompts and replies)
  traces_1b.jsonl.gz    the step traces without the prompts (0.24 MB, committed)
  tables/               arms, main_results, estimators, interpretation, mechanism,
                        budget_by_action, failure_flags, first_fatal_event,
                        scripted_reference, run_overview
  figures/              permission_gradient.png
  report.md             this file
```
