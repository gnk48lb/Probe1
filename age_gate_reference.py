#!/usr/bin/env python3
"""Independent reference implementation of the Probe 1b GATE RULE (scripted, no LLM).

This file is the executable definition of the controller rule.  It is deliberately
self-contained (stdlib only) and never edits your env.py: it reads the source text,
patches ONE validation line in memory (so that p = 0.1 is accepted), and executes
the patched copy.

Usage (from the repo root):
    python age_gate_reference.py src/dynhouse/env.py
    python age_gate_reference.py src/dynhouse/env.py --seeds 0:1000 --seeds 3000:3100 --ps 0 0.1 0.2 0.4

THE RULE  (p-aware age gate; tau_low = 20, tau_high = 1)
--------------------------------------------------------
advice(item)  -- computed from the agent's own ledger, never from ground truth
    if believed_room is None                      -> "verify"         (location unknown)
    if disturbance_p == 0                         -> "trust"          (static world)
    if source == "ask_human" and not yet picked  -> "trust"          (answers are frozen: public rule)
    if risk == high_risk                          -> "trust" iff age <= 1  else "verify"
    if risk == low_risk                           -> "trust" iff age <= 20 else "verify"
  where age = (steps taken so far) - (step at which the belief was last confirmed);
  the opening inspection counts as confirmed at step -inspection_gap.

recommended action for the CURRENT target t (this is what the "auto" arm is told):
    held                                          -> place at the target room
    t was answered by the human (frozen)          -> go to the answered room, pick
    t was just observed in the current room       -> pick
    advice(t) == "trust"                          -> go to the believed room, pick
    else (verify):
        if (high_risk or location unknown) and asks_remaining > 0 -> ask_human("Where is the t?")
        elif believed room known and not there    -> move toward it
        elif the last action was an observe       -> move to the nearest room not yet observed
        else                                      -> observe

Reference numbers produced by this file (env: max_asks=1, freeze_asked=True,
n_targets = 2 + seed % 2):
    p     seeds 0-999: SR%  cost   |  seeds 3000-3099: SR%  cost
    0.0        100.0   11.8        |        100.0   11.8
    0.1         87.7   32.8        |         90.0   32.7
    0.2         75.3   39.3        |         72.0   38.5
    0.4         55.8   44.0        |         54.0   43.8
"""
from __future__ import annotations

import argparse
import collections
import statistics
import sys
import types

TAU_LOW = 20
TAU_HIGH = 1


def load_env(path: str):
    src = open(path, encoding="utf-8").read()
    old = "if self.disturbance_p not in (0.0, 0.2, 0.4):"
    if old in src:
        src = src.replace(old, "if not 0.0 <= self.disturbance_p <= 1.0:")
    mod = types.ModuleType("env_ref")
    mod.__dict__["__name__"] = mod.__name__
    sys.modules[mod.__name__] = mod          # dataclasses needs the module registered
    exec(compile(src, "<env>", "exec"), mod.__dict__)
    return mod


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


class Ledger:
    """What the agent knows: the opening inspection, its own observations, the human's answer."""

    def __init__(self, env):
        self.env = env
        self.belief = {}                 # item -> room or None
        self.confirmed = {}              # item -> step of last confirmation
        self.source = {}                 # item -> "inspection" | "observe" | "ask_human" | ...
        self.seen_rooms = set()
        self.asked = {}                  # item -> room (human answers)
        self.asks_used = 0
        self.last = None
        for room, items in env.inspection.items():
            for it in items:
                self.belief[it] = room
                self.confirmed[it] = -env.inspection_gap
                self.source[it] = "inspection"

    def age(self, item):
        return self.env.step_count - self.confirmed.get(item, -self.env.inspection_gap)

    def update(self, action, out):
        step = self.env.step_count
        kind = action["action"]
        if out.get("observation"):
            room, items = out["observation"]["room"], set(out["observation"]["items"])
            for it in list(self.belief):
                if self.belief[it] == room and it not in items:
                    self.belief[it] = None
                    self.confirmed[it] = step
                    self.source[it] = "observe_absence"
            for it in items:
                self.belief[it] = room
                self.confirmed[it] = step
                self.source[it] = "observe"
            self.seen_rooms.add(room)
        if kind == "ask_human" and out["ok"] and out.get("location"):
            it = out["item"]
            self.asked[it] = out["location"]
            self.belief[it] = out["location"]
            self.confirmed[it] = step
            self.source[it] = "ask_human"
            self.asks_used += 1
        if kind == "pick" and not out["ok"]:
            self.belief[action["item"]] = None
            self.confirmed[action["item"]] = step
            self.source[action["item"]] = "pick_failed"
        self.last = (action, out)


