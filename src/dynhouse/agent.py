"""One episode of one arm: build the prompt, call the model, apply the action.

Per step: exactly one LLM call.  A response that does not parse is retried
with the *same* request (up to `format_retries` extra times, not consuming a
step); if it still does not parse, the step is spent on a deliberately invalid
action (0 budget, 1 step), exactly like any other invalid action.
"""
from __future__ import annotations

import time
from typing import Any

from .env import ITEMS, DynamicHouseEnv
from .gateway import MagpieClient, parse_action
from .memory import MemoryBundle
from .prompts import build_user_message, system_prompt


def invalid_fallback_action(env: DynamicHouseEnv) -> dict[str, Any]:
    """A syntactically valid action the environment always rejects.

    `place` of an item that is not held is rejected by the environment with
    "INVALID: cannot place an item that is not held." -> 0 budget, 1 step.
    """
    for item in ITEMS:
        if item not in env.held:
            return {"action": "place", "item": item, "room": env.current_room}
    raise RuntimeError("every item is held; no invalid-action fallback available")


class ArmAgent:
    """Agent for one (seed, p, arm) cell.  `representation` is R, `policy_prompt` is P."""

    def __init__(self, env: DynamicHouseEnv, client: MagpieClient, model: str,
                 representation: str, policy_prompt: str, format_retries: int = 2):
        self.env, self.client, self.model = env, client, model
        self.representation, self.policy_prompt = representation, policy_prompt
        self.format_retries = format_retries
        self.system = system_prompt(policy_prompt)
        self.memory = MemoryBundle(representation, env.inspection, env.inspection_gap)
        self.history: list[dict[str, Any]] = []
        self.exchanges: list[dict[str, Any]] = []
        self.trace: list[dict[str, Any]] = []
        self.usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0,
                      "llm_calls": 0, "request_retries": 0, "format_retries": 0,
                      "format_failures": 0}
        self.invalid_actions = 0
        self.pick_records: list[dict[str, Any]] = []

    # -- prompting --------------------------------------------------------- #
    def user_message(self) -> str:
        return build_user_message(self.env, self.history, self.memory.view(self.env.step_count))

    # -- one decision ------------------------------------------------------ #
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
                # Same request, resent: it does not consume a step.
                self.usage["llm_calls"] += 1
                self.usage["format_retries"] += 1
                self.usage["request_retries"] += meta.get("request_retries", 0)
                for key in ("input_tokens", "output_tokens", "total_tokens"):
                    self.usage[key] += meta.get(key) or 0
                text, meta = self.client.complete(self.model, system, user)
            try:
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

    # -- the episode ------------------------------------------------------- #
    def run(self) -> dict[str, Any]:
        started = time.monotonic()
        while not self.env.done:
            step = self.env.step_count + 1
            decision = self.decide()
            action = decision["action"]
            outcome = self.env.step(action)
            self._update(action, outcome)
            self.trace.append({
                "step": step, "action": action, "ok": outcome["ok"],
                "message": outcome["message"], "cost": outcome["cost"],
                "failure_reason": outcome.get("failure_reason"),
                "disturbance": outcome.get("disturbance"),
                "parse_error": decision["parse_error"],
            })
        summary = self.env.episode_summary()
        summary["terminal_reason"] = self.env.failure_reason
        summary["invalid_actions"] = self.invalid_actions
        summary["usage"] = dict(self.usage)
        summary["wall_time_s"] = round(time.monotonic() - started, 3)
        summary["pick_records"] = self.pick_records
        return summary

    # -- memory bookkeeping ------------------------------------------------ #
    def _update(self, action: dict[str, Any], outcome: dict[str, Any]) -> None:
        step = outcome["step"]
        name = action["action"]
        observation = outcome.get("observation")
        if observation:
            self.memory.observe(step, observation["room"], observation["items"])
        if name == "ask_human" and outcome.get("answer"):
            self.memory.ask_human(step, outcome["item"], outcome["location"])
        if name == "pick":
            age = self.memory.evidence.age(action["item"], step)
            self.pick_records.append({"step": step, "item": action["item"], "ok": outcome["ok"],
                                      "evidence_age": age, "room": self.env.current_room,
                                      "failure_reason": outcome.get("failure_reason")})
            if outcome["ok"]:
                self.memory.pick_succeeded(step, action["item"])
            else:
                self.memory.pick_failed(step, action["item"], self.env.current_room)
        if not outcome["ok"] and outcome.get("failure_reason") == "invalid_action":
            self.invalid_actions += 1
        self.history.append({"step": step, "action": action, "result": outcome["message"]})
