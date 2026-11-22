"""Probe 1c supplement (post-hoc).

    uv run python -m dynhouse.supplement_1c --results results_1c --out results_1c/supplement.md

Everything here is **post-hoc**: it is computed after the 1c verdict was known
and it changes no verdict.  It exists because the review of the 1c report found
that two of its statements needed the wrong denominator:

* the repeat-ask flag looked like a failure mechanism (95% of the failures
  against 55% of the successes) but it tracks the *length* of the episode;
  the table below stratifies it by episode length;
* the safety definition needed to be stated once and for all: the event
  definition (`safety_count > 0`) and the `failure_reason` definition give
  different numbers, because `_finish` can be overwritten by the budget
  running out in the same step.

Nothing in the preregistered analysis is touched by this file.
"""
from __future__ import annotations

import argparse
import gzip
import json
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np

from .scripted import POLICIES, evaluate

ROOT = Path(__file__).resolve().parent.parent.parent
ARMS = ("led_C", "app_C")
P_MAIN = 0.2
N_BOOT = 10000
BOOT_SEED = 20261119
BANDS = ((1, 14), (15, 19), (20, 24), (25, 30))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def latest_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    latest = {}
    for row in rows:
        latest[(row["arm"], row["disturbance_p"], row["seed"])] = row
    return list(latest.values())


def paired_ci(values_a: dict[int, float], values_b: dict[int, float], seeds: list[int]):
    rng = np.random.default_rng(BOOT_SEED)
    index = rng.integers(0, len(seeds), size=(N_BOOT, len(seeds)))
    diff = np.array([values_a[s] - values_b[s] for s in seeds], dtype=float)
    samples = diff[index].mean(axis=1)
    return (float(diff.mean()), float(np.percentile(samples, 2.5)),
            float(np.percentile(samples, 97.5)))


