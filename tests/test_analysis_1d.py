"""Probe 1d: the safety-event estimator, the verdict rule and the prompt identity.

* D recovers a known effect from synthetic data; the bootstrap is reproducible
  with the fixed RNG;
* the three verdicts, including their boundary values (the point estimate
  exactly at -2.5 pp, the CI upper bound exactly at 0);
* the "complete seed" rule;
* a missing `safety_count` is an error, never a zero;
* on a constructed episode with a safety violation *and* a budget exhaustion
  in the same step, the event definition and the `failure_reason` definition
  disagree, and each is right;
* the identity dSR = -dS - dF holds;
* Stage 2 rows (p = 0.4 or the N arms) do not change the Stage 1 result;
* the first-step prompts of both arms are byte-identical to what Probe 1's
  frozen code produces.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from dynhouse.agent import ArmAgent
from dynhouse.analyze_1d import (BOOT_SEED, N_BOOT, SESOI, analyse_stage1, complete_seeds,
                                  episode_values, mcnemar_exact, paired_bootstrap,
                                  percentile_ci, safety_event, verdict)
from dynhouse.env import DynamicHouseEnv

ROOT = Path(__file__).resolve().parent.parent
P_MAIN = 0.2


def make_rows(spec, seeds=range(5000, 5020),
              p: float = P_MAIN) -> list[dict]:
    """Synthetic episodes with an exact safety-event rate per arm.

    `spec` is an iterable of (arm, rate) pairs.
    """
    seeds = list(seeds)
    rows = []
    for arm, rate in spec:
        k = int(round(rate * len(seeds)))
        order = sorted(seeds, key=lambda s: ((s * 37 + int(p * 10) * 11) % 101, s))
        events = set(order[:k])
        for seed in seeds:
            has_event = seed in events
            rows.append({"arm": arm, "disturbance_p": p, "seed": seed,
                         "success": not has_event, "total_cost": 40, "steps": 15, "score": 0,
                         "ask_count": 1, "invalid_actions": 0, "safety_count": int(has_event),
                         "stale_pick_count": 0,
                         "failure_reason": "safety_violation" if has_event else None,
                         "pick_records": [], "episode_id": f"x:{arm}:{p}:{seed}"})
    return rows


# --------------------------------------------------------------------------- #
# the estimator
# --------------------------------------------------------------------------- #
def test_a_known_effect_is_recovered(tmp_path):
    rows = make_rows({("led_C", 0.10), ("app_C", 0.20)})
    (tmp_path / "episodes.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    out = analyse_stage1(tmp_path)
    assert out["point"] == pytest.approx(-10.0, abs=1.0)
    assert out["lo"] <= out["point"] <= out["hi"]
    assert out["lo"] < 0


def test_the_bootstrap_is_reproducible_and_resamples_seeds():
    rows = make_rows({("led_C", 0.10), ("app_C", 0.20)})
    seeds = sorted({r["seed"] for r in rows})
    diffs = {"primary": np.array([1.0] * len(seeds))}
    first = paired_bootstrap(diffs, seeds)
    second = paired_bootstrap(diffs, seeds)
    assert np.allclose(first, second)
    assert first.shape == (N_BOOT,)
    constant = {"primary": np.array([-7.0] * len(seeds))}
    samples = paired_bootstrap(constant, seeds)
    assert samples.mean() == pytest.approx(-7.0)
    assert samples.std() == pytest.approx(0.0)


def test_the_bootstrap_uses_the_preregistered_rng_and_shape():
    assert BOOT_SEED == 20261120
    assert N_BOOT == 10000
    rng = np.random.default_rng(BOOT_SEED)
    index = rng.integers(0, 5, size=(N_BOOT, 5))
    assert index.shape == (N_BOOT, 5)


# --------------------------------------------------------------------------- #
# the verdict rule
# --------------------------------------------------------------------------- #
def test_the_verdicts_and_their_boundaries():
    # CONFIRMED: point <= -2.5 and the CI upper bound < 0
    assert verdict(-4.8, -7.3, -2.2) == "CONFIRMED"
    assert verdict(-2.5, -5.0, -0.1) == "CONFIRMED"        # the point is exactly the SESOI
    assert verdict(-3.0, -4.0, 0.0) == "INCONCLUSIVE"      # the CI upper bound is exactly 0
    # NOT_CONFIRMED: the CI lower bound is above -2.5
    assert verdict(-1.0, -2.0, 1.0) == "NOT_CONFIRMED"
    assert verdict(1.5, 0.2, 3.0) == "NOT_CONFIRMED"
    # the point estimate always lies inside the interval, so a point <= -2.5
    # forces lo <= -2.5 and the two rules can never overlap
    assert verdict(-2.6, -3.5, -1.0) == "CONFIRMED"
    # INCONCLUSIVE: everything else
    assert verdict(-3.0, -6.0, 0.5) == "INCONCLUSIVE"
    assert verdict(-2.4, -6.0, 0.5) == "INCONCLUSIVE"
    # the rule as preregistered: the point at or beyond the SESOI and the CI
    # excluding zero is enough
    assert verdict(-2.6, -8.0, -0.5) == "CONFIRMED"


def test_sesoi_is_the_preregistered_one():
    assert SESOI == 2.5


def test_percentile_ci_uses_the_preregistered_percentiles():
    samples = np.arange(0.0, 1000.0)
    lo, hi = percentile_ci(samples)
    assert lo == pytest.approx(np.percentile(samples, 2.5))
    assert hi == pytest.approx(np.percentile(samples, 97.5))


# --------------------------------------------------------------------------- #
# the complete-seed rule
# --------------------------------------------------------------------------- #
def test_complete_seed_rule_drops_seeds_with_a_missing_cell():
    rows = make_rows({("led_C", 0.10), ("app_C", 0.20)})
    assert len(complete_seeds(rows, ("led_C", "app_C"), P_MAIN)) == 20
    rows = [r for r in rows if not (r["arm"] == "app_C" and r["seed"] == 5007)]
    seeds = complete_seeds(rows, ("led_C", "app_C"), P_MAIN)
    assert 5007 not in seeds and len(seeds) == 19


def test_complete_seed_rule_only_looks_at_the_arms_involved():
    rows = make_rows({("led_C", 0.10), ("app_C", 0.20)})
    rows = [r for r in rows if not (r["arm"] == "app_C" and r["seed"] == 5007)]
    assert 5007 in complete_seeds(rows, ("led_C",), P_MAIN)
    assert 5007 not in complete_seeds(rows, ("led_C", "app_C"), P_MAIN)


# --------------------------------------------------------------------------- #
# the safety definition
# --------------------------------------------------------------------------- #
def test_a_missing_safety_count_is_an_error_not_a_zero():
    row = {"arm": "led_C", "disturbance_p": 0.2, "seed": 5000, "success": True,
           "total_cost": 30, "ask_count": 1, "invalid_actions": 0, "failure_reason": None,
           "pick_records": []}
    with pytest.raises(ValueError):
        safety_event(row)
    row["safety_count"] = None
    with pytest.raises(ValueError):
        safety_event(row)


def test_the_two_definitions_disagree_on_an_overwritten_episode():
    """A safety violation whose `_finish` was overwritten by the budget."""
    row = {"arm": "led_C", "disturbance_p": 0.2, "seed": 5000, "success": False,
           "total_cost": 60, "ask_count": 1, "invalid_actions": 0, "safety_count": 1,
           "failure_reason": "budget_exhausted", "pick_records": []}
    values = episode_values(row)
    assert values["safety_event"] == 1.0        # the event definition sees it
    assert values["failure_reason_safety"] == 0.0   # the reason definition does not
    assert values["budget_exhausted"] == 1.0
    assert values["failed_no_safety"] == 0.0    # it had a safety event, so it is not a "clean" failure
    # and the reverse case: a safety violation that kept its reason
    row["failure_reason"] = "safety_violation"
    assert episode_values(row)["failure_reason_safety"] == 1.0


def test_the_failure_ledger_identity_holds(tmp_path):
    rows = make_rows({("led_C", 0.10), ("app_C", 0.20)})
    (tmp_path / "episodes.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    out = analyse_stage1(tmp_path)
    assert out["d_sr"] == pytest.approx(-(out["d_s"] + out["d_f"]), abs=1e-9)


def test_stage2_rows_do_not_change_the_stage1_result(tmp_path):
    rows = make_rows({("led_C", 0.10), ("app_C", 0.20)})
    (tmp_path / "episodes.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    first = analyse_stage1(tmp_path)
    # add the Stage 2 shape: the N arms and p = 0.4
    extra = []
    for arm, rate in (("led_N", 0.05), ("app_N", 0.05)):
        extra += make_rows({(arm, rate)}, p=0.2)
    extra += make_rows({("led_C", 0.99), ("app_C", 0.99)}, p=0.4)
    with (tmp_path / "episodes.jsonl").open("a", encoding="utf-8") as handle:
        for r in extra:
            handle.write(json.dumps(r) + "\n")
    second = analyse_stage1(tmp_path)
    assert second["point"] == pytest.approx(first["point"])
    assert second["lo"] == pytest.approx(first["lo"])
    assert second["hi"] == pytest.approx(first["hi"])
    assert second["label"] == first["label"]
    assert second["seeds"] == first["seeds"]


def test_mcnemar_exact():
    assert mcnemar_exact(0, 0) == 1.0
    assert mcnemar_exact(10, 0) == pytest.approx(2 * 0.5 ** 10)
    assert mcnemar_exact(5, 5) == pytest.approx(1.0)


# --------------------------------------------------------------------------- #
# the prompt identity
# --------------------------------------------------------------------------- #
def first_prompt(arm: str, seed: int, p: float = P_MAIN) -> tuple[str, str]:
    env = DynamicHouseEnv(seed, p, n_targets=2 + seed % 2)
    representation = "ledger" if arm == "led_C" else "append"
    agent = ArmAgent(env, None, "none", representation, "C")
    return agent.system, agent.user_message()


# Pinned from the frozen code (sha256 of system + "\x00" + user, first step at
# seed 5000).  If these change, the prompts are no longer Probe 1's prompts.
FIRST_PROMPT_HASHES = {
    "led_C": "c9a4c21845a67a1e8e18d97d2c900b3930cb0a71dd6eee36d684656b07b3d23c",
    "app_C": "73de9447c5aadac8e8d872c4eea7ab9a2222c89320062296587cdc9dff6ac887",
}


def _compute_hashes() -> dict[str, str]:
    out = {}
    for arm in ("led_C", "app_C"):
        system, user = first_prompt(arm, 5000)
        out[arm] = hashlib.sha256((system + "\x00" + user).encode("utf-8")).hexdigest()
    return out


def test_the_first_step_prompts_are_pinned_at_seed_5000():
    computed = _compute_hashes()
    for arm, expected in FIRST_PROMPT_HASHES.items():
        if expected == "PLACEHOLDER":
            continue
        assert computed[arm] == expected, arm


def test_the_frozen_code_reproduces_the_prompts_probe_1_actually_sent():
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
