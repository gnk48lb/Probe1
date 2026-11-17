"""Environment tests: matching, determinism, ask cap, no ground-truth leakage."""
from __future__ import annotations

import json
import re

import pytest

from dynhouse.env import (INITIAL_LAYOUT, ITEMS, ROOMS, DynamicHouseEnv, named_items)


# --------------------------------------------------------------------------- #
# (a) whole-word item matching
# --------------------------------------------------------------------------- #
def test_every_item_name_can_be_asked():
    for item in ITEMS:
        env = DynamicHouseEnv(0, 0.0)
        out = env.step({"action": "ask_human", "question": f"Where is the {item}?"})
        assert out["ok"], item
        assert out["item"] == item


def test_space_and_underscore_are_interchangeable():
    assert named_items("Where is the coffee mug?") == ["coffee_mug"]
    assert named_items("Where is the coffee_mug?") == ["coffee_mug"]
    assert named_items("Where is the COFFEE_MUG?") == ["coffee_mug"]


def test_notebook_does_not_match_book():
    assert named_items("Where is the notebook?") == ["notebook"]
    assert named_items("Where is the book?") == ["book"]
    assert named_items("Where is the notebook and the book?") == ["book", "notebook"]


def test_question_naming_two_items_is_invalid():
    env = DynamicHouseEnv(0, 0.0)
    out = env.step({"action": "ask_human", "question": "Where is the book or the notebook?"})
    assert not out["ok"]
    assert out["failure_reason"] == "invalid_action"
    assert env.ask_count == 0


def test_ask_returns_the_named_items_own_location():
    env = DynamicHouseEnv(0, 0.0)
    out = env.step({"action": "ask_human", "question": "Where is the notebook?"})
    assert out["item"] == "notebook"
    assert out["location"] == env.locations["notebook"]
    assert out["location"] != env.locations["book"]


# --------------------------------------------------------------------------- #
# determinism
# --------------------------------------------------------------------------- #
def test_same_seed_and_p_are_fully_deterministic():
    actions = [{"action": "move", "room": "Kitchen"}, {"action": "observe"},
               {"action": "pick", "item": "coffee_mug"}, {"action": "place", "item": "coffee_mug", "room": "Study"}]
    runs = []
    for _ in range(2):
        env = DynamicHouseEnv(37, 0.4)
        outcomes = []
        for action in actions:
            outcomes.append(env.step(dict(action)))
        runs.append((env.episode_summary(), outcomes))
    assert runs[0][0]["events"] == runs[0][0]["events"]
    assert json.dumps(runs[0][0], sort_keys=True) == json.dumps(runs[1][0], sort_keys=True)
    assert [o["message"] for o in runs[0][1]] == [o["message"] for o in runs[1][1]]


def test_p_zero_never_moves_an_item():
    for seed in range(30):
        env = DynamicHouseEnv(seed, 0.0)
        for _ in range(6):
            env.step({"action": "observe"})
            env.step({"action": "move", "room": ROOMS[0] if env.current_room != "LivingRoom" else "Kitchen"})
        for room, items in INITIAL_LAYOUT.items():
            assert sorted(env.room_items[room]) == sorted(items)


# --------------------------------------------------------------------------- #
# public state carries no ground truth
# --------------------------------------------------------------------------- #
def test_public_state_contains_no_ground_truth():
    env = DynamicHouseEnv(3, 0.4)
    env.step({"action": "move", "room": "Kitchen"})
    state = env.public_state()
    blob = json.dumps(state)
    assert "locations" not in state
    assert "room_items" not in state
    assert "ground_truth" not in blob
    mentioned = {item for item in ITEMS
                 if re.search(r"(?<![a-z0-9_])" + item.replace("_", "[ _]") + r"(?![a-z0-9_])", blob.lower())}
    allowed = ({t["item"] for t in state["targets"]} | set(state["held_items"])
               | set(state["completed_items"]))
    assert mentioned <= allowed


# --------------------------------------------------------------------------- #
# (b) max_asks semantics
# --------------------------------------------------------------------------- #
def test_second_valid_ask_is_rejected():
    env = DynamicHouseEnv(0, 0.0)
    first = env.step({"action": "ask_human", "question": "Where is the book?"})
    assert first["ok"]
    assert env.ask_count == 1
    budget_before = env.budget
    second = env.step({"action": "ask_human", "question": "Where is the notebook?"})
    assert not second["ok"]
    assert second["message"] == "INVALID: ask limit reached."
    assert second["cost"] == 0
    assert env.budget == budget_before
    assert env.step_count == 2
    assert env.ask_count == 1


def test_invalid_question_does_not_consume_the_ask_budget():
    env = DynamicHouseEnv(0, 0.0)
    bad = env.step({"action": "ask_human", "question": "Where is it?"})
    assert not bad["ok"]
    assert env.ask_count == 0
    good = env.step({"action": "ask_human", "question": "Where is the book?"})
    assert good["ok"]
    assert env.ask_count == 1


def test_max_asks_zero_rejects_every_ask():
    env = DynamicHouseEnv(0, 0.0, max_asks=0)
    out = env.step({"action": "ask_human", "question": "Where is the book?"})
    assert not out["ok"]
    assert out["message"] == "INVALID: ask limit reached."
    assert env.ask_count == 0


def test_asked_item_is_frozen_until_picked_up():
    env = DynamicHouseEnv(11, 0.4)
    asked = env.current_target["item"]
    env.step({"action": "ask_human", "question": f"Where is the {asked}?"})
    location = env.locations[asked]
    for _ in range(10):
        env.step({"action": "observe"})
    assert env.locations[asked] == location


def test_nofreeze_variant_does_not_freeze():
    env = DynamicHouseEnv(11, 0.4, freeze_asked=False)
    asked = env.current_target["item"]
    env.step({"action": "ask_human", "question": f"Where is the {asked}?"})
    assert asked not in env.asked_items


# --------------------------------------------------------------------------- #
# staleness of the opening inspection memory
# --------------------------------------------------------------------------- #
def _first_target_stale_fraction(p: float, seeds: int = 1000) -> float:
    stale = 0
    for seed in range(seeds):
        env = DynamicHouseEnv(seed, p, n_targets=2 + seed % 2)
        item = env.targets[0]["item"]
        inspected_room = next(room for room, items in env.inspection.items() if item in items)
        if env.locations[item] != inspected_room:
            stale += 1
    return stale / seeds


def test_opening_inspection_is_already_stale_at_the_stated_rates():
    assert 0.40 <= _first_target_stale_fraction(0.2) <= 0.60
    assert 0.60 <= _first_target_stale_fraction(0.4) <= 0.80


def test_opening_inspection_is_never_stale_when_p_is_zero():
    assert _first_target_stale_fraction(0.0) == 0.0


def test_environment_constants_are_unchanged():
    assert len(ITEMS) == 18
    assert sum(1 for v in ITEMS.values() if v == "high_risk") == 6
    assert len(ROOMS) == 5
    env = DynamicHouseEnv(0, 0.0)
    assert env.budget == 60
    assert env.max_steps == 30
    assert env.inspection_gap == 8
