# RESUME — Probe 1c (state of 2026-11-18, paused by the user)

Nothing is running.  The machine was shut down for the night; the user will say
**"continue"** in the morning and the extension resumes from here.

## Where things stand

| | |
|---|---|
| Branch / base | `probe1c`, based on the tag `probe1-final` (Probe 1's frozen code, byte-identical) |
| Preregistration | `PREREG_1C.md`, lock `prereg_1c.lock`, tag `prereg-1c` (commit `50cdd21`) |
| Stage 1 | **done**: seeds 4000–4299, 600 episodes, 0 infrastructure failures |
| Stage 1 verdict | Δ = SR(led_C) − SR(app_C) at p=0.2 = **+2.7 pp, 95% CI [−3.7, +9.0], N=300 → INCONCLUSIVE** → the preregistered extension was triggered |
| Stage 2 (extension) | **paused** at 743 episodes on disk: 370 complete seeds (4000..4374), seeds 4361 / 4367 / 4372 missing one arm, 0 infrastructure failures |
| Still to run | the rest of seeds 4300–4599 (≈ 460 episodes, ≈ 1.5 h) |

## Exact commands

```bash
cd D:/code/ClaudeCode/Probe1

# 1. the extension (6 blocks of 50 seeds, both arms in one call; finished cells are skipped)
for s in 4300 4350 4400 4450 4500 4550; do
  uv run python -m dynhouse.run --seed-start $s --seeds 50 --arms led_C,app_C --ps 0.2 \
    --output-dir results_1c --concurrency 10 --progress-seconds 600 || break
done

# 2. the final analysis (600 seeds) -- only after the extension is complete
uv run python -m dynhouse.analyze_1c --results results_1c

# 3. Stage 3, ONLY if the final verdict is REPLICATED (descriptive, no verdict):
#    app_N and led_N on seeds 4000-4299, then repeat step 2

# 4. the report (English) and the compressed traces
uv run python -m dynhouse.pack_traces_1c --results results_1c
#    write results_1c/report.md from results_1c/tables/ (real logs only)

# 5. commit (never push, never add a remote)
git add -A && git commit
```

## Rules that must not be broken

* The frozen sources `src/dynhouse/{env,memory,prompts,agent,gateway,run,analyze,scripted}.py`
  and `prompts.lock` must stay **byte-identical to `probe1-final`**; `run.py` is used as it is.
* `analyze_1c.py` and `age_gate_reference.py` are locked by `prereg_1c.lock`; the analysis refuses
  to run when they drift.
* Do not change the verdict rule, δ, the bootstrap count or the seed rules of `PREREG_1C.md`.
* Output only to `results_1c/`; **never** write into `results/` (Probe 1's frozen results).
* Only `minimax-code-global/MiniMax-M3.1-Flash`.  Never Gemini; never Antigravity as an
  experimental model.
* During the run, report infrastructure health only (episodes done, error rate, format failures,
  wall clock, tokens) — **not** the per-arm success rates.
* Post-hoc findings are marked exploratory; nothing outside the preregistration enters a verdict.
* Ask the app to keep the machine awake, and remind the user to set
  "never sleep when plugged in" (Windows: Settings → System → Power → Screen and sleep).

## Push

```bash
git push origin probe1c
git push origin --tags
```
