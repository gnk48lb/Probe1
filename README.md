# Dynamic House — 受控重跑 (R × P)

在修好对照设计之后，量化两个正交开关各自带来多少成功率与成本变化：

- **R（记忆表示）** ∈ {`window`, `append`, `ledger`}
- **P（策略提示）** ∈ {`N` (neutral), `C` (cost-aware)}

6 个臂：`win_N` `app_N` `led_N` `win_C` `app_C` `led_C`。
除 R、P 外，臂与臂之间一个字符都不许不同（由 `tests/test_prompts.py` 强制）。

设计与判定规则全部冻结在 [`PREREG.md`](PREREG.md)；计划在 [`PLAN.md`](PLAN.md)；
结果报告在 [`results/report.md`](results/report.md)。

## 快速开始

```bash
uv sync                                   # 标准库 + numpy + matplotlib + pytest
uv run pytest -q                          # 60 个测试，含脚本参考线复现（约 45 s）
uv run python -m dynhouse.scripted_table  # 脚本参考线（新环境）
uv run python -m dynhouse.probe_gateway   # M1 网关探测 -> docs/GATEWAY.md
uv run python -m dynhouse.parity          # -> docs/PARITY.md（每臂 prompt 字符数）
uv run python -m dynhouse.run --help      # 运行器
uv run python -m dynhouse.analyze         # 全部表与图 -> results/{tables,figures}
```

正式跑（后台，断点续跑）：

```bash
uv run python -m dynhouse.run --seed-start 1000 --seeds 60 --output-dir results/main --concurrency 12
```

每局写盘才算完成；中断后重跑同一条命令即可续跑。
`prompts.lock` 校验提示模板与记忆构造代码的哈希，不一致时运行器拒绝启动。

## 目录

```
src/dynhouse/
  env.py          环境（相对 pilot 只改两处：整词匹配 + max_asks）
  scripted.py     四个零 LLM 成本的脚本参考策略
  scripted_table.py  脚本参考线表格
  memory.py       三种记忆表示 + 取证年龄追踪（harness 侧）
  prompts.py      BASE_SYSTEM（六个臂逐字相同）+ P=C 后缀
  gateway.py      Magpie 客户端（从旧仓库移植）
  agent.py        一局一回合的 agent 循环
  run.py          并发 + 断点续跑 + infra 重试的运行器
  analyze.py      全部表与图（一条命令复现）
  probe_gateway.py / parity.py / show_episode.py
tests/            env / scripted / memory / prompts 四组测试
docs/             GATEWAY.md（网关探测）、PARITY.md（提示字符数）
results/          main/（episodes.jsonl, traces.jsonl, raw.jsonl, run_manifest.json）
                  tables/、figures/、report.md
_ref/             旧仓库的只读副本（.gitignore，不修改）
```

## 环境相对 pilot-v1 的两处改动

1. `ask_human` 整词匹配：`notebook` 不再命中 `book`；`coffee mug` 与 `coffee_mug` 都认。
2. `max_asks`（主版本 1）：第 2 次**有效**问人起返回 `INVALID: ask limit reached.`
   （0 预算、占 1 步）。无效提问不计入次数。

其余语义一字未动：5 房间 / 18 物品（6 high_risk）/ 预算 60 / 30 步 /
move 2、observe 3、ask_human 10、pick 1、place 1 / 缺失 pick −15 /
high_risk 误抓或抓空 −25 且立即失败 / `inspection_gap=8` / `p∈{0,0.2,0.4}` /
`n_targets = 2 + seed % 2` / 室友优先移动当前待办目标 / 问过的物品在抓住前不再被移动。

新环境在 1000 个种子上**逐格复现**旧环境的脚本参考线（success 差 ≤0.1pp、cost 差 ≤0.1）。

## 模型

`minimax-code-global/MiniMax-M3.1-Flash`，经本地 Magpie 网关 `http://127.0.0.1:3425`
（OpenAI 兼容协议，temperature=0，max_tokens=4000）。
API key 从环境变量 `MAGPIE_API_KEY` 读，默认占位值 `local`。
