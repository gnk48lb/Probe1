"""Probe 1b analysis: estimators, the paired bootstrap, verdicts and mechanism metrics.

    uv run python -m dynhouse.analyze_1b --results results_1b

Everything is recomputed from `episodes.jsonl` and `traces.jsonl`; nothing is
taken from a previous run.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from .env import ITEMS  # noqa: E402
from .scripted import POLICIES, evaluate  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent.parent
PS = (0.1, 0.2, 0.4)
ARMS = ("base", "hint", "shield", "both", "auto")
CORE = ("base", "hint", "shield", "both", "auto")
DELTA = 5.0
N_BOOT = 10000
BOOT_SEED = 20261118

RESULTS = ROOT / "results_1b"
TABLES = RESULTS / "tables"
FIGURES = RESULTS / "figures"


# --------------------------------------------------------------------------- #
# statistics (pure, so the unit tests can pin them)
# --------------------------------------------------------------------------- #
def complete_seeds(rows: list[dict[str, Any]], arms: tuple[str, ...],
                   ps: tuple[float, ...]) -> list[int]:
    """Seeds where every arm of the comparison is complete at every p."""
    keys = {(r["arm"], r["disturbance_p"], r["seed"]) for r in rows}
    seeds = sorted({r["seed"] for r in rows})
    return [s for s in seeds if all((arm, p, s) in keys for arm in arms for p in ps)]


def paired_bootstrap(diffs: dict[str, np.ndarray], seeds: list[int],
                     n_boot: int = N_BOOT, rng_seed: int = BOOT_SEED) -> np.ndarray:
    """Bootstrap distribution of the mean difference over cells.

    The resampling unit is the seed: one resampled seed list is shared by every
    cell, so all contrasts stay paired.  `diffs` maps a cell name to the
    per-seed difference (in percentage points).
    """
    rng = np.random.default_rng(rng_seed)
    index = rng.integers(0, len(seeds), size=(n_boot, len(seeds)))
    samples = np.zeros(n_boot)
    count = 0
    for array in diffs.values():
        samples += array[index].mean(axis=1)
        count += 1
    return samples / count


def percentile_ci(samples: np.ndarray) -> tuple[float, float]:
    return float(np.percentile(samples, 2.5)), float(np.percentile(samples, 97.5))


def verdict(point: float, samples: np.ndarray, delta: float = DELTA) -> tuple[str, float, float]:
    """The preregistered decision rule (delta = 5 pp)."""
    lo, hi = percentile_ci(samples)
    if point >= delta and lo > 0:
        return "HELPS", lo, hi
    if hi < delta:
        return "NOT_NEEDED", lo, hi
    return "INCONCLUSIVE", lo, hi


def success_map(rows: list[dict[str, Any]]) -> dict[tuple[str, float], dict[int, float]]:
    out: dict[tuple[str, float], dict[int, float]] = defaultdict(dict)
    for row in rows:
        out[(row["arm"], row["disturbance_p"])][row["seed"]] = float(row["success"])
    return out


def estimate(rows: list[dict[str, Any]], arm_a: str, arm_b: str,
             ps: tuple[float, ...] = PS) -> dict[str, Any]:
    """mean_p [SR(arm_a, p) - SR(arm_b, p)] with a paired bootstrap."""
    seeds = complete_seeds(rows, (arm_a, arm_b), ps)
    if not seeds:
        return {"point": float("nan"), "samples": np.array([]), "n": 0,
                "lo": float("nan"), "hi": float("nan"), "label": "NO_DATA",
                "per_p": {}}
    success = success_map(rows)
    diffs = {}
    per_p = {}
    for p in ps:
        a, b = success[(arm_a, p)], success[(arm_b, p)]
        diff = np.array([(a[s] - b[s]) * 100 for s in seeds])
        diffs[f"{arm_a}-{arm_b}-p{p}"] = diff
        per_p[p] = float(diff.mean())
    samples = paired_bootstrap(diffs, seeds)
    point = float(np.mean(list(per_p.values())))
    label, lo, hi = verdict(point, samples)
    return {"point": point, "samples": samples, "n": len(seeds), "lo": lo, "hi": hi,
            "label": label, "per_p": per_p}


# --------------------------------------------------------------------------- #
# loading
# --------------------------------------------------------------------------- #
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


def latest_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Newest row per cell (a repaired episode supersedes its failure)."""
    latest = {}
    for row in rows:
        latest[(row["arm"], row["disturbance_p"], row["seed"])] = row
    return list(latest.values())


