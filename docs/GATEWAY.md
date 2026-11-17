# M1 -- Magpie gateway probe

- date: 2026-11-17 (sweeps between 15:40 and 16:20)
- base_url: `http://127.0.0.1:3425`
- main model: `minimax-code-global/MiniMax-M3.1-Flash` — **present in `/v1/models`: yes**
  (catalog holds 27 models; `minimax-code-global/MiniMax-M3.1-Flash` is one of them)
- request body used for every measurement: system 2502 chars + user 3778 chars,
  temperature=0, max_tokens=4000 — the same size and shape the experiment sends.

## Concurrency sweeps

The route is fast but noisy: the same concurrency level produced very different
throughput across sweeps, and the higher levels occasionally stall for tens of
seconds (Magpie soft-queues upstream requests).  All five sweeps, in order:

**Sweep A — 8 requests per level**

| concurrency | throughput (req/min) | latency mean | max | errors |
|---|---|---|---|---|
| 1 | 10.6 | 5.68 s | 13.6 s | 0 |
| 4 | 17.1 | 10.09 s | 24.0 s | 0 |
| 8 | 17.0 | 18.25 s | 28.3 s | 0 |
| 10 | 36.1 | 10.66 s | 13.3 s | 0 |
| 12 | 43.9 | 8.54 s | 10.9 s | 0 |

**Sweep B — 24 requests per level**

| concurrency | throughput (req/min) | latency mean | max | errors |
|---|---|---|---|---|
| 1 | 7.4 | 8.12 s | 27.2 s | 0 |
| 4 | 9.3 | 6.86 s | 23.7 s | 1 |
| 8 | 64.9 | 6.46 s | 13.8 s | 0 |
| 10 | 82.4 | 5.09 s | 9.4 s | 0 |
| 12 | 59.1 | 6.56 s | 16.6 s | 0 |

**Sweep C — 60 requests per level**

| concurrency | throughput (req/min) | latency mean | max | errors |
|---|---|---|---|---|
| 6 | 54.9 | 6.31 s | 36.1 s | 0 |
| 8 | 25.8 | 6.89 s | 120.5 s | 0 |
| 10 | 112.9 | 4.91 s | 10.0 s | 0 |
| 12 | 116.7 | 5.73 s | 12.4 s | 0 |

**Sweep D — 60 requests per level (repeat of C with the full level list)**

| concurrency | throughput (req/min) | latency mean | p50 | max | errors |
|---|---|---|---|---|---|
| 1 | 11.9 | 5.03 s | 4.25 s | 25.1 s | 0 |
| 4 | 48.7 | 4.77 s | 4.41 s | 14.0 s | 0 |
| 8 | 81.0 | 5.72 s | 4.41 s | 17.8 s | 0 |
| 10 | 52.2 | 5.88 s | 4.24 s | 57.7 s | 0 |
| 12 | 24.8 | 9.72 s | 3.64 s | 107.4 s | 0 |

**Sweep E — 120 requests per level (tie-break)**

| concurrency | throughput (req/min) | latency mean | max | errors |
|---|---|---|---|---|
| 10 | 99.4 | 5.87 s | 17.4 s | 0 |
| 12 | 127.2 | 5.12 s | 15.2 s | 0 |

## Decision: concurrency = 10

Zero errors at every level in four of five sweeps (sweep B had one failure at
concurrency 4).  The medians across the sweeps are:

| concurrency | observed throughputs (req/min) | median |
|---|---|---|
| 8 | 17.0, 64.9, 25.8, 81.0 | ~45 |
| 10 | 36.1, 82.4, 112.9, 52.2, 99.4 | **~82** |
| 12 | 43.9, 59.1, 116.7, 24.8, 127.2 | ~59 |

Concurrency 10 has the best median throughput and the mildest tail: concurrency 12
produced a 107 s request (sweep D) and concurrency 8 a 120 s request (sweep C),
both uncomfortably close to the 150 s hard deadline, and such a stall costs
wall-clock time even though it does not fail.

**Chosen concurrency: 10.**  Expected sustained throughput ~80 req/min
(the pilot README's 70 req/min estimate from the old pilot is in the same range;
its 1.2 s/request figure does not hold for this route and this prompt size —
the measured per-request latency is ~5 s).

## usage shape

```json
{
  "latency_ms": 4391,
  "input_tokens": 1838,
  "output_tokens": 150,
  "total_tokens": 1988,
  "http_status": 200,
  "request_retries": 0
}
```

- usage keys: `input_tokens` / `output_tokens` / `total_tokens` (plain OpenAI
  `usage` object; the gateway renames `prompt_tokens` -> `input_tokens`).
- **no reasoning block**: the reply body carries only the assistant text — no
  `reasoning_content`, no `<think>` part.  A sample reply:

```
{"action":"ask_human","question":"Where is the laptop?"}
```

- `output_tokens` ~150 for a one-line JSON action, so the 4000-token budget is
  ample; the doubling-on-empty-reply path in the client is kept as insurance
  only and was not triggered in these sweeps.

## Time estimate at concurrency 10

| scenario | calls | at 80 req/min |
|---|---|---|
| ~15 calls per episode (expected) | 16,200 | ~3.4 h |
| 30 calls per episode (worst case, every episode runs to max_steps) | 32,400 | ~6.8 h |

The M5 pilot (seeds 1000-1001, 36 episodes, identical configuration) measures
the real figure before the main run starts.
