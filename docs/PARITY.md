# PARITY -- per-arm prompt character counts

Seed 1000, disturbance_p 0.2.  The four core arms (app_N, led_N, app_C, led_C) carry the analysis; `win_*` are the memory-free baselines.

## System prompt

| arm | R | P | system chars | base + suffix |
|---|---|---|---|---|
| win_N | window | N | 2502 | BASE_SYSTEM |
| app_N | append | N | 2502 | BASE_SYSTEM |
| led_N | ledger | N | 2502 | BASE_SYSTEM |
| win_C | window | C | 2944 | BASE_SYSTEM + P=C suffix |
| app_C | append | C | 2944 | BASE_SYSTEM + P=C suffix |
| led_C | ledger | C | 2944 | BASE_SYSTEM + P=C suffix |

- `BASE_SYSTEM`: 2502 chars
- `P=C` suffix: 441 chars
- P=C system prompt: 2944 chars

## User message, step by step

| arm | step | system chars | user chars | state | history | memory | memory type |
|---|---|---|---|---|---|---|---|
| win_N | 1 | 2502 | 1101 | 1059 | 2 | 2 | list |
| win_N | 2 | 2502 | 1177 | 1052 | 85 | 2 | list |
| win_N | 3 | 2502 | 1306 | 1052 | 214 | 2 | list |
| win_N | 4 | 2502 | 1389 | 1049 | 300 | 2 | list |
| win_N | 5 | 2502 | 1501 | 1049 | 412 | 2 | list |
| win_N | 6 | 2502 | 1535 | 1049 | 446 | 2 | list |
| app_N | 1 | 2502 | 1516 | 1059 | 2 | 417 | list |
| app_N | 2 | 2502 | 1592 | 1052 | 85 | 417 | list |
| app_N | 3 | 2502 | 1823 | 1052 | 214 | 519 | list |
| app_N | 4 | 2502 | 1906 | 1049 | 300 | 519 | list |
| app_N | 5 | 2502 | 2102 | 1049 | 412 | 603 | list |
| app_N | 6 | 2502 | 2136 | 1049 | 446 | 603 | list |
| led_N | 1 | 2502 | 3528 | 1059 | 2 | 2429 | dict |
| led_N | 2 | 2502 | 3604 | 1052 | 85 | 2429 | dict |
| led_N | 3 | 2502 | 3728 | 1052 | 214 | 2424 | dict |
| led_N | 4 | 2502 | 3811 | 1049 | 300 | 2424 | dict |
| led_N | 5 | 2502 | 3903 | 1049 | 412 | 2404 | dict |
| led_N | 6 | 2502 | 3937 | 1049 | 446 | 2404 | dict |
| win_C | 1 | 2944 | 1101 | 1059 | 2 | 2 | list |
| win_C | 2 | 2944 | 1177 | 1052 | 85 | 2 | list |
| win_C | 3 | 2944 | 1306 | 1052 | 214 | 2 | list |
| win_C | 4 | 2944 | 1389 | 1049 | 300 | 2 | list |
| win_C | 5 | 2944 | 1501 | 1049 | 412 | 2 | list |
| win_C | 6 | 2944 | 1535 | 1049 | 446 | 2 | list |
| app_C | 1 | 2944 | 1516 | 1059 | 2 | 417 | list |
| app_C | 2 | 2944 | 1592 | 1052 | 85 | 417 | list |
| app_C | 3 | 2944 | 1823 | 1052 | 214 | 519 | list |
| app_C | 4 | 2944 | 1906 | 1049 | 300 | 519 | list |
| app_C | 5 | 2944 | 2102 | 1049 | 412 | 603 | list |
| app_C | 6 | 2944 | 2136 | 1049 | 446 | 603 | list |
| led_C | 1 | 2944 | 3528 | 1059 | 2 | 2429 | dict |
| led_C | 2 | 2944 | 3604 | 1052 | 85 | 2429 | dict |
| led_C | 3 | 2944 | 3728 | 1052 | 214 | 2424 | dict |
| led_C | 4 | 2944 | 3811 | 1049 | 300 | 2424 | dict |
| led_C | 5 | 2944 | 3903 | 1049 | 412 | 2404 | dict |
| led_C | 6 | 2944 | 3937 | 1049 | 446 | 2404 | dict |

## What differs between arms

- **system prompt**: only the P suffix.  `win_*`/`app_*`/`led_*` with the same P are byte-identical; `*_N` differs from `*_C` only by the verbatim DECISION GUIDANCE paragraph.
- **user message**: only the `memory` field.  `state` and `recent_history` are identical across all six arms at every step.
- The memory field is a list (`window`, `append`) or a dict (`ledger`); its size depends on the representation, which is the point of the R switch.

## Consistency checks (pytest)

- `tests/test_prompts.py::test_base_system_is_identical_for_every_arm`
- `tests/test_prompts.py::test_user_messages_differ_only_in_the_memory_field`
- `tests/test_prompts.py::test_over_a_whole_episode_the_arms_differ_only_in_r_and_p`
- `tests/test_prompts.py::test_every_example_action_is_accepted_by_the_environment`
- `tests/test_memory.py::test_ledger_is_recomputable_from_the_append_log`
