"""Memory representations (the R switch) and the harness-side evidence tracker.

Three representations, all built deterministically by code -- never extracted
by the LLM:

* ``window``  no long-term memory at all (``[]``); the agent also never sees
  the opening inspection.
* ``append``  chronological, append-only raw records: the 5 inspection
  records, one per observe, one per answered ask_human, one per failed pick.
* ``ledger``  one row per item holding the current belief, its age and how
  often it was superseded.  The update rules follow
  `_ref/gate_dynamic_house/ledger.py`.

The ledger is a *lossy summary of the append log*: `ledger_from_records`
rebuilds it from the append records alone, which is what the information
equivalence test checks.
"""
from __future__ import annotations

from typing import Any

INSPECTION_SOURCE = "inspection"
OBSERVE_SOURCE = "observe"
ABSENCE_SOURCE = "observe_absence"
ASK_SOURCE = "ask_human"
PICK_FAILED_SOURCE = "pick_failed"

REPRESENTATIONS = ("window", "append", "ledger")
POLICY_PROMPTS = ("N", "C")


class AppendMemory:
    """Chronological, append-only raw records."""

    def __init__(self, inspection: dict[str, list[str]], inspection_gap: int):
        self.records: list[dict[str, Any]] = [
            {"step": -inspection_gap, "room": room, "items": list(items)}
            for room, items in inspection.items()
        ]

    def observe(self, step: int, room: str, items: list[str]) -> None:
        self.records.append({"step": step, "room": room, "items": list(items)})

    def ask_human(self, step: int, item: str, location: str) -> None:
        self.records.append({"step": step, "human_answer": {"item": item, "location": location}})

    def pick_failed(self, step: int, item: str, room: str) -> None:
        self.records.append({"step": step, "pick_failed": {"item": item, "room": room}})

    def view(self) -> list[dict[str, Any]]:
        return self.records


class LedgerMemory:
    """One row per item: current belief, age, source, superseded count."""

    def __init__(self, inspection: dict[str, list[str]], inspection_gap: int):
        self.rows: dict[str, dict[str, Any]] = {}
        for room, items in inspection.items():
            for item in items:
                self.rows[item] = {
                    "believed_room": room,
                    "last_verified_step": -inspection_gap,
                    "source": INSPECTION_SOURCE,
                    "history": [],           # loc of every superseded version
                }

    # -- update rules ------------------------------------------------------ #
    def _write(self, item: str, room: str | None, step: int, source: str) -> None:
        row = self.rows.get(item)
        if row is None:
            # An item the inspection never covered: we know nothing about it.
            self.rows[item] = {"believed_room": room, "last_verified_step": step,
                                "source": source, "history": []}
            return
        row["history"].append(row["believed_room"])
        row["believed_room"] = room
        row["last_verified_step"] = step
        row["source"] = source

    def observe(self, step: int, room: str, items: list[str]) -> None:
        seen = set(items)
        for item in items:
            row = self.rows.get(item)
            if row is None:
                self._write(item, room, step, OBSERVE_SOURCE)
            elif row["believed_room"] != room:
                # A positive sighting supersedes the older location.
                self._write(item, room, step, OBSERVE_SOURCE)
            else:
                # Same room: refresh the evidence in place, nothing superseded.
                row["last_verified_step"] = step
                row["source"] = OBSERVE_SOURCE
        for item, row in self.rows.items():
            if row["believed_room"] == room and item not in seen:
                # Believed here, not here now: the location is unknown.
                self._write(item, None, step, ABSENCE_SOURCE)

    def ask_human(self, step: int, item: str, location: str) -> None:
        self._write(item, location, step, ASK_SOURCE)

    def pick_failed(self, step: int, item: str, room: str) -> None:
        self._write(item, None, step, PICK_FAILED_SOURCE)

    # -- prompt view ------------------------------------------------------- #
    def view(self, current_step: int) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        for item, row in self.rows.items():
            entry: dict[str, Any] = {
                "item": item,
                "believed_room": row["believed_room"],
                "last_verified_step": row["last_verified_step"],
                "age": current_step - row["last_verified_step"],
                "source": row["source"],
                "superseded_count": len(row["history"]),
            }
            if row["believed_room"] is None and row["history"]:
                last_seen = row["history"][-1]
                if last_seen is not None:
                    entry["last_room"] = last_seen
            out[item] = entry
        return out


