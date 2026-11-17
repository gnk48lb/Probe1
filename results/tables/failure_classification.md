| category | failed episodes |
|---|---|
| acted on stale memory | 178 |
| verified but the target moved again | 204 |
| wasted the ask | 313 |
| invalid format | 1 |
| budget or steps exhausted | 0 |
| other | 0 |
| **total** | **696** |

| arm | failed | acted on stale memory | verified but the target moved again | wasted the ask | invalid format | budget or steps exhausted | other |
|---|---|---|---|---|---|---|---|
| app_N | 97 | 22 | 29 | 46 | 0 | 0 | 0 |
| led_N | 100 | 21 | 45 | 34 | 0 | 0 | 0 |
| app_C | 101 | 19 | 32 | 49 | 1 | 0 | 0 |
| led_C | 88 | 13 | 29 | 46 | 0 | 0 | 0 |
| win_N | 155 | 53 | 37 | 65 | 0 | 0 | 0 |
| win_C | 155 | 50 | 32 | 73 | 0 | 0 | 0 |

### failure signatures (overlapping)

| signature (categories overlap) | failed episodes | share |
|---|---|---|
| a grasp missed (stale pick) | 382 | 54.9% |
| asked again after the one allowed ask | 652 | 93.7% |
| ran out of budget | 538 | 77.3% |
| ran out of steps | 3 | 0.4% |
| ended in a safety violation | 172 | 24.7% |
| never used the ask | 13 | 1.9% |
| used the ask | 683 | 98.1% |

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
