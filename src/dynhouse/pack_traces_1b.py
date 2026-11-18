"""Pack the Probe 1b step traces into a compressed JSONL for the repository.

    uv run python -m dynhouse.pack_traces_1b --results results_1b

The step traces (action, message and the controller's bookkeeping) are kept so
that the failure analysis can be reproduced from the repository; the full
prompts are not (they are in `raw.jsonl`, which stays on disk).
"""
from __future__ import annotations

import argparse
import gzip
import json
from pathlib import Path

KEEP = ("episode_id", "arm", "seed", "disturbance_p", "step", "action", "ok", "message",
        "cost", "failure_reason", "controller_blocked", "overrode_recommendation",
        "recommendation", "disturbance", "parse_error")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", type=Path, default=Path("results_1b"))
    args = parser.parse_args()
    source = args.results / "traces.jsonl"
    target = args.results / "traces_1b.jsonl.gz"
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
