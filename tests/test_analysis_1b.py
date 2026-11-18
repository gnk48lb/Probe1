"""T8: the Probe 1b estimators, the paired bootstrap, the verdicts and the seed rule.

Everything is checked on synthetic data with a known effect, so a mistake in the
statistics cannot hide behind the data.
"""
from __future__ import annotations

import numpy as np
import pytest

from dynhouse.analyze_1b import (DELTA, N_BOOT, complete_seeds, estimate, paired_bootstrap,
                                  percentile_ci, success_map, verdict)

PS = (0.1, 0.2, 0.4)


def make_rows(spec: dict[str, float], seeds=range(3000, 3040), ps=PS) -> list[dict]:
    """Synthetic episodes: `spec` maps an arm to its success rate.

    The winners are picked deterministically so the rate is exact and the true
    difference is known.
    """
    seeds = list(seeds)
    rows = []
    for arm, rate in spec.items():
        for p in ps:
            k = int(round(rate * len(seeds)))
            order = sorted(seeds, key=lambda s: ((s * 37 + int(p * 10) * 11) % 101, s))
            winners = set(order[:k])
            for seed in seeds:
                rows.append({"arm": arm, "disturbance_p": p, "seed": seed,
                             "success": seed in winners, "cost": 30, "steps": 10,
                             "ask_count": 1, "stale_pick_count": 0, "safety_count": 0,
                             "invalid_actions": 0, "blocked_count": 0, "usage": {},
                             "pick_records": []})
    return rows


def test_complete_seed_rule_drops_seeds_with_a_missing_cell():
    rows = make_rows({"base": 0.5, "both": 0.5})
    seeds = complete_seeds(rows, ("base", "both"), PS)
    assert len(seeds) == 40
    # remove one cell of one seed -> that seed is out
    rows = [r for r in rows if not (r["arm"] == "both" and r["seed"] == 3010 and r["disturbance_p"] == 0.2)]
    seeds = complete_seeds(rows, ("base", "both"), PS)
    assert 3010 not in seeds and len(seeds) == 39


def test_complete_seed_rule_depends_on_the_arms_involved():
    rows = make_rows({"base": 0.5, "both": 0.5, "auto": 0.5})
    rows = [r for r in rows if not (r["arm"] == "auto" and r["seed"] == 3005 and r["disturbance_p"] == 0.1)]
    assert 3005 in complete_seeds(rows, ("base", "both"), PS)
    assert 3005 not in complete_seeds(rows, ("base", "both", "auto"), PS)


def test_identical_arms_give_exactly_zero():
    rows = make_rows({"base": 0.5, "both": 0.5})
    est = estimate(rows, "both", "base")
    assert est["point"] == pytest.approx(0.0, abs=1e-9)
    assert est["lo"] == pytest.approx(0.0, abs=1e-9)
    assert est["hi"] == pytest.approx(0.0, abs=1e-9)
    assert est["label"] == "NOT_NEEDED"


def test_a_known_effect_is_recovered():
    rows = make_rows({"base": 0.5, "both": 0.75})
    est = estimate(rows, "both", "base")
    assert est["point"] == pytest.approx(25.0, abs=1.0)
    assert est["n"] == 40
    assert est["label"] == "HELPS"


def test_the_bootstrap_is_paired_and_reproducible():
    rows = make_rows({"base": 0.5, "both": 0.75})
    first = estimate(rows, "both", "base")
    second = estimate(rows, "both", "base")
    assert np.allclose(first["samples"], second["samples"])
    assert first["samples"].shape == (N_BOOT,)


def test_the_bootstrap_resamples_seeds_not_rows():
    """A constant per-seed offset must not widen the interval."""
    seeds = list(range(50))
    diffs = {"cell": np.array([10.0] * len(seeds))}
    samples = paired_bootstrap(diffs, seeds)
    assert samples.mean() == pytest.approx(10.0)
    assert samples.std() == pytest.approx(0.0)


def test_the_verdicts_and_their_boundaries():
    # HELPS: point >= 5 and the interval above zero
    assert verdict(5.0, np.array([1.0, 5.0, 9.0]))[0] == "HELPS"
    assert verdict(12.0, np.array([3.0, 12.0, 20.0]))[0] == "HELPS"
    # NOT_NEEDED: the whole interval is below 5
    assert verdict(1.0, np.array([0.0, 1.0, 2.0]))[0] == "NOT_NEEDED"
    assert verdict(4.9, np.array([0.0, 4.9, 4.0]))[0] == "NOT_NEEDED"
    # INCONCLUSIVE: the interval reaches zero or crosses the delta
    assert verdict(6.0, np.array([-1.0, 6.0, 12.0]))[0] == "INCONCLUSIVE"
    assert verdict(2.0, np.array([0.0, 2.0, 9.0]))[0] == "INCONCLUSIVE"
    # a point estimate of exactly 4.9 with an interval below 5 is NOT_NEEDED,
    # a point estimate of exactly 5.0 with the lower bound above 0 is HELPS
    assert verdict(4.9, np.array([0.5, 4.9, 4.9]))[0] == "NOT_NEEDED"


def test_delta_is_five_points():
    assert DELTA == 5.0


def test_percentile_ci_uses_the_preregistered_percentiles():
    samples = np.arange(0.0, 1000.0)
    lo, hi = percentile_ci(samples)
    assert lo == pytest.approx(np.percentile(samples, 2.5))
    assert hi == pytest.approx(np.percentile(samples, 97.5))


def test_success_map_indexes_by_arm_and_p():
    rows = make_rows({"base": 0.5})
    table = success_map(rows)
    assert set(table) == {("base", p) for p in PS}
    assert len(table[("base", 0.1)]) == 40


def test_estimate_without_data_is_reported_not_crashed():
    rows = make_rows({"base": 0.5})
    est = estimate(rows, "both", "base")
    assert est["label"] == "NO_DATA"
    assert est["n"] == 0