class EvidenceTracker:
    """Harness-side record of how old the agent's evidence was at each pick.

    Written for every arm, but never shown to the model: it is the mechanism
    analysis instrument, not part of any prompt.
    """

    def __init__(self, inspection_gap: int):
        self.confirmed_at: dict[str, int] = {}
        self.inspection_gap = inspection_gap

    def seed_from_inspection(self, inspection: dict[str, list[str]]) -> None:
        for items in inspection.values():
            for item in items:
                self.confirmed_at[item] = -self.inspection_gap

    def confirm(self, item: str, step: int) -> None:
        self.confirmed_at[item] = step

    def age(self, item: str, step: int) -> int | None:
        if item not in self.confirmed_at:
            return None
        return step - self.confirmed_at[item]


def ledger_from_records(records: list[dict[str, Any]], current_step: int) -> dict[str, dict[str, Any]]:
    """Rebuild the ledger view from the append log alone.

    Used by the information-equivalence test: every ledger field must be
    derivable from the append records, i.e. the ledger never carries more
    information than the raw log.
    """
    ledger: dict[str, dict[str, Any]] = {}
    for record in records:
        step = record.get("step", 0)
        if "human_answer" in record:
            answer = record["human_answer"]
            item = answer["item"]
            row = ledger.get(item)
            if row is None:
                ledger[item] = {"believed_room": answer["location"], "last_verified_step": step,
                                 "source": ASK_SOURCE, "history": []}
            else:
                row["history"].append(row["believed_room"])
                row["believed_room"] = answer["location"]
                row["last_verified_step"] = step
                row["source"] = ASK_SOURCE
        elif "pick_failed" in record:
            failed = record["pick_failed"]
            item = failed["item"]
            row = ledger.get(item)
            if row is None:
                ledger[item] = {"believed_room": None, "last_verified_step": step,
                                 "source": PICK_FAILED_SOURCE, "history": []}
            else:
                row["history"].append(row["believed_room"])
                row["believed_room"] = None
                row["last_verified_step"] = step
                row["source"] = PICK_FAILED_SOURCE
        elif "items" in record:
            room = record["room"]
            if step < 0:
                for item in record["items"]:
                    ledger[item] = {"believed_room": room, "last_verified_step": step,
                                     "source": INSPECTION_SOURCE, "history": []}
                continue
            seen = set(record["items"])
            for item in record["items"]:
                row = ledger.get(item)
                if row is None:
                    ledger[item] = {"believed_room": room, "last_verified_step": step,
                                     "source": OBSERVE_SOURCE, "history": []}
                    continue
                if row["believed_room"] != room:
                    row["history"].append(row["believed_room"])
                    row["believed_room"] = room
                    row["last_verified_step"] = step
                    row["source"] = OBSERVE_SOURCE
                else:
                    row["last_verified_step"] = step
                    row["source"] = OBSERVE_SOURCE
            for item, row in ledger.items():
                if row["believed_room"] == room and item not in seen:
                    row["history"].append(row["believed_room"])
                    row["believed_room"] = None
                    row["last_verified_step"] = step
                    row["source"] = ABSENCE_SOURCE
    view: dict[str, dict[str, Any]] = {}
    for item, row in ledger.items():
        entry: dict[str, Any] = {
            "item": item,
            "believed_room": row["believed_room"],
            "last_verified_step": row["last_verified_step"],
            "age": current_step - row["last_verified_step"],
            "source": row["source"],
            "superseded_count": len(row["history"]),
        }
        if row["believed_room"] is None and row["history"]:
            last_seen = row["history"][-1]
            if last_seen is not None:
                entry["last_room"] = last_seen
        view[item] = entry
    return view


class MemoryBundle:
    """The arm's memory plus the harness-side evidence tracker."""

    def __init__(self, representation: str, inspection: dict[str, list[str]], inspection_gap: int):
        self.representation = representation
        self.append = AppendMemory(inspection, inspection_gap)
        self.ledger = LedgerMemory(inspection, inspection_gap)
        self.evidence = EvidenceTracker(inspection_gap)
        self.evidence.seed_from_inspection(inspection)

    def view(self, current_step: int) -> Any:
        if self.representation == "window":
            return []
        if self.representation == "append":
            return self.append.view()
        return self.ledger.view(current_step)

    def observe(self, step: int, room: str, items: list[str]) -> None:
        self.append.observe(step, room, items)
        self.ledger.observe(step, room, items)
        for item in items:
            self.evidence.confirm(item, step)

    def ask_human(self, step: int, item: str, location: str) -> None:
        self.append.ask_human(step, item, location)
        self.ledger.ask_human(step, item, location)
        self.evidence.confirm(item, step)

    def pick_failed(self, step: int, item: str, room: str) -> None:
        self.append.pick_failed(step, item, room)
        self.ledger.pick_failed(step, item, room)

    def pick_succeeded(self, step: int, item: str) -> None:
        # A grasp confirms the item was in this room at this step.
        self.evidence.confirm(item, step)
