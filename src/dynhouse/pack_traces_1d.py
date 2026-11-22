"""Pack the Probe 1d step traces into a compressed JSONL for the repository.

    uv run python -m dynhouse.pack_traces_1d --results results_1d
"""
from __future__ import annotations

import argparse
import gzip
import json
from pathlib import Path

KEEP = ("episode_id", "arm", "seed", "disturbance_p", "step", "action", "ok", "message",
        "cost", "failure_reason", "disturbance", "parse_error")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", type=Path, default=Path("results_1d"))
    args = parser.parse_args()
    source = args.results / "traces.jsonl"
    target = args.results / "traces_1d.jsonl.gz"
    rows = 0
    with source.open(encoding="utf-8") as handle, gzip.open(target, "wt", encoding="utf-8") as out:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            out.write(json.dumps({k: row[k] for k in KEEP if k in row},
                                 ensure_ascii=False, separators=(",", ":")) + "\n")
            rows += 1
    print(f"{rows} step traces -> {target} ({target.stat().st_size / 1e6:.2f} MB)")


if __name__ == "__main__":
    main()
