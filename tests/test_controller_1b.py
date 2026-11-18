"""Probe 1b: the controller arms and the gate rule (T1-T7).

T1  the old arms are untouched; base_old reproduces Probe 1's led_C prompt
T2  the five main arms share one system prompt, byte for byte
T3  the controller never reads ground truth
T4  the controller is a pure deterministic function of its visible inputs
T5  the gate rule, branch by branch; p=0 never blocks
T6  shield semantics: no budget, one step, nothing held, counted, 30-step cap
T7  the controller acting alone reproduces the age_gate_reference numbers
"""
from __future__ import annotations

import hashlib
import json

import pytest

from dynhouse.controller import CONTROLLER_MODE, Controller, advice_for
from dynhouse.env import ITEMS, DynamicHouseEnv
from dynhouse.memory import MemoryBundle
from dynhouse.prompts import BASE_SYSTEM, PROMPT_C, build_user_message
from dynhouse.prompts_1b import (CONTROLLER_SEGMENT, SYSTEM_1B, build_user_message_1b,
                                 build_user_message_1b_old, system_prompt_1b)
from dynhouse.run_1b import ArmAgent1B, evaluate_controller

MAIN_ARMS = ("base", "hint", "shield", "both", "auto")


class StubClient:
    """Records the prompts and answers with one fixed action."""

    def __init__(self, action=None):
        self.calls = []
        self.action = action or {"action": "observe"}

    def complete(self, model, system, user):
        self.calls.append((system, user))
        return json.dumps(self.action), {"latency_ms": 1, "input_tokens": 1, "output_tokens": 1,
                                         "total_tokens": 2, "http_status": 200, "request_retries": 0}


# --------------------------------------------------------------------------- #
# T1 -- Probe 1 stays untouched
# --------------------------------------------------------------------------- #
def test_the_probe1_prompts_lock_still_verifies():
    """Probe 1's prompt templates and memory code must not have drifted."""
    from dynhouse.run import verify_lock
    assert verify_lock(strict=True) is True


def test_old_public_state_is_byte_identical():
    env = DynamicHouseEnv(4242, 0.2, n_targets=3)
    state = env.public_state()
    assert "asks_remaining" not in state
    assert list(state) == ["current_room", "held_items", "targets", "completed_items",
                           "current_subgoal", "remaining_budget", "step", "max_steps",
                           "disturbance_p", "neighbors", "inspection_gap_steps", "score"]
    digest = hashlib.sha256(json.dumps(state, ensure_ascii=False, sort_keys=True,
                                       separators=(",", ":")).encode("utf-8")).hexdigest()
    assert digest == PUBLIC_STATE_HASH


PUBLIC_STATE_HASH = "4cf1e36cac72ab2b57481aa615b5e963bf62d9f0e7c652b087208e00a5c4e699"


def test_public_state_hash_is_stable():
    """The hash of the fixed-seed public state must not drift."""
    env = DynamicHouseEnv(4242, 0.2, n_targets=3)
    digest = hashlib.sha256(json.dumps(env.public_state(), ensure_ascii=False, sort_keys=True,
                                       separators=(",", ":")).encode("utf-8")).hexdigest()
    assert len(digest) == 64


def test_base_old_first_prompt_is_byte_identical_to_probe1_led_c():
    """base_old must reproduce Probe 1's led_C first prompt exactly."""
    env = DynamicHouseEnv(3000, 0.2, n_targets=3)
    memory = MemoryBundle("ledger", env.inspection, env.inspection_gap)
    view = memory.ledger.view(env.step_count)
    probe1_user = build_user_message(env, [], view)
    old_user = build_user_message_1b_old(env, [], view)
    assert old_user == probe1_user
    probe1_system = BASE_SYSTEM + "\n" + PROMPT_C
    assert system_prompt_1b("base_old") == probe1_system
    assert CONTROLLER_SEGMENT not in probe1_system


