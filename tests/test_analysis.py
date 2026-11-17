"""The statistics and the preregistered decision rule."""
from __future__ import annotations

import numpy as np
import pytest

from dynhouse.analyze import Bootstrap, decide


def test_bootstrap_is_paired_over_seeds():
    seeds = list(range(20))
    boot = Bootstrap(seeds, n_boot=2000, seed=1)
    a = {s: 1.0 for s in seeds}
    b = {s: 0.0 for s in seeds}
    cells = {("arm", 0.2): a, ("other", 0.2): b}
    samples = boot.paired_diff(["arm"], ["other"], 0.2, cells)
    assert samples.shape == (2000,)
    assert samples.mean() == pytest.approx(100.0)      # percentage points
    assert np.allclose(samples, 100.0)


def test_paired_difference_keeps_the_pairing():
    """Pairing is what makes the interval tight: two identical arms cancel
    exactly, seed by seed, however the resampling falls."""
    seeds = list(range(40))
    boot = Bootstrap(seeds, n_boot=2000, seed=2)
    a = {s: float(s % 3 == 0) for s in seeds}
    b = {s: float(s % 5 == 0) for s in seeds}
    cells = {("arm", 0.2): a, ("other", 0.2): b}
    identical = boot.paired_diff(["arm"], ["arm"], 0.2, cells)
    assert np.allclose(identical, 0.0)
    # a constant offset shifts the paired difference by exactly that offset
    shifted = {s: a[s] + 0.2 for s in seeds}
    cells2 = {("arm", 0.2): a, ("other", 0.2): shifted}
    samples = boot.paired_diff(["arm"], ["other"], 0.2, cells2)
    assert np.allclose(samples, -20.0)


def test_cell_mean_is_a_success_rate_in_percent():
    seeds = list(range(10))
    boot = Bootstrap(seeds, n_boot=2000, seed=3)
    values = {s: float(s < 5) for s in seeds}
    samples = boot.cell_mean("arm", 0.2, {("arm", 0.2): values})
    assert samples.mean() == pytest.approx(50.0, abs=1.0)
    assert samples.min() >= 0.0 and samples.max() <= 100.0


def test_decide_implements_the_preregistered_rule():
    # HELPS: large effect, CI clearly above zero
    assert decide(12.0, np.array([11.0, 12.0, 13.0]))[0] == "HELPS"
    # NOT_NEEDED: the whole CI is below the delta
    assert decide(5.0, np.array([4.0, 5.0, 6.0]))[0] == "NOT_NEEDED"
    # INCONCLUSIVE: the point estimate is large but the CI touches zero
    assert decide(12.0, np.array([-1.0, 5.0, 20.0]))[0] == "INCONCLUSIVE"
    # INCONCLUSIVE: the CI crosses the delta
    assert decide(5.0, np.array([1.0, 8.0, 20.0]))[0] == "INCONCLUSIVE"
    # exactly at the delta with a CI above zero -> HELPS (>= is inclusive)
    assert decide(10.0, np.array([0.5, 10.0, 12.0]))[0] == "HELPS"
    # a CI whose upper bound is below the delta -> NOT_NEEDED
    assert decide(2.0, np.array([1.0, 5.0, 10.0]))[0] == "NOT_NEEDED"
    # a zero effect with a CI below the delta -> NOT_NEEDED
    assert decide(0.0, np.array([-1.0, 0.0, 1.0]))[0] == "NOT_NEEDED"


def test_decide_reports_the_interval_around_the_point():
    samples = np.linspace(3.0, 17.0, 101)
    label, lo, hi = decide(10.0, samples)
    assert lo < 10.0 < hi
    assert label == "HELPS"


def test_decide_uses_the_2_5_and_97_5_percentiles():
    samples = np.arange(0.0, 1000.0)
    label, lo, hi = decide(50.0, samples)
    assert lo == pytest.approx(np.percentile(samples, 2.5))
    assert hi == pytest.approx(np.percentile(samples, 97.5))
