"""Scripted (zero-LLM) reference policies, ported to run directly on `dynhouse.env`.

These are the environment-version reference lines: the experiment's environment
is selected by what trivial programs can achieve here, NOT by what the LLM
arms score.  The policies are the ones from `scripted_baselines.py`, but they
drive the real `DynamicHouseEnv` class instead of a text-patched copy.

    trust_memory  newest sighting, go there, pick; never verify, never ask
    observe_pick  go to believed room, observe, pick only if seen; never ask
    ask_fetch     ask the human for each target, walk there, pick (falls back to
                  observe_pick when the ask is rejected)
    ledger_gate   p=0: trust memory; p>0: ask for high_risk / unknown targets,
                  observe-then-pick for the others
"""
from __future__ import annotations

import collections
import statistics
from typing import Any

from .env import GRAPH, ITEMS, DynamicHouseEnv

POLICIES = ("trust_memory", "observe_pick", "ask_fetch", "ledger_gate")


def bfs_path(graph, src, dst):
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


class ScriptedMemory:
    """What the scripted agent knows: initial inspection + its own observations."""

    def __init__(self, env):
        self.belief: dict[str, str | None] = {}
        self.seen_rooms: set[str] = set()
        self.asked: dict[str, str] = {}
        self.ask_failed: set[str] = set()
        self.last: tuple[dict[str, Any], dict[str, Any]] | None = None
        self.pending_ask: str | None = None
        for room, items in env.inspection.items():
            for it in items:
                self.belief[it] = room

    def update(self, action, out):
        kind = action["action"]
        if out.get("observation"):
            obs = out["observation"]
            room, items = obs["room"], set(obs["items"])
            for it in list(self.belief):
                if self.belief[it] == room and it not in items:
                    self.belief[it] = None
            for it in items:
                self.belief[it] = room
            self.seen_rooms.add(room)
        if kind == "ask_human":
            if out["ok"] and out.get("location"):
                self.asked[out["item"]] = out["location"]
                self.belief[out["item"]] = out["location"]
            else:
                self.ask_failed.add(self.pending_ask)
        if kind == "pick" and not out["ok"]:
            self.belief[action["item"]] = None
        self.last = (action, out)


def make_policy(name, graph, items):
    def next_unseen_room(env, mem):
        rooms = [r for r in graph if r != env.current_room and r not in mem.seen_rooms]
        if not rooms:
            mem.seen_rooms = {env.current_room}
            rooms = [r for r in graph if r != env.current_room]
        rooms.sort(key=lambda r: len(bfs_path(graph, env.current_room, r)))
        return rooms[0]

    def move_to(env, dst):
        return {"action": "move", "room": bfs_path(graph, env.current_room, dst)[0]}

    def policy(env, mem):
        target = env.current_target
        item, target_room = target["item"], target["room"]
        risk = items[item]
        if item in env.held:
            return {"action": "place", "item": item, "room": target_room}
        here, last = env.current_room, mem.last
        just_observed = bool(last and last[0]["action"] == "observe")
        seen_here_now = bool(just_observed and last[1].get("observation")
                             and item in last[1]["observation"]["items"])
        believed = mem.belief.get(item)

        def go_or(act, dst):
            return act if here == dst else move_to(env, dst)

        def observe_then_pick():
            if seen_here_now:
                return {"action": "pick", "item": item}
            if believed is not None and here != believed:
                return move_to(env, believed)
            if just_observed:
                return move_to(env, next_unseen_room(env, mem))
            return {"action": "observe"}

        if name == "trust_memory":
            if believed is None:
                if seen_here_now:
                    return {"action": "pick", "item": item}
                if just_observed or here in mem.seen_rooms:
                    return move_to(env, next_unseen_room(env, mem))
                return {"action": "observe"}
            return go_or({"action": "pick", "item": item}, believed)
        if name == "observe_pick":
            return observe_then_pick()
        if name == "ask_fetch":
            if item in mem.asked:
                return go_or({"action": "pick", "item": item}, mem.asked[item])
            if item not in mem.ask_failed:
                mem.pending_ask = item
                return {"action": "ask_human", "question": f"Where is the {item}?"}
            return observe_then_pick()
        if name == "ledger_gate":
            if item in mem.asked:
                return go_or({"action": "pick", "item": item}, mem.asked[item])
            p = env.disturbance_p
            if p == 0:
                return go_or({"action": "pick", "item": item}, believed) if believed else {"action": "observe"}
            if (risk == "high_risk" or believed is None) and item not in mem.ask_failed:
                mem.pending_ask = item
                return {"action": "ask_human", "question": f"Where is the {item}?"}
            return observe_then_pick()
        raise ValueError(name)

    return policy


def run_episode(policy_name: str, seed: int, p: float, *, max_asks: int = 1,
                freeze_asked: bool = True, n_targets: int | None = None) -> dict[str, Any]:
    env = DynamicHouseEnv(seed, p, n_targets=n_targets if n_targets is not None else 2 + seed % 2,
                          max_asks=max_asks, freeze_asked=freeze_asked)
    mem, policy = ScriptedMemory(env), make_policy(policy_name, GRAPH, ITEMS)
    for _ in range(200):
        if env.done:
            break
        action = policy(env, mem)
        try:
            out = env.step(action)
        except (ValueError, RuntimeError):
            break
        mem.update(action, out)
    return env.episode_summary()


def evaluate(policy_name: str, seeds, p: float, *, max_asks: int = 1,
             freeze_asked: bool = True) -> dict[str, float]:
    runs = [run_episode(policy_name, s, p, max_asks=max_asks, freeze_asked=freeze_asked)
            for s in seeds]
    n = len(runs)
    return {
        "success": 100 * sum(r["success"] for r in runs) / n,
        "cost": statistics.mean(r["total_cost"] for r in runs),
        "unsafe": 100 * sum(r["safety_count"] > 0 for r in runs) / n,
        "asks": statistics.mean(r["ask_count"] for r in runs),
        "n": n,
    }
