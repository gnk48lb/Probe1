"""M1: probe the Magpie gateway.

* `GET /v1/models` -- is the main model in the catalog?
* the same request body under concurrency 1 / 4 / 8 / 10 / 12 -- throughput,
  latency, error rate; the runner uses the highest concurrency with zero errors.
* the shape of `usage` and whether the reply carries a reasoning block.

    uv run python -m dynhouse.probe_gateway --out docs/GATEWAY.md
"""
from __future__ import annotations

import argparse
import json
import statistics
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from .env import GRAPH, ITEMS, DynamicHouseEnv
from .gateway import DEFAULT_BASE_URL, DEFAULT_MODEL, MagpieClient, api_key, base_url, model_catalog
from .memory import MemoryBundle
from .prompts import BASE_SYSTEM, build_user_message, system_prompt


def representative_prompt() -> tuple[str, str]:
    """A prompt of the same size/shape the experiment actually sends."""
    env = DynamicHouseEnv(1000, 0.2, n_targets=3)
    memory = MemoryBundle("ledger", env.inspection, env.inspection_gap)
    memory.observe(1, "Kitchen", sorted(env.room_items["Kitchen"]))
    memory.observe(2, "Bedroom", sorted(env.room_items["Bedroom"]))
    history = [{"step": 1, "action": {"action": "move", "room": "Kitchen"},
                "result": "Moved to Kitchen."},
               {"step": 2, "action": {"action": "observe"},
                "result": "Observed Kitchen: coffee_mug, frying_pan, hot_kettle, kitchen_knife."}]
    return system_prompt("N"), build_user_message(env, history, memory.view(env.step_count))


def one_request(client: MagpieClient, model: str, system: str, user: str) -> dict[str, Any]:
    started = time.monotonic()
    try:
        text, meta = client.complete(model, system, user)
        return {"ok": True, "latency_s": time.monotonic() - started, "meta": meta,
                "text_len": len(text), "text_head": text[:400]}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "latency_s": time.monotonic() - started, "error": repr(exc)}


def sweep(client: MagpieClient, model: str, system: str, user: str,
          concurrencies: list[int], requests: int) -> list[dict[str, Any]]:
    results = []
    for concurrency in concurrencies:
        started = time.monotonic()
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            rows = list(pool.map(lambda _: one_request(client, model, system, user),
                                 range(requests)))
        elapsed = time.monotonic() - started
        latencies = [r["latency_s"] for r in rows if r["ok"]]
        errors = [r for r in rows if not r["ok"]]
        results.append({
            "concurrency": concurrency, "requests": requests,
            "elapsed_s": round(elapsed, 2),
            "throughput_req_per_min": round(len(rows) / elapsed * 60, 1),
            "latency_mean_s": round(statistics.mean(latencies), 3) if latencies else None,
            "latency_p50_s": round(statistics.median(latencies), 3) if latencies else None,
            "latency_max_s": round(max(latencies), 3) if latencies else None,
            "errors": len(errors),
            "error_rate": len(errors) / len(rows),
            "first_error": errors[0].get("error") if errors else None,
            "sample_meta": next((r["meta"] for r in rows if r["ok"]), None),
            "sample_text_head": next((r["text_head"] for r in rows if r["ok"]), None),
        })
        print(f"concurrency={concurrency:3d}  {results[-1]['throughput_req_per_min']:6.1f} req/min  "
              f"latency mean={results[-1]['latency_mean_s']}s max={results[-1]['latency_max_s']}s  "
              f"errors={results[-1]['errors']}", flush=True)
    return results


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=base_url())
    parser.add_argument("--api-key", default=api_key())
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--concurrencies", default="1,4,8,10,12")
    parser.add_argument("--requests", type=int, default=10)
    parser.add_argument("--out", type=Path, default=Path("docs/GATEWAY.md"))
    args = parser.parse_args()

    print(f"base_url={args.base_url}", flush=True)
    catalog = model_catalog(args.base_url, args.api_key)
    ids = sorted(entry["id"] for entry in catalog)
    print(f"catalog: {len(ids)} models", flush=True)
    if args.model not in ids:
        print(f"ERROR: main model {args.model!r} is NOT in the catalog.", flush=True)
        print("candidates containing 'minimax':", [i for i in ids if "minimax" in i.lower()], flush=True)
        raise SystemExit(3)
    print(f"main model {args.model!r} is in the catalog", flush=True)

    system, user = representative_prompt()
    print(f"prompt sizes: system={len(system)} chars, user={len(user)} chars", flush=True)

    client = MagpieClient(args.base_url, args.api_key, timeout=150.0, max_retries=0)
    concurrencies = [int(c) for c in args.concurrencies.split(",")]
    rows = sweep(client, args.model, system, user, concurrencies, args.requests)

    zero_error = [r for r in rows if r["errors"] == 0]
    chosen = max(zero_error, key=lambda r: r["throughput_req_per_min"]) if zero_error else None

    meta = chosen["sample_meta"] if chosen else rows[0]["sample_meta"]
    head = chosen["sample_text_head"] if chosen else rows[0]["sample_text_head"]
    usage_keys = sorted((meta or {}).keys())

    lines = ["# M1 -- Magpie gateway probe", "",
             f"- date: {time.strftime('%Y-%m-%d %H:%M:%S')}",
             f"- base_url: `{args.base_url}`",
             f"- main model: `{args.model}` (present in `/v1/models`: yes)",
             f"- catalog size: {len(ids)} models",
             f"- request body: system {len(system)} chars + user {len(user)} chars, "
             f"temperature=0, max_tokens=4000",
             "", "## Concurrency sweep", "",
             "| concurrency | throughput (req/min) | latency mean | p50 | max | errors |",
             "|---|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r['concurrency']} | {r['throughput_req_per_min']} | "
                     f"{r['latency_mean_s']} s | {r['latency_p50_s']} s | {r['latency_max_s']} s | "
                     f"{r['errors']} |")
    lines += ["", f"**Chosen concurrency: {chosen['concurrency'] if chosen else 'none'}** "
                  f"(highest zero-error throughput: "
                  f"{chosen['throughput_req_per_min'] if chosen else 'n/a'} req/min).", "",
              "## usage shape", "", "```", json.dumps(meta, ensure_ascii=False, indent=2), "```", "",
              f"- usage/meta keys: {usage_keys}",
              "- reasoning block present in the reply: see the sample below", ""]
    errors = [(r["concurrency"], r["first_error"]) for r in rows if r["errors"]]
    if errors:
        lines += ["## first errors seen", ""]
        lines += [f"- concurrency {c}: `{e}`" for c, e in errors]
        lines += [""]
    lines += ["## sample reply head", "", "```", (head or "")[:400], "```", ""]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {args.out}", flush=True)


if __name__ == "__main__":
    main()
