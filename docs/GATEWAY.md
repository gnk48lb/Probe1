# M1 -- Magpie gateway probe

- date: 2026-11-17 15:53:19
- base_url: `http://127.0.0.1:3425`
- main model: `minimax-code-global/MiniMax-M3.1-Flash` (present in `/v1/models`: yes)
- catalog size: 27 models
- request body: system 2502 chars + user 3778 chars, temperature=0, max_tokens=4000

## Concurrency sweep

| concurrency | throughput (req/min) | latency mean | p50 | max | errors |
|---|---|---|---|---|---|
| 6 | 54.9 | 6.308 s | 4.617 s | 36.093 s | 0 |
| 8 | 25.8 | 6.888 s | 4.477 s | 120.5 s | 0 |
| 10 | 112.9 | 4.908 s | 4.578 s | 10.031 s | 0 |
| 12 | 116.7 | 5.732 s | 5.266 s | 12.391 s | 0 |

**Chosen concurrency: 12** (highest zero-error throughput: 116.7 req/min).

## usage shape

```
{
  "latency_ms": 8875,
  "input_tokens": 1838,
  "output_tokens": 361,
  "total_tokens": 2199,
  "http_status": 200,
  "request_retries": 0
}
```

- usage/meta keys: ['http_status', 'input_tokens', 'latency_ms', 'output_tokens', 'request_retries', 'total_tokens']
- reasoning block present in the reply: see the sample below

## sample reply head

```
{"action":"ask_human","question":"Where is the laptop?"}
```
