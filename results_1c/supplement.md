# Probe 1c supplement (post-hoc)

**Everything in this file is post-hoc.**  It was computed after the 1c verdict was
known, it changes no verdict, and it is not part of the preregistered analysis
(`analyze_1c.py` and `prereg_1c.lock` are untouched; the lock still verifies).
It exists because the independent review of `results_1c/report.md` found that two of
its statements needed the wrong denominator.

## 1. The repeat ask, stratified by episode length

The unstratified numbers (95% of the failures against 55% of the successes) are an
artefact of the episode length: the repeat ask needs a second ask to have been
spent, and long episodes are both more likely to repeat-ask and more likely to
fail.  Within a length band the two rates are nearly the same.

| arm | episode steps | episodes | repeat ask (all) | successes (n / rate) | failures (n / rate) |
|---|---|---|---|---|---|
| led_C | 1-14 | 198 | 23% (46/198) | 185 / 23% (42/185) | 13 / 31% (4/13) |
| led_C | 15-19 | 81 | 83% (67/81) | 72 / 81% (58/72) | 9 / 100% (9/9) |
| led_C | 20-24 | 74 | 93% (69/74) | 67 / 94% (63/67) | 7 / 86% (6/7) |
| led_C | 25-30 | 247 | 99% (244/247) | 35 / 97% (34/35) | 212 / 99% (210/212) |
| app_C | 1-14 | 188 | 35% (65/188) | 159 / 35% (55/159) | 29 / 34% (10/29) |
| app_C | 15-19 | 85 | 89% (76/85) | 76 / 88% (67/76) | 9 / 100% (9/9) |
| app_C | 20-24 | 65 | 97% (63/65) | 59 / 97% (57/59) | 6 / 100% (6/6) |
| app_C | 25-30 | 262 | 100% (261/262) | 45 / 100% (45/45) | 217 / 100% (216/217) |

## 2. The two safety definitions

`_finish` can be overwritten by the budget running out in the same step, so a safety
violation is sometimes recorded as `budget_exhausted`.  The event definition
(`safety_count > 0`) is the primary one; the `failure_reason` definition is a
sensitivity analysis.

| definition | led_C count | led_C rate | app_C count | app_C rate | difference (pp) | 95% CI |
|---|---|---|---|---|---|---|
| event (`safety_count > 0`) | 32 | 5.3% | 61 | 10.2% | -4.83 | [-7.33, -2.17] |
| `failure_reason == "safety_violation"` | 29 | 4.8% | 50 | 8.3% | -3.50 | [-6.00, -1.00] |
| overwritten by `_finish` (event minus reason) | 3 |  | 11 |  |  |  |

## 3. Budget exhaustion with and without the safety episodes

| arm | budget exhausted (all episodes) | budget exhausted (safety episodes removed) | episodes with a safety event | episodes that succeeded |
|---|---|---|---|---|
| led_C | 211 / 35.2% | 208 / 34.7% | 32 / 5.3% | 359 |
| app_C | 209 / 34.8% | 198 / 33.0% | 61 / 10.2% | 339 |

## 4. The stale-evidence missed grasps

| arm | episodes with a stale-evidence missed grasp | of which failed | conditional failure rate |
|---|---|---|---|
| led_C | 75 | 74 | 98.7% |
| app_C | 87 | 83 | 95.4% |

## 5. The scripted reference lines on both seed ranges

`PREREG_1C.md` section 2.7 asked for the scripted lines on seeds 4000-4299; the
1c report used all 600 analysed seeds.  Both are given here.

| policy | SR% (600 seeds) | cost | unsafe% | SR% (seeds 4000-4299) | cost | unsafe% |
|---|---|---|---|---|---|---|
| trust_memory | 45.8 | 26.5 | 41.0% | 46.3 | 24.7 | 43.7% |
| observe_pick | 59.2 | 42.4 | 10.8% | 60.3 | 42.5 | 9.3% |
| ask_fetch | 62.3 | 44.3 | 7.2% | 64.7 | 43.8 | 8.3% |
| ledger_gate | 68.5 | 43.7 | 4.8% | 70.7 | 43.1 | 5.7% |
