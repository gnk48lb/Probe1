<!-- 报告草稿：稳定章节先行，数字与 TL;DR 在主实验完成后填入。 -->

# Dynamic House 受控重跑：R（记忆表示）× P（策略提示）

## 1. TL;DR

<!-- 待填 -->

## 2. 与 pilot-v1 的差异

<!-- 待填 -->

## 3. 方法与一致性检查

### 3.1 环境（只改两处）

pilot-v1 的环境把「总是问人」当成几乎无代价的万能手段：脚本策略 `ask_fetch` 在旧环境里成功率
94–100%，因此任何记忆设计都区分不出来；`ask_human` 用子串匹配物品名，`book` 命中 `notebook`，
60 个种子里有 11 个的目标永远问不了人。

本实验的环境只改两处，其余语义一字未动：

| 改动 | 内容 |
|---|---|
| (a) 整词匹配 | `ask_human` 用 `named_items(question)`：`notebook` 不再命中 `book`；`coffee mug` 与 `coffee_mug` 都认 |
| (b) `max_asks` | 主版本 1：第 2 次**有效**问人起返回 `INVALID: ask limit reached.`（0 预算、占 1 步）；无效提问不计入次数 |

未改动：5 房间、18 件物品（6 件 high_risk）、预算 60、最长 30 步、成本
move 2 / observe 3 / ask_human 10 / pick 1 / place 1、缺失 pick −15、high_risk 误抓或抓空
−25 且立即失败、`inspection_gap=8`、p∈{0,0.2,0.4}、`n_targets = 2 + seed % 2`、
室友优先移动当前待办目标、被问过的物品在抓住前不再被移动。

**环境版本由脚本参考线选定，不按 LLM 结果调整。** 在 1000 个种子（0–999）上，新环境逐格复现旧环境
`fixed+askcap1` 变体的参考线（success 差 ≤0.1pp、cost 差 ≤0.1，容差分别是 ±2pp / ±1.5）：

| policy | p=0 | p=0.2 | p=0.4 |
|---|---|---|---|
| trust_memory | 100 / 11.8 | 46.5 / 26.6 | 26.2 / 30.7 |
| observe_pick | 100 / 19.3 | 64.5 / 41.9 | 36.8 / 47.8 |
| ask_fetch | 100 / 26.3 | 66.3 / 43.4 | 46.3 / 47.4 |
| ledger_gate | 100 / 11.8 | 70.9 / 42.7 | 47.6 / 47.6 |

主版本里没有任何脚本策略一招通吃（p=0.2 最高 70.9%，p=0.4 最高 47.6%），环境因此具备分辨力。
对照：旧环境原样里 `ask_fetch` = 100 / 96.1 / 94.2 —— 这正是旧闸门不可信的主因。

### 3.2 两个正交开关

| | P=N（neutral） | P=C（cost-aware） |
|---|---|---|
| **R=window** | `win_N` | `win_C` |
| **R=append** | `app_N` | `app_C` |
| **R=ledger** | `led_N` | `led_C` |

一致性铁律：**除 R、P 之外，臂与臂之间一个字符都不许不同。**

- `BASE_SYSTEM` 六个臂逐字相同（2502 字符）。它以旧 pilot 的 `BASE_SYSTEM` 为起点，补上了旧版只告诉
  部分臂的规则：被问过的物品在抓住前不再被移动、每局最多问人 1 次、18 个物品的风险级别、
  `disturbance_p` 的含义；并把旧版那个非法示例 `Where is the current_target item?` 换成合法的
  `Where is the coffee_mug?`。
- `P=C` 在 BASE 末尾逐字追加固定的 DECISION GUIDANCE 段（441 字符 → 2942 字符），
  不加任何环境专用微策略。
- 用户消息 = `{"state", "recent_history", "memory"}`：`state` 与 `recent_history` 六个臂逐字相同，
  只有 `memory` 字段随 R 变化。`memory` 全部由代码确定性构造，不用 LLM 抽取。

这些不变量由 `tests/test_prompts.py` 强制：系统提示只在 P 后缀处不同、用户消息只在 `memory` 字段不同，
并且是**整局**逐步对比（同一 stub 客户端跑六臂，逐请求比对）。每臂 prompt 的字符数见
[`docs/PARITY.md`](../docs/PARITY.md)。

### 3.3 记忆构造与信息等价

- `window`：`[]`（无长期记忆，也看不到巡检记录）。
- `append`：只追加的原始记录 —— 巡检 5 条（step=−8）、每次 observe 一条、每次有效 ask_human 一条、
  每次失败的 pick 一条；不加任何评论性文字。
- `ledger`：每个物品一行 `{"item", "believed_room", "last_verified_step", "age", "source",
  "superseded_count"}`，`believed_room` 为 null 时额外带 `last_room`；更新规则照旧仓库的
  `ledger.py`（正向看到 → 覆盖并累计 superseded；观察到缺失 → 置 null；失败 pick → 置 null）。
  `risk_level` 不进 ledger（已在 BASE 里）。

信息等价由 `tests/test_memory.py` 保证：200 条随机事件序列下，ledger 的每个字段都能**只由 append 日志**
重算（ledger 的信息不多于 append）；ledger 里存的是「信念」而不是真值——测试断言目标物被室友移动后，
ledger 仍记着巡检时的房间。

### 3.4 运行与统计

- 模型 `minimax-code-global/MiniMax-M3.1-Flash`（本地 Magpie 网关，OpenAI 兼容协议），
  temperature=0、max_tokens=4000、单请求硬墙钟 150s。网关探测见 [`docs/GATEWAY.md`](../docs/GATEWAY.md)：
  5 轮并发扫描（1/4/8/10/12），选中并发 10。
- 每步 1 次 LLM 调用；解析失败**重发同一请求**最多 2 次（不占步数，记 `format_retries`），
  仍失败则当一次 INVALID 动作（占 1 步、不扣预算）。基础设施失败（超时/空响应/5xx/限流）
  用指数退避重试到拿到有效回复，不算 agent 失败；重试仍失败的回合标 `infra_failed`，不进分析，
  最后补跑。
- 每局写盘才算完成，可断点续跑；`prompts.lock` 冻结提示模板与记忆构造代码的哈希，不一致时拒绝运行。
- 统计：所有对比按种子配对；95% CI = 对种子的配对 bootstrap（10000 次，固定随机种子 20261117，
  同一种子的所有 p 与臂一起重抽）；δ = 10pp。

## 4. 结果

<!-- 待填 -->

## 5. 威胁有效性

<!-- 待填 -->

## 6. 下一步

<!-- 待填 -->
