"""The deterministic controller of Probe 1b (harness-side gating).

What the controller may use
---------------------------
Only the public state, the item risk levels, and the agent's own visible
history -- its observations, the human's answers and its own actions -- plus
the ledger built from those.  It must never read ground truth: the items'
real locations, the roommate's internal state or the environment's RNG.  The
test suite proves this by turning every ground-truth attribute into a
sentinel that raises on access.

The gate rule (Probe 1b section 4.3), per ledger row, in order:

    1. believed_room is None                    -> "verify"   (location unknown)
    2. disturbance_p == 0                       -> "trust"    (static world)
    3. source == "ask_human" and not yet picked -> "trust"    (answers are frozen)
    4. high_risk                                -> "trust" iff age <= 1  else "verify"
    5. low_risk                                 -> "trust" iff age <= 20 else "verify"

`age` is the ledger view's `age` field (current step - last_verified_step).
The thresholds and the recommended action mirror `age_gate_reference.py`,
which is the executable definition of the rule.
"""
from __future__ import annotations

import collections
from typing import Any

from .env import GRAPH, ITEMS

TAU_LOW = 20
TAU_HIGH = 1

MODES = ("none", "advice", "shield", "both", "recommend")

# what each arm's controller actually does, and what it announces in the state
CONTROLLER_MODE = {
    "base": "none", "hint": "advice", "shield": "shield", "both": "both",
    "auto": "recommend", "base_old": "none",
}
ANNOUNCED = {
    "none": (), "advice": ("advice",), "shield": ("shield",),
    "both": ("advice", "shield"), "recommend": ("recommend",),
}


def bfs_path(graph, src: str, dst: str) -> list[str]:
    if src == dst:
        return []
    prev, queue = {src: None}, collections.deque([src])
    while queue:
        u = queue.popleft()
        for v in graph[u]:
            if v not in prev:
                prev[v] = u
                queue.append(v)
    path, cur = [], dst
    while cur != src:
        path.append(cur)
        cur = prev[cur]
    return path[::-1]


def advice_for(row: dict[str, Any] | None, risk: str, disturbance_p: float,
               held: bool) -> str:
    """The gate rule for one item, from its ledger row.  Pure function."""
    if row is None:
        return "verify"
    if row["believed_room"] is None:
        return "verify"
    if disturbance_p == 0:
        return "trust"
    if row["source"] == "ask_human" and not held:
        # The human's answer is frozen until the item is picked up: a public rule.
        return "trust"
    tau = TAU_HIGH if risk == "high_risk" else TAU_LOW
    return "trust" if row["age"] <= tau else "verify"


