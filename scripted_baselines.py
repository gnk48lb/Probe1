#!/usr/bin/env python3
"""Scripted (non-LLM) reference policies for the Dynamic House environment.

Why this exists
---------------
Before comparing LLM agents, measure what *trivial programs* achieve in the
environment.  If a 20-line script that always asks the human gets ~100%, the
environment cannot tell memory designs apart; if "trust the newest memory"
already gets 90%, there is no stale-memory problem to solve.  These numbers go
in the paper as lower/upper reference lines next to the LLM arms.

Usage
-----
    python scripted_baselines.py PATH/TO/env.py            # 1000 seeds, all variants
    python scripted_baselines.py PATH/TO/env.py --seeds 300

The script never edits your env.py.  It reads the source, applies small text
patches IN MEMORY for each variant, and executes the patched copy.

Variants
--------
    as_run         your env.py exactly as it was used for the 1440-episode run
    fixed          ask_human matches whole item names only ("notebook" != "book")
    fixed+nofreeze fixed, and an asked item is NOT frozen afterwards
    fixed+askcap1  fixed, at most one ask_human per episode
    fixed+ask20    fixed, ask_human costs 20 instead of 10
    fixed+budget40 fixed, budget 40 instead of 60

Policies (they only use what an agent may legitimately know)
------------------------------------------------------------
    trust_memory  newest sighting, go there, pick; never verify, never ask
    observe_pick  go to believed room, observe, pick only if seen; never ask
    ask_fetch     ask the human for each target, walk there, pick (falls back to
                  observe_pick when the ask is rejected)
    ledger_gate   p=0: trust memory; p>0: ask for high_risk / unknown targets,
                  observe-then-pick for the others
"""
from __future__ import annotations

import argparse
import collections
import statistics
import sys
import types

# ----------------------------------------------------------------------------
# environment loading with in-memory variant patches
# ----------------------------------------------------------------------------
HELPER = '''
import re as _re
def _named_items(question):
    q = str(question).lower()
    return [item for item in ITEMS
            if _re.search(r"(?<![a-z0-9_])" + item.replace("_", "[ _]") + r"(?![a-z0-9_])", q)]
'''


def load_env(path: str, variant: str):
    src = open(path, encoding="utf-8").read()

    def sub(old: str, new: str) -> None:
        nonlocal src
        if old not in src:
            raise SystemExit(f"[{variant}] expected text not found in env.py: {old[:60]!r}")
        src = src.replace(old, new)

    if variant != "as_run":
        # whole-word matching for ask_human (works on the original env.py)
        if "named_items(" not in src:
            sub("COSTS = {", HELPER + "\nCOSTS = {")
            sub('len([item for item in ITEMS if item in action["question"]]) != 1',
                'len(_named_items(action["question"])) != 1')
            sub("named_items = [item for item in ITEMS if item in question]",
                "named_items = _named_items(question)")
    if variant == "fixed+nofreeze":
        sub("            self.asked_items.add(item)\n", "            pass  # variant: asked item is not frozen\n")
    if variant == "fixed+askcap1":
        sub('        if name == "ask_human" and len(_named_items',
            '        if name == "ask_human" and self.ask_count >= 1:\n'
            '            return "INVALID: ask limit reached."\n'
            '        if name == "ask_human" and len(_named_items')
    if variant == "fixed+ask20":
        sub('"ask_human": 10', '"ask_human": 20')
    if variant == "fixed+budget40":
        sub("budget: int = 60", "budget: int = 40")
        sub("60 - self.budget", "40 - self.budget")

    mod = types.ModuleType(f"env_{variant.replace('+', '_')}")
    mod.__dict__["__name__"] = mod.__name__
    sys.modules[mod.__name__] = mod  # dataclasses needs the module registered
    exec(compile(src, f"<env:{variant}>", "exec"), mod.__dict__)
    return mod


# ----------------------------------------------------------------------------
# scripted policies
# ----------------------------------------------------------------------------
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


class Memory:
    """What the agent knows: initial inspection + its own observations + human answers."""

    def __init__(self, env):
        self.belief = {}
        self.seen_rooms = set()
        self.asked = {}
        self.ask_failed = set()
        self.last = None
        self.pending_ask = None
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


POLICIES = ("trust_memory", "observe_pick", "ask_fetch", "ledger_gate")


def run_episode(E, policy_name, seed, p):
    env = E.DynamicHouseEnv(seed, p, n_targets=2 + seed % 2)
    mem, policy = Memory(env), make_policy(policy_name, E.GRAPH, E.ITEMS)
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


def evaluate(E, policy_name, seeds, p):
    runs = [run_episode(E, policy_name, s, p) for s in seeds]
    n = len(runs)
    return {
        "success": 100 * sum(r["success"] for r in runs) / n,
        "cost": statistics.mean(r["total_cost"] for r in runs),
        "unsafe": 100 * sum(r["safety_count"] > 0 for r in runs) / n,
        "asks": statistics.mean(r["ask_count"] for r in runs),
    }


VARIANTS = ("as_run", "fixed", "fixed+nofreeze", "fixed+askcap1", "fixed+ask20", "fixed+budget40")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("env_py", help="path to gate_dynamic_house/env.py")
    ap.add_argument("--seeds", type=int, default=1000)
    ap.add_argument("--variants", nargs="*", default=list(VARIANTS))
    args = ap.parse_args()
    seeds = range(args.seeds)
    for variant in args.variants:
        E = load_env(args.env_py, variant)
        print(f"\n=== variant: {variant}   ({args.seeds} seeds per cell)")
        print(f"{'policy':13s} | " + " | ".join(f"p={p}: success  cost  asks unsafe" for p in (0.0, 0.2, 0.4)))
        for pol in POLICIES:
            cells = []
            for p in (0.0, 0.2, 0.4):
                r = evaluate(E, pol, seeds, p)
                cells.append(f"      {r['success']:6.1f}% {r['cost']:5.1f} {r['asks']:4.1f} {r['unsafe']:5.1f}%")
            print(f"{pol:13s} | " + " | ".join(cells))


if __name__ == "__main__":
    main()
