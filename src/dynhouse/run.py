"""Concurrent, resumable runner for the six-arm experiment.

Design rules that matter:
* A job is one (seed, p, arm) episode.  The job order is seed-major, then
  p, then the arms with the four core arms first, so an interrupted run
  always leaves paired data for the core arms.
* An episode counts as complete only after its row has been written to
  `episodes.jsonl`; the runner resumes by reading that file.
* Infrastructure failures (timeout / empty body / 5xx / rate limit) are
  retried with exponential backoff inside the client and never counted as
  agent failures.  An episode whose turn still fails is marked `infra_failed`,
  excluded from the analysis, and re-run at the end.
* Before anything runs, the prompt/memory sources are checked against
  `prompts.lock`; a mismatch aborts the run.
"""
from __future__ import annotations

import argparse
import hashlib
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

from .agent import ArmAgent
from .env import DynamicHouseEnv
from .gateway import DEFAULT_BASE_URL, DEFAULT_MODEL, MagpieClient, api_key, base_url
from .prompts import ARMS as ARM_PARTS, CORE_ARMS

ROOT = Path(__file__).resolve().parent.parent.parent
ARMS = ("app_N", "led_N", "app_C", "led_C", "win_N", "win_C")
CORE_ARMS = ("app_N", "led_N", "app_C", "led_C")
PS = (0.0, 0.2, 0.4)

