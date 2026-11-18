"""Probe 1c analysis: the replication test of led_C vs app_C at p = 0.2.

    uv run python -m dynhouse.analyze_1c --results results_1c

Everything is recomputed from `episodes.jsonl` and `traces.jsonl`.  The primary
estimator is the paired difference in success rate between the two arms on the
seeds where both arms are complete, with a paired bootstrap over seeds
(10,000 resamples, RNG seed 20261119).  The verdict rule is the one frozen in
`PREREG_1C.md`: REPLICATED / NOT_REPLICATED / INCONCLUSIVE with delta = 5 pp.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
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
P_MAIN = 0.2
ARMS = ("led_C", "app_C")
DELTA = 5.0
N_BOOT = 10000
BOOT_SEED = 20261119
PS = (0.2,)

RESULTS = ROOT / "results_1c"
TABLES = RESULTS / "tables"
FIGURES = RESULTS / "figures"

# Probe 1's original (post-hoc, different seeds, N=100) observation, shown next
# to the replication estimate.  It never enters a verdict.
PROBE1_REFERENCE = {"led_C": 67.0, "app_C": 57.0, "difference": 10.0,
                    "ci": "[-2, +22]", "n": 100}

# The sources this analysis is locked against (see `PREREG_1C.md`).
LOCKED_SOURCES_1C = ("src/dynhouse/analyze_1c.py", "age_gate_reference.py")
LOCK_PATH_1C = ROOT / "prereg_1c.lock"


# --------------------------------------------------------------------------- #
# lock (CRLF is normalised to LF before hashing, on Windows and on the tag)
# --------------------------------------------------------------------------- #
def sha256_normalised(path: Path) -> str:
    """sha256 of a file with CRLF normalised to LF."""
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def compute_lock_1c() -> dict[str, str]:
    return {rel: sha256_normalised(ROOT / rel) for rel in LOCKED_SOURCES_1C}


def verify_lock_1c(strict: bool = True) -> bool:
    current = compute_lock_1c()
    if not LOCK_PATH_1C.exists():
        if strict:
            print("ERROR: prereg_1c.lock is missing; the preregistration is not in place.")
        return False
    expected = json.loads(LOCK_PATH_1C.read_text(encoding="utf-8"))["files"]
    if expected != current:
        print("ERROR: the locked sources do not match prereg_1c.lock.")
        for rel in LOCKED_SOURCES_1C:
            if expected.get(rel) != current.get(rel):
                print(f"  {rel}: locked {expected.get(rel)} != current {current.get(rel)}")
        return False
    return True


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
    cell, so the contrasts stay paired.
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
    """The preregistered rule: REPLICATED / NOT_REPLICATED / INCONCLUSIVE."""
    lo, hi = percentile_ci(samples)
    if point >= delta and lo > 0:
        return "REPLICATED", lo, hi
    if hi < delta:
        return "NOT_REPLICATED", lo, hi
    return "INCONCLUSIVE", lo, hi


def paired_difference(rows: list[dict[str, Any]], arm_a: str, arm_b: str, p: float,
                      values_a: dict[int, float], values_b: dict[int, float],
                      seeds: list[int], n_boot: int = N_BOOT,
                      rng_seed: int = BOOT_SEED) -> tuple[float, float, float, int]:
    """Paired difference arm_a - arm_b of a per-episode quantity, with a CI."""
    diffs = np.array([values_a[s] - values_b[s] for s in seeds], dtype=float)
    rng = np.random.default_rng(rng_seed)
    index = rng.integers(0, len(seeds), size=(n_boot, len(seeds)))
    samples = diffs[index].mean(axis=1)
    lo, hi = percentile_ci(samples)
    return float(diffs.mean()), lo, hi, len(seeds)


# --------------------------------------------------------------------------- #
# per-episode quantities
# --------------------------------------------------------------------------- #
def episode_values(row: dict[str, Any]) -> dict[str, float]:
    """The per-episode quantities the preregistration lists as secondary."""
    picks = row.get("pick_records") or []
    missed = [p for p in picks if not p["ok"]]
    competing = [p for p in missed if (p.get("evidence_age") or 99) <= 1]
    stale = [p for p in missed if (p.get("evidence_age") or 0) >= 2]
    return {
        "success": float(bool(row["success"])),
        "total_cost": float(row["total_cost"]),
        "safety_violation": float(bool(row.get("safety_count", 0))),
        "budget_exhausted": float(row.get("failure_reason") == "budget_exhausted"),
        "invalid_count": float(row.get("invalid_actions", 0) or 0),
        "ask_count": float(row.get("ask_count", 0) or 0),
        "pick_fail_competing": float(len(competing) > 0),
        "pick_fail_stale": float(len(stale) > 0),
        "high_risk_pick": float(any(p.get("item") in ITEMS and ITEMS[p["item"]] == "high_risk"
                                    for p in picks)),
    }


def failure_flags(row: dict[str, Any], repeat_ask: bool) -> dict[str, bool]:
    """Non-exclusive flags for one episode."""
    values = episode_values(row)
    return {
        "competing_pick_fail": bool(values["pick_fail_competing"]),
        "stale_pick_fail": bool(values["pick_fail_stale"]),
        "high_risk_pick": bool(values["high_risk_pick"]),
        "repeat_ask": bool(repeat_ask),
        "budget_exhausted": bool(values["budget_exhausted"]),
        "safety_violation": bool(values["safety_violation"]),
        "never_used_ask": bool(values["ask_count"] == 0),
    }


FLAG_ORDER = ["competing_pick_fail", "stale_pick_fail", "high_risk_pick", "repeat_ask",
              "budget_exhausted", "safety_violation", "never_used_ask"]


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
    repeat_ask_by_cell: dict[tuple, bool] = defaultdict(bool)
    for t in traces:
        if t.get("failure_reason") == "invalid_action" and "ask limit" in (t.get("message") or ""):
            repeat_ask_by_cell[(t["arm"], t["disturbance_p"], t["seed"])] = True

    seeds = complete_seeds(rows, ARMS, PS)
    dropped_seeds = sorted({r["seed"] for r in rows} - set(seeds))

    values: dict[tuple[str, float], dict[int, dict[str, float]]] = defaultdict(dict)
    for row in rows:
        values[(row["arm"], row["disturbance_p"])][row["seed"]] = episode_values(row)

    # ---- the primary estimator -------------------------------------------- #
    diffs = {"main": np.array([values[("led_C", P_MAIN)][s]["success"]
                                - values[("app_C", P_MAIN)][s]["success"] for s in seeds]) * 100}
    samples = paired_bootstrap(diffs, seeds)
    point = float(diffs["main"].mean())
    label, lo, hi = verdict(point, samples)
    primary = {"point": point, "lo": lo, "hi": hi, "label": label, "n": len(seeds),
               "samples": samples}

    # ---- the arms table ----------------------------------------------------- #
    arm_rows = []
    cell_ci = {}
    for arm in ARMS:
        cell = [r for r in rows if r["arm"] == arm and r["disturbance_p"] == P_MAIN]
        by_seed = {r["seed"]: float(r["success"]) for r in cell}
        n = len(cell)
        success = 100 * sum(by_seed.values()) / n if n else float("nan")
        rng = np.random.default_rng(BOOT_SEED)
        index = rng.integers(0, len(seeds), size=(N_BOOT, len(seeds)))
        ci = percentile_ci(np.array([by_seed[s] for s in seeds])[index].mean(axis=1) * 100)
        cell_ci[arm] = ci
        reasons = Counter(r.get("failure_reason") for r in cell if not r["success"])
        arm_rows.append([
            arm, str(n), f"{success:.1f}", f"[{ci[0]:.1f}, {ci[1]:.1f}]",
            f"{sum(r['total_cost'] for r in cell) / n:.1f}",
            f"{100 * sum(1 for r in cell if r.get('safety_count', 0)) / n:.1f}",
            f"{100 * sum(1 for r in cell if r.get('failure_reason') == 'budget_exhausted') / n:.1f}",
            f"{sum(r.get('invalid_actions', 0) or 0 for r in cell) / n:.2f}",
            f"{sum(r.get('ask_count', 0) or 0 for r in cell) / n:.2f}",
            f"{sum(r.get('stale_pick_count', 0) or 0 for r in cell) / n:.2f}",
            f"{sum(r['total_cost'] for r in cell if r['success']) / max(sum(1 for r in cell if r['success']), 1):.1f}",
            f"{sum(r['total_cost'] for r in cell if not r['success']) / max(sum(1 for r in cell if not r['success']), 1):.1f}",
            str(reasons.get("budget_exhausted", 0)), str(reasons.get("safety_violation", 0)),
        ])
    arms_table = md_table(
        ["arm", "n", "SR%", "SR 95% CI", "cost", "safety%", "budget_exhausted%", "invalid",
         "asks", "stale_picks", "cost of a success", "cost of a failure",
         "failures: budget", "failures: safety"], arm_rows)
    (TABLES / "arms.md").write_text(arms_table + "\n", encoding="utf-8")

    # ---- the primary result -------------------------------------------------- #
    primary_table = md_table(
        ["quantity", "value"],
        [["arms", "led_C - app_C"], ["disturbance", f"p = {P_MAIN}"],
         ["seeds used", f"{seeds[0]}..{seeds[-1]} ({len(seeds)})" if seeds else "none"],
         ["seeds dropped (an arm missing)", str(len(dropped_seeds))],
         ["effect (pp)", f"{point:+.1f}"],
         ["95% CI", f"[{lo:+.1f}, {hi:+.1f}]"],
         ["verdict", label],
         ["bootstrap", f"{N_BOOT} resamples, RNG seed {BOOT_SEED}"],
         ["delta", f"{DELTA} pp"],
         ["Probe 1's original estimate (post-hoc, different seeds, N=100)",
          f"{PROBE1_REFERENCE['difference']:+.1f} pp, CI {PROBE1_REFERENCE['ci']} "
          f"(led_C {PROBE1_REFERENCE['led_C']} vs app_C {PROBE1_REFERENCE['app_C']})"]])
    (TABLES / "primary.md").write_text(primary_table + "\n", encoding="utf-8")

    # ---- secondary metrics: the paired difference of each ---------------------- #
    metric_names = [("success", "success rate (pp)"), ("total_cost", "total cost"),
                     ("safety_violation", "safety violation rate (pp)"),
                     ("budget_exhausted", "budget exhausted rate (pp)"),
                     ("invalid_count", "invalid actions"),
                     ("ask_count", "asks"),
                     ("pick_fail_competing", "competing pick failure (pp)"),
                     ("pick_fail_stale", "stale pick failure (pp)"),
                     ("high_risk_pick", "high-risk pick (pp)")]
    sec_rows = []
    for key, label_text in metric_names:
        a = {s: values[("led_C", P_MAIN)][s][key] for s in seeds}
        b = {s: values[("app_C", P_MAIN)][s][key] for s in seeds}
        scale = 100.0 if key in ("success", "safety_violation", "budget_exhausted",
                                 "pick_fail_competing", "pick_fail_stale", "high_risk_pick") else 1.0
        mean, mlo, mhi, n = paired_difference(rows, "led_C", "app_C", P_MAIN, a, b, seeds)
        sec_rows.append([label_text, f"{mean * scale:+.2f}",
                         f"[{mlo * scale:+.2f}, {mhi * scale:+.2f}]",
                         f"{np.mean(list(a.values())) * scale:.2f}",
                         f"{np.mean(list(b.values())) * scale:.2f}", str(n)])
    secondary_table = md_table(
        ["metric (led_C - app_C)", "difference", "95% CI", "led_C", "app_C", "N seeds"],
        sec_rows)
    (TABLES / "secondary.md").write_text(secondary_table + "\n", encoding="utf-8")

    # ---- failure analysis (flags with the successful-episode baseline) -------- #
    flag_rows = []
    for arm in ARMS:
        cell = [r for r in rows if r["arm"] == arm and r["disturbance_p"] == P_MAIN]
        failed = [r for r in cell if not r["success"]]
        succeeded = [r for r in cell if r["success"]]
        f_flags = [failure_flags(r, repeat_ask_by_cell.get((r["arm"], r["disturbance_p"], r["seed"]), False))
                   for r in failed]
        s_flags = [failure_flags(r, repeat_ask_by_cell.get((r["arm"], r["disturbance_p"], r["seed"]), False))
                   for r in succeeded]
        for name in FLAG_ORDER:
            f_count = sum(1 for f in f_flags if f[name])
            s_count = sum(1 for f in s_flags if f[name])
            f_share = 100 * f_count / max(len(failed), 1)
            s_share = 100 * s_count / max(len(succeeded), 1)
            risk = f_share / s_share if s_share > 0 else float("inf") if f_share > 0 else float("nan")
            flag_rows.append([arm, name, f"{f_count}/{len(failed)}", f"{f_share:.1f}%",
                              f"{s_count}/{len(succeeded)}", f"{s_share:.1f}%",
                              f"{risk:.2f}" if risk != float("inf") else "inf"])
    flags_table = md_table(
        ["arm", "flag", "failed episodes", "share of failures", "successful episodes",
         "share of successes", "relative risk"], flag_rows)
    (TABLES / "failure_flags.md").write_text(flags_table + "\n", encoding="utf-8")

    # ---- scripted reference lines -------------------------------------------- #
    script_rows = []
    scripted_points: dict[str, float] = {}
    for policy in POLICIES:
        res = evaluate(policy, seeds, P_MAIN, max_asks=1, freeze_asked=True)
        scripted_points[policy] = res["success"]
        script_rows.append([policy, str(res["n"]), f"{res['success']:.1f}", f"{res['cost']:.1f}",
                            f"{res['asks']:.2f}", f"{res['unsafe']:.1f}"])
    age_gate = age_gate_reference(seeds, P_MAIN)
    scripted_points["age_gate"] = age_gate["success"]
    script_rows.append(["age_gate (no LLM)", str(age_gate["n"]), f"{age_gate['success']:.1f}",
                        f"{age_gate['cost']:.1f}", "-", f"{age_gate['unsafe']:.1f}"])
    (TABLES / "scripted_reference.md").write_text(
        md_table(["policy", "n", "success%", "cost", "asks", "unsafe%"], script_rows) + "\n",
        encoding="utf-8")

    # ---- figure ---------------------------------------------------------------- #
    make_figure(cell_ci, scripted_points)

    (TABLES / "run_overview.md").write_text(
        md_table(["quantity", "value"], [
            ["episodes on disk", str(len(raw_rows))],
            ["episodes in analysis", str(len(rows))],
            ["infrastructure failure events (repaired)", str(infra_events)],
            ["seeds used", f"{seeds[0]}..{seeds[-1]} ({len(seeds)})" if seeds else "none"],
            ["seeds dropped (an arm missing)", str(len(dropped_seeds))],
            ["bootstrap", f"{N_BOOT} resamples, RNG seed {BOOT_SEED}"],
            ["delta", f"{DELTA} pp"],
            ["verdict", label],
        ]) + "\n", encoding="utf-8")

    return {"rows": rows, "raw_rows": raw_rows, "seeds": seeds, "dropped": dropped_seeds,
            "primary": primary, "infra_events": infra_events, "scripted": scripted_points,
            "values": values}


def age_gate_reference(seeds, p: float) -> dict[str, float]:
    """The age-gate reference policy on the given seeds (no LLM)."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("age_gate_reference", ROOT / "age_gate_reference.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    env_module = module.load_env(str(ROOT / "src/dynhouse/env.py"))
    result = module.evaluate(env_module, seeds, p)
    return {"success": result["success"], "cost": result["cost"], "unsafe": result["unsafe"],
            "n": len(list(seeds))}


