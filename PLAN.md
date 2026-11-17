# PLAN — Dynamic House 受控重跑

> 目标：在修好对照设计之后，量化两个正交开关各自带来多少成功率与成本变化：
> **(R) 记忆表示** ∈ {window, append, ledger} × **(P) 策略提示** ∈ {N (neutral), C (cost)}。
> 正结果和负结果都要如实写进报告。

---

## 0. 为什么要重做（pilot-v1 的四条缺陷）

1. **臂混杂**：旧 pilot 的 ledger 臂额外获得约 6,000 字符环境专用策略提示，系统提示 7,388 字符；
   append-only 臂只有 1,342 字符基础提示 + 一句话。p=0（世界静止，记忆不可能过期）时两者仍差约 10pp
   （100% vs 90%）→ 差距来自提示而不是记忆结构。
2. **环境偏向"总是问人"**：不依赖巡检记忆的脚本 "ask_fetch" 在旧环境里成功率 94–100%，环境无法分辨设计。
3. **ask_human 子串匹配**：`book` 命中 `notebook`，含 notebook 的目标永远问不了人（60 个种子里有 11 个）。
4. **双模型不可复现**：DeepSeek 额度耗尽。

新实验 = 修环境 → 先用脚本策略定环境版本 → 对称提示 + 两个正交开关 → 预注册 → 重跑 → 报告。

---

## 1. 硬约束

- Windows / Surface Laptop 5 / 16GB / 无 GPU。Python ≥ 3.11，用 **uv**。
- 依赖仅：标准库 + numpy + matplotlib + pytest。HTTP 用标准库 `urllib`（与旧客户端一致）。
- **不装 torch，不装任何仿真器。**
- `git init`，不加 remote，不 push。不提交任何 key；占位值 `local`，真 key 从 `MAGPIE_API_KEY` 环境变量读。
- 旧仓库只读：本地副本在 `_ref/gate_dynamic_house`（`.gitignore` 掉了，绝不修改）。
- 路径一律用 `pathlib`；读写文件显式 `utf-8`；不假设 bash。

> ⚠️ **运行前请把电源设为「插电时从不睡眠」（Windows: 设置 → 系统 → 电源 → 屏幕和睡眠 → 接通电源时从不睡眠）。**
> 正式跑约 4 小时（估算见 §5），中途休眠会打断 run 的断点续跑并拖慢整体。

---

## 2. 模型与额度

- 网关：本地 Magpie `http://127.0.0.1:3425`，OpenAI 兼容 `POST /v1/chat/completions`。
- **主力模型：`minimax-code-global/MiniMax-M3.1-Flash`（无限额度）。**
  开发 / 冒烟 / 正式实验一律只用它。其他模型额度有限（DeepSeek 已耗尽）→ 默认禁止；
  确需使用先停下来问用户，并给出预计调用次数。
- 客户端：移植 `_ref/gate_dynamic_house/agents.py` 的 `MagpieClient`
  （temperature=0、max_tokens=4000、空文本翻倍重试上限 16000、单请求硬墙钟超时 150s）。不重新发明协议。
- 先 `GET /v1/models` 确认模型 ID 在列表里；不在就停下报告候选。
- 基础设施失败（超时/空响应/5xx/限流）用指数退避重试到拿到有效回复，不算 agent 失败，记录重试次数。
  重试仍失败的回合标 `infra_failed`，不进分析，报告个数并在最后补跑。

---

## 3. 环境（`src/dynhouse/env.py`）

复制旧 `env.py`，**只改两处**：

- **(a)** `ask_human` 的物品名匹配改成整词匹配 `named_items(question)`：
  `notebook` 不再命中 `book`；物品名里的下划线或空格都算分隔（`coffee_mug` 与 `coffee mug` 都认）。
- **(b)** 新增构造参数 `max_asks`（主版本取 1）：第 2 次**有效** ask_human 起返回 `INVALID: ask limit reached.`
  （0 预算、占 1 步，与其他 INVALID 一致）。无效提问（没点名物品等）不计入次数。

其余语义一律不动：5 个房间、18 件物品（6 件 high_risk）、预算 60、最长 30 步、
成本 move 2 / observe 3 / ask_human 10 / pick 1 / place 1、缺失 pick −15、
high_risk 误抓或抓空 −25 且立即失败、inspection_gap=8、p∈{0,0.2,0.4}、`n_targets = 2 + seed % 2`、
室友优先移动当前待办目标、被问过的物品在抓住前不再被移动。

> **已知设计选择（报告中披露）**：室友优先移动当前待办目标。随机从 18 件物品里移只有约 10% 命中目标，
> "过期"几乎不会发生，所以保留这条。

`nofreeze` 变体（不冻结、不限 ask）只在主实验之后跑。

---

## 4. 里程碑