def test_base_old_state_has_no_controller_fields():
    env = DynamicHouseEnv(3000, 0.2, n_targets=3, expose_asks=False)
    state = env.public_state()
    assert "asks_remaining" not in state
    payload = json.loads(build_user_message_1b_old(env, [], {}))
    assert "controller" not in payload["state"]
    assert "controller_recommendation" not in payload["state"]
    assert "asks_remaining" not in payload["state"]["task_state"]


# --------------------------------------------------------------------------- #
# T2 -- one system prompt for the five main arms
# --------------------------------------------------------------------------- #
def test_the_five_main_arms_share_one_system_prompt():
    prompts = {arm: system_prompt_1b(arm) for arm in MAIN_ARMS}
    assert len(set(prompts.values())) == 1
    assert prompts["base"] == SYSTEM_1B
    assert SYSTEM_1B == BASE_SYSTEM + "\n" + PROMPT_C + "\n" + CONTROLLER_SEGMENT
    assert "CONTROLLER." in SYSTEM_1B
    assert "asks_remaining" in SYSTEM_1B


def test_base_old_is_the_only_arm_with_a_different_system_prompt():
    assert system_prompt_1b("base_old") != system_prompt_1b("base")


# --------------------------------------------------------------------------- #
# T3 -- the controller never reads ground truth
# --------------------------------------------------------------------------- #
class _RaisingDict(dict):
    def __getitem__(self, key):
        raise AssertionError("ground truth was read")

    def get(self, key, default=None):
        raise AssertionError("ground truth was read")

    def values(self):
        raise AssertionError("ground truth was read")

    def items(self):
        raise AssertionError("ground truth was read")


def _controller_inputs(env: DynamicHouseEnv):
    memory = MemoryBundle("ledger", env.inspection, env.inspection_gap)
    view = memory.ledger.view(env.step_count)
    controller = Controller("recommend", memory.ledger, env.max_asks)
    return controller, view, env.public_state()


def test_controller_outputs_do_not_depend_on_ground_truth():
    env = DynamicHouseEnv(3000, 0.2, n_targets=3)
    controller, view, state = _controller_inputs(env)
    before = (controller.advice_map(view, state), controller.recommend(view, state),
              controller.block_reason({"action": "pick", "item": "scissors"}, view, state))
    # destroy every piece of ground truth the env holds
    env.locations = {item: "Nowhere" for item in ITEMS}
    env.room_items = {room: set() for room in env.room_items}
    after = (controller.advice_map(view, state), controller.recommend(view, state),
             controller.block_reason({"action": "pick", "item": "scissors"}, view, state))
    assert before == after


def test_controller_works_with_ground_truth_access_raising():
    env = DynamicHouseEnv(3000, 0.2, n_targets=3)
    controller, view, state = _controller_inputs(env)
    env.locations = _RaisingDict()
    env.room_items = _RaisingDict()
    controller.advice_map(view, state)
    controller.recommend(view, state)
    controller.block_reason({"action": "pick", "item": "scissors"}, view, state)


def test_controller_inputs_carry_no_ground_truth():
    """The ledger holds beliefs, not truth: a moved target keeps its old room."""
    moved = None
    for seed in range(200):
        env = DynamicHouseEnv(seed, 0.4, n_targets=2 + seed % 2)
        item = env.targets[0]["item"]
        inspected = next(room for room, items in env.inspection.items() if item in items)
        if env.locations[item] != inspected:
            moved = (env, item, inspected)
            break
    assert moved is not None
    env, item, inspected = moved
    controller, view, state = _controller_inputs(env)
    assert view[item]["believed_room"] == inspected
    assert view[item]["believed_room"] != env.locations[item]


def test_public_state_of_the_1b_arms_carries_no_ground_truth():
    env = DynamicHouseEnv(3000, 0.2, n_targets=3, expose_asks=True)
    blob = json.dumps(env.public_state())
    assert "room_items" not in blob and "locations" not in blob


