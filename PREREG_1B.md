# PREREG_1B — Probe 1b: the controller (harness gating) experiment

**Status** frozen before the first test seed (3000+) was run.
**Tag** `prereg-1b` · **Lock** `prompts_1b.lock` (sha256 of `prompts_1b.py`,
`controller.py`, `analyze_1b.py`, `age_gate_reference.py`).

Probe 1 (frozen, independently re-checked) showed that six arms
(memory window/append/ledger × prompt N/C) all came out level at p ≥ 0.2:
S = +2.3 pp [−3.2, +7.5], Π = +1.8 pp [−4.0, +7.5].  Neither the memory
representation nor the "decision prompt" was the bottleneck.  Meanwhile a
15-line script that decides *when to verify* from risk × evidence age was
clearly stronger: on Probe 1's 100 test seeds it scored 71% at p = 0.2 for
37.8 cost, against 56–67% (mean 59%) for the LLM arms at about 45 cost; on
1000 held-out seeds it scored 75% / 56% at p = 0.2 / 0.4, while the LLM arms
scored 42–48% at p = 0.4.  The C prompt already stated the same rule in
words; the LLM did not execute it.

**Probe 1b asks: if the decision "should I verify this?" is taken away from the
model and handed to a deterministic controller on the harness side, how much of
the gap can be recovered?**

---

## 1. Design

### 1.1 The parts every arm shares

- Environment = Probe 1's environment (`max_asks=1`, `freeze_asked=True`,
  whole-word question matching).  Additive additions:
  - p is relaxed to `0 <= p <= 1` (this experiment uses 0.1 / 0.2 / 0.4), as an
    option (`allow_any_p`, default keeps the old validation);
  - optional `expose_asks=True`: `public_state` gains `"asks_remaining"` (an int);
  - a "controller veto" step: a blocked action changes nothing in the world,
    costs no budget, advances the step counter by 1 (it counts towards the
    30-step limit) and is counted separately in `blocked_count`.
- Memory representation: **every arm uses the ledger** (Probe 1's ledger view,
  fields unchanged).
- System prompt (`prompts_1b.py`): the five main arms are byte-identical =
  Probe 1's `BASE_SYSTEM` + `PROMPT_C` (imported, never copied) + the paragraph
  below, verbatim:

  > CONTROLLER. A controller sits between you and the world. The state field "controller" lists what it does in this episode ("advice", "shield", "recommend"; an empty list means it does nothing). "advice": every memory entry carries advice "trust" or "verify", computed from the item's risk level and from the age and the source of your evidence; "verify" means re-check the item before acting on it. "shield": picking a high_risk item whose advice is "verify" is BLOCKED (nothing is picked, 0 budget, 1 step). "recommend": the state carries controller_recommendation, one action you may follow or override. The state field "asks_remaining" is the number of ask_human actions you still have.

  The only difference between arms is what the controller actually does, and
  `state["controller"]` states that truthfully.

### 1.2 The arms

```
base      controller = []
hint      controller = ["advice"]        (every ledger row gains an advice field)
shield    controller = ["shield"]        (same rule, used to intercept; the ledger shows no advice)
both      controller = ["advice","shield"]
auto      controller = ["recommend"]     (positive control; the state carries
                                          controller_recommendation; the ledger shows no advice)
base_old  (optional, last) Probe 1's led_C reproduced exactly: the original
          system prompt (no CONTROLLER paragraph), no asks_remaining in the
          state, no controller field.  p = 0.2 and 0.4 only.
```

### 1.3 The gating rule (fixed; no parameter may be tuned on any LLM data)

For every item of the ledger, in this order:

1. `believed_room` is None → "verify"
2. `disturbance_p == 0` → "trust" (static world: the controller never blocks
   and never recommends a verification)
3. `source == "ask_human"` and the item has not been picked yet → "trust"
   (under the freeze rule a human answer cannot go stale; this is a public rule)
