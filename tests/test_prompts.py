"""The consistency law: apart from R and P, no two arms may differ by a character.

These tests must pass before any LLM run.
"""
from __future__ import annotations

import json

import pytest

from dynhouse.agent import ArmAgent
from dynhouse.env import ITEMS, ROOMS, DynamicHouseEnv, named_items
from dynhouse.memory import MemoryBundle
from dynhouse.prompts import BASE_SYSTEM, POLICY_SUFFIX, PROMPT_C, build_user_message, system_prompt

ARMS = {"win_N": ("window", "N"), "app_N": ("append", "N"), "led_N": ("ledger", "N"),
        "win_C": ("window", "C"), "app_C": ("append", "C"), "led_C": ("ledger", "C")}
CORE = ("app_N", "led_N", "app_C", "led_C")


def extract_examples(text: str) -> list[dict]:
    examples = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith('{"action"'):
            examples.append(json.loads(line))
    return examples


# --------------------------------------------------------------------------- #
# BASE_SYSTEM
# --------------------------------------------------------------------------- #
def test_base_system_is_identical_for_every_arm():
    neutral = {arm: system_prompt("N") for arm in ARMS}
    costed = {arm: system_prompt("C") for arm in ARMS}
    assert len(set(neutral.values())) == 1
    assert len(set(costed.values())) == 1
    assert set(neutral.values()) == {BASE_SYSTEM}
    for arm in ARMS:
        assert costed[arm] == BASE_SYSTEM + "\n" + PROMPT_C
        assert costed[arm].endswith(PROMPT_C)
        assert neutral[arm] + "\n" + PROMPT_C == costed[arm]


def test_the_policy_suffix_is_verbatim():
    expected = ("DECISION GUIDANCE. Information you hold may be out of date because the roommate "
                "keeps moving items while you act. For each decision, weigh how old your evidence "
                "is and how likely the item has moved against what a mistake would cost and what "
                "checking costs (observe: 3 plus the moves needed; ask_human: 10, at most once). "
                "Trust fresh evidence; verify old evidence when a mistake would be expensive; skip "
                "checks that are not worth their price.")
    assert PROMPT_C == expected
    assert POLICY_SUFFIX == {"N": "", "C": PROMPT_C}


def test_no_illegal_example_in_the_base_system():
    assert "current_target" not in BASE_SYSTEM
    for example in extract_examples(BASE_SYSTEM):
        if example["action"] == "ask_human":
            assert len(named_items(example["question"])) == 1, example


def test_every_example_action_is_accepted_by_the_environment():
    examples = extract_examples(BASE_SYSTEM)
    assert examples, "BASE_SYSTEM must contain example actions"
    for example in examples:
        env = DynamicHouseEnv(0, 0.0)
        name = example["action"]
        if name == "move":
            out = env.step(example)                       # start room: LivingRoom
        elif name == "observe":
            out = env.step(example)
        elif name == "ask_human":
            out = env.step(example)                       # one ask is allowed
        elif name == "pick":
            env.current_room = env.locations[example["item"]]
            out = env.step(example)
        elif name == "place":
            env.current_room = env.locations[example["item"]]
            held = env.step({"action": "pick", "item": example["item"]})
            assert held["ok"], example
            out = env.step(example)
        else:
            raise AssertionError(name)
        assert out.get("failure_reason") != "invalid_action", example
        assert out["ok"], example


def test_base_system_states_the_rules_that_only_some_old_arms_knew():
    for high_risk in ("medicine_box", "scissors", "kitchen_knife", "hot_kettle",
                       "glass_cleaner", "razor"):
        assert high_risk in BASE_SYSTEM
    for item in ITEMS:
        assert item in BASE_SYSTEM
    assert "disturbance_p" in BASE_SYSTEM
    assert "at most ONCE" in BASE_SYSTEM
    assert "not moved again until you pick it up" in BASE_SYSTEM


# --------------------------------------------------------------------------- #
# user messages
# --------------------------------------------------------------------------- #
def _user_payloads(env, history):
    payloads = {}
    for arm, (representation, _) in ARMS.items():
        bundle = MemoryBundle(representation, env.inspection, env.inspection_gap)
        bundle.observe(1, "Kitchen", sorted(env.room_items["Kitchen"]))
        bundle.ask_human(2, "book", "Study")
        user = build_user_message(env, history, bundle.view(env.step_count))
        payloads[arm] = json.loads(user)
    return payloads