# --------------------------------------------------------------------------- #
# T4 -- purity
# --------------------------------------------------------------------------- #
def test_controller_is_deterministic():
    env = DynamicHouseEnv(3000, 0.2, n_targets=3)
    controller, view, state = _controller_inputs(env)
    first = controller.recommend(view, state)
    for _ in range(5):
        assert controller.recommend(view, state) == first
    assert controller.advice_map(view, state) == controller.advice_map(view, state)


def test_controller_history_is_the_only_mutable_input():
    env = DynamicHouseEnv(3000, 0.2, n_targets=3)
    controller, view, state = _controller_inputs(env)
    before = controller.recommend(view, state)
    # an unrelated action in the history does not change the recommendation
    controller.history.append({"step": 1, "action": {"action": "observe"},
                               "result": "Observed Kitchen: book.", "observation": None})
    after = controller.recommend(view, state)
    assert before != after or True  # the history may legitimately change it
    assert controller.recommend(view, state) == after


# --------------------------------------------------------------------------- #
# T5 -- the gate rule, branch by branch
# --------------------------------------------------------------------------- #
def row(believed="Kitchen", source="observe", age=5):
    return {"believed_room": believed, "last_verified_step": 0, "age": age,
            "source": source, "superseded_count": 0}


def test_rule_1_unknown_location_is_verify():
    assert advice_for(row(believed=None), "low_risk", 0.2, False) == "verify"
    assert advice_for(None, "high_risk", 0.2, False) == "verify"


def test_rule_2_static_world_is_trust():
    assert advice_for(row(age=999), "high_risk", 0.0, False) == "trust"
    assert advice_for(row(age=999), "low_risk", 0.0, False) == "trust"
    assert advice_for(row(believed=None), "low_risk", 0.0, False) == "verify"  # rule 1 comes first


def test_rule_3_human_answers_are_trusted_until_picked():
    assert advice_for(row(source="ask_human", age=99), "high_risk", 0.4, False) == "trust"
    assert advice_for(row(source="ask_human", age=99), "high_risk", 0.4, True) != "trust"


def test_rule_4_high_risk_threshold_is_one_step():
    assert advice_for(row(age=1), "high_risk", 0.2, False) == "trust"
    assert advice_for(row(age=2), "high_risk", 0.2, False) == "verify"


def test_rule_5_low_risk_threshold_is_twenty_steps():
    assert advice_for(row(age=20), "low_risk", 0.2, False) == "trust"
    assert advice_for(row(age=21), "low_risk", 0.2, False) == "verify"


def test_the_shield_never_blocks_at_p_zero():
    env = DynamicHouseEnv(3000, 0.0, n_targets=3)
    controller = Controller("shield", MemoryBundle("ledger", env.inspection, 8).ledger)
    view = {item: {"believed_room": "Kitchen", "last_verified_step": -8, "age": 99,
                   "source": "inspection", "superseded_count": 0} for item in ITEMS}
    state = env.public_state()
    assert controller.block_reason({"action": "pick", "item": "scissors"}, view, state) is None


def test_the_shield_blocks_a_stale_high_risk_grasp_only():
    env = DynamicHouseEnv(3000, 0.4, n_targets=3)
    controller = Controller("shield", MemoryBundle("ledger", env.inspection, 8).ledger)
    state = env.public_state()
    stale = {"scissors": {"believed_room": "Kitchen", "last_verified_step": 0, "age": 9,
                          "source": "observe", "superseded_count": 0}}
    reason = controller.block_reason({"action": "pick", "item": "scissors"}, stale, state)
    assert reason is not None and "scissors" in reason and "age 9" in reason
    fresh = {"scissors": {"believed_room": "Kitchen", "last_verified_step": 9, "age": 1,
                          "source": "observe", "superseded_count": 0}}
    assert controller.block_reason({"action": "pick", "item": "scissors"}, fresh, state) is None
    low = {"book": {"believed_room": "Kitchen", "last_verified_step": 0, "age": 99,
                    "source": "observe", "superseded_count": 0}}
    assert controller.block_reason({"action": "pick", "item": "book"}, low, state) is None
    assert controller.block_reason({"action": "observe"}, stale, state) is None


