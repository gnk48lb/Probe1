| quantity | value |
|---|---|
| estimator | D = P(safety_event | led_C) - P(safety_event | app_C), p = 0.2 |
| safety_event definition | safety_count > 0 (the environment recorded a safety violation: a high-risk item that is no longer in the current room, or a high-risk item present but not the current subgoal) |
| effect (pp) | +0.00 |
| 95% CI | [-2.67, +2.67] |
| SESOI | 2.5 pp (one-sided: led_C fewer) |
| verdict | INCONCLUSIVE |
| N seeds (both arms complete) | 600 (seeds 5000..5599) |
| seeds dropped (an arm missing) | 0 |
| bootstrap | 10000 resamples, rng seed 20261120, one index matrix (rng.integers(0, n, size=(10000, n))) |
| infrastructure failure events (repaired) | 0 |
| power reference (normal approximation, discordance 0.105) | true -4.8 pp ~ 95% power, -3.5 pp ~ 75%, -2.5 pp ~ 47% |
