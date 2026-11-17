"""Generate docs/PARITY.md: the per-arm prompt character counts.

    uv run python -m dynhouse.parity --out docs/PARITY.md
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .agent import ArmAgent
from .env import DynamicHouseEnv
from .gateway import MagpieClient
from .prompts import ARMS, BASE_SYSTEM, PROMPT_C

CORE = ("app_N", "led_N", "app_C", "led_C")


class ScriptedClient:
    """A deterministic stand-in for the model: plays a fixed, legal action."""

    def __init__(self, script):
        self.script = list(script)
        self.index = 0

    def complete(self, model, system, user):
        action = self.script[min(self.index, len(self.script) - 1)]
        self.index += 1
        return json.dumps(action), {"latency_ms": 1, "input_tokens": 0, "output_tokens": 0,
                                    "total_tokens": 0, "http_status": 200, "request_retries": 0}


def collect(seed: int, p: float, steps: int = 6):
    """Per-arm prompt sizes over the first `steps` steps of one episode."""
    script = [{"action": "move", "room": "Kitchen"}, {"action": "observe"},
              {"action": "move", "room": "Bathroom"}, {"action": "observe"},
              {"action": "move", "room": "LivingRoom"}, {"action": "observe"}]
    sizes: dict[str, list[dict]] = {}
    for arm, (representation, policy_prompt) in ARMS.items():
        env = DynamicHouseEnv(seed, p, n_targets=2 + seed % 2)
        agent = ArmAgent(env, ScriptedClient(script), "stub", representation, policy_prompt)
        rows = []
        while not env.done and len(rows) < steps:
            step = env.step_count + 1
            system = agent.system
            user = agent.user_message()
            payload = json.loads(user)
            rows.append({
                "step": step,
                "system_chars": len(system),
                "user_chars": len(user),
                "state_chars": len(json.dumps(payload["state"], ensure_ascii=False, separators=(",", ":"))),
                "history_chars": len(json.dumps(payload["recent_history"], ensure_ascii=False, separators=(",", ":"))),
                "memory_chars": len(json.dumps(payload["memory"], ensure_ascii=False, separators=(",", ":"))),
                "memory_type": type(payload["memory"]).__name__,
            })
            decision = agent.decide()
            outcome = env.step(decision["action"])
            agent._update(decision["action"], outcome)
        sizes[arm] = rows
    return sizes


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path("docs/PARITY.md"))
    parser.add_argument("--seed", type=int, default=1000)
    parser.add_argument("--p", type=float, default=0.2)
    args = parser.parse_args()

    sizes = collect(args.seed, args.p)
    lines = ["# PARITY -- per-arm prompt character counts", "",
             f"Seed {args.seed}, disturbance_p {args.p}.  The four core arms "
             f"({', '.join(CORE)}) carry the analysis; `win_*` are the memory-free baselines.", "",
             "## System prompt", "",
             "| arm | R | P | system chars | base + suffix |", "|---|---|---|---|---|"]
    for arm, (representation, policy_prompt) in ARMS.items():
        system = BASE_SYSTEM + ("\n" + PROMPT_C if policy_prompt == "C" else "")
        lines.append(f"| {arm} | {representation} | {policy_prompt} | {len(system)} | "
                     f"{'BASE_SYSTEM' if policy_prompt == 'N' else 'BASE_SYSTEM + P=C suffix'} |")
    lines += ["", f"- `BASE_SYSTEM`: {len(BASE_SYSTEM)} chars",
              f"- `P=C` suffix: {len(PROMPT_C)} chars",
              f"- P=C system prompt: {len(BASE_SYSTEM) + 1 + len(PROMPT_C)} chars", "",
              "## User message, step by step", "",
              "| arm | step | system chars | user chars | state | history | memory | memory type |",
              "|---|---|---|---|---|---|---|---|"]
    for arm, rows in sizes.items():
        for row in rows:
            lines.append(f"| {arm} | {row['step']} | {row['system_chars']} | {row['user_chars']} | "
                         f"{row['state_chars']} | {row['history_chars']} | {row['memory_chars']} | "
                         f"{row['memory_type']} |")
    lines += ["", "## What differs between arms", "",
              "- **system prompt**: only the P suffix.  `win_*`/`app_*`/`led_*` with the same P are "
              "byte-identical; `*_N` differs from `*_C` only by the verbatim DECISION GUIDANCE paragraph.",
              "- **user message**: only the `memory` field.  `state` and `recent_history` are "
              "identical across all six arms at every step.",
              "- The memory field is a list (`window`, `append`) or a dict (`ledger`); its size "
              "depends on the representation, which is the point of the R switch.", "",
              "## Consistency checks (pytest)", "",
              "- `tests/test_prompts.py::test_base_system_is_identical_for_every_arm`",
              "- `tests/test_prompts.py::test_user_messages_differ_only_in_the_memory_field`",
              "- `tests/test_prompts.py::test_over_a_whole_episode_the_arms_differ_only_in_r_and_p`",
              "- `tests/test_prompts.py::test_every_example_action_is_accepted_by_the_environment`",
              "- `tests/test_memory.py::test_ledger_is_recomputable_from_the_append_log`", ""]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