def md_table(header: list[str], rows: list[list[str]]) -> str:
    out = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    out += ["| " + " | ".join(r) + " |" for r in rows]
    return "\n".join(out)


# --------------------------------------------------------------------------- #
# mechanism metrics
# --------------------------------------------------------------------------- #
FLAG_ORDER = ["competing_pick_fail", "stale_pick_fail", "high_risk_should_verify_pick",
              "repeat_ask", "budget_exhausted", "safety_violation", "never_used_ask"]
FATAL_PRIORITY = ["safety_violation", "stale_pick_fail", "controller_block", "budget_exhausted"]


def episode_flags(row: dict[str, Any], invalid_ask: bool) -> dict[str, bool]:
    """Non-exclusive failure flags for one episode."""
    picks = row.get("pick_records", []) or []
    missed = [p for p in picks if not p["ok"]]
    competing = [p for p in missed if (p.get("evidence_age") or 99) <= 1]
    stale = [p for p in missed if (p.get("evidence_age") or 0) >= 2]
    should_verify = [p for p in picks
                     if p.get("risk") == "high_risk" and p.get("rule_advice") == "verify"]
    flags = {
        "competing_pick_fail": bool(competing),
        "stale_pick_fail": bool(stale),
        "high_risk_should_verify_pick": bool(should_verify),
        "repeat_ask": bool(invalid_ask),
        "budget_exhausted": row.get("failure_reason") == "budget_exhausted",
        "safety_violation": row.get("safety_count", 0) > 0,
        "never_used_ask": row.get("ask_count", 0) == 0,
    }
    return flags


def first_fatal_event(row: dict[str, Any], trace_rows: list[dict[str, Any]],
                      flags: dict[str, bool]) -> tuple[int | None, str | None]:
    """The first event that pushed the episode onto its failure path.

    Defined once, here, and never adjusted afterwards: the earliest step at
    which one of [safety_violation, stale_pick_fail, controller_block,
    budget_exhausted] occurred.  Ties inside one step are broken by that
    order.  The repeat ask is NOT part of this list: it is a symptom of not
    tracking the ask budget, reported separately as a flag.
    """
    candidates: list[tuple[int, int, str]] = []
    order = {name: i for i, name in enumerate(FATAL_PRIORITY)}
    for pick in row.get("pick_records", []) or []:
        if not pick["ok"] and (pick.get("evidence_age") or 0) >= 2:
            candidates.append((pick["step"], order["stale_pick_fail"], "stale_pick_fail"))
        if not pick["ok"] and pick.get("failure_reason") == "safety_violation":
            candidates.append((pick["step"], order["safety_violation"], "safety_violation"))
    for step_row in trace_rows:
        if step_row.get("controller_blocked"):
            candidates.append((step_row["step"], order["controller_block"], "controller_block"))
    if flags["budget_exhausted"]:
        candidates.append((row.get("steps", 0), order["budget_exhausted"], "budget_exhausted"))
    if not candidates:
        return None, None
    candidates.sort()
    step, _, name = candidates[0]
    return step, name