def test_user_messages_differ_only_in_the_memory_field():
    env = DynamicHouseEnv(1000, 0.2, n_targets=3)
    history = [{"step": 1, "action": {"action": "move", "room": "Kitchen"},
                "result": "Moved to Kitchen."}]
    payloads = _user_payloads(env, history)
    base = payloads["app_N"]
    for arm, payload in payloads.items():
        assert set(payload) == {"state", "recent_history", "memory"}
        assert payload["state"] == base["state"]
        assert payload["recent_history"] == base["recent_history"]
    # the memory view depends on R only, never on P
    assert payloads["app_N"]["memory"] == payloads["app_C"]["memory"]
    assert payloads["led_N"]["memory"] == payloads["led_C"]["memory"]
    assert payloads["win_N"]["memory"] == payloads["win_C"]["memory"] == []
    assert payloads["app_N"]["memory"] != payloads["led_N"]["memory"]
    assert payloads["app_N"]["memory"] != payloads["win_N"]["memory"]


def test_recent_history_holds_the_last_four_steps_only():
    env = DynamicHouseEnv(1000, 0.2)
    history = [{"step": i, "action": {"action": "observe"}, "result": f"Observed {i}."}
               for i in range(1, 9)]
    bundle = MemoryBundle("append", env.inspection, env.inspection_gap)
    payload = json.loads(build_user_message(env, history, bundle.view(0)))
    assert len(payload["recent_history"]) == 4
    assert payload["recent_history"][0]["step"] == 5
    assert payload["recent_history"][-1]["step"] == 8
    assert set(payload["recent_history"][0]) == {"step", "action", "result"}


# --------------------------------------------------------------------------- #
# end-to-end: the same episode under all six arms
# --------------------------------------------------------------------------- #
class StubClient:
    """Records every prompt and always answers with the same valid action."""

    def __init__(self, action=None):
        self.calls: list[tuple[str, str]] = []
        self.action = action or {"action": "observe"}

    def complete(self, model, system, user):
        self.calls.append((system, user))
        return json.dumps(self.action), {"latency_ms": 1, "input_tokens": 1, "output_tokens": 1,
                                         "total_tokens": 2, "http_status": 200, "request_retries": 0}


def test_over_a_whole_episode_the_arms_differ_only_in_r_and_p():
    transcripts = {}
    for arm, (representation, policy_prompt) in ARMS.items():
        env = DynamicHouseEnv(1000, 0.2, n_targets=3)
        client = StubClient()
        agent = ArmAgent(env, client, "stub", representation, policy_prompt)
        agent.run()
        transcripts[arm] = client.calls
    lengths = {arm: len(calls) for arm, calls in transcripts.items()}
    assert len(set(lengths.values())) == 1, lengths
    for index in range(next(iter(lengths.values()))):
        systems = {arm: transcripts[arm][index][0] for arm in ARMS}
        assert len(set(systems.values())) == 2, "only the P suffix may differ"
        for arm in ARMS:
            expected = system_prompt(ARMS[arm][1])
            assert systems[arm] == expected
        users = {arm: json.loads(transcripts[arm][index][1]) for arm in ARMS}
        base = users["app_N"]
        for arm in ARMS:
            assert users[arm]["state"] == base["state"]
            assert users[arm]["recent_history"] == base["recent_history"]
            assert set(users[arm]) == {"state", "recent_history", "memory"}


@pytest.mark.parametrize("arm", ARMS)
def test_each_arm_produces_a_well_formed_prompt(arm):
    representation, policy_prompt = ARMS[arm]
    env = DynamicHouseEnv(1000, 0.2, n_targets=3)
    client = StubClient()
    agent = ArmAgent(env, client, "stub", representation, policy_prompt)
    agent.run()
    system, user = client.calls[0]
    payload = json.loads(user)
    assert system.startswith(BASE_SYSTEM)
    assert isinstance(payload["memory"], (list, dict))
    assert payload["state"]["task_state"]["current_room"] == "LivingRoom"
    assert set(payload["state"]) == {"task_state", "room_graph", "item_risk_levels", "instruction"}
