"""Probe 1d supplement: the `age_gate` reference line and the run timestamps.

    uv run python -m dynhouse.supplement_1d --results results_1d

`analyze_1d.py` is locked by `prereg_1d.lock` and writes the four scripted
reference lines, but the preregistration (section 3.6) also asks for the
`age_gate` policy on the seeds actually included in the analysis.  That line is
computed here instead, in a separate file, so that the locked analysis stays
byte-identical.  The omission is recorded in `DEVIATIONS_1D.md`.
"""
from __future__ import annotations

import argparse
import datetime
import importlib.util
import json
import subprocess
from pathlib import Path

from .analyze_1d import latest_rows, load_jsonl

ROOT = Path(__file__).resolve().parent.parent.parent


def age_gate_on(seeds, p: float) -> dict[str, float]:
    """The age-gate policy (no LLM) on the given seeds, via the locked reference."""
    spec = importlib.util.spec_from_file_location("age_gate_reference",
                                                  ROOT / "age_gate_reference.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    env_module = module.load_env(str(ROOT / "src/dynhouse/env.py"))
    result = module.evaluate(env_module, seeds, p)
    return {"success": result["success"], "cost": result["cost"], "unsafe": result["unsafe"],
            "n": len(list(seeds))}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", type=Path, default=ROOT / "results_1d")
    args = parser.parse_args()

    rows = [r for r in latest_rows(load_jsonl(args.results / "episodes.jsonl"))
            if r["disturbance_p"] == 0.2 and r["arm"] in ("led_C", "app_C")
            and not r.get("infra_failed") and r.get("success") is not None]
    seeds = sorted({r["seed"] for r in rows})
    both = all(("app_C", 0.2, s) in {(r["arm"], r["disturbance_p"], r["seed"]) for r in rows}
               and ("led_C", 0.2, s) in {(r["arm"], r["disturbance_p"], r["seed"]) for r in rows}
               for s in seeds)
    if not both:
        raise SystemExit("the two arms are not complete on the same seeds")

    gate = age_gate_on(seeds, 0.2)

    manifest = json.loads((args.results / "run_manifest.json").read_text(encoding="utf-8"))
    last_write = datetime.datetime.fromtimestamp(
        (args.results / "episodes.jsonl").stat().st_mtime,
        datetime.timezone.utc).isoformat()
    tag_commit = subprocess.run(["git", "rev-list", "-n", "1", "prereg-1d"],
                                capture_output=True, text=True).stdout.strip()
    tag_time = subprocess.run(["git", "log", "-1", "--format=%ci", tag_commit],
                              capture_output=True, text=True).stdout.strip()

    lines = [
        "# age_gate reference line (supplement to `analyze_1d.py`)",
        "",
        "`PREREG_1D.md` section 3.6 asks for the `age_gate` policy on the seeds",
        "actually included in the analysis; the locked analysis does not compute it, so it is",
        "computed here.  It involves no LLM and can be recomputed at any time.",
        "",
        "| policy | n | success% | cost | unsafe% |",
        "|---|---|---|---|---|",
        f"| age_gate (the rule itself, no LLM) | {gate['n']} | {gate['success']:.1f} | "
        f"{gate['cost']:.1f} | {gate['unsafe']:.1f}% |",
        "",
        "## Timestamps",
        "",
        "| what | when |",
        "|---|---|",
        f"| `prereg-1d` tag ({tag_commit[:8]}) | {tag_time} |",
        f"| the run's manifest created (the run started) | {manifest['created_at']} |",
        f"| the last episode written | {last_write} |",
        "",
    ]
    (args.results / "tables" / "age_gate.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {args.results / 'tables' / 'age_gate.md'}")
    print(f"  age_gate on seeds {seeds[0]}..{seeds[-1]} (n={gate['n']}): "
          f"SR {gate['success']:.1f}%  cost {gate['cost']:.1f}  unsafe {gate['unsafe']:.1f}%")


if __name__ == "__main__":
    main()
