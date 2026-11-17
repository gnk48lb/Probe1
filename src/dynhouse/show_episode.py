"""Print a full episode transcript for manual review.

    uv run python -m dynhouse.show_episode results/smoke --arm led_C --seed 0
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def load_raw(path: Path) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("results", type=Path)
    parser.add_argument("--arm", default="led_C")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--p", type=float, default=0.2)
    parser.add_argument("--full-system", action="store_true",
                        help="print the whole system prompt instead of a digest")
    args = parser.parse_args()

    raws = load_raw(args.results / "raw.jsonl")
    traces = load_raw(args.results / "traces.jsonl")
    episodes = load_raw(args.results / "episodes.jsonl")

    match = [r for r in raws if r["arm"] == args.arm and r["seed"] == args.seed
             and abs(r["disturbance_p"] - args.p) < 1e-9]
    if not match:
        raise SystemExit(f"no episode for arm={args.arm} seed={args.seed} p={args.p}")
    raw = match[-1]
    ep = [e for e in episodes if e["arm"] == args.arm and e["seed"] == args.seed
          and abs(e["disturbance_p"] - args.p) < 1e-9][-1]
    steps = [t for t in traces if t["arm"] == args.arm and t["seed"] == args.seed
             and abs(t["disturbance_p"] - args.p) < 1e-9]

    print("=" * 100)
    print(f"EPISODE arm={args.arm} seed={args.seed} p={args.p}")
    print(f"success={ep['success']} reason={ep.get('failure_reason')} cost={ep.get('total_cost')} "
          f"steps={ep.get('steps')} asks={ep.get('ask_count')} stale={ep.get('stale_pick_count')} "
          f"safety={ep.get('safety_count')} invalid={ep.get('invalid_actions')}")
    print(f"usage={ep.get('usage')}")
    print(f"targets={ep.get('targets')}")
    print("=" * 100)

    for exchange, step in zip(raw["exchanges"], steps):
        payload = json.loads(exchange["user"])
        print("-" * 100)
        print(f"STEP {exchange['step']}   attempts={exchange['attempts']}  "
              f"parse_error={exchange['parse_error']}")
        print(f"STATE: room={payload['state']['task_state']['current_room']} "
              f"budget={payload['state']['task_state']['remaining_budget']} "
              f"subgoal={payload['state']['task_state']['current_subgoal']}")
        print(f"RECENT HISTORY: {json.dumps(payload['recent_history'], ensure_ascii=False)}")
        memory = payload["memory"]
        if isinstance(memory, list) and memory and "items" in memory[0]:
            print(f"MEMORY (append, last 3 of {len(memory)}): "
                  f"{json.dumps(memory[-3:], ensure_ascii=False)}")
        elif isinstance(memory, list) and memory:
            print(f"MEMORY (append, last 3 of {len(memory)}): "
                  f"{json.dumps(memory[-3:], ensure_ascii=False)}")
        else:
            rows = memory if isinstance(memory, dict) else {}
            interesting = {k: v for k, v in rows.items()
                           if k in [t["item"] for t in payload["state"]["task_state"]["targets"]]}
            print(f"MEMORY (ledger, {len(rows)} rows; targets only): "
                  f"{json.dumps(interesting, ensure_ascii=False)}")
        print(f"ACTION: {json.dumps(step['action'], ensure_ascii=False)}")
        print(f"RESULT: {step['message']}")
        if step.get("disturbance"):
            print(f"ROOMMATE: {json.dumps(step['disturbance'], ensure_ascii=False)}")
        print(f"RAW REPLY: {exchange['response'][:600]}")


if __name__ == "__main__":
    main()
