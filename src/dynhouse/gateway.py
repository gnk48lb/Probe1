"""Magpie gateway client + JSON action protocol.

Ported from `_ref/gate_dynamic_house/agents.py` (which ran 1440 episodes
against this gateway).  The wire protocol is not reinvented: OpenAI-compatible
`POST {base}/v1/chat/completions`, temperature=0, max_tokens=4000 with the
output budget doubled on an empty (reasoning-exhausted) reply up to 16000, and
a hard wall-clock deadline of 150 s per request.
"""
from __future__ import annotations

import json
import os
import random
import re
import threading
import time
import urllib.error
import urllib.request
from typing import Any

from .env import ITEMS, ROOMS

ACTION_KEYS = {"move": {"action", "room"}, "pick": {"action", "item"},
               "place": {"action", "item", "room"}, "observe": {"action"},
               "ask_human": {"action", "question"}}
JSON_PATTERN = re.compile(r"\{[^{}]*\}")

DEFAULT_BASE_URL = "http://127.0.0.1:3425"
DEFAULT_MODEL = "minimax-code-global/MiniMax-M3.1-Flash"


class EmptyResponseError(ValueError):
    """The model returned no visible text (all budget spent on reasoning)."""


def api_key() -> str:
    return os.getenv("MAGPIE_API_KEY", "local")


def base_url() -> str:
    return os.getenv("MAGPIE_BASE_URL", DEFAULT_BASE_URL)


def parse_action(text: str) -> dict[str, Any]:
    """Extract exactly one valid flat JSON action, including from Markdown fences."""
    if not isinstance(text, str):
        raise ValueError("response is not text")
    stripped = text.strip().removeprefix("```json").removesuffix("```").strip()
    if stripped.startswith("[") and stripped.endswith("]"):
        raise ValueError("top-level action must be a JSON object, not an array")
    candidates = [text.strip()]
    candidates += [m.group(0) for m in JSON_PATTERN.finditer(text)]
    last_error = "no JSON object found"
    for candidate in candidates:
        try:
            value = json.loads(candidate.strip().removeprefix("```json").removesuffix("```").strip())
            if not isinstance(value, dict):
                raise ValueError("action must be a JSON object")
            name = value.get("action")
            if name not in ACTION_KEYS:
                raise ValueError("unknown action")
            if set(value) != ACTION_KEYS[name]:
                raise ValueError(f"fields for {name} must be {sorted(ACTION_KEYS[name])}")
            if name in ("move", "place") and value["room"] not in ROOMS:
                raise ValueError("unknown room")
            if name in ("pick", "place") and value["item"] not in ITEMS:
                raise ValueError("unknown item")
            if name == "ask_human" and not str(value["question"]).strip():
                raise ValueError("empty question")
            return value
        except (json.JSONDecodeError, ValueError) as exc:
            last_error = str(exc)
    raise ValueError(last_error)


def extract_text(payload: dict[str, Any]) -> str:
    """Accept both native OpenAI and translated Anthropic response shapes."""
    if isinstance(payload.get("choices"), list) and payload["choices"]:
        content = payload["choices"][0].get("message", {}).get("content", "")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return "".join(part.get("text", "") for part in content if isinstance(part, dict))
    if isinstance(payload.get("content"), list):
        return "".join(block.get("text", "") for block in payload["content"]
                       if isinstance(block, dict) and block.get("type") == "text")
    if isinstance(payload.get("content"), str):
        return payload["content"]
    raise ValueError("response contains no text content")


class MagpieClient:
    """Thread-safe client with exponential backoff on infrastructure failures."""

    def __init__(self, base_url: str = DEFAULT_BASE_URL, api_key: str = "local",
                 timeout: float = 150.0, max_retries: int = 4, max_tokens: int = 4000):
        self.url = base_url.rstrip("/") + "/v1/chat/completions"
        self.api_key, self.timeout, self.max_retries = api_key, timeout, max_retries
        self.max_tokens = max_tokens
        self.local = threading.local()

    def _post_with_deadline(self, request, timeout: float) -> str:
        """Hard wall-clock deadline.

        Magpie's socket timeout never fires on a route that keeps the connection
        alive without answering, so the socket timeout alone can hang forever.
        """
        result: dict[str, Any] = {}

        def run() -> None:
            try:
                with urllib.request.urlopen(request, timeout=timeout) as response:
                    result["body"] = response.read().decode("utf-8")
            except BaseException as exc:  # noqa: BLE001 - re-raised in the caller thread
                result["error"] = exc

        worker = threading.Thread(target=run, daemon=True)
        worker.start()
        worker.join(timeout)
        if worker.is_alive():
            raise TimeoutError(f"request exceeded the hard {timeout}s deadline")
        if "error" in result:
            raise result["error"]
        return result["body"]

    def complete(self, model: str, system: str, user: str) -> tuple[str, dict[str, Any]]:
        """One chat completion.  Returns (text, meta).  Raises RuntimeError when
        every attempt failed (the caller treats that as an infrastructure
        failure, not as an agent failure)."""
        body = {"model": model, "temperature": 0, "max_tokens": self.max_tokens,
                "messages": [{"role": "system", "content": system},
                             {"role": "user", "content": user}]}
        request = urllib.request.Request(
            self.url, data=json.dumps(body).encode("utf-8"), method="POST",
            headers={"Authorization": f"Bearer {self.api_key}",
                     "Content-Type": "application/json"})
        last_error = None
        for attempt in range(self.max_retries + 1):
            started = time.monotonic()
            try:
                payload = json.loads(self._post_with_deadline(request, self.timeout))
                text = extract_text(payload)
                if not text.strip():
                    # Thinking models can spend the whole token budget on reasoning
                    # and return an empty body. Retry with a larger budget.
                    raise EmptyResponseError("empty model text")
                usage = payload.get("usage", {}) or {}
                meta = {"latency_ms": round((time.monotonic() - started) * 1000),
                        "input_tokens": usage.get("prompt_tokens", usage.get("input_tokens")),
                        "output_tokens": usage.get("completion_tokens", usage.get("output_tokens")),
                        "total_tokens": usage.get("total_tokens"),
                        "http_status": 200, "request_retries": attempt}
                return text, meta
            except EmptyResponseError as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                body["max_tokens"] = min(int(body["max_tokens"] * 2), 16000)
                if attempt < self.max_retries:
                    time.sleep((2 ** attempt) * 0.5 + random.random() * 0.2)
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError, OSError) as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                if attempt < self.max_retries:
                    time.sleep((2 ** attempt) * 0.5 + random.random() * 0.2)
        raise RuntimeError(f"Magpie request failed after {self.max_retries + 1} attempts: {last_error}")


def model_catalog(base: str = DEFAULT_BASE_URL, key: str = "local") -> list[dict[str, Any]]:
    request = urllib.request.Request(base.rstrip("/") + "/v1/models",
                                     headers={"Authorization": f"Bearer {key}"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))["data"]