def make_figure(cell_ci, scripted_points) -> None:
    """Both arms' SR with CI; Probe 1's observation and the script lines as references."""
    fig, ax = plt.subplots(figsize=(9, 5.2))
    labels = {"led_C": "led_C (Probe 1c)", "app_C": "app_C (Probe 1c)"}
    colors = {"led_C": "#C44E52", "app_C": "#4C72B0"}
    for i, arm in enumerate(ARMS):
        lo, hi = cell_ci[arm]
        mid = (lo + hi) / 2
        ax.errorbar(mid, i, xerr=[[mid - lo], [hi - mid]], fmt="o", color=colors[arm],
                    capsize=4, markersize=9)
        ax.annotate(f"{mid:.1f}%  CI [{lo:.1f}, {hi:.1f}]", (mid, i),
                    textcoords="offset points", xytext=(0, 10), ha="center", fontsize=9)
    ax.set_yticks(range(len(ARMS)))
    ax.set_yticklabels([labels[a] for a in ARMS])
    ax.invert_yaxis()
    for name, value in scripted_points.items():
        ax.axvline(value, color="gray", linestyle=":", linewidth=1, alpha=0.8)
        ax.annotate(name, (value, 1.55), rotation=90, fontsize=7, color="dimgray",
                    ha="right", va="top")
    for arm, value in (("led_C", PROBE1_REFERENCE["led_C"]), ("app_C", PROBE1_REFERENCE["app_C"])):
        ax.scatter([value], [ARMS.index(arm)], marker="D", s=70, facecolor="none",
                   edgecolor="dimgray", zorder=4)
        ax.annotate("Probe 1 (post-hoc, different seeds)", (value, ARMS.index(arm)),
                    textcoords="offset points", xytext=(8, -16), fontsize=8, color="dimgray")
    ax.set_xlabel("success rate at p = 0.2 (%)")
    ax.set_title("Probe 1c: the replication test of led_C vs app_C\n"
                 "(dotted: scripted reference lines; diamonds: Probe 1's original observation)",
                 fontsize=10)
    ax.grid(alpha=0.3, axis="x")
    ax.set_ylim(len(ARMS) - 0.4, -0.6)
    fig.tight_layout()
    fig.savefig(FIGURES / "replication.png", dpi=150)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", type=Path, default=RESULTS)
    parser.add_argument("--no-lock-check", action="store_true")
    parser.add_argument("--write-lock", action="store_true")
    args = parser.parse_args()
    if args.write_lock:
        payload = {"written_at": datetime.now(timezone.utc).isoformat(),
                   "files": compute_lock_1c()}
        LOCK_PATH_1C.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                                encoding="utf-8")
        print(f"wrote {LOCK_PATH_1C}")
        return
    if not args.no_lock_check and not verify_lock_1c():
        raise SystemExit(2)
    out = analyse(args.results)
    primary = out["primary"]
    print(f"episodes in analysis: {len(out['rows'])}  seeds: {len(out['seeds'])}  "
          f"infra events: {out['infra_events']}")
    print(f"Delta = SR(led_C) - SR(app_C) at p=0.2 = {primary['point']:+.1f} pp  "
          f"CI [{primary['lo']:+.1f}, {primary['hi']:+.1f}]  N={primary['n']}  "
          f"-> {primary['label']}")
    print(f"tables -> {TABLES}, figures -> {FIGURES}")


if __name__ == "__main__":
    main()