4. high_risk: `age <= 1` → "trust", otherwise "verify"
5. low_risk: `age <= 20` → "trust", otherwise "verify"

`age` is the ledger view's `age` field (current step − `last_verified_step`).

- **shield**: for a `pick(item)`, if the item is high_risk and the rule above
  (computed from exactly the ledger view the agent sees at that moment) says
  "verify" → intercept, returning
  `"BLOCKED by controller: evidence for <item> is stale (age N). Verify first (observe in its room, or ask_human)."`
- **recommend**: the next action, following `age_gate_reference.py`.

### 1.4 Seeds, p and size

- Dev seeds 0–19: smoke tests only; the rule must not be tuned on them.
- Test seeds: **3000–3099** (Stage 1); **3100–3199** (Stage 2 extension, §1.7).
  Seeds 1000–1099 and 2000–2399 have been used before and are not reused.
- p ∈ {0.1, 0.2, 0.4}; `n_targets = 2 + seed % 2`.
- Stage 1 = {base, hint, shield, both, auto} × 3 p × 100 seeds = **1500 episodes**
  (about 4 h at about 130 calls/min).  Outer loop over seed blocks
  (3000–3024, 3025–3049, …), all cells rotated within a seed, so that an
  interruption always leaves whole seeds behind.
- Stage 3 (optional, last): `base_old` × p ∈ {0.2, 0.4} × seeds 3000–3099.

### 1.5 Estimators and decision rules

All comparisons are paired by seed; the 95% CI is a **paired bootstrap over
seeds** (10,000 resamples, RNG seed 20261118, 95% percentile); only seeds where
**all arms involved in the comparison are complete at all p** are used.
Infrastructure failures are repaired and re-run first, with the Probe 1 rules,
and the repair count is reported.

- **Primary (the only confirmatory estimator)**
  `G_both = mean_p [SR(both, p) − SR(base, p)]`, p ∈ {0.1, 0.2, 0.4}.
- **Positive control** `PC = mean_p [SR(auto, p) − SR(base, p)]`.
- **Secondary (point estimate + CI, no verdict)**: `G_hint`, `G_shield`,
  `both − hint`, `both − shield`, and the per-p difference of each.
- **Decision rule** (δ = 5 pp.  Deliberately below Probe 1's 10 pp: the
  script-margin measurement shows the gains reachable in this environment are
  small to begin with):
  `HELPS`: point estimate ≥ +5 and the CI's lower bound > 0;
  `NOT_NEEDED`: the CI's upper bound < +5; otherwise `INCONCLUSIVE`.
- **Instrument validity**: PC must be judged `HELPS`.  Otherwise the whole
  experiment is marked `INSTRUMENT_FAILED`: no "the controller does not help"
  reading of hint / shield / both is allowed; stop immediately, report and
  diagnose (compliance rate, format failures, interception loops).
- **Interpretation table** (written into this preregistration):

  | PC | G_both | reading |
  |---|---|---|
  | PC=HELPS | G_both=HELPS | harness gating recovers part of the gap → the paper's main line |
  | PC=HELPS | G_both otherwise | the LLM cannot use advice or a shield, only full delegation works → the "controller permission gradient" story |
  | PC not HELPS | — | instrument failure, see above |

### 1.6 Secondary / mechanism metrics (pre-declared; everything else is exploratory)

Success rate, total cost, safety-violation rate, steps, LLM calls, tokens,
`blocked_count`, `invalid_count`; plus

- `pick_records` gains the fields `source`, `believed_room` and `rule_advice`
  (the advice the rule above would have given at that pick) **for every arm**;
- the number of times a high-risk item whose advice was "verify" was picked
  anyway — computed retroactively with the same rule for every arm (including
  `base`); under the shield, the intercepted attempts are counted separately;
- the advice compliance rate (hint / both): for a target item whose advice is
  "verify", whether an observe or an ask happened before the next pick;
  `base` is computed the same way as a control; `auto`'s override rate;