LOCKED_SOURCES = ("src/dynhouse/prompts.py", "src/dynhouse/memory.py")
LOCK_PATH = ROOT / "prompts.lock"
VARIANTS = {
    # name -> (max_asks, freeze_asked)
    "main": (1, True),
    "nofreeze": (99, False),
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compute_lock() -> dict[str, str]:
    return {rel: sha256_file(ROOT / rel) for rel in LOCKED_SOURCES}


def verify_lock(strict: bool = True) -> bool:
    """Refuse to run when the prompt templates or memory code drifted."""
    current = compute_lock()
    if not LOCK_PATH.exists():
        if strict:
            print("ERROR: prompts.lock is missing. Run `uv run python -m dynhouse.run --write-lock` "
                  "after the smoke test (M4).", file=sys.stderr)
            return False
        return False
    expected = json.loads(LOCK_PATH.read_text(encoding="utf-8"))["files"]
    if expected != current:
        print("ERROR: prompt/memory sources do not match prompts.lock; refusing to run.",
              file=sys.stderr)
        for rel in LOCKED_SOURCES:
            if expected.get(rel) != current.get(rel):
                print(f"  {rel}: locked {expected.get(rel)} != current {current.get(rel)}", file=sys.stderr)
        return False
    return True


def write_lock() -> None:
    payload = {"written_at": now(), "files": compute_lock()}
    LOCK_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {LOCK_PATH}")


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


def run_episode(seed: int, p: float, arm: str, client: MagpieClient, model: str,
                variant: str, format_retries: int, run_id: str) -> dict[str, Any]:
    representation, policy_prompt = ARM_PARTS[arm]
    max_asks, freeze_asked = VARIANTS[variant]
    env = DynamicHouseEnv(seed, p, n_targets=2 + seed % 2,
                          max_asks=max_asks, freeze_asked=freeze_asked)
    agent = ArmAgent(env, client, model, representation, policy_prompt,
                     format_retries=format_retries)
    episode_id = f"{run_id}:{variant}:p{p}:s{seed}:{arm}"
    summary = agent.run()
    summary.update(run_id=run_id, episode_id=episode_id, variant=variant, arm=arm,
                   model=model, seed=seed, disturbance_p=p,
                   representation=representation, policy_prompt=policy_prompt)
    trace_rows = [{"episode_id": episode_id, "arm": arm, "seed": seed, "disturbance_p": p,
                   "variant": variant, **row} for row in agent.trace]
    raw = {"episode_id": episode_id, "arm": arm, "seed": seed, "disturbance_p": p,
           "variant": variant, "model": model, "exchanges": agent.exchanges}
    return summary, trace_rows, raw


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed-start", type=int, default=1000)
    parser.add_argument("--seeds", type=int, default=60, help="number of seeds per cell")
    parser.add_argument("--arms", default=",".join(ARMS))
    parser.add_argument("--ps", default=",".join(str(p) for p in PS))
    parser.add_argument("--variant", default="main", choices=sorted(VARIANTS))
    parser.add_argument("--output-dir", type=Path, default=ROOT / "results" / "main")
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--timeout", type=float, default=150.0)
    parser.add_argument("--max-tokens", type=int, default=4000)
    parser.add_argument("--request-retries", type=int, default=4)
    parser.add_argument("--format-retries", type=int, default=2)
    parser.add_argument("--base-url", default=base_url())
    parser.add_argument("--api-key", default=api_key())
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--write-lock", action="store_true")
    parser.add_argument("--no-lock-check", action="store_true")
    parser.add_argument("--progress-seconds", type=float, default=600.0)
    parser.add_argument("--run-id", default=None)
    args = parser.parse_args()

    if args.write_lock:
        write_lock()
        return
    if not args.no_lock_check and not verify_lock():
        raise SystemExit(2)

    arms = [a.strip() for a in args.arms.split(",") if a.strip()]
    ps = [float(p) for p in args.ps.split(",") if p.strip()]
    for arm in arms:
        if arm not in ARM_PARTS:
            raise SystemExit(f"unknown arm {arm}; choose from {sorted(ARM_PARTS)}")
    seeds = list(range(args.seed_start, args.seed_start + args.seeds))

    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    episodes_path = output / "episodes.jsonl"
    traces_path = output / "traces.jsonl"
    raw_path = output / "raw.jsonl"
    manifest_path = output / "run_manifest.json"

    config = {
        "run_id": args.run_id or time.strftime("dynhouse_%Y%m%d_%H%M%S"),
        "created_at": now(), "variant": args.variant, "arms": arms, "disturbance_levels": ps,
        "seed_start": args.seed_start, "seeds": args.seeds,
        "seed_range": [seeds[0], seeds[-1]] if seeds else [],
        "model": args.model, "temperature": 0, "max_tokens": args.max_tokens,
        "concurrency": args.concurrency, "timeout_s": args.timeout,
        "request_retries": args.request_retries, "format_retries": args.format_retries,
        "base_url": args.base_url, "budget": 60, "max_steps": 30, "inspection_gap": 8,
        "target_count_rule": "2 + seed % 2", "env_max_asks": VARIANTS[args.variant][0],
        "env_freeze_asked": VARIANTS[args.variant][1],
        "python": sys.version.split()[0], "platform": sys.platform,
    }
    if manifest_path.exists():
        previous = json.loads(manifest_path.read_text(encoding="utf-8"))
        for key in ("run_id", "created_at", "concurrency", "timeout_s", "max_tokens",
                    "request_retries", "format_retries"):
            previous.pop(key, None)
            config.pop(key, None)
        if previous != config:
            raise SystemExit(f"Output manifest differs from {manifest_path}; use a new output "
                             f"directory.\n  previous: {previous}\n  requested: {config}")
        config["run_id"] = json.loads(manifest_path.read_text(encoding="utf-8"))["run_id"]
    else:
        manifest_path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")

    done_keys = {(r["arm"], r["disturbance_p"], r["seed"]) for r in load_jsonl(episodes_path)}
    jobs = []
    for seed in seeds:                      # outer loop: seed
        for p in ps:                        # inner loop: p x arm
            for arm in arms:
                if (arm, p, seed) not in done_keys:
                    jobs.append((seed, p, arm))
    total_cells = len(seeds) * len(ps) * len(arms)
    print(f"run {config['run_id']} variant={args.variant} model={args.model} "
          f"concurrency={args.concurrency}", flush=True)
    print(f"{len(jobs)} episodes to run / {total_cells} cells "
          f"({len(done_keys)} already done)", flush=True)
    if not jobs:
        return

    client = MagpieClient(args.base_url, args.api_key, args.timeout,
                          args.request_retries, args.max_tokens)
    writers = {name: JsonlWriter(path) for name, path in
               (("episodes", episodes_path), ("traces", traces_path), ("raw", raw_path))}
    counts = {"done": 0, "infra": 0, "calls": 0}
    lock = threading.Lock()
    started = time.monotonic()
    last_progress = started

    def record(summary: dict[str, Any], trace_rows: list[dict[str, Any]], raw: dict[str, Any]) -> None:
        # The episode row stays compact: the full event log and the ground
        # truth stay out of the analysis file (the step traces keep the
        # roommate moves that the failure analysis needs).
        for bulky in ("events", "ground_truth"):
            summary.pop(bulky, None)
        writers["episodes"].write(summary)
        for row in trace_rows:
            writers["traces"].write(row)
        writers["raw"].write(raw)

    def execute(job):
        seed, p, arm = job
        try:
            return run_episode(seed, p, arm, client, args.model, args.variant,
                               args.format_retries, config["run_id"])
        except Exception as exc:  # infrastructure failure, not a policy failure
            traceback.print_exc()
            summary = {"run_id": config["run_id"], "episode_id": f"{config['run_id']}:{args.variant}:p{p}:s{seed}:{arm}",
                       "variant": args.variant, "arm": arm, "seed": seed, "disturbance_p": p,
                       "model": args.model, "success": False, "infra_failed": True,
                       "failure_reason": "infrastructure_failure", "infrastructure_error": repr(exc),
                       "total_cost": None, "steps": None, "ask_count": None, "stale_pick_count": None,
                       "safety_count": None, "invalid_actions": None, "time": now()}
            return summary, [], {"episode_id": summary["episode_id"], "arm": arm, "seed": seed,
                                 "disturbance_p": p, "variant": args.variant, "exchanges": []}

    with ThreadPoolExecutor(max_workers=args.concurrency, thread_name_prefix="dyn") as pool:
        futures = [pool.submit(execute, job) for job in jobs]
        for future in as_completed(futures):
            summary, trace_rows, raw = future.result()
            record(summary, trace_rows, raw)
            with lock:
                counts["done"] += 1
                if summary.get("infra_failed"):
                    counts["infra"] += 1
                counts["calls"] += (summary.get("usage") or {}).get("llm_calls", 0)
                elapsed = time.monotonic() - started
                if time.monotonic() - last_progress >= args.progress_seconds:
                    rate = counts["done"] / max(elapsed, 1e-9) * 60
                    call_rate = counts["calls"] / max(elapsed, 1e-9) * 60
                    print(f"[progress] {counts['done']}/{len(jobs)} episodes | {rate:.1f} ep/min | "
                          f"{call_rate:.1f} calls/min | infra_failed={counts['infra']} | "
                          f"elapsed={elapsed/60:.1f} min", flush=True)
                    last_progress = time.monotonic()
                if not summary.get("infra_failed"):
                    print(f"  [{counts['done']}/{len(jobs)}] p={summary['disturbance_p']} "
                          f"seed={summary['seed']} {summary['arm']}: success={summary['success']} "
                          f"reason={summary.get('failure_reason')} cost={summary.get('total_cost')} "
                          f"steps={summary.get('steps')}", flush=True)

    # Repair pass: infrastructure failures are provider faults, not policy
    # outcomes.  Re-run them at a low concurrency so the comparison is not
    # contaminated by provider flakiness.
    rows = load_jsonl(episodes_path)
    latest: dict[tuple[str, float, int], dict[str, Any]] = {}
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

    remaining = [row for key, row in latest.items()
                 if row.get("infra_failed") or row.get("failure_reason") == "infrastructure_failure"]
    print(f"Run finished in {(time.monotonic()-started)/60:.1f} min. "
          f"Output: {output}. Still infra-failed: {len(remaining)}", flush=True)


if __name__ == "__main__":
    main()