def md_table(header: list[str], rows: list[list[str]]) -> str:
    out = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    out += ["| " + " | ".join(r) + " |" for r in rows]
    return "\n".join(out)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", type=Path, default=ROOT / "results_1c")
    parser.add_argument("--out", type=Path, default=ROOT / "results_1c" / "supplement.md")
    args = parser.parse_args()

    rows = latest_rows(load_jsonl(args.results / "episodes.jsonl"))
    cells = {(r["arm"], r["disturbance_p"], r["seed"]): r for r in rows}
    seeds = sorted({k[2] for k in cells if k[0] in ARMS and k[1] == P_MAIN})

    repeat_ask: set[tuple] = set()
    traces_path = args.results / "traces_1c.jsonl.gz"
    if traces_path.exists():
        with gzip.open(traces_path, "rt", encoding="utf-8") as handle:
            for line in handle:
                t = json.loads(line)
                if t.get("failure_reason") == "invalid_action" and "ask limit" in (t.get("message") or ""):
                    repeat_ask.add((t["arm"], t["disturbance_p"], t["seed"]))

    # ---- 1. the repeat ask, stratified by episode length -------------------- #
    strat_rows = []
    for arm in ARMS:
        for lo, hi in BANDS:
            cell = [cells[(arm, P_MAIN, s)] for s in seeds
                    if lo <= cells[(arm, P_MAIN, s)]["steps"] <= hi]
            if not cell:
                continue
            def rate(sub: list[dict[str, Any]]) -> str:
                if not sub:
                    return "n/a"
                hits = sum(1 for r in sub if (r["arm"], r["disturbance_p"], r["seed"]) in repeat_ask)
                return f"{100 * hits / len(sub):.0f}% ({hits}/{len(sub)})"
            succ = [r for r in cell if r["success"]]
            fail = [r for r in cell if not r["success"]]
            strat_rows.append([arm, f"{lo}-{hi}", str(len(cell)), rate(cell),
                               f"{len(succ)} / {rate(succ)}", f"{len(fail)} / {rate(fail)}"])
    strat_table = md_table(
        ["arm", "episode steps", "episodes", "repeat ask (all)", "successes (n / rate)",
         "failures (n / rate)"], strat_rows)

    # ---- 2. the two safety definitions -------------------------------------- #
    event = {arm: {s: float(cells[(arm, P_MAIN, s)]["safety_count"] > 0) for s in seeds}
             for arm in ARMS}
    reason = {arm: {s: float(cells[(arm, P_MAIN, s)].get("failure_reason") == "safety_violation")
                     for s in seeds} for arm in ARMS}
    ev_point, ev_lo, ev_hi = paired_ci(event["led_C"], event["app_C"], seeds)
    fr_point, fr_lo, fr_hi = paired_ci(reason["led_C"], reason["app_C"], seeds)
    safety_rows = [
        ["event (`safety_count > 0`)", f"{sum(event['led_C'].values()):.0f}", f"{100 * sum(event['led_C'].values()) / len(seeds):.1f}%",
         f"{sum(event['app_C'].values()):.0f}", f"{100 * sum(event['app_C'].values()) / len(seeds):.1f}%",
         f"{ev_point * 100:+.2f}", f"[{ev_lo * 100:+.2f}, {ev_hi * 100:+.2f}]"],
        ["`failure_reason == \"safety_violation\"`", f"{sum(reason['led_C'].values()):.0f}", f"{100 * sum(reason['led_C'].values()) / len(seeds):.1f}%",
         f"{sum(reason['app_C'].values()):.0f}", f"{100 * sum(reason['app_C'].values()) / len(seeds):.1f}%",
         f"{fr_point * 100:+.2f}", f"[{fr_lo * 100:+.2f}, {fr_hi * 100:+.2f}]"],
        ["overwritten by `_finish` (event minus reason)",
         f"{sum(event['led_C'].values()) - sum(reason['led_C'].values()):.0f}", "",
         f"{sum(event['app_C'].values()) - sum(reason['app_C'].values()):.0f}", "", "", ""],
    ]
    safety_table = md_table(
        ["definition", "led_C count", "led_C rate", "app_C count", "app_C rate",
         "difference (pp)", "95% CI"], safety_rows)

    # ---- 3. the budget-exhaustion rate with and without the safety episodes -- #
    budget_rows = []
    for arm in ARMS:
        total = len(seeds)
        be = sum(1 for s in seeds if cells[(arm, P_MAIN, s)].get("failure_reason") == "budget_exhausted")
        be_clean = sum(1 for s in seeds
                       if cells[(arm, P_MAIN, s)].get("failure_reason") == "budget_exhausted"
                       and cells[(arm, P_MAIN, s)]["safety_count"] == 0)
        safety = sum(1 for s in seeds if cells[(arm, P_MAIN, s)]["safety_count"] > 0)
        succeeded = sum(1 for s in seeds if cells[(arm, P_MAIN, s)]["success"])
        budget_rows.append([arm, f"{be} / {100 * be / total:.1f}%",
                            f"{be_clean} / {100 * be_clean / total:.1f}%",
                            f"{safety} / {100 * safety / total:.1f}%", str(succeeded)])
    budget_table = md_table(
        ["arm", "budget exhausted (all episodes)", "budget exhausted (safety episodes removed)",
         "episodes with a safety event", "episodes that succeeded"], budget_rows)

    # ---- 4. the stale-evidence missed grasps ---------------------------------- #
    stale_rows = []
    for arm in ARMS:
        n_ep = n_fail = 0
        for s in seeds:
            r = cells[(arm, P_MAIN, s)]
            stale = [p for p in r["pick_records"]
                     if not p["ok"] and p.get("evidence_age") is not None and p["evidence_age"] >= 2]
            if stale:
                n_ep += 1
                n_fail += (not r["success"])
        stale_rows.append([arm, str(n_ep), str(n_fail),
                           f"{100 * n_fail / n_ep:.1f}%" if n_ep else "n/a"])
    stale_table = md_table(
        ["arm", "episodes with a stale-evidence missed grasp", "of which failed",
         "conditional failure rate"], stale_rows)

    # ---- 5. the scripted reference lines on the preregistered seed range ------ #
    script_rows = []
    for policy in POLICIES:
        wide = evaluate(policy, seeds, P_MAIN, max_asks=1, freeze_asked=True)
        narrow = evaluate(policy, range(4000, 4300), P_MAIN, max_asks=1, freeze_asked=True)
        script_rows.append([policy, f"{wide['success']:.1f}", f"{wide['cost']:.1f}",
                            f"{wide['unsafe']:.1f}%", f"{narrow['success']:.1f}",
                            f"{narrow['cost']:.1f}", f"{narrow['unsafe']:.1f}%"])
    script_table = md_table(
        ["policy", "SR% (600 seeds)", "cost", "unsafe%", "SR% (seeds 4000-4299)", "cost",
         "unsafe%"], script_rows)

    text = "\n".join([
        "# Probe 1c supplement (post-hoc)",
        "",
        "**Everything in this file is post-hoc.**  It was computed after the 1c verdict was",
        "known, it changes no verdict, and it is not part of the preregistered analysis",
        "(`analyze_1c.py` and `prereg_1c.lock` are untouched; the lock still verifies).",
        "It exists because the independent review of `results_1c/report.md` found that two of",
        "its statements needed the wrong denominator.",
        "",
        "## 1. The repeat ask, stratified by episode length",
        "",
        "The unstratified numbers (95% of the failures against 55% of the successes) are an",
        "artefact of the episode length: the repeat ask needs a second ask to have been",
        "spent, and long episodes are both more likely to repeat-ask and more likely to",
        "fail.  Within a length band the two rates are nearly the same.",
        "",
        strat_table,
        "",
        "## 2. The two safety definitions",
        "",
        "`_finish` can be overwritten by the budget running out in the same step, so a safety",
        "violation is sometimes recorded as `budget_exhausted`.  The event definition",
        "(`safety_count > 0`) is the primary one; the `failure_reason` definition is a",
        "sensitivity analysis.",
        "",
        safety_table,
        "",
        "## 3. Budget exhaustion with and without the safety episodes",
        "",
        budget_table,
        "",
        "## 4. The stale-evidence missed grasps",
        "",
        stale_table,
        "",
        "## 5. The scripted reference lines on both seed ranges",
        "",
        "`PREREG_1C.md` section 2.7 asked for the scripted lines on seeds 4000-4299; the",
        "1c report used all 600 analysed seeds.  Both are given here.",
        "",
        script_table,
        "",
    ])
    args.out.write_text(text, encoding="utf-8")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
