"""Probe 1b: the controller arms, their agent loop and a resumable runner.

Arms (Probe 1b section 4.2):

    base      controller = []                       (the 1b control)
    hint      controller = ["advice"]               (the ledger carries an advice field)
    shield    controller = ["shield"]               (stale high-risk grasps are blocked)
    both      controller = ["advice", "shield"]
    auto      controller = ["recommend"]            (positive control)
    base_old  Probe 1's led_C, byte for byte       (optional Stage 3)

Every arm uses the ledger memory of Probe 1.  The controller sees only the
public state and the agent's own visible history; the harness applies a
shield veto as an environment step (no world change, no budget, one step).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .agent import invalid_fallback_action
from .controller import ANNOUNCED, CONTROLLER_MODE, Controller, advice_for
from .env import ITEMS, DynamicHouseEnv
from .gateway import DEFAULT_BASE_URL, DEFAULT_MODEL, MagpieClient, api_key, base_url
from .memory import LedgerMemory, MemoryBundle
from .prompts_1b import (build_user_message_1b, build_user_message_1b_old,
                         system_prompt_1b)

ROOT = Path(__file__).resolve().parent.parent.parent
ARMS = ("base", "hint", "shield", "both", "auto")
ARMS_STAGE3 = ("base_old",)
PS = (0.1, 0.2, 0.4)
SEED_BLOCK = 25


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class JsonlWriter:
    def __init__(self, path: Path):
        self.path, self.lock = path, threading.Lock()

    def write(self, row: dict[str, Any]) -> None:
        with self.lock:
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
                handle.flush()
                os.fsync(handle.fileno())


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


class ArmAgent1B:
    """One episode of one arm."""

    def __init__(self, env: DynamicHouseEnv, client: MagpieClient | None, model: str,
                 arm: str, format_retries: int = 2, no_llm: bool = False):
        self.env, self.client, self.model = env, client, model
        self.arm = arm
        self.format_retries = format_retries
        self.no_llm = no_llm
        self.system = system_prompt_1b(arm)
        self.memory = MemoryBundle("ledger", env.inspection, env.inspection_gap)
        self.controller = Controller(CONTROLLER_MODE[arm], self.memory.ledger, env.max_asks)
        self.history: list[dict[str, Any]] = []
        self.exchanges: list[dict[str, Any]] = []
        self.trace: list[dict[str, Any]] = []
        self.usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0,
                      "llm_calls": 0, "request_retries": 0, "format_retries": 0,
                      "format_failures": 0}
        self.invalid_actions = 0
        self.blocked_count = 0
        self.pick_records: list[dict[str, Any]] = []
        self.checked_since_verify: dict[str, bool] = {}
        self.overrides = 0
        self.recommendations = 0
        self.budget_by_action: dict[str, int] = {}
        self.budget_by_action_success: dict[str, int] = {}

    # -- the state the agent sees ------------------------------------------ #
    def ledger_view(self) -> dict[str, Any]:
        view = self.memory.ledger.view(self.env.step_count)
        if self.controller.shows_advice():
            p = self.env.disturbance_p
            held = set(self.env.held)
            for item, row in view.items():
                row["advice"] = advice_for(row, ITEMS.get(item, "low_risk"), p, item in held)
        return view

    def controller_fields(self, view: dict[str, Any]) -> dict[str, Any]:
        fields: dict[str, Any] = {"controller": self.controller.announces,
                                  "asks_remaining": max(self.env.max_asks - self.env.ask_count, 0)}
        if self.controller.recommends():
            fields["controller_recommendation"] = self.controller.recommend(view, self.env.public_state())
        return fields

    def user_message(self) -> str:
        view = self.ledger_view()
        history = self.history[-4:]
        if self.arm == "base_old":
            return build_user_message_1b_old(self.env, history, view)
        return build_user_message_1b(self.env, history, view, self.controller_fields(view))

    # -- one decision ------------------------------------------------------- #
    def decide(self) -> dict[str, Any]:
        system, user = self.system, self.user_message()
        text, meta = self.client.complete(self.model, system, user)
        self.usage["llm_calls"] += 1
        self.usage["request_retries"] += meta.get("request_retries", 0)
        for key in ("input_tokens", "output_tokens", "total_tokens"):
            self.usage[key] += meta.get(key) or 0
        action, error = None, None
        for attempt in range(self.format_retries + 1):
            if attempt:
                self.usage["llm_calls"] += 1
                self.usage["format_retries"] += 1
                self.usage["request_retries"] += meta.get("request_retries", 0)
                for key in ("input_tokens", "output_tokens", "total_tokens"):
                    self.usage[key] += meta.get(key) or 0
                text, meta = self.client.complete(self.model, system, user)
            try:
                from .gateway import parse_action
                action = parse_action(text)
                error = None
                break
            except ValueError as exc:
                error = str(exc)
        if action is None:
            self.usage["format_failures"] += 1
            action = invalid_fallback_action(self.env)
        self.exchanges.append({"step": self.env.step_count + 1, "system": system, "user": user,
                               "response": text, "attempts": attempt + 1, "parse_error": error,
                               "meta": meta})
        return {"action": action, "parse_error": error, "response": text}

    # -- the episode -------------------------------------------------------- #
    def run(self) -> dict[str, Any]:
        started = time.monotonic()
        while not self.env.done:
            step = self.env.step_count + 1
            view = self.ledger_view()
            recommendation = None
            if self.controller.recommends():
                recommendation = self.controller.recommend(view, self.env.public_state())
            if self.no_llm:
                # The controller acts by itself (the T7 regression target).
                if recommendation is None:
                    break
                decision = {"action": recommendation, "parse_error": None, "response": ""}
            else:
                decision = self.decide()
            action = decision["action"]
            overrode = False
            if recommendation is not None:
                self.recommendations += 1
                if action != recommendation:
                    self.overrides += 1
                    overrode = True
            reason = self.controller.block_reason(action, view, self.env.public_state())
            if reason is not None:
                outcome = self.env.controller_veto(action, reason)
                self.blocked_count += 1
            else:
                outcome = self.env.step(action)
            self._update(action, outcome, view)
            self.trace.append({
                "step": step, "action": action, "ok": outcome["ok"],
                "message": outcome["message"], "cost": outcome["cost"],
                "failure_reason": outcome.get("failure_reason"),
                "disturbance": outcome.get("disturbance"),
                "parse_error": decision["parse_error"],
                "controller_blocked": reason is not None,
                "overrode_recommendation": overrode,
                "recommendation": recommendation,
            })
        summary = self.env.episode_summary()
        summary["terminal_reason"] = self.env.failure_reason
        summary["invalid_actions"] = self.invalid_actions
        summary["blocked_count"] = self.blocked_count
        summary["usage"] = dict(self.usage)
        summary["wall_time_s"] = round(time.monotonic() - started, 3)
        summary["pick_records"] = self.pick_records
        summary["recommendations"] = self.recommendations
        summary["overrides"] = self.overrides
        summary["budget_by_action"] = dict(self.budget_by_action)
        summary["budget_by_action_success"] = dict(self.budget_by_action_success)
        return summary

    # -- bookkeeping --------------------------------------------------------- #
    def _update(self, action: dict[str, Any], outcome: dict[str, Any],
                view: dict[str, Any]) -> None:
        step = outcome["step"]
        name = action["action"]
        observation = outcome.get("observation")
        if observation:
            self.memory.observe(step, observation["room"], observation["items"])
            for item in self.checked_since_verify:
                self.checked_since_verify[item] = True
        if name == "ask_human" and outcome.get("answer"):
            self.memory.ask_human(step, outcome["item"], outcome["location"])
            self.checked_since_verify[outcome["item"]] = True
        if name == "pick":
            item = action["item"]
            row = view.get(item)
            risk = ITEMS.get(item, "low_risk")
            held = item in self.env.held
            advice = advice_for(row, risk, self.env.disturbance_p, held)
            age = row["age"] if row else None
            self.pick_records.append({
                "step": step, "item": item, "ok": outcome["ok"],
                "evidence_age": age, "room": self.env.current_room,
                "failure_reason": outcome.get("failure_reason"),
                "source": row["source"] if row else None,
                "believed_room": row["believed_room"] if row else None,
                "rule_advice": advice,
                "risk": risk,
                "checked_before_pick": bool(self.checked_since_verify.get(item, False)),
            })
            if advice == "verify":
                self.checked_since_verify.setdefault(item, False)
            if outcome["ok"]:
                self.memory.pick_succeeded(step, item)
            else:
                self.memory.pick_failed(step, item, self.env.current_room)
        if not outcome["ok"] and outcome.get("failure_reason") == "invalid_action":
            self.invalid_actions += 1
        if outcome.get("cost"):
            self.budget_by_action[name] = self.budget_by_action.get(name, 0) + outcome["cost"]
        self.controller.update(action, outcome)
        self.history.append({"step": step, "action": action, "result": outcome["message"]})


def run_episode(seed: int, p: float, arm: str, client: MagpieClient, model: str,
                format_retries: int, run_id: str, no_llm: bool = False) -> tuple[dict, list[dict], dict]:
    expose_asks = arm != "base_old"
    env = DynamicHouseEnv(seed, p, n_targets=2 + seed % 2, max_asks=1, freeze_asked=True,
                          allow_any_p=True, expose_asks=expose_asks)
    agent = ArmAgent1B(env, client, model, arm, format_retries=format_retries, no_llm=no_llm)
    episode_id = f"{run_id}:p{p}:s{seed}:{arm}"
    summary = agent.run()
    summary.update(run_id=run_id, episode_id=episode_id, arm=arm, model=model, seed=seed,
                   disturbance_p=p, controller=list(ANNOUNCED[CONTROLLER_MODE[arm]]))
    trace_rows = [{"episode_id": episode_id, "arm": arm, "seed": seed, "disturbance_p": p,
                   **row} for row in agent.trace]
    raw = {"episode_id": episode_id, "arm": arm, "seed": seed, "disturbance_p": p,
           "model": model, "exchanges": agent.exchanges}
    return summary, trace_rows, raw


def build_jobs(seeds: list[int], ps: tuple[float, ...], arms: tuple[str, ...],
               done: set[tuple]) -> list[tuple[int, float, str]]:
    """Seed-major order with the cells rotated per seed.

    Seed-major keeps completed seeds contiguous (an interruption then always
    leaves whole seeds behind); the rotation keeps any concurrent window from
    always working on the same arm.
    """
    cells = [(p, arm) for p in ps for arm in arms]
    jobs = []
    for index, seed in enumerate(seeds):
        offset = index % len(cells)
        for p, arm in cells[offset:] + cells[:offset]:
            if (arm, p, seed) not in done:
                jobs.append((seed, p, arm))
    return jobs


def evaluate_controller(seeds, p: float) -> dict[str, float]:
    """The controller acting on its own (no LLM): the T7 regression target."""
    runs = []
    for seed in seeds:
        env = DynamicHouseEnv(seed, p, n_targets=2 + seed % 2, max_asks=1, freeze_asked=True,
                              allow_any_p=True)
        agent = ArmAgent1B(env, None, "none", "auto", no_llm=True)
        runs.append(agent.run())
    n = len(runs)
    return {"success": 100 * sum(r["success"] for r in runs) / n,
            "cost": float(sum(r["total_cost"] for r in runs) / n),
            "n": n}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed-start", type=int, default=3000)
    parser.add_argument("--seeds", type=int, default=100)
    parser.add_argument("--arms", default=",".join(ARMS))
    parser.add_argument("--ps", default=",".join(str(p) for p in PS))
    parser.add_argument("--output-dir", type=Path, default=ROOT / "results_1b")
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--timeout", type=float, default=150.0)
    parser.add_argument("--max-tokens", type=int, default=4000)
    parser.add_argument("--request-retries", type=int, default=6)
    parser.add_argument("--format-retries", type=int, default=2)
    parser.add_argument("--base-url", default=base_url())
    parser.add_argument("--api-key", default=api_key())
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--progress-seconds", type=float, default=600.0)
    parser.add_argument("--run-id", default=None)
    args = parser.parse_args()

    arms = tuple(a.strip() for a in args.arms.split(",") if a.strip())
    ps = tuple(float(p) for p in args.ps.split(",") if p.strip())
    for arm in arms:
        if arm not in CONTROLLER_MODE:
            raise SystemExit(f"unknown arm {arm}; choose from {sorted(CONTROLLER_MODE)}")
    seeds = list(range(args.seed_start, args.seed_start + args.seeds))

    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    episodes_path = output / "episodes.jsonl"
    traces_path = output / "traces.jsonl"
    raw_path = output / "raw.jsonl"
    manifest_path = output / "run_manifest.json"

    config = {
        "run_id": args.run_id or time.strftime("dynhouse1b_%Y%m%d_%H%M%S"),
        "created_at": now(), "arms": list(arms), "disturbance_levels": list(ps),
        "seed_start": args.seed_start, "seeds": args.seeds,
        "seed_range": [seeds[0], seeds[-1]] if seeds else [],
        "model": args.model, "temperature": 0, "max_tokens": args.max_tokens,
        "concurrency": args.concurrency, "timeout_s": args.timeout,
        "request_retries": args.request_retries, "format_retries": args.format_retries,
        "base_url": args.base_url, "budget": 60, "max_steps": 30, "inspection_gap": 8,
        "target_count_rule": "2 + seed % 2", "env_max_asks": 1, "env_freeze_asked": True,
        "env_allow_any_p": True, "python": sys.version.split()[0], "platform": sys.platform,
    }
    if manifest_path.exists():
        previous = json.loads(manifest_path.read_text(encoding="utf-8"))
        ignore = ("run_id", "created_at", "concurrency", "timeout_s", "max_tokens",
                  "request_retries", "format_retries", "seeds", "seed_start", "seed_range")
        previous_cmp = {k: v for k, v in previous.items() if k not in ignore}
        config_cmp = {k: v for k, v in config.items() if k not in ignore}
        if previous_cmp != config_cmp:
            raise SystemExit(f"Output manifest differs from {manifest_path}; use a new output "
                             f"directory.\n  previous: {previous_cmp}\n  requested: {config_cmp}")
        config["run_id"] = previous["run_id"]
        config["created_at"] = previous["created_at"]
    manifest_path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")

    done = {(r["arm"], r["disturbance_p"], r["seed"]) for r in load_jsonl(episodes_path)}
    jobs = build_jobs(seeds, ps, arms, done)
    print(f"run {config['run_id']} arms={arms} ps={ps} concurrency={args.concurrency}", flush=True)
    print(f"{len(jobs)} episodes to run / {len(seeds) * len(ps) * len(arms)} cells "
          f"({len(done)} already done)", flush=True)
    if not jobs:
        return

    client = MagpieClient(args.base_url, args.api_key, args.timeout,
                          args.request_retries, args.max_tokens)
    writers = {name: JsonlWriter(path) for name, path in
               (("episodes", episodes_path), ("traces", traces_path), ("raw", raw_path))}
    counts = {"done": 0, "infra": 0, "calls": 0, "format_failures": 0}
    lock = threading.Lock()
    started = time.monotonic()
    last_progress = started

    def record(summary: dict[str, Any], trace_rows: list[dict[str, Any]], raw: dict[str, Any]) -> None:
        for bulky in ("events", "ground_truth"):
            summary.pop(bulky, None)
        writers["episodes"].write(summary)
        for row in trace_rows:
            writers["traces"].write(row)
        writers["raw"].write(raw)

    def execute(job):
        seed, p, arm = job
        try:
            return run_episode(seed, p, arm, client, args.model, args.format_retries,
                               config["run_id"])
        except Exception as exc:  # infrastructure failure, not a policy failure
            traceback.print_exc()
            summary = {"run_id": config["run_id"], "episode_id": f"{config['run_id']}:p{p}:s{seed}:{arm}",
                       "arm": arm, "seed": seed, "disturbance_p": p, "model": args.model,
                       "success": False, "infra_failed": True,
                       "failure_reason": "infrastructure_failure",
                       "infrastructure_error": repr(exc), "total_cost": None, "steps": None,
                       "ask_count": None, "stale_pick_count": None, "safety_count": None,
                       "invalid_actions": None, "blocked_count": None, "time": now()}
            return summary, [], {"episode_id": summary["episode_id"], "arm": arm, "seed": seed,
                                 "disturbance_p": p, "exchanges": []}

    with ThreadPoolExecutor(max_workers=args.concurrency, thread_name_prefix="dyn1b") as pool:
        futures = [pool.submit(execute, job) for job in jobs]
        for future in as_completed(futures):
            summary, trace_rows, raw = future.result()
            record(summary, trace_rows, raw)
            with lock:
                counts["done"] += 1
                if summary.get("infra_failed"):
                    counts["infra"] += 1
                usage = summary.get("usage") or {}
                counts["calls"] += usage.get("llm_calls", 0)
                counts["format_failures"] += usage.get("format_failures", 0)
                elapsed = time.monotonic() - started
                if time.monotonic() - last_progress >= args.progress_seconds:
                    print(f"[progress] {counts['done']}/{len(jobs)} episodes | "
                          f"{counts['done'] / max(elapsed, 1e-9) * 60:.1f} ep/min | "
                          f"{counts['calls'] / max(elapsed, 1e-9) * 60:.1f} calls/min | "
                          f"infra_failed={counts['infra']} | format_failures={counts['format_failures']} | "
                          f"elapsed={elapsed / 60:.1f} min", flush=True)
                    last_progress = time.monotonic()
                if not summary.get("infra_failed"):
                    print(f"  [{counts['done']}/{len(jobs)}] p={summary['disturbance_p']} "
                          f"seed={summary['seed']} {summary['arm']}: success={summary['success']} "
                          f"reason={summary.get('failure_reason')} cost={summary.get('total_cost')} "
                          f"steps={summary.get('steps')} blocked={summary.get('blocked_count')}",
                          flush=True)

    rows = load_jsonl(episodes_path)
    latest = {}
    for row in rows:
        latest[(row["arm"], row["disturbance_p"], row["seed"])] = row
    failed = [row for key, row in latest.items()
              if row.get("infra_failed") or row.get("failure_reason") == "infrastructure_failure"]
    if failed:
        print(f"Repair pass: re-running {len(failed)} infrastructure-failed episodes", flush=True)
        repair_jobs = [(row["seed"], row["disturbance_p"], row["arm"]) for row in failed]
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(execute, job) for job in repair_jobs]
            for future in as_completed(futures):
                summary, trace_rows, raw = future.result()
                if not summary.get("infra_failed"):
                    summary["repair_of_infrastructure_failure"] = True
                record(summary, trace_rows, raw)
        print("Repair pass finished", flush=True)

    rows = load_jsonl(episodes_path)
    latest = {}
    for row in rows:
        latest[(row["arm"], row["disturbance_p"], row["seed"])] = row
    remaining = [row for key, row in latest.items()
                 if row.get("infra_failed") or row.get("failure_reason") == "infrastructure_failure"]
    print(f"Run finished in {(time.monotonic() - started) / 60:.1f} min. Output: {output}. "
          f"Still infra-failed: {len(remaining)}", flush=True)


if __name__ == "__main__":
    main()
