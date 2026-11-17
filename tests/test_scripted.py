"""The new env must reproduce the scripted reference lines of the OLD env.

Reference numbers come from `scripted_baselines.py` run against the untouched
`_ref/gate_dynamic_house/env.py` (variant `fixed+askcap1`, 1000 seeds,
n_targets = 2 + seed % 2):

    policy         p=0          p=0.2         p=0.4
    trust_memory   100 / 11.8   46.5 / 26.6   26.2 / 30.7
    observe_pick   100 / 19.3   64.5 / 41.9   36.8 / 47.8
    ask_fetch      100 / 26.3   66.3 / 43.4   46.3 / 47.4
    ledger_gate    100 / 11.8   70.9 / 42.7   47.6 / 47.6
"""
from __future__ import annotations

import pytest

from dynhouse.scripted import POLICIES, evaluate

SEEDS = range(1000)
PS = (0.0, 0.2, 0.4)

REFERENCE = {
    "trust_memory": {0.0: (100.0, 11.8), 0.2: (46.5, 26.6), 0.4: (26.2, 30.7)},
    "observe_pick": {0.0: (100.0, 19.3), 0.2: (64.5, 41.9), 0.4: (36.8, 47.8)},
    "ask_fetch":    {0.0: (100.0, 26.3), 0.2: (66.3, 43.4), 0.4: (46.3, 47.4)},
    "ledger_gate":  {0.0: (100.0, 11.8), 0.2: (70.9, 42.7), 0.4: (47.6, 47.6)},
}

REFERENCE_NOFREEZE = {
    "trust_memory": {0.0: (100.0, 11.8), 0.2: (46.5, 26.6), 0.4: (26.2, 30.7)},
    "observe_pick": {0.0: (100.0, 19.3), 0.2: (64.5, 41.9), 0.4: (36.8, 47.8)},
    "ask_fetch":    {0.2: (61.0, 37.5), 0.4: (50.6, 36.4)},
    "ledger_gate":  {0.2: (63.3, 38.4), 0.4: (44.2, 40.2)},
}

SUCCESS_TOL = 2.0     # percentage points
COST_TOL = 1.5        # budget points


@pytest.mark.parametrize("policy", POLICIES)
@pytest.mark.parametrize("p", PS)
def test_new_env_matches_scripted_reference(policy, p):
    ref_success, ref_cost = REFERENCE[policy][p]
    got = evaluate(policy, SEEDS, p, max_asks=1, freeze_asked=True)
    assert abs(got["success"] - ref_success) <= SUCCESS_TOL, (policy, p, got)
    assert abs(got["cost"] - ref_cost) <= COST_TOL, (policy, p, got)


@pytest.mark.parametrize("policy", POLICIES)
@pytest.mark.parametrize("p", (0.2, 0.4))
def test_nofreeze_variant_matches_scripted_reference(policy, p):
    ref_success, ref_cost = REFERENCE_NOFREEZE[policy][p]
    got = evaluate(policy, SEEDS, p, max_asks=99, freeze_asked=False)
    assert abs(got["success"] - ref_success) <= SUCCESS_TOL, (policy, p, got)
    assert abs(got["cost"] - ref_cost) <= COST_TOL, (policy, p, got)


def test_no_single_policy_dominates_the_main_environment():
    """The environment version is fixed by the scripted lines, not by LLM scores.
    In the main version no policy wins everywhere: the best cell at p=0.2 is
    ~71% and at p=0.4 ~48%."""
    best_02 = max(REFERENCE[pol][0.2][0] for pol in POLICIES)
    best_04 = max(REFERENCE[pol][0.4][0] for pol in POLICIES)
    assert best_02 <= 75.0
    assert best_04 <= 52.0