| 里程碑 | 内容 | 产出 |
|---|---|---|
| **M0** | 读旧仓库（`agents.py` 客户端与 BASE_SYSTEM、`run_benchmark.py` 的并发与断点续跑、`ledger.py`），写 PLAN.md | `PLAN.md`、`.gitignore`、`pyproject.toml` |
| **M1** | 网关探测：`/v1/models`；同一请求体在并发 1/4/8/10/12 下的吞吐、延迟、错误率；选定最高的零错误并发；记录 usage 形态与是否有推理块 | `docs/GATEWAY.md` |
| **M2** | env + 单测 + 脚本参考线（对旧 env 复现参考表，对新 env 一致） | `src/dynhouse/env.py`、`src/dynhouse/scripted.py`、`tests/` |
| **M3** | 记忆构造器、提示、一致性测试、agent 循环、runner（并发 + 断点续跑 + infra 重试） | `src/dynhouse/{memory,prompts,gateway,agent,run}.py` |
| **M4** | 开发种子冒烟：6 臂 × p=0.2 × 种子 0–4（30 局）；人工读 ≥6 条完整转录；格式失败率 <3%、无非法示例、无真值泄漏；写 `prompts.lock` | `prompts.lock` |
| **M5** | 写 `PREREG.md` → `git tag prereg-v1` → 试跑量吞吐 → 正式跑（后台，每 10 分钟一行进度） | `results/main/` |
| **M6** | `uv run python -m dynhouse.analyze` 一条命令复现全部表图 | `results/figures/`、`results/tables/` |
| **M7** | `results/report.md`（中文） | `results/report.md` |

---

## 5. 规模与估时

- 开发种子 0–19：只修格式/合法性/解析问题，**不进结果**。禁止根据开发集得分调整 `P=C` 文本或 `R` 呈现方式。
- 测试种子从 **1000** 起（与旧 pilot 的 0–59 不重叠）。
- 主实验：`p ∈ {0, 0.2, 0.4} × 6 臂 × 种子 1000–1059 (N=60)` = **1080 局**。
- 外层循环是种子（逐个），内层是 `p × 臂`；核心 4 臂（`app_N, led_N, app_C, led_C`）在前，`win_N, win_C` 在后。
  → 任何时候中断都有配对完整的数据。分析只用核心臂在三个 p 上都完整的种子。
- 估时：每局约 15 次调用 → 约 **16k 次调用**；按 70 请求/分钟 → **约 4 小时**。
  先用种子 1000–1001 试跑（36 局，配置与正式跑完全相同，结果保留并计入正式数据）量真实吞吐。
  **若预计总时长 > 5.5 小时，停下来问用户（建议把 N 降到 40），不自行改设计。**
- 预注册内唯一一次延伸：只在 §7 决策表给不出结论时触发（S 为 INCONCLUSIVE；或 S 为 NOT_NEEDED 且 Π 为 INCONCLUSIVE），
  再跑种子 1060–1099（N=100）。
- 稳健性（主结论之后，可选）：变体 `nofreeze`，4 个核心臂 × p ∈ {0,0.2,0.4} × 种子 1000–1039。

---

## 6. 六臂与一致性铁律

`win_N, app_N, led_N, win_C, app_C, led_C`

**除 R、P 这两个开关外，臂与臂之间一个字符都不许不同。**

- `BASE_SYSTEM`：6 个臂逐字相同（从旧 `BASE_SYSTEM` 出发，补上旧版只告诉部分臂的规则）。
- `P=N`：不追加任何内容。`P=C`：在 BASE 末尾追加逐字固定的 DECISION GUIDANCE 段。
- 用户消息 = `{"state": ..., "recent_history": 最近4步原始, "memory": R 三选一}`。
  `memory` 一律由代码确定性构造，不用 LLM 抽取。
- 一致性测试（pytest，任何 LLM 运行前必须通过）：同一 `(seed,p,step)`，6 臂 system prompt 只在 P 后缀处不同，
  用户消息只在 `memory` 字段不同。字符数表写进 `docs/PARITY.md`。

---

## 7. 判定规则（冻结于 `PREREG.md`）

- `S` = 记忆结构效应 = 对 `P∈{N,C}`、`p∈{0.2,0.4}` 共 4 格取平均的 `SR(led_P,p) − SR(app_P,p)`。
- `S0` = 阴性对照 = 对 `P∈{N,C}` 取平均的 `SR(led_P,0) − SR(app_P,0)`；CI 应含 0，否则记 "control failed"。
- `Π` = 策略提示效应 = 对 `R∈{app,led}`、`p∈{0.2,0.4}` 共 4 格取平均的 `SR(R_C,p) − SR(R_N,p)`。
- δ = 10pp。判定量 ≥ +δ 且 CI 下界 > 0 → `HELPS`；CI 上界 < +δ → `NOT_NEEDED`；其余 → `INCONCLUSIVE`。
- 标签：`STRUCTURE_HELPS / STRUCTURE_NOT_NEEDED`、`PROMPT_HELPS / PROMPT_NOT_NEEDED`。
- CI = 对种子的配对 bootstrap（≥10000 次，固定随机数种子，同一种子的所有 p 与臂一起重抽）。

---

## 8. 停下来问用户的条件（仅此五类）

1. 网关或主力模型不可用；
2. 两轮修复后单测或脚本参考线仍对不上；
3. 预计总时长 > 5.5 小时；
4. 需要调用非主力模型；
5. 需要改动 §3 的环境语义或 §7 的判定规则。

需要用户动手的事（放文件、授权、电源设置）一次性列成清单，不一件件问。

---

## 9. 工作纪律

- 数字一律来自真实日志；负结果如实写。
- 不用 LLM 的结果去选环境版本或改提示。
- 运行期间只汇报进度、吞吐和 infra 失败率，**不看各臂成功率并据此改动任何东西**。
- 代码保持小，不重建旧仓库那种大而全的结构。
