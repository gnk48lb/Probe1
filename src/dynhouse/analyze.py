"""M6: reproduce every table and figure of the experiment.

    uv run python -m dynhouse.analyze

Reads `results/main/episodes.jsonl` (written by the runner), plus the scripted
reference lines recomputed on the very same seeds, and writes
`results/tables/*.md` and `results/figures/*.png`.
"""
from __future__ import annotations

import argparse
import json
import math
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
PS = (0.0, 0.2, 0.4)
ARMS = ("app_N", "led_N", "app_C", "led_C", "win_N", "win_C")
CORE = ("app_N", "led_N", "app_C", "led_C")
DELTA = 10.0            # preregistered effect threshold, in percentage points
N_BOOT = 10000          # preregistered bootstrap resamples
BOOT_SEED = 20261117    # preregistered bootstrap random seed
SCRIPTED_TOL = 2.0

RESULTS = ROOT / "results"
TABLES = RESULTS / "tables"
FIGURES = RESULTS / "figures"


# --------------------------------------------------------------------------- #
# loading
# --------------------------------------------------------------------------- #
def load_episodes(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def usable(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split out the episodes that may enter the analysis.

    An episode is usable when it finished (no infrastructure failure).  Seeds
    are kept only when all four core arms are complete at all three p, so
    every comparison is paired.
    """
    good = [r for r in rows if not r.get("infra_failed")
            and r.get("failure_reason") != "infrastructure_failure"
            and r.get("success") is not None]
    core_keys = {(r["arm"], r["disturbance_p"], r["seed"]) for r in good if r["arm"] in CORE}
    seeds = sorted({r["seed"] for r in good})
    complete = []
    for seed in seeds:
        if all((arm, p, seed) in core_keys for arm in CORE for p in PS):
            complete.append(seed)
    keep = [r for r in good if r["seed"] in set(complete)]
    dropped = [r for r in rows if r.get("infra_failed")
               or r.get("failure_reason") == "infrastructure_failure"]
    return keep, dropped


# --------------------------------------------------------------------------- #
# statistics
# --------------------------------------------------------------------------- #
class Bootstrap:
    def __init__(self, seeds: list[int], n_boot: int = N_BOOT, seed: int = BOOT_SEED):
        self.seeds = seeds
        self.rng = np.random.default_rng(seed)
        self.index = self.rng.integers(0, len(seeds), size=(n_boot, len(seeds)))

    def paired_diff(self, arms_a: list[str], arms_b: list[str], p: float,
                    by_cell: dict[tuple[str, float], dict[int, float]]) -> np.ndarray:
        """Bootstrap distribution of mean(a) - mean(b) over cells, resampling seeds."""
        samples = np.zeros(len(self.index))
        cells = 0
        for arm_a, arm_b in zip(arms_a, arms_b):
            a = by_cell[(arm_a, p)]
            b = by_cell[(arm_b, p)]
            diff = np.array([a[s] - b[s] for s in self.seeds])
            samples += diff[self.index].mean(axis=1)
            cells += 1
        return samples / max(cells, 1)

    def cell_mean(self, arm: str, p: float,
                  by_cell: dict[tuple[str, float], dict[int, float]]) -> np.ndarray:
        values = np.array([by_cell[(arm, p)][s] for s in self.seeds])
        return values[self.index].mean(axis=1)


def ci(samples: np.ndarray) -> tuple[float, float]:
    return float(np.percentile(samples, 2.5)), float(np.percentile(samples, 97.5))


def decide(point: float, samples: np.ndarray, delta: float = DELTA) -> tuple[str, float, float]:
    lo, hi = ci(samples)
    if point >= delta and lo > 0:
        return "HELPS", lo, hi
    if hi < delta:
        return "NOT_NEEDED", lo, hi
    return "INCONCLUSIVE", lo, hi


def fmt_pct(value: float) -> str:
    return f"{value:.1f}"


def md_table(header: list[str], rows: list[list[str]]) -> str:
    out = ["| " + " | ".join(header) + " |",
           "|" + "|".join("---" for _ in header) + "|"]
    out += ["| " + " | ".join(r) + " |" for r in rows]
    return "\n".join(out)


# --------------------------------------------------------------------------- #
# the analysis
# --------------------------------------------------------------------------- #
def analyse(results_dir: Path) -> dict[str, Any]:
    episodes_path = results_dir / "episodes.jsonl"
    rows = load_episodes(episodes_path)
    keep, dropped = usable(rows)
    seeds = sorted({r["seed"] for r in keep})
    TABLES.mkdir(parents=True, exist_ok=True)
    FIGURES.mkdir(parents=True, exist_ok=True)

    # per (arm, p): seed -> success (0/1) and the secondary metrics
    success: dict[tuple[str, float], dict[int, float]] = {}
    agg: dict[tuple[str, float], dict[str, float]] = {}
    for arm in ARMS:
        for p in PS:
            cell = [r for r in keep if r["arm"] == arm and r["disturbance_p"] == p]
            by_seed = {r["seed"]: float(r["success"]) for r in cell}
            success[(arm, p)] = by_seed
            n = max(len(cell), 1)
            agg[(arm, p)] = {
                "n": len(cell),
                "success": 100 * sum(r["success"] for r in cell) / n,
                "cost": float(np.mean([r["total_cost"] for r in cell])) if cell else float("nan"),
                "stale_pick": float(np.mean([r["stale_pick_count"] for r in cell])) if cell else float("nan"),
                "stale_pick_any": 100 * sum(1 for r in cell if r["stale_pick_count"]) / n,
                "safety": 100 * sum(1 for r in cell if r["safety_count"]) / n,
                "asks": float(np.mean([r["ask_count"] for r in cell])) if cell else float("nan"),
                "invalid": float(np.mean([r["invalid_actions"] for r in cell])) if cell else float("nan"),
                "calls": float(np.mean([r["usage"]["llm_calls"] for r in cell])) if cell else float("nan"),
                "tokens": float(np.mean([r["usage"]["total_tokens"] for r in cell])) if cell else float("nan"),
                "steps": float(np.mean([r["steps"] for r in cell])) if cell else float("nan"),
            }

    boot = Bootstrap(seeds)

    # ---- main table ------------------------------------------------------ #
    main_rows = []
    for arm in ARMS:
        for p in PS:
            a = agg[(arm, p)]
            samples = boot.cell_mean(arm, p, success) * 100
            lo, hi = ci(samples)
            main_rows.append([arm, fmt_pct(p), str(a["n"]), f"{a['success']:.1f}",
                              f"[{lo:.1f}, {hi:.1f}]", f"{a['cost']:.1f}",
                              f"{a['stale_pick_any']:.1f}", f"{a['safety']:.1f}",
                              f"{a['asks']:.2f}", f"{a['invalid']:.2f}",
                              f"{a['calls']:.1f}", f"{a['tokens']:.0f}"])
    main_table = md_table(
        ["arm", "p", "n", "SR%", "SR 95% CI", "cost", "stale_pick%", "safety%",
         "asks", "invalid", "llm_calls", "tokens"], main_rows)
    (TABLES / "main_table.md").write_text(main_table + "\n", encoding="utf-8")

    # ---- paired differences ---------------------------------------------- #
    pairs = [("led_N", "app_N", "R: ledger vs append, P=N"),
             ("led_C", "app_C", "R: ledger vs append, P=C"),
             ("app_C", "app_N", "P: cost vs neutral, R=append"),
             ("led_C", "led_N", "P: cost vs neutral, R=ledger")]
    pair_rows = []
    for arm_a, arm_b, label in pairs:
        for p in PS:
            samples = boot.paired_diff([arm_a], [arm_b], p, success)
            point = 100 * (np.mean([success[(arm_a, p)][s] for s in seeds])
                           - np.mean([success[(arm_b, p)][s] for s in seeds]))
            lo, hi = ci(samples)
            pair_rows.append([label, fmt_pct(p), f"{point:+.1f}", f"[{lo:+.1f}, {hi:+.1f}]",
                              "yes" if lo > 0 else ("no" if hi < 0 else "no")])
    pair_table = md_table(["contrast", "p", "diff (pp)", "95% CI", "CI excludes 0"], pair_rows)
    (TABLES / "paired_differences.md").write_text(pair_table + "\n", encoding="utf-8")

    # ---- S, S0, Pi ------------------------------------------------------- #
    def mean_diff(arm_a_cells, arm_b_cells, p_list):
        samples = np.zeros(len(boot.index))
        count = 0
        for arm_a, arm_b in zip(arm_a_cells, arm_b_cells):
            for p in p_list:
                diff = np.array([success[(arm_a, p)][s] - success[(arm_b, p)][s] for s in seeds])
                samples += diff[boot.index].mean(axis=1)
                count += 1
        samples /= count
        point = 100 * sum(np.mean([success[(a, p)][s] for s in seeds]
                                   - np.mean([success[(b, p)][s] for s in seeds]))
                           for a, b in zip(arm_a_cells, arm_b_cells) for p in p_list) / count
        return point, samples

    s_point, s_samples = mean_diff(["led_N", "led_C"], ["app_N", "app_C"], (0.2, 0.4))
    s_label, s_lo, s_hi = decide(s_point, s_samples)
    s0_point, s0_samples = mean_diff(["led_N", "led_C"], ["app_N", "app_C"], (0.0,))
    s0_lo, s0_hi = ci(s0_samples)
    s0_ok = s0_lo <= 0 <= s0_hi
    pi_point, pi_samples = mean_diff(["app_C", "led_C"], ["app_N", "led_N"], (0.2, 0.4))
    pi_label, pi_lo, pi_hi = decide(pi_point, pi_samples)

    # p=0 cost-vs-neutral difference (the cost of over-verification), reported apart
    over_rows = []
    for arm in ("app", "led"):
        d0 = 100 * (np.mean([success[(arm + "_C", 0.0)][s] for s in seeds])
                    - np.mean([success[(arm + "_N", 0.0)][s] for s in seeds]))
        c0 = np.mean([agg[(arm + "_C", 0.0)]["cost"] - agg[(arm + "_N", 0.0)]["cost"]])
        over_rows.append([f"{arm}_C - {arm}_N", f"{d0:+.1f}", f"{c0:+.1f}"])
    over_table = md_table(["contrast at p=0", "SR diff (pp)", "cost diff"], over_rows)

    did_point = s_point - s0_point
    did_samples = s_samples - s0_samples
    did_label, did_lo, did_hi = decide(did_point, did_samples)

    judge_rows = [
        ["S  (structure, p in {0.2,0.4})", f"{s_point:+.1f}", f"[{s_lo:+.1f}, {s_hi:+.1f}]",
         f"STRUCTURE_{s_label}"],
        ["S0 (control, p=0)", f"{s0_point:+.1f}", f"[{s0_lo:+.1f}, {s0_hi:+.1f}]",
         "control OK" if s0_ok else "CONTROL FAILED"],
        ["S_DiD = S - S0", f"{did_point:+.1f}", f"[{did_lo:+.1f}, {did_hi:+.1f}]",
         f"STRUCTURE_{did_label}"],
        ["Pi (prompt, p in {0.2,0.4})", f"{pi_point:+.1f}", f"[{pi_lo:+.1f}, {pi_hi:+.1f}]",
         f"PROMPT_{pi_label}"],
    ]
    judge_table = md_table(["quantity", "effect (pp)", "95% CI", "verdict"], judge_rows)

    # ---- scripted reference lines on the very same seeds ------------------ #
    script_rows = []
    scripted_points: dict[tuple[str, float], tuple[float, float]] = {}
    for policy in POLICIES:
        for p in PS:
            res = evaluate(policy, seeds, p, max_asks=1, freeze_asked=True)
            scripted_points[(policy, p)] = (res["cost"], res["success"])
            script_rows.append([policy, fmt_pct(p), str(res["n"]), f"{res['success']:.1f}",
                                f"{res['cost']:.1f}", f"{res['asks']:.2f}", f"{res['unsafe']:.1f}"])
    script_table = md_table(["policy", "p", "n", "success%", "cost", "asks", "unsafe%"], script_rows)

    # ---- cost dominance ---------------------------------------------------- #
    cost_by_cell: dict[tuple[str, float], dict[int, float]] = {}
    for arm in ARMS:
        for p in PS:
            cell = [r for r in keep if r["arm"] == arm and r["disturbance_p"] == p]
            cost_by_cell[(arm, p)] = {r["seed"]: float(r["total_cost"]) for r in cell}

    dom_rows = []
    for arm in ARMS:
        for other in ARMS:
            if arm == other:
                continue
            for p in (0.2, 0.4):
                sr_diff = 100 * (np.mean([success[(arm, p)][s] for s in seeds])
                                 - np.mean([success[(other, p)][s] for s in seeds]))
                if sr_diff < -SCRIPTED_TOL:
                    continue           # not a cost-dominated candidate
                diff = np.array([cost_by_cell[(arm, p)][s] - cost_by_cell[(other, p)][s]
                                 for s in seeds])
                samples = diff[boot.index].mean(axis=1)
                lo, hi = ci(samples)
                dom_rows.append([arm, other, fmt_pct(p), f"{sr_diff:+.1f}", f"{diff.mean():+.1f}",
                                 f"[{lo:+.1f}, {hi:+.1f}]",
                                 "COST-DOMINANT" if hi < 0 else ""])
    dominance_table = md_table(
        ["arm", "compared with", "p", "SR diff (pp)", "cost diff", "cost diff 95% CI", "verdict"],
        dom_rows)

    # ---- evidence age ------------------------------------------------------- #
    ages_ok: list[int] = []
    ages_bad: list[int] = []
    ages_by_arm: dict[str, list[int]] = defaultdict(list)
    ages_by_p: dict[float, tuple[list[int], list[int]]] = {p: ([], []) for p in PS}
    for r in keep:
        for pick in r.get("pick_records", []):
            age = pick.get("evidence_age")
            if age is None:
                continue
            bucket = ages_by_p[r["disturbance_p"]]
            if pick["ok"]:
                ages_ok.append(age)
                bucket[0].append(age)
            else:
                ages_bad.append(age)
                bucket[1].append(age)
            ages_by_arm[r["arm"]].append(age)

    # ---- failure classification -------------------------------------------- #
    categories = ["acted on stale memory", "verified but the target moved again",
                  "wasted the ask", "invalid format", "budget or steps exhausted", "other"]
    failures: list[tuple[dict[str, Any], str]] = []
    for r in keep:
        if r["success"]:
            continue
        failures.append((r, classify(r)))
    class_counts = Counter(label for _, label in failures)
    class_table = md_table(["category", "failed episodes"],
                            [[c, str(class_counts.get(c, 0))] for c in categories]
                            + [["**total**", f"**{len(failures)}**"]])
    by_arm_rows = []
    for arm in ARMS:
        cell = [(r, lab) for r, lab in failures if r["arm"] == arm]
        counts = Counter(lab for _, lab in cell)
        by_arm_rows.append([arm, str(len(cell))]
                            + [str(counts.get(c, 0)) for c in categories])
    class_by_arm = md_table(["arm", "failed"] + categories, by_arm_rows)

    sample_rows = [[r["arm"], fmt_pct(r["disturbance_p"]), str(r["seed"]), lab,
                    str(r["failure_reason"]), str(r["stale_pick_count"]),
                    str(r["ask_count"]), str(r["invalid_actions"])]
                   for r, lab in failures[:40]]
    class_samples = md_table(["arm", "p", "seed", "category", "failure_reason",
                              "stale_pick", "asks", "invalid"], sample_rows)

    # ---- write everything --------------------------------------------------- #
    (TABLES / "judgements.md").write_text(
        judge_table + "\n\n" + over_table + "\n", encoding="utf-8")
    (TABLES / "scripted_reference.md").write_text(
        script_table + "\n\n### same seeds, paired with the LLM arms\n\n" + script_table
        + "\n", encoding="utf-8")
    (TABLES / "failure_classification.md").write_text(
        class_table + "\n\n" + class_by_arm + "\n\n### first 40 failed episodes\n\n"
        + class_samples + "\n", encoding="utf-8")
    (TABLES / "cost_dominance.md").write_text(dominance_table + "\n", encoding="utf-8")
    (TABLES / "run_overview.md").write_text(
        md_table(["quantity", "value"], [
            ["episodes on disk", str(len(rows))],
            ["episodes in analysis", str(len(keep))],
            ["infrastructure failures (excluded)", str(len(dropped))],
            ["seeds used", f"{seeds[0]}..{seeds[-1]} ({len(seeds)})"],
            ["bootstrap", f"{N_BOOT} resamples, seed {BOOT_SEED}"],
            ["delta", f"{DELTA} pp"],
        ]) + "\n", encoding="utf-8")

    # ---- figures ------------------------------------------------------------ #
    make_figures(agg, success, seeds, boot, scripted_points, ages_ok, ages_bad, ages_by_arm)

    return {"rows": rows, "keep": keep, "dropped": dropped, "seeds": seeds,
            "agg": agg, "s_point": s_point, "s_samples": s_samples, "s_label": s_label,
            "s_lo": s_lo, "s_hi": s_hi, "s0_point": s0_point, "s0_lo": s0_lo, "s0_hi": s0_hi,
            "s0_ok": s0_ok, "pi_point": pi_point, "pi_samples": pi_samples, "pi_label": pi_label,
            "pi_lo": pi_lo, "pi_hi": pi_hi, "did_point": did_point, "did_label": did_label,
            "did_lo": did_lo, "did_hi": did_hi, "failures": failures,
            "class_counts": class_counts}


def classify(r: dict[str, Any]) -> str:
    """One label per failed episode, in preregistered order of specificity."""
    picks = r.get("pick_records", [])
    failed_picks = [p for p in picks if not p["ok"]]
    if failed_picks:
        fresh = [p for p in failed_picks if (p.get("evidence_age") or 99) <= 1]
        if fresh:
            return "verified but the target moved again"
        return "acted on stale memory"
    usage = r.get("usage", {})
    if usage.get("format_failures", 0) > 0 or r.get("invalid_actions", 0) >= 3:
        return "invalid format"
    if r.get("ask_count", 0) >= 1:
        return "wasted the ask"
    if r.get("failure_reason") in ("budget_exhausted", "max_steps"):
        return "budget or steps exhausted"
    return "other"


def make_figures(agg, success, seeds, boot, scripted_points, ages_ok, ages_bad, ages_by_arm) -> None:
    # ---- Pareto: one panel per p ------------------------------------------ #
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.8))
    colors = {"app_N": "#4C72B0", "led_N": "#DD8452", "app_C": "#55A868", "led_C": "#C44E52",
              "win_N": "#8172B2", "win_C": "#937860"}
    markers = {"N": "o", "C": "s"}
    for ax, p in zip(axes, PS):
        for arm in ARMS:
            a = agg[(arm, p)]
            ax.scatter(a["cost"], a["success"], s=90, c=colors[arm], marker=markers[arm[-1]],
                       edgecolor="black", linewidth=0.5, zorder=3, label=arm)
            ax.annotate(arm, (a["cost"], a["success"]), textcoords="offset points",
                        xytext=(6, 4), fontsize=8)
        for policy in POLICIES:
            cost, succ = scripted_points[(policy, p)]
            ax.scatter(cost, succ, s=60, c="gray", marker="x", zorder=2)
            ax.annotate(policy, (cost, succ), textcoords="offset points",
                        xytext=(6, -10), fontsize=8, color="dimgray")
        ax.set_title(f"p = {p}")
        ax.set_xlabel("cost (budget points)")
        ax.set_ylabel("success rate (%)")
        ax.grid(alpha=0.3)
    axes[0].legend(fontsize=8, loc="lower left")
    fig.suptitle("Pareto: LLM arms (points) vs scripted reference lines (x)", fontsize=11)
    fig.tight_layout()
    fig.savefig(FIGURES / "pareto.png", dpi=150)
    plt.close(fig)

    # ---- evidence age ------------------------------------------------------- #
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.2))
    for ax, p in zip(axes, PS):
        ok_ages, bad_ages = ages_by_p[p]
        ax.hist(ok_ages, bins=range(0, 35), alpha=0.65, label="pick succeeded",
                color="#55A868", density=True)
        ax.hist(bad_ages, bins=range(0, 35), alpha=0.65, label="pick failed",
                color="#C44E52", density=True)
        ax.set_title(f"evidence age at pick (all arms, p={p} pooled)")
        ax.set_xlabel("steps since the item was last confirmed")
        ax.set_ylabel("density")
        ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(FIGURES / "evidence_age.png", dpi=150)
    plt.close(fig)

    # ---- per-arm evidence age ------------------------------------------------ #
    fig, axes = plt.subplots(2, 3, figsize=(15, 8))
    for ax, arm in zip(axes.flatten(), ARMS):
        ages = ages_by_arm.get(arm, [])
        ax.hist(ages, bins=range(0, 35), color="#4C72B0", alpha=0.85)
        ax.set_title(arm, fontsize=10)
        ax.set_xlabel("evidence age at pick")
    fig.suptitle("Evidence age at each pick, by arm")
    fig.tight_layout()
    fig.savefig(FIGURES / "evidence_age_by_arm.png", dpi=150)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", type=Path, default=RESULTS / "main")
    args = parser.parse_args()
    out = analyse(args.results)
    print(f"episodes on disk: {len(out['rows'])}, in analysis: {len(out['keep'])}, "
          f"infra-failed: {len(out['dropped'])}, seeds: {len(out['seeds'])}")
    print(f"S  = {out['s_point']:+.1f} pp  CI [{out['s_lo']:+.1f}, {out['s_hi']:+.1f}]  "
          f"-> STRUCTURE_{out['s_label']}")
    print(f"S0 = {out['s0_point']:+.1f} pp  CI [{out['s0_lo']:+.1f}, {out['s0_hi']:+.1f}]  "
          f"-> {'control OK' if out['s0_ok'] else 'CONTROL FAILED'}")
    print(f"Pi = {out['pi_point']:+.1f} pp  CI [{out['pi_lo']:+.1f}, {out['pi_hi']:+.1f}]  "
          f"-> PROMPT_{out['pi_label']}")
    print(f"failed episodes classified: {len(out['failures'])}")
    for label, count in out["class_counts"].most_common():
        print(f"  {label}: {count}")
    print(f"tables -> {TABLES}, figures -> {FIGURES}")


if __name__ == "__main__":
    main()
