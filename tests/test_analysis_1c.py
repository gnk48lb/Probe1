"""Probe 1c: the replication statistics, and the prompt-identity checks.

* the estimator recovers a known effect from synthetic data;
* the paired bootstrap over seeds is reproducible;
* the three verdicts, including their boundary values;
* the "complete seed" rule;
* the first-step prompts of led_C and app_C are byte-identical to what
  probe1-final's frozen code produces -- and, where Probe 1's own transcripts
  are on disk, byte-identical to what Probe 1 actually sent.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from dynhouse.agent import ArmAgent
from dynhouse.analyze_1c import (BOOT_SEED, DELTA, N_BOOT, complete_seeds, episode_values,
                                  failure_flags, paired_bootstrap, paired_difference,
                                  percentile_ci, verdict)
from dynhouse.env import DynamicHouseEnv

ROOT = Path(__file__).resolve().parent.parent          # the repository root
PS = (0.2,)


def metric_values(rows, arm: str, key: str) -> dict[int, float]:
    """One per-episode quantity per seed, for one arm."""
    return {r["seed"]: episode_values(r)[key] for r in rows if r["arm"] == arm}


def make_rows(spec: dict[str, float], seeds=range(4000, 4040), p: float = 0.2) -> list[dict]:
    """Synthetic episodes with an exact success rate per arm."""
    seeds = list(seeds)
    rows = []
    for arm, rate in spec.items():
        k = int(round(rate * len(seeds)))
        order = sorted(seeds, key=lambda s: ((s * 37 + int(p * 10) * 11) % 101, s))
        winners = set(order[:k])
        for seed in seeds:
            rows.append({"arm": arm, "disturbance_p": p, "seed": seed,
                         "success": seed in winners, "total_cost": 30, "steps": 10,
                         "ask_count": 1, "stale_pick_count": 0, "safety_count": 0,
                         "invalid_actions": 0, "failure_reason": None if seed in winners else "budget_exhausted",
                         "pick_records": []})
    return rows


# --------------------------------------------------------------------------- #
# the estimators
# --------------------------------------------------------------------------- #
def test_complete_seed_rule_drops_seeds_with_a_missing_cell():
    rows = make_rows({"led_C": 0.6, "app_C": 0.5})
    assert len(complete_seeds(rows, ("led_C", "app_C"), PS)) == 40
    rows = [r for r in rows if not (r["arm"] == "app_C" and r["seed"] == 4007)]
    seeds = complete_seeds(rows, ("led_C", "app_C"), PS)
    assert 4007 not in seeds and len(seeds) == 39


def test_complete_seed_rule_only_looks_at_the_arms_involved():
    rows = make_rows({"led_C": 0.6, "app_C": 0.5})
    rows = [r for r in rows if not (r["arm"] == "app_C" and r["seed"] == 4007)]
    assert 4007 in complete_seeds(rows, ("led_C",), PS)
    assert 4007 not in complete_seeds(rows, ("led_C", "app_C"), PS)


def test_known_effect_is_recovered():
    rows = make_rows({"led_C": 0.75, "app_C": 0.5})
    seeds = complete_seeds(rows, ("led_C", "app_C"), PS)
    values = {arm: metric_values(rows, arm, "success") for arm in ("led_C", "app_C")}
    mean, lo, hi, n = paired_difference(rows, "led_C", "app_C", 0.2,
                                        values["led_C"], values["app_C"], seeds)
    assert mean * 100 == pytest.approx(25.0, abs=1.0)
    assert n == 40
    assert lo > 0


def test_identical_arms_give_exactly_zero():
    rows = make_rows({"led_C": 0.5, "app_C": 0.5})
    seeds = complete_seeds(rows, ("led_C", "app_C"), PS)
    values = {arm: metric_values(rows, arm, "success") for arm in ("led_C", "app_C")}
    mean, lo, hi, _ = paired_difference(rows, "led_C", "app_C", 0.2,
                                        values["led_C"], values["app_C"], seeds)
    assert mean == pytest.approx(0.0, abs=1e-9)
    assert lo == pytest.approx(0.0, abs=1e-9)
    assert hi == pytest.approx(0.0, abs=1e-9)


def test_the_bootstrap_is_reproducible_and_resamples_seeds():
    rows = make_rows({"led_C": 0.75, "app_C": 0.5})
    seeds = complete_seeds(rows, ("led_C", "app_C"), PS)
    diffs = {"main": np.array([1.0, -1.0] * (len(seeds) // 2))}
    first = paired_bootstrap(diffs, seeds)
    second = paired_bootstrap(diffs, seeds)
    assert np.allclose(first, second)
    assert first.shape == (N_BOOT,)
    # a constant per-seed offset has no spread: the bootstrap resamples seeds,
    # not rows, and the pairing is preserved
    constant = {"main": np.array([7.0] * len(seeds))}
    samples = paired_bootstrap(constant, seeds)
    assert samples.mean() == pytest.approx(7.0)
    assert samples.std() == pytest.approx(0.0)


def test_the_verdicts_and_their_boundaries():
    # REPLICATED: point >= 5 and the interval above zero
    assert verdict(5.0, np.array([1.0, 5.0, 9.0]))[0] == "REPLICATED"
    assert verdict(12.0, np.array([3.0, 12.0, 20.0]))[0] == "REPLICATED"
    # NOT_REPLICATED: the whole interval is below 5
    assert verdict(1.0, np.array([0.0, 1.0, 2.0]))[0] == "NOT_REPLICATED"
    assert verdict(4.9, np.array([0.5, 4.9, 4.9]))[0] == "NOT_REPLICATED"
    # INCONCLUSIVE: the interval reaches zero or crosses the delta
    assert verdict(6.0, np.array([-1.0, 6.0, 12.0]))[0] == "INCONCLUSIVE"
    assert verdict(2.0, np.array([0.0, 2.0, 9.0]))[0] == "INCONCLUSIVE"
    # a point estimate of exactly 4.9 with the interval below 5 is NOT_REPLICATED
    assert verdict(4.9, np.array([0.5, 4.9, 4.9]))[0] == "NOT_REPLICATED"


def test_delta_and_bootstrap_are_the_preregistered_ones():
    assert DELTA == 5.0
    assert N_BOOT == 10000
    assert BOOT_SEED == 20261119


def test_percentile_ci_uses_the_preregistered_percentiles():
    samples = np.arange(0.0, 1000.0)
    lo, hi = percentile_ci(samples)
    assert lo == pytest.approx(np.percentile(samples, 2.5))
    assert hi == pytest.approx(np.percentile(samples, 97.5))


def test_failure_flags_are_not_mutually_exclusive():
    row = {"success": False, "total_cost": 60, "ask_count": 1, "safety_count": 1,
           "stale_pick_count": 1, "invalid_actions": 2,
           "failure_reason": "budget_exhausted",
           "pick_records": [{"item": "scissors", "ok": False, "evidence_age": 1},
                            {"item": "book", "ok": False, "evidence_age": 9}]}
    flags = failure_flags(row, repeat_ask=True)
    assert flags["competing_pick_fail"] and flags["stale_pick_fail"]
    assert flags["high_risk_pick"] and flags["repeat_ask"]
    assert flags["budget_exhausted"] and flags["safety_violation"]
    assert not flags["never_used_ask"]


# --------------------------------------------------------------------------- #
# the prompt identity checks
# --------------------------------------------------------------------------- #
def first_prompt(arm: str, seed: int, p: float = 0.2) -> tuple[str, str]:
    """The first-step system and user prompt, from the frozen Probe 1 code."""
    env = DynamicHouseEnv(seed, p, n_targets=2 + seed % 2)
    representation = "ledger" if arm == "led_C" else "append"
    agent = ArmAgent(env, None, "none", representation, "C")
    return agent.system, agent.user_message()


# Pinned at the start of Probe 1c from the frozen code (sha256 of
# system + "\x00" + user for the first step at seed 4000, p = 0.2).  If these
# change, the prompts are no longer Probe 1's prompts.
FIRST_PROMPT_HASHES = {
    "led_C": "19a9f844bc0e00376f2f995d0cea9e63c3e24f7134ff7dfc59a6ffd7064ffa3d",
    "app_C": "debe57374d217c5387d409650630417c1478bb376e4e5a8b84f736d32aeacbbb",
}


def test_first_step_prompts_are_pinned_at_seed_4000():
    for arm in ("led_C", "app_C"):
        system, user = first_prompt(arm, 4000)
        digest = hashlib.sha256((system + "\x00" + user).encode("utf-8")).hexdigest()
        assert digest == FIRST_PROMPT_HASHES[arm], arm


def test_the_frozen_code_reproduces_the_prompts_probe_1_actually_sent():
    """Where Probe 1's transcripts are on disk, the frozen code must rebuild the
    very same first-step prompt, byte for byte."""
    raw = ROOT / "results" / "main" / "raw.jsonl"
    if not raw.exists():
        pytest.skip("Probe 1's raw transcripts are not on disk")
    checked = 0
    with raw.open(encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            if row.get("arm") != "led_C" or row.get("disturbance_p") != 0.2:
                continue
            if row.get("seed") != 1000:
                continue
            exchange = row["exchanges"][0]
            system, user = first_prompt("led_C", 1000)
            assert exchange["system"] == system
            assert exchange["user"] == user
            checked += 1
            break
    assert checked == 1
