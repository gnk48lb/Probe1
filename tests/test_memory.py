"""Information equivalence: the ledger may never carry more than the append log."""
from __future__ import annotations

import json
import random
import re

from dynhouse.env import ITEMS, ROOMS, DynamicHouseEnv
from dynhouse.memory import (ABSENCE_SOURCE, ASK_SOURCE, INSPECTION_SOURCE, OBSERVE_SOURCE,
                             PICK_FAILED_SOURCE, AppendMemory, EvidenceTracker, LedgerMemory,
                             MemoryBundle, ledger_from_records)


def _random_event_stream(rng: random.Random, length: int):
    """A random sequence of events that the environment could have produced."""
    events = []
    for step in range(1, length + 1):
        roll = rng.random()
        if roll < 0.5:
            room = rng.choice(ROOMS)
            items = sorted(rng.sample(sorted(ITEMS), rng.randint(0, 6)))
            events.append(("observe", step, room, items))
        elif roll < 0.8:
            item = rng.choice(sorted(ITEMS))
            location = rng.choice(ROOMS)
            events.append(("ask", step, item, location))
        else:
            item = rng.choice(sorted(ITEMS))
            room = rng.choice(ROOMS)
            events.append(("pick_failed", step, item, room))
    return events


def test_ledger_is_recomputable_from_the_append_log():
    """200+ random event streams: every ledger field must follow from the append log."""
    rng = random.Random(20261117)
    for trial in range(200):
        inspection_gap = 8
        # a realistic inspection: all 18 items, spread over the 5 rooms
        shuffled = sorted(ITEMS)
        rng.shuffle(shuffled)
        inspection = {room: sorted(shuffled[i::5]) for i, room in enumerate(ROOMS)}
        append, ledger = AppendMemory(inspection, inspection_gap), LedgerMemory(inspection, inspection_gap)
        events = _random_event_stream(rng, rng.randint(1, 25))
        for event in events:
            kind = event[0]
            if kind == "observe":
                _, step, room, items = event
                append.observe(step, room, items)
                ledger.observe(step, room, items)
            elif kind == "ask":
                _, step, item, location = event
                append.ask_human(step, item, location)
                ledger.ask_human(step, item, location)
            else:
                _, step, item, room = event
                append.pick_failed(step, item, room)
                ledger.pick_failed(step, item, room)
        current_step = events[-1][1] if events else 0
        rebuilt = ledger_from_records(append.view(), current_step)
        assert rebuilt == ledger.view(current_step), trial


def test_ledger_sources_are_from_the_allowed_set():
    allowed = {INSPECTION_SOURCE, OBSERVE_SOURCE, ABSENCE_SOURCE, ASK_SOURCE, PICK_FAILED_SOURCE}
    rng = random.Random(7)
    for _ in range(50):
        inspection = {room: sorted(rng.sample(sorted(ITEMS), 3)) for room in ROOMS}
        ledger = LedgerMemory(inspection, 8)
        for event in _random_event_stream(rng, 20):
            kind = event[0]
            if kind == "observe":
                ledger.observe(event[1], event[2], event[3])
            elif kind == "ask":
                ledger.ask_human(event[1], event[2], event[3])
            else:
                ledger.pick_failed(event[1], event[2], event[3])
        for row in ledger.view(20).values():
            assert row["source"] in allowed


def test_ledger_row_fields_match_the_specified_shape():
    env = DynamicHouseEnv(0, 0.0)
    ledger = LedgerMemory(env.inspection, env.inspection_gap)
    view = ledger.view(0)
    assert set(view) == set(ITEMS)
    for item, row in view.items():
        assert set(row) == {"item", "believed_room", "last_verified_step", "age", "source",
                            "superseded_count"}
        assert row["item"] == item
        assert row["believed_room"] in ROOMS
        assert row["last_verified_step"] == -8
        assert row["age"] == 8
        assert row["source"] == INSPECTION_SOURCE
        assert row["superseded_count"] == 0


def test_last_room_only_appears_when_the_belief_is_null():
    env = DynamicHouseEnv(0, 0.0)
    ledger = LedgerMemory(env.inspection, env.inspection_gap)
    ledger.observe(1, "Kitchen", [])          # everything believed in Kitchen is now absent
    view = ledger.view(1)
    for item, row in view.items():
        if row["believed_room"] is None:
            assert row["last_room"] == "Kitchen"
        else:
            assert "last_room" not in row


def test_append_log_shape_matches_the_specification():
    env = DynamicHouseEnv(0, 0.0)
    append = AppendMemory(env.inspection, env.inspection_gap)
    assert len(append.view()) == 5
    for record in append.view():
        assert record["step"] == -8
        assert set(record) == {"step", "room", "items"}
    append.observe(3, "Kitchen", ["coffee_mug", "frying_pan"])
    assert append.view()[-1] == {"step": 3, "room": "Kitchen", "items": ["coffee_mug", "frying_pan"]}
    append.ask_human(4, "book", "Study")
    assert append.view()[-1] == {"step": 4, "human_answer": {"item": "book", "location": "Study"}}
    append.pick_failed(5, "book", "Kitchen")
    assert append.view()[-1] == {"step": 5, "pick_failed": {"item": "book", "room": "Kitchen"}}


def test_append_log_carries_no_commentary():
    env = DynamicHouseEnv(0, 0.0)
    append = AppendMemory(env.inspection, env.inspection_gap)
    blob = json.dumps(append.view(), ensure_ascii=False)
    for banned in ("stale", "out of date", "outdated", "old", "invalid", "expired"):
        assert banned not in blob.lower()


def test_window_memory_is_empty():
    env = DynamicHouseEnv(0, 0.0)
    bundle = MemoryBundle("window", env.inspection, env.inspection_gap)
    bundle.observe(1, "Kitchen", ["coffee_mug"])
    bundle.ask_human(2, "book", "Study")
    assert bundle.view(env.step_count) == []


def test_ledger_holds_beliefs_not_the_ground_truth():
    """The ledger stores what the agent was told, not where things really are."""
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
    ledger = LedgerMemory(env.inspection, env.inspection_gap)
    row = ledger.view(0)[item]
    assert row["believed_room"] == inspected            # the belief it was given
    assert row["believed_room"] != env.locations[item]  # not the truth


def test_evidence_tracker_records_the_age_of_the_last_confirmation():
    env = DynamicHouseEnv(0, 0.0)
    tracker = EvidenceTracker(env.inspection_gap)
    tracker.seed_from_inspection(env.inspection)
    assert tracker.age("book", 0) == 8          # the inspection is 8 steps old
    tracker.confirm("book", 3)
    assert tracker.age("book", 3) == 0
    assert tracker.age("book", 7) == 4
