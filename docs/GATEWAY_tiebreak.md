# M1 -- Magpie gateway probe

- date: 2026-11-17 15:57:17
- base_url: `http://127.0.0.1:3425`
- main model: `minimax-code-global/MiniMax-M3.1-Flash` (present in `/v1/models`: yes)
- catalog size: 27 models
- request body: system 2502 chars + user 3778 chars, temperature=0, max_tokens=4000

## Concurrency sweep

| concurrency | throughput (req/min) | latency mean | p50 | max | errors |
|---|---|---|---|---|---|
| 10 | 99.4 | 5.873 s | 4.938 s | 17.36 s | 0 |
| 12 | 127.2 | 5.115 s | 4.305 s | 15.156 s | 0 |

**Chosen concurrency: 12** (highest zero-error throughput: 127.2 req/min).

## usage shape

```
{
  "latency_ms": 7891,
  "input_tokens": 1838,
  "output_tokens": 430,
  "total_tokens": 2268,
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