def advice(env, led, item, risk):
    if led.belief.get(item) is None:
        return "verify"
    if env.disturbance_p == 0:
        return "trust"
    if led.source.get(item) == "ask_human" and item not in env.held:
        return "trust"
    tau = TAU_HIGH if risk == "high_risk" else TAU_LOW
    return "trust" if led.age(item) <= tau else "verify"


def make_policy(E):
    graph, items = E.GRAPH, E.ITEMS

    def next_unseen_room(env, led):
        rooms = [r for r in graph if r != env.current_room and r not in led.seen_rooms]
        if not rooms:
            led.seen_rooms = {env.current_room}
            rooms = [r for r in graph if r != env.current_room]
        rooms.sort(key=lambda r: len(bfs_path(graph, env.current_room, r)))
        return rooms[0]

    def move_to(env, dst):
        return {"action": "move", "room": bfs_path(graph, env.current_room, dst)[0]}

    def policy(env, led, max_asks=1):
        target = env.current_target
        item, target_room = target["item"], target["room"]
        risk = items[item]
        if item in env.held:
            return {"action": "place", "item": item, "room": target_room}
        here, last = env.current_room, led.last
        just_observed = bool(last and last[0]["action"] == "observe")
        seen_here_now = bool(just_observed and last[1].get("observation")
                             and item in last[1]["observation"]["items"])
        believed = led.belief.get(item)
        go_or = lambda act, dst: act if here == dst else move_to(env, dst)
        if item in led.asked:
            return go_or({"action": "pick", "item": item}, led.asked[item])
        if seen_here_now:
            return {"action": "pick", "item": item}
        if advice(env, led, item, risk) == "trust":
            return go_or({"action": "pick", "item": item}, believed)
        if (risk == "high_risk" or believed is None) and led.asks_used < max_asks:
            return {"action": "ask_human", "question": f"Where is the {item}?"}
        if believed is not None and here != believed:
            return move_to(env, believed)
        if just_observed:
            return move_to(env, next_unseen_room(env, led))
        return {"action": "observe"}

    return policy


def evaluate(E, seeds, p):
    policy = make_policy(E)
    runs = []
    for s in seeds:
        env = E.DynamicHouseEnv(s, p, n_targets=2 + s % 2)
        led = Ledger(env)
        for _ in range(200):
            if env.done:
                break
            action = policy(env, led)
            try:
                out = env.step(action)
            except (ValueError, RuntimeError):
                break
            led.update(action, out)
        runs.append(env.episode_summary())
    n = len(runs)
    return {"success": 100 * sum(r["success"] for r in runs) / n,
            "cost": statistics.mean(r["total_cost"] for r in runs),
            "unsafe": 100 * sum(r["safety_count"] > 0 for r in runs) / n}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("env_py")
    ap.add_argument("--seeds", action="append", default=None, help="START:STOP (repeatable)")
    ap.add_argument("--ps", nargs="*", type=float, default=[0.0, 0.1, 0.2, 0.4])
    args = ap.parse_args()
    ranges = args.seeds or ["0:1000", "3000:3100"]
    E = load_env(args.env_py)
    print("age_gate reference (tau_low=%d, tau_high=%d)" % (TAU_LOW, TAU_HIGH))
    for rg in ranges:
        a, b = map(int, rg.split(":"))
        print(f"  seeds {a}..{b - 1}")
        for p in args.ps:
            r = evaluate(E, range(a, b), p)
            print(f"    p={p:<4}  SR {r['success']:5.1f}%   cost {r['cost']:5.1f}   unsafe {r['unsafe']:4.1f}%")


if __name__ == "__main__":
    main()