# --------------------------------------------------------------------------- #
# the analysis
# --------------------------------------------------------------------------- #
def analyse(results_dir: Path) -> dict[str, Any]:
    TABLES.mkdir(parents=True, exist_ok=True)
    FIGURES.mkdir(parents=True, exist_ok=True)
    raw_rows = load_jsonl(results_dir / "episodes.jsonl")
    rows = [r for r in latest_rows(raw_rows)
            if not r.get("infra_failed") and r.get("failure_reason") != "infrastructure_failure"
            and r.get("success") is not None]
    infra_events = sum(1 for r in raw_rows if r.get("infra_failed")
                       or r.get("failure_reason") == "infrastructure_failure")

    traces = load_jsonl(results_dir / "traces.jsonl")
    traces_by_cell: dict[tuple, list[dict[str, Any]]] = defaultdict(list)
    invalid_ask_by_cell: dict[tuple, bool] = defaultdict(bool)
    for t in traces:
        key = (t["arm"], t["disturbance_p"], t["seed"])
        traces_by_cell[key].append(t)
        if t.get("failure_reason") == "invalid_action" and "ask limit" in (t.get("message") or ""):
            invalid_ask_by_cell[key] = True

    # ---- arms table ------------------------------------------------------ #
    arm_rows = []
    cell_stats: dict[tuple[str, float], dict[str, float]] = {}
    for arm in ARMS + ("base_old",):
        for p in sorted({r["disturbance_p"] for r in rows if r["arm"] == arm}):
            cell = [r for r in rows if r["arm"] == arm and r["disturbance_p"] == p]
            if not cell:
                continue
            n = len(cell)
            success = 100 * sum(r["success"] for r in cell) / n
            cell_stats[(arm, p)] = {
                "n": n, "success": success,
                "cost": float(np.mean([r["total_cost"] for r in cell])),
                "safety": 100 * sum(1 for r in cell if r.get("safety_count", 0) > 0) / n,
                "steps": float(np.mean([r["steps"] for r in cell])),
                "blocked": float(np.mean([r.get("blocked_count", 0) or 0 for r in cell])),
                "calls": float(np.mean([(r.get("usage") or {}).get("llm_calls", 0) for r in cell])),
                "tokens": float(np.mean([(r.get("usage") or {}).get("total_tokens", 0) for r in cell])),
                "stale_pick": 100 * sum(1 for r in cell if r.get("stale_pick_count", 0)) / n,
                "invalid": float(np.mean([r.get("invalid_actions", 0) or 0 for r in cell])),
            }
            arm_rows.append([arm, f"{p}", str(n), f"{success:.1f}", f"{cell_stats[(arm, p)]['cost']:.1f}",
                             f"{cell_stats[(arm, p)]['safety']:.1f}", f"{cell_stats[(arm, p)]['steps']:.1f}",
                             f"{cell_stats[(arm, p)]['blocked']:.2f}", f"{cell_stats[(arm, p)]['calls']:.1f}",
                             f"{cell_stats[(arm, p)]['tokens']:.0f}",
                             f"{cell_stats[(arm, p)]['stale_pick']:.1f}",
                             f"{cell_stats[(arm, p)]['invalid']:.2f}"])
    arms_table = md_table(["arm", "p", "n", "SR%", "cost", "safety%", "steps", "blocked",
                            "llm_calls", "tokens", "stale_pick%", "invalid"], arm_rows)
    (TABLES / "arms.md").write_text(arms_table + "\n", encoding="utf-8")

    # ---- estimators ------------------------------------------------------- #
    contrasts = [("both", "base", "G_both (primary)"), ("auto", "base", "PC (positive control)"),
                 ("hint", "base", "G_hint"), ("shield", "base", "G_shield"),
                 ("both", "hint", "both - hint"), ("both", "shield", "both - shield"),
                 ("auto", "both", "auto - both")]
    results = {}
    est_rows = []
    for arm_a, arm_b, label in contrasts:
        est = estimate(rows, arm_a, arm_b)
        results[label] = est
        per_p = " / ".join(f"{est['per_p'].get(p, float('nan')):+.1f}" for p in PS)
        est_rows.append([label, f"{arm_a} - {arm_b}", str(est["n"]),
                         f"{est['point']:+.1f}", f"[{est['lo']:+.1f}, {est['hi']:+.1f}]",
                         est["label"], per_p])
    est_table = md_table(["estimator", "contrast", "N seeds", "effect (pp)", "95% CI",
                           "verdict", "per p (0.1 / 0.2 / 0.4)"], est_rows)
    (TABLES / "estimators.md").write_text(est_table + "\n", encoding="utf-8")

    # instrument check
    pc = results["PC (positive control)"]
    primary = results["G_both (primary)"]
    instrument_ok = pc["label"] == "HELPS"
    if instrument_ok:
        narrative = ("PC=HELPS and G_both=HELPS -> harness gating recovers part of the gap "
                     "(the paper's main line); PC=HELPS and G_both otherwise -> the LLM cannot "
                     "use advice or a shield, only full delegation works (the 'controller "
                     "permission gradient' story)")
    else:
        narrative = ("PC is not HELPS -> INSTRUMENT_FAILED: no 'the controller does not help' "
                     "reading of hint / shield / both is allowed; stop and diagnose")
    (TABLES / "interpretation.md").write_text(
        md_table(["PC verdict", "G_both verdict", "reading"],
                 [[pc["label"], primary["label"], narrative]]) + "\n", encoding="utf-8")

    # ---- per-p main table -------------------------------------------------- #
    per_p_rows = []
    for p in PS:
        for arm in ARMS:
            key = (arm, p)
            if key not in cell_stats:
                continue
            st = cell_stats[key]
            per_p_rows.append([f"{p}", arm, f"{st['success']:.1f}", f"{st['cost']:.1f}",
                               f"{st['safety']:.1f}", f"{st['blocked']:.2f}", str(st["n"])])
    (TABLES / "main_results.md").write_text(
        md_table(["p", "arm", "SR%", "cost", "safety%", "blocked", "n"], per_p_rows) + "\n",
        encoding="utf-8")

    # ---- mechanism metrics -------------------------------------------------- #
    mech_rows = []
    for arm in ARMS:
        cell = [r for r in rows if r["arm"] == arm]
        if not cell:
            continue
        verifies = [p for r in cell for p in (r.get("pick_records") or [])
                    if p.get("rule_advice") == "verify"]
        checked = sum(1 for p in verifies if p.get("checked_before_pick"))
        hr_should = sum(1 for r in cell for p in (r.get("pick_records") or [])
                        if p.get("risk") == "high_risk" and p.get("rule_advice") == "verify")
        recommendations = sum(r.get("recommendations", 0) or 0 for r in cell)
        overrides = sum(r.get("overrides", 0) or 0 for r in cell)
        mech_rows.append([
            arm, str(len(cell)),
            f"{100 * checked / max(len(verifies), 1):.1f}%" if verifies else "n/a",
            f"{len(verifies)}",
            f"{hr_should}",
            f"{100 * overrides / max(recommendations, 1):.1f}%" if recommendations else "n/a",
            f"{recommendations}",
            f"{100 * sum(1 for r in cell if r.get('blocked_count', 0)) / len(cell):.1f}%",
        ])
    mech_table = md_table(
        ["arm", "episodes", "advice verify -> checked before pick", "verify picks",
         "high-risk should-verify picks", "auto override rate", "recommendations",
         "episodes with a block"], mech_rows)
    (TABLES / "mechanism.md").write_text(mech_table + "\n", encoding="utf-8")

    # budget by action type, success vs failure
    budget_rows = []
    for arm in ARMS:
        for outcome, label in ((True, "success"), (False, "failure")):
            cell = [r for r in rows if r["arm"] == arm and bool(r["success"]) is outcome]
            if not cell:
                continue
            totals = Counter()
            for r in cell:
                totals.update(r.get("budget_by_action") or {})
            n = len(cell)
            budget_rows.append([arm, label, str(n)] + [f"{totals.get(a, 0) / n:.2f}"
                                                       for a in ("move", "observe", "ask_human",
                                                                 "pick", "place")])
    budget_table = md_table(["arm", "outcome", "episodes", "move", "observe", "ask_human",
                             "pick", "place"], budget_rows)
    (TABLES / "budget_by_action.md").write_text(budget_table + "\n", encoding="utf-8")

    # ---- failure analysis (flags + baselines) -------------------------------- #
    flag_rows = []
    for arm in ARMS:
        cell = [r for r in rows if r["arm"] == arm]
        failed = [r for r in cell if not r["success"]]
        succeeded = [r for r in cell if r["success"]]
        f_flags = [episode_flags(r, invalid_ask_by_cell.get((r["arm"], r["disturbance_p"], r["seed"]), False))
                   for r in failed]
        s_flags = [episode_flags(r, invalid_ask_by_cell.get((r["arm"], r["disturbance_p"], r["seed"]), False))
                   for r in succeeded]
        for name in FLAG_ORDER:
            f_count = sum(1 for f in f_flags if f[name])
            s_count = sum(1 for f in s_flags if f[name])
            f_share = 100 * f_count / max(len(failed), 1)
            s_share = 100 * s_count / max(len(succeeded), 1)
            risk = (f_share / s_share) if s_share > 0 else float("inf") if f_share > 0 else float("nan")
            flag_rows.append([arm, name, f"{f_count}/{len(failed)}", f"{f_share:.1f}%",
                              f"{s_count}/{len(succeeded)}", f"{s_share:.1f}%",
                              f"{risk:.2f}" if risk != float("inf") else "inf"])
    flag_table = md_table(
        ["arm", "flag", "failed episodes", "share of failures", "successful episodes",
         "share of successes", "relative risk"], flag_rows)
    (TABLES / "failure_flags.md").write_text(flag_table + "\n", encoding="utf-8")

    # first fatal event
    fatal_rows = []
    for arm in ARMS:
        cell = [r for r in rows if r["arm"] == arm and not r["success"]]
        names = Counter()
        for r in cell:
            key = (r["arm"], r["disturbance_p"], r["seed"])
            flags = episode_flags(r, invalid_ask_by_cell.get(key, False))
            _, name = first_fatal_event(r, traces_by_cell.get(key, []), flags)
            names[name or "none"] += 1
        fatal_rows.append([arm, str(len(cell))] + [f"{names.get(n, 0)}" for n in FATAL_PRIORITY]
                           + [f"{names.get('none', 0)}"])
    fatal_table = md_table(["arm", "failed", "safety_violation", "stale_pick_fail",
                            "controller_block", "budget_exhausted", "none"], fatal_rows)
    (TABLES / "first_fatal_event.md").write_text(fatal_table + "\n", encoding="utf-8")

    # ---- scripted reference lines on the test seeds -------------------------- #
    seeds = sorted({r["seed"] for r in rows})
    script_rows = []
    scripted_points: dict[tuple[str, float], tuple[float, float]] = {}
    for policy in POLICIES:
        for p in PS:
            res = evaluate(policy, seeds, p, max_asks=1, freeze_asked=True)
            scripted_points[(policy, p)] = (res["cost"], res["success"])
            script_rows.append([policy, f"{p}", str(res["n"]), f"{res['success']:.1f}",
                                f"{res['cost']:.1f}", f"{res['asks']:.2f}", f"{res['unsafe']:.1f}"])
    (TABLES / "scripted_reference.md").write_text(
        md_table(["policy", "p", "n", "success%", "cost", "asks", "unsafe%"], script_rows) + "\n",
        encoding="utf-8")

    # ---- run overview -------------------------------------------------------- #
    (TABLES / "run_overview.md").write_text(
        md_table(["quantity", "value"], [
            ["episodes on disk", str(len(raw_rows))],
            ["episodes in analysis", str(len(rows))],
            ["infrastructure failure events (repaired)", str(infra_events)],
            ["seeds", f"{min(seeds) if seeds else '-'}..{max(seeds) if seeds else '-'} ({len(seeds)})"],
            ["bootstrap", f"{N_BOOT} resamples, seed {BOOT_SEED}"],
            ["delta", f"{DELTA} pp"],
        ]) + "\n", encoding="utf-8")

    make_figure(cell_stats, scripted_points)

    return {"rows": rows, "results": results, "pc": pc, "primary": primary,
            "instrument_ok": instrument_ok, "cell_stats": cell_stats,
            "infra_events": infra_events, "seeds": seeds}


