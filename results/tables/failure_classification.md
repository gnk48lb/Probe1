| category | failed episodes |
|---|---|
| acted on stale memory | 17 |
| verified but the target moved again | 23 |
| wasted the ask | 34 |
| invalid format | 0 |
| budget or steps exhausted | 0 |
| other | 0 |
| **total** | **74** |

| arm | failed | acted on stale memory | verified but the target moved again | wasted the ask | invalid format | budget or steps exhausted | other |
|---|---|---|---|---|---|---|---|
| app_N | 11 | 1 | 5 | 5 | 0 | 0 | 0 |
| led_N | 8 | 0 | 4 | 4 | 0 | 0 | 0 |
| app_C | 9 | 2 | 3 | 4 | 0 | 0 | 0 |
| led_C | 8 | 1 | 2 | 5 | 0 | 0 | 0 |
| win_N | 19 | 6 | 5 | 8 | 0 | 0 | 0 |
| win_C | 19 | 7 | 4 | 8 | 0 | 0 | 0 |

### failure signatures (overlapping)

| signature (categories overlap) | failed episodes | share |
|---|---|---|
| a grasp missed (stale pick) | 40 | 54.1% |
| asked again after the one allowed ask | 66 | 89.2% |
| ran out of budget | 59 | 79.7% |
| ran out of steps | 0 | 0.0% |
| ended in a safety violation | 16 | 21.6% |
| never used the ask | 2 | 2.7% |
| used the ask | 72 | 97.3% |

### first 40 failed episodes

| arm | p | seed | category | failure_reason | stale_pick | asks | invalid |
|---|---|---|---|---|---|---|---|
| app_C | 0.2 | 1000 | verified but the target moved again | safety_violation | 1 | 1 | 0 |
| win_N | 0.4 | 1000 | verified but the target moved again | safety_violation | 1 | 1 | 0 |
| win_N | 0.0 | 1001 | wasted the ask | budget_exhausted | 0 | 1 | 2 |
| led_C | 0.2 | 1000 | wasted the ask | budget_exhausted | 0 | 1 | 2 |
| led_C | 0.4 | 1000 | wasted the ask | budget_exhausted | 0 | 1 | 4 |
| app_N | 0.2 | 1001 | wasted the ask | budget_exhausted | 0 | 1 | 2 |
| app_C | 0.2 | 1001 | wasted the ask | budget_exhausted | 0 | 1 | 3 |
| led_N | 0.2 | 1000 | wasted the ask | budget_exhausted | 0 | 1 | 3 |
| led_C | 0.2 | 1001 | wasted the ask | budget_exhausted | 0 | 1 | 4 |
| win_C | 0.0 | 1001 | acted on stale memory | budget_exhausted | 1 | 1 | 3 |
| win_N | 0.2 | 1001 | wasted the ask | budget_exhausted | 0 | 1 | 2 |
| app_C | 0.4 | 1001 | acted on stale memory | budget_exhausted | 1 | 1 | 2 |
| win_C | 0.4 | 1001 | verified but the target moved again | budget_exhausted | 1 | 1 | 3 |
| win_N | 0.4 | 1001 | verified but the target moved again | budget_exhausted | 3 | 1 | 4 |
| led_N | 0.4 | 1001 | verified but the target moved again | safety_violation | 1 | 1 | 2 |
| win_C | 0.2 | 1002 | acted on stale memory | budget_exhausted | 1 | 1 | 4 |
| app_N | 0.4 | 1002 | verified but the target moved again | budget_exhausted | 2 | 1 | 5 |
| win_N | 0.2 | 1003 | acted on stale memory | safety_violation | 1 | 1 | 1 |
| win_C | 0.0 | 1003 | wasted the ask | budget_exhausted | 0 | 1 | 3 |
| app_C | 0.4 | 1003 | verified but the target moved again | safety_violation | 1 | 1 | 0 |
| led_N | 0.4 | 1003 | verified but the target moved again | safety_violation | 1 | 1 | 0 |
| win_N | 0.0 | 1003 | wasted the ask | budget_exhausted | 0 | 1 | 3 |
| led_C | 0.4 | 1003 | verified but the target moved again | safety_violation | 1 | 0 | 1 |
| app_N | 0.4 | 1003 | verified but the target moved again | safety_violation | 1 | 1 | 1 |
| win_C | 0.2 | 1003 | wasted the ask | budget_exhausted | 0 | 1 | 3 |
| app_N | 0.2 | 1003 | wasted the ask | budget_exhausted | 0 | 1 | 2 |
| win_C | 0.4 | 1003 | verified but the target moved again | safety_violation | 1 | 1 | 1 |
| led_C | 0.2 | 1002 | acted on stale memory | budget_exhausted | 2 | 1 | 3 |
| win_N | 0.4 | 1004 | wasted the ask | budget_exhausted | 0 | 1 | 4 |
| win_N | 0.2 | 1005 | verified but the target moved again | safety_violation | 1 | 1 | 2 |
| win_C | 0.4 | 1004 | wasted the ask | budget_exhausted | 0 | 1 | 3 |
| win_C | 0.0 | 1005 | acted on stale memory | budget_exhausted | 1 | 1 | 3 |
| app_C | 0.2 | 1005 | wasted the ask | budget_exhausted | 0 | 1 | 2 |
| led_N | 0.4 | 1005 | verified but the target moved again | safety_violation | 1 | 1 | 0 |
| win_N | 0.0 | 1005 | acted on stale memory | budget_exhausted | 1 | 1 | 5 |
| win_C | 0.2 | 1005 | verified but the target moved again | safety_violation | 1 | 1 | 4 |
| app_N | 0.2 | 1005 | wasted the ask | budget_exhausted | 0 | 1 | 3 |
| led_C | 0.4 | 1005 | verified but the target moved again | budget_exhausted | 1 | 1 | 3 |
| win_N | 0.4 | 1005 | wasted the ask | budget_exhausted | 0 | 1 | 5 |
| app_N | 0.4 | 1005 | verified but the target moved again | safety_violation | 1 | 1 | 3 |
