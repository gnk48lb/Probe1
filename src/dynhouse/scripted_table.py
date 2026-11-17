"""Print the scripted reference table for the NEW env (and the nofreeze variant).

    uv run python -m dynhouse.scripted_table --seeds 1000
"""
from __future__ import annotations

import argparse

from .scripted import POLICIES, evaluate

PS = (0.0, 0.2, 0.4)


def table(seeds, *, max_asks: int = 1, freeze_asked: bool = True) -> dict:
    print(f"{'policy':13s} | " + " | ".join(f"p={p}: success  cost  asks unsafe" for p in PS))
    out = {}
    for pol in POLICIES:
        cells, row = [], {}
        for p in PS:
            r = evaluate(pol, seeds, p, max_asks=max_asks, freeze_asked=freeze_asked)
            row[p] = r
            cells.append(f"      {r['success']:6.1f}% {r['cost']:5.1f} {r['asks']:4.1f} {r['unsafe']:5.1f}%")
        out[pol] = row
        print(f"{pol:13s} | " + " | ".join(cells))
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=1000)
    args = ap.parse_args()
    seeds = range(args.seeds)
    print(f"=== new env, fixed + askcap1 ({args.seeds} seeds per cell)")
    table(seeds, max_asks=1, freeze_asked=True)
    print(f"\n=== new env, fixed + nofreeze + no ask cap ({args.seeds} seeds per cell)")
    table(seeds, max_asks=99, freeze_asked=False)


if __name__ == "__main__":
    main()