- the budget split by action type (move / observe / ask / pick / place):
  successful vs failed episodes, for every arm.

**Failure analysis** (replaces Probe 1's mutually exclusive priority classes):

- every failed episode gets several **non-exclusive flags**, and the same flag's
  rate in the **successful** episodes is reported next to it, with the relative
  risk.  At least: competing pick failure (`evidence_age <= 1`), stale pick
  failure (`age >= 2`), high-risk "should have verified but picked", repeat ask
  (invalid ask), budget exhausted, safety violation, never used the ask;
- in addition, the **"first fatal event"** of each failed episode (the first
  event that pushed it onto the failure path).  Defined here, once, and not
  adjusted afterwards: the earliest step at which one of
  [safety_violation, stale_pick_fail, controller_block, budget_exhausted]
  occurred, ties inside one step broken in that order.  The repeat ask is **not**
  in this list: it is a symptom of not tracking the ask budget and is reported
  separately as a flag.
- co-occurrence must not be written as causation.

### 1.7 Extension and stopping rules

- The **only** allowed extension: when PC = HELPS **and** G_both =
  INCONCLUSIVE, add seeds 3100–3199 (3 p) for `base` and `both`; the primary
  decision then uses 200 seeds, every other estimator stays at 100 seeds.
- If Stage 1 has to be stopped for time, only the wall clock may decide it;
  the analysis uses the seeds that are complete, the verdict follows the same
  rule, and N is reported honestly.

---

## 2. Implementation notes (fixed at preregistration time)

- The controller's inputs are the public state, the item risk levels and the
  agent's own visible history (its observations, the human's answers, its own
  actions) plus the ledger built from those.  It never receives the
  environment, so it cannot read ground truth (pinned by test T3, which also
  checks that the controller's decisions do not change when the environment's
  true locations are rewritten).
- `state["controller"]`, `state["controller_recommendation"]` and
  `state["asks_remaining"]` are placed at the top level of the state object and
  mirrored inside `task_state`, so that the model finds them either way.
  `base_old` has none of them.
- The controller's recommendation for `auto` is computed from the same visible
  information the model has, before the model acts; the model may follow or
  override it, and the override rate is reported.
- The runner is resumable: an episode counts only after its row is on disk.
  Infrastructure failures are retried with exponential backoff inside the
  client, marked `infra_failed`, excluded from the analysis and re-run at the
  end.
- `prompts_1b.lock` pins the four preregistered sources; the runner refuses to
  start when they drift.

## 3. Known limitations (declared before the data)

1. One model family only (MiniMax-M3.1-Flash); a controller that a small model
   cannot follow would look like a controller that does not work.
2. The gate rule is the one in `age_gate_reference.py` (τ_low = 20, τ_high = 1).
   It was written before Probe 1b and is not tuned here, but it is *one* rule:
   the experiment does not compare gate rules.
3. `both` combines two interventions (information and interception); the
   secondary contrasts `both − hint` and `both − shield` separate them only
   partially.
4. The `auto` arm measures whether the model *follows* a recommendation, not
   whether a controller is optimal: a low override rate can also mean a
   compliant but unhelpful recommendation.
5. The environment is the Probe 1 text house; the conclusions transfer to it
   and to nothing else.
6. The positive control can fail for reasons that have nothing to do with the
   gate (the model ignoring the recommendation).  That is why PC is a
   precondition for interpreting the zeros.
7. Dev seeds 0–19 were used for the smoke test; the rule was not tuned on them,
   but the smoke did look at their format failures and block counts.

## 4. Freeze statement

δ = 5 pp, 10,000 bootstrap resamples, RNG seed 20261118, the "complete seed"
rule, the verdict boundaries, the flag list and the first-fatal-event
definition are fixed here and may not be changed after the first test seed.
If a change is unavoidable, the original version is kept and the change is
recorded in `DEVIATIONS.md` with its reason.