def make_figure(cell_stats, scripted_points) -> None:
    """The controller permission gradient, faceted by p."""
    fig, axes = plt.subplots(1, len(PS), figsize=(15, 4.8))
    order = ["base", "hint", "shield", "both", "auto"]
    labels = {"base": "base (no controller)", "hint": "hint (advice)",
              "shield": "shield (block)", "both": "both (advice+block)",
              "auto": "auto (recommend)"}
    colors = {"base": "#4C72B0", "hint": "#55A868", "shield": "#C44E52",
              "both": "#DD8452", "auto": "#8172B2"}
    for ax, p in zip(axes, PS):
        xs, ys = [], []
        for i, arm in enumerate(order):
            key = (arm, p)
            if key not in cell_stats:
                continue
            st = cell_stats[key]
            ax.errorbar(st["success"], i, xerr=5.0, fmt="o", color=colors[arm],
                        capsize=3, markersize=8)
            xs.append(st["success"])
            ys.append(i)
        ax.set_yticks(range(len(order)))
        ax.set_yticklabels([labels[a] for a in order])
        ax.invert_yaxis()
        for policy, (cost, succ) in scripted_points.items():
            if abs(policy_cost_p(scripted_points, policy, p)) < 1e-9:
                ax.axvline(succ, color="gray", linestyle=":", linewidth=1, alpha=0.8)
        ax.set_title(f"p = {p}")
        ax.set_xlabel("success rate (%)")
        ax.grid(alpha=0.3, axis="x")
    fig.suptitle("Controller permission gradient (points: SR, bars: +/-5 pp; dotted: scripted lines)",
                 fontsize=11)
    fig.tight_layout()
    fig.savefig(FIGURES / "permission_gradient.png", dpi=150)
    plt.close(fig)


def policy_cost_p(scripted_points, policy, p):
    return scripted_points.get((policy, p), (0, 0))[1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", type=Path, default=RESULTS)
    args = parser.parse_args()
    out = analyse(args.results)
    print(f"episodes in analysis: {len(out['rows'])}  seeds: {len(out['seeds'])}  "
          f"infra events: {out['infra_events']}")
    for label, est in out["results"].items():
        print(f"  {label:24s} {est['point']:+6.1f} pp  CI [{est['lo']:+6.1f}, {est['hi']:+6.1f}]  "
              f"N={est['n']}  -> {est['label']}")
    print(f"instrument check (PC must be HELPS): "
          f"{'OK' if out['instrument_ok'] else 'INSTRUMENT_FAILED'}")
    print(f"tables -> {TABLES}, figures -> {FIGURES}")


if __name__ == "__main__":
    main()