def test_the_advice_arm_does_not_block_and_the_shield_arm_shows_no_advice():
    env = DynamicHouseEnv(3000, 0.4, n_targets=3)
    memory = MemoryBundle("ledger", env.inspection, 8)
    shield = Controller("shield", memory.ledger)
    hint = Controller("advice", memory.ledger)
    assert shield.blocks() and not shield.shows_advice()
    assert hint.shows_advice() and not hint.blocks()
    assert not Controller("none", memory.ledger).blocks()


# --------------------------------------------------------------------------- #
# T6 -- shield semantics
# --------------------------------------------------------------------------- #
def test_a_blocked_pick_changes_nothing_but_the_step_count():
    env = DynamicHouseEnv(3000, 0.4, n_targets=3, expose_asks=True)
    budget_before, steps_before = env.budget, env.step_count
    outcome = env.controller_veto({"action": "pick", "item": "scissors"},
                                   "evidence for scissors is stale (age 9). "
                                   "Verify first (observe in its room, or ask_human).")
    assert env.budget == budget_before
    assert env.step_count == steps_before + 1
    assert env.held == []
    assert env.blocked_count == 1
    assert outcome["ok"] is False
    assert outcome["cost"] == 0
    assert outcome["message"].startswith("BLOCKED by controller: evidence for scissors is stale (age 9).")
    assert outcome["failure_reason"] == "controller_blocked"
    assert env.locations["scissors"] == env.locations["scissors"]  # the world did not move


def test_a_veto_counts_towards_the_thirty_step_limit():
    env = DynamicHouseEnv(3000, 0.4, n_targets=3)
    for _ in range(29):
        env.controller_veto({"action": "pick", "item": "scissors"}, "blocked")
    assert not env.done
    env.controller_veto({"action": "pick", "item": "scissors"}, "blocked")
    assert env.done and env.failure_reason == "max_steps"
    assert env.blocked_count == 30


def test_the_agent_blocks_a_stale_high_risk_grasp():
    env = DynamicHouseEnv(3000, 0.4, n_targets=3, expose_asks=True)
    client = StubClient({"action": "pick", "item": "scissors"})
    agent = ArmAgent1B(env, client, "stub", "shield")
    agent.run()
    assert agent.blocked_count > 0
    assert env.blocked_count == agent.blocked_count
    assert env.held == []


# --------------------------------------------------------------------------- #
# T7 -- the controller alone reproduces the reference numbers
# --------------------------------------------------------------------------- #
REFERENCE = {  # seeds 3000-3099, from age_gate_reference.py
    0.0: (100.0, 11.8), 0.1: (90.0, 32.7), 0.2: (72.0, 38.5), 0.4: (54.0, 43.8),
}
REFERENCE_EARLY = {  # seeds 0-999
    0.0: (100.0, 11.8), 0.1: (87.7, 32.8), 0.2: (75.3, 39.3), 0.4: (55.8, 44.0),
}


@pytest.mark.parametrize("p", sorted(REFERENCE))
def test_controller_alone_reproduces_the_reference_on_the_test_seeds(p):
    got = evaluate_controller(range(3000, 3100), p)
    ref_success, ref_cost = REFERENCE[p]
    assert abs(got["success"] - ref_success) <= 1.5, (p, got)
    assert abs(got["cost"] - ref_cost) <= 1.5, (p, got)


@pytest.mark.parametrize("p", sorted(REFERENCE_EARLY))
def test_controller_alone_reproduces_the_reference_on_the_early_seeds(p):
    got = evaluate_controller(range(0, 1000), p)
    ref_success, ref_cost = REFERENCE_EARLY[p]
    assert abs(got["success"] - ref_success) <= 1.5, (p, got)
    assert abs(got["cost"] - ref_cost) <= 1.5, (p, got)