class Controller:
    """Deterministic gate over (public state, agent-visible history, ledger).

    Every query method is a pure function of its arguments; the instance only
    carries the agent-visible history that the harness feeds it.
    """

    def __init__(self, mode: str, ledger: Any, max_asks: int = 1):
        if mode not in MODES:
            raise ValueError(f"unknown controller mode {mode!r}; choose from {MODES}")
        self.mode = mode
        self.ledger = ledger
        self.max_asks = max_asks
        self.asked: dict[str, str] = {}      # item -> room the human answered
        self.seen_rooms: set[str] = set()
        self.asks_used = 0
        self.history: list[dict[str, Any]] = []

    # -- what the controller announces ------------------------------------ #
    @property
    def announces(self) -> list[str]:
        return list(ANNOUNCED.get(self.mode, ()))

    def shows_advice(self) -> bool:
        return "advice" in self.announces

    def blocks(self) -> bool:
        return "shield" in self.announces

    def recommends(self) -> bool:
        return "recommend" in self.announces

    # -- history bookkeeping (agent-visible only) --------------------------- #
    def update(self, action: dict[str, Any], outcome: dict[str, Any]) -> None:
        """Fold one executed action into the controller's visible history."""
        observation = outcome.get("observation")
        if observation:
            self.seen_rooms.add(observation["room"])
        if action["action"] == "ask_human" and outcome.get("answer"):
            self.asked[outcome["item"]] = outcome["location"]
            self.asks_used += 1
        self.history.append({"step": outcome["step"], "action": action,
                             "result": outcome["message"], "observation": observation})

    # -- advice ------------------------------------------------------------ #
    def advice_map(self, ledger_view: dict[str, dict[str, Any]],
                   public_state: dict[str, Any]) -> dict[str, str]:
        """Per-item "trust"/"verify", from the ledger view only."""
        p = public_state["disturbance_p"]
        held = set(public_state.get("held_items", []))
        return {item: advice_for(row, ITEMS.get(item, "low_risk"), p, item in held)
                for item, row in ledger_view.items()}

    # -- shield ------------------------------------------------------------ #
    def block_reason(self, action: dict[str, Any], ledger_view: dict[str, dict[str, Any]],
                     public_state: dict[str, Any]) -> str | None:
        """Why this action is blocked, or None.  Only high-risk grasps can be."""
        if not self.blocks():
            return None
        if action.get("action") != "pick":
            return None
        item = action.get("item")
        risk = ITEMS.get(item)
        if risk != "high_risk":
            return None
        held = set(public_state.get("held_items", []))
        row = ledger_view.get(item)
        verdict = advice_for(row, risk, public_state["disturbance_p"], item in held)
        if verdict != "verify":
            return None
        age = row["age"] if row else "?"
        return (f"evidence for {item} is stale (age {age}). "
                f"Verify first (observe in its room, or ask_human).")

    # -- recommendation ----------------------------------------------------- #
    def recommend(self, ledger_view: dict[str, dict[str, Any]],
                  public_state: dict[str, Any]) -> dict[str, Any] | None:
        """The action the controller would take, mirroring age_gate_reference.py."""
        subgoal = public_state.get("current_subgoal")
        if not subgoal:
            return None
        item, target_room = subgoal["item"], subgoal["room"]
        risk = ITEMS[item]
        held = list(public_state.get("held_items", []))
        if item in held:
            return {"action": "place", "item": item, "room": target_room}
        here = public_state["current_room"]
        graph = GRAPH
        last = self.history[-1] if self.history else None
        just_observed = bool(last and last["action"]["action"] == "observe")
        seen_here_now = bool(just_observed and last.get("observation")
                             and item in last["observation"]["items"])
        row = ledger_view.get(item)
        believed = row["believed_room"] if row else None

        def go_or(act: dict[str, Any], dst: str) -> dict[str, Any]:
            return act if here == dst else self._move_to(graph, here, dst)

        if item in self.asked:
            return go_or({"action": "pick", "item": item}, self.asked[item])
        if seen_here_now:
            return {"action": "pick", "item": item}
        if advice_for(row, risk, public_state["disturbance_p"], item in held) == "trust":
            return go_or({"action": "pick", "item": item}, believed)
        # verify branch
        if (risk == "high_risk" or believed is None) and self.asks_used < self.max_asks:
            return {"action": "ask_human", "question": f"Where is the {item}?"}
        if believed is not None and here != believed:
            return self._move_to(graph, here, believed)
        if just_observed:
            return self._move_to(graph, here, self._next_unseen_room(graph, here))
        return {"action": "observe"}

    # -- helpers ------------------------------------------------------------ #
    @staticmethod
    def _move_to(graph, src: str, dst: str) -> dict[str, Any]:
        return {"action": "move", "room": bfs_path(graph, src, dst)[0]}

    def _next_unseen_room(self, graph, here: str) -> str:
        rooms = [r for r in graph if r != here and r not in self.seen_rooms]
        if not rooms:
            self.seen_rooms = {here}
            rooms = [r for r in graph if r != here]
        rooms.sort(key=lambda r: len(bfs_path(graph, here, r)))
        return rooms[0]
