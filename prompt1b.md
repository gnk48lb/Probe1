# Probe 1b：controller（harness 门控）实验

你在 D:\code\ClaudeCode\Probe1（Dynamic House 环境，已有一次预注册实验 Probe 1，结果已冻结）里工作。这是一个有纪律的科研任务：先读、先预注册、再跑，不要抢步。对我的汇报用中文，仓库里的文档用英文。

## 0. 先读
PREREG.md、results/report.md、src/dynhouse/{env,memory,prompts,agent,run,analyze,scripted}.py、tests/，以及仓库根目录的 age_gate_reference.py（门控规则的可执行定义，见 §3）。

## 1. 背景与问题
Probe 1（已被独立复核，数字可信）：6 个 arm（记忆 window/append/ledger × 提示 N/C）在 p>=0.2 全部打平，S=+2.3pp [-3.2,+7.5]，Π=+1.8pp [-4.0,+7.5]。记忆表示和"决策提示"都不是瓶颈。
同时，一个 15 行的脚本（按"风险 × 证据年龄"决定要不要验证）明显更强：在 Probe 1 的 100 个测试 seed 上 p=0.2 得 71%、花费 37.8；LLM 各 arm 是 56–67%（均 59%），花费约 45。在 1000 个 held-out seed 上脚本 p=0.2 / 0.4 分别为 75% / 56%，而 LLM 在 p=0.4 是 42–48%。C prompt 已经用文字写了同样的规则，LLM 并没有执行。

本实验要回答：**把"何时该验证"这个决定交给确定性的 controller（harness 侧），LLM 的成功率能恢复多少？**
controller 的权限梯度：none → advice（只给建议）→ shield（拦截）→ advice+shield → recommend（直接给推荐动作，作阳性对照）。

Probe 1 的报告里有几处说得比数据强，这次必须避免：
(a) 把"失败局里发生重复 ask 的比例(93.7%)"当原因。成功局里 p>0 也有 68% 出现无效动作。任何失败分析都必须同时给出成功局的基线。
(b) 互斥的优先级失败分类（几乎所有预算耗尽都被归进了"wasted the ask"）。
(c) 把 freeze 规则的机械结果（"人类回答 0/1342 失败"）当成发现。
(d) 没做余量分析就定 δ=10pp。脚本测算显示：该环境里任何"利用证据年龄"的策略，比最好的简单策略也只高 +1 ~ +9pp。
(e) 分析代码在主实验已有部分数据之后才写。
(f) 没有阳性对照，无法证明这个实验"测得出"效应。

## 2. 硬性规则
1. 冻结：不得修改 PREREG.md、results/**、src/dynhouse/prompts.py、memory.py，不得使 prompts.lock 失效。env.py / run.py / analyze.py 只许"加法式"扩展（新增可选参数，默认行为逐字节不变）；现有全部 tests 必须继续通过。新代码放新文件（controller.py、prompts_1b.py、run_1b.py、analyze_1b.py、tests/test_*_1b.py 等）。先 `git tag probe1-final`，再在分支 `probe1b` 上工作；每个 Phase 至少一个提交。
2. 先预注册后跑数：PREREG_1B.md 与 prompts_1b.lock（对 prompts_1b.py、controller.py、analyze_1b.py、age_gate_reference.py 做 sha256）必须提交并打 tag `prereg-1b`，之后才允许跑任何测试 seed（3000 及以上）。tag 不得改写；若评审后需要改动，新建 `prereg-1b-v2`，仍须在任何测试 seed 之前。
3. 不偷看：主实验期间只许看基础设施健康指标（完成数、HTTP 错误率、格式失败数、墙钟、token），不许看各 arm 的成功率。唯一允许依据结果做的决定，是 §4.7 预先写明的扩展规则。
4. analyze_1b.py 及其单元测试必须在主实验前完成并锁定。主实验期间只许修真 bug，并记入 DEVIATIONS.md。
5. controller 严禁读取 ground truth（物品真实位置、roommate 内部状态、env 的 RNG）。它只能使用：公开 state、item_risk_levels、agent 自己可见的历史（观察、回答、动作）以及由此构成的 ledger。必须有测试证明（T3）。
6. 模型：主实验只用 minimax-code-global/MiniMax-M3.1-Flash，temperature 0，沿用 Probe 1 的 gateway 客户端、并发 10–12、重试与基础设施失败修复规则。绝不要通过 Magpie 网关调 Gemini（会导致封号），也不要把 Antigravity / Gemini 当实验模型。
7. 不要把任何 API key、邮箱写进仓库。Windows 笔记本跑长任务：日志写文件、任务可恢复、提醒我关掉休眠。

## 3. 参照实现（脚本，不涉及 LLM）
age_gate_reference.py 是门控规则的可执行定义（文件开头的 docstring 就是规则全文）。你的 controller 必须与它给出完全相同的决策。它在本环境（max_asks=1, freeze_asked=True, n_targets=2+seed%2）上的数字，是你的回归目标（容差 ±1.5pp；controller 的 recommend 在无 LLM 情况下全程自动执行时必须复现）：

    p     seeds 0-999: SR%  cost   |  seeds 3000-3099: SR%  cost
    0.0        100.0   11.8        |        100.0   11.8
    0.1         87.7   32.8        |         90.0   32.7
    0.2         75.3   39.3        |         72.0   38.5
    0.4         55.8   44.0        |         54.0   43.8

另外，在 scripted.py 里补上 p=0.1，并在 seeds 3000–3199 上算出 4 条旧脚本线（trust_memory、observe_pick、ask_fetch、ledger_gate）与 age_gate 的 SR/cost，作为最终图里的参照线。

## 4. 实验设计（逐字写进 PREREG_1B.md，并一字不改地执行）

### 4.1 对所有 arm 相同的部分
- 环境 = Probe 1 的 env（max_asks=1, freeze_asked=True, whole-word 提问匹配）。加法式新增：
  - p 放宽为 0<=p<=1（本实验用 0.1 / 0.2 / 0.4）。做成可选项（例如 allow_any_p，默认仍用旧校验），避免破坏现有测试；
  - 可选项 expose_asks=True：public_state 增加 "asks_remaining"（整数）；
  - "controller veto" 步：被拦截的动作不改变世界、不扣预算、step+1（计入 30 步上限），单独计数 blocked_count。
- 记忆表示：所有 arm 都用 ledger（Probe 1 的 ledger 视图，字段不变）。
- system prompt（prompts_1b.py）：五个主 arm 逐字节相同 = Probe 1 的 BASE_SYSTEM + PROMPT_C（直接 import，不要复制）+ 下面这一段（英文原文，一字不改）：

    CONTROLLER. A controller sits between you and the world. The state field "controller" lists what it does in this episode ("advice", "shield", "recommend"; an empty list means it does nothing). "advice": every memory entry carries advice "trust" or "verify", computed from the item's risk level and from the age and the source of your evidence; "verify" means re-check the item before acting on it. "shield": picking a high_risk item whose advice is "verify" is BLOCKED (nothing is picked, 0 budget, 1 step). "recommend": the state carries controller_recommendation, one action you may follow or override. The state field "asks_remaining" is the number of ask_human actions you still have.

  各 arm 之间唯一的差别，是 controller 实际做什么，以及 state["controller"] 如实列出它做什么。

### 4.2 arms
    base      controller = []
    hint      controller = ["advice"]（ledger 每行增加 advice 字段）
    shield    controller = ["shield"]（按同一条规则拦截；ledger 里不显示 advice）
    both      controller = ["advice","shield"]
    auto      controller = ["recommend"]（阳性对照；state 里带 controller_recommendation；ledger 里不显示 advice）
    base_old  （可选，最后跑）原样复刻 Probe 1 的 led_C：原 system prompt（无 CONTROLLER 段）、state 无 asks_remaining、无 controller 字段。仅 p=0.2、0.4。

### 4.3 门控规则（固定；禁止用任何 LLM 数据调参）
对 ledger 的每个 item，按顺序判定：
  1. believed_room 为 None → "verify"
  2. disturbance_p == 0 → "trust"（静态世界：controller 永不拦截、永不推荐验证）
  3. source == "ask_human" 且该物品尚未被 pick → "trust"（人类回答在 freeze 规则下不会再被挪动，这是公开规则）
  4. high_risk：age <= 1 → "trust"，否则 "verify"
  5. low_risk：age <= 20 → "trust"，否则 "verify"
age 即 ledger 视图里的 age 字段（当前 step − last_verified_step）。
shield：对 pick(item)，若 item 为 high_risk 且按上述规则（与 agent 此刻所见的 ledger 视图完全相同的计算）为 "verify" → 拦截，返回 "BLOCKED by controller: evidence for <item> is stale (age N). Verify first (observe in its room, or ask_human)."
recommend：按 age_gate_reference.py 的策略给出下一步动作（JSON 动作）。

### 4.4 种子、p、规模
- dev seeds 0–19：只用于烟测，不得用来调规则。
- 测试 seeds：3000–3099（Stage 1）；3100–3199（Stage 2 扩展，§4.7）。1000–1099 和 2000–2399 已被用过，不要用。
- p ∈ {0.1, 0.2, 0.4}；n_targets = 2 + seed % 2。
- Stage 1 = {base, hint, shield, both, auto} × 3 个 p × 100 seeds = 1500 个 episode（约 4 小时 @ 约 130 calls/min）。按 seed 块（3000–3024、3025–3049、……）做外层循环，所有 cell 轮转，保证随时中断都留下"完整 seed"。
- Stage 3（可选，最后）：base_old × p∈{0.2, 0.4} × seeds 3000–3099。

### 4.5 估计量与判定
全部使用：按 seed 成对 bootstrap（resample seeds），10,000 次，RNG seed 20261118，95% 百分位 CI；只使用"参与比较的所有 arm 在所有 p 上都完整"的 seed；基础设施失败先修复重跑，规则同 Probe 1，并如实报告修复数。
- 主要（唯一 confirmatory）估计量：G_both = mean_p [SR(both,p) − SR(base,p)]，p∈{0.1,0.2,0.4}。
- 阳性对照：PC = mean_p [SR(auto,p) − SR(base,p)]。
- 次要（只报点估计 + CI，不下 verdict）：G_hint、G_shield、both−hint、both−shield，以及每个 p 单独的差值。
- 判定规则（δ=5pp。刻意低于 Probe 1 的 10pp：脚本余量测算显示该环境里可达的增益本来就小）：
  HELPS：点估计 >= +5 且 CI 下界 > 0；NOT_NEEDED：CI 上界 < +5；否则 INCONCLUSIVE。
- 仪器有效性：PC 须判为 HELPS。否则整个实验标记 INSTRUMENT_FAILED：不得对 hint / shield / both 的零结果做任何"没用"的解读，立即停下汇报并诊断（遵循率、格式失败、拦截死循环）。
- 解释表（写进 PREREG）：
    PC=HELPS 且 G_both=HELPS            → harness 门控能恢复一部分差距 → 论文主线
    PC=HELPS 且 G_both 为其他           → LLM 用不好建议/拦截，只有"完全托管"才有效 → "controller 权限梯度"叙事
    PC 不是 HELPS                       → 仪器失败，见上

### 4.6 次要 / 机制指标（预先列出，其余一律标 exploratory）
成功率、总花费、安全违规率、步数、LLM 调用数、token、blocked_count、invalid_count；
- pick_records 对所有 arm 增加字段：source、believed_room、rule_advice（该 pick 时按 §4.3 规则本应给出的建议）；
- 高风险"该验证却尝试 pick"的次数：对所有 arm（含 base）回溯地用同一条规则判定；shield 下统计被拦截的尝试；
- advice 遵循率（hint/both）：advice=verify 的目标物品，在下一次 pick 前是否做了 observe 或 ask；base 用同一规则回溯计算作对照；auto 的 override 率；
- 预算按动作类型（move/observe/ask/pick/place）的分解：成功局 vs 失败局，每个 arm。
失败分析（取代 Probe 1 的互斥优先级分类）：
- 每个失败局打多个"标志"（非互斥），并同时给出成功局里同一标志的基线比例与相对风险。标志至少包括：竞争型 pick 失败（evidence_age<=1）、过期型 pick 失败（age>=2）、高风险"该验证却 pick"、重复 ask（无效 ask）、预算耗尽、安全违规、从未使用 ask；
- 另给"首个致命事件"（失败局里第一个把它推上失败路径的事件）。定义由你现在写进 PREREG，事后不得调整；
- 共现不得写成因果。

### 4.7 扩展与停止规则
- 仅当 PC=HELPS 且 G_both=INCONCLUSIVE 时，允许且仅允许一次扩展：对 base 与 both 追加 seeds 3100–3199（3 个 p），最终的主要判定使用 200 个 seed；其余估计量仍为 100 个 seed。
- 若因时间被迫中止 Stage 1，只能由墙钟决定；用已完整的 seed 做分析，按同一规则出 verdict，并如实标注 N。

## 5. 执行阶段
Phase 0（无 LLM，<=1h）：env 加法式改动 + 单元测试；跑 age_gate_reference.py 核对 §3 数字；scripted.py 补 p=0.1。
Phase 1：controller.py、prompts_1b.py、run_1b.py（可恢复）、analyze_1b.py。单元测试全部通过才进入下一阶段：
  T1  现有全部测试通过，prompts.lock 校验通过；旧 arm 的 public_state 逐字节不变（固定 seed 的 JSON 哈希）；base_old 的首步 system+user prompt 与 Probe 1 的 led_C 逐字节相同。
  T2  五个主 arm 的 system prompt 逐字节相同。
  T3  controller 不接触 ground truth：把 env 的真实位置/RNG 换成"一访问就抛异常"的哨兵，controller 仍能工作。
  T4  controller 是（公开 state、agent 可见历史/ledger）的纯确定性函数。
  T5  门控规则逐分支的表驱动测试；p=0 时永不拦截。
  T6  shield 语义：被拦截的 pick——预算不变、step+1、不持有物品、计入 30 步上限、blocked_count+1；一直被拦截会在 30 步终止。
  T7  auto 在无 LLM 下自动执行，复现 §3 的数字。
  T8  analyze_1b.py：用已知效应的合成数据验证估计量、成对 bootstrap、三种 verdict（含边界值）与"完整 seed"规则。
Phase 2（烟测）：dev seeds 0–19，p=0.2，五个 arm（约 100 个 episode）。只检查管道是否正常：格式失败率、拦截死循环、每局 blocked 数、token/时长、controller 字段是否如实出现。不得据此调整门控规则；发现实现 bug 可以修，并记入 DEVIATIONS.md。
Phase 3：写 PREREG_1B.md（含 §4 全部内容、解释表、已知局限）、生成 prompts_1b.lock、提交、打 tag prereg-1b。

**CHECKPOINT：做到这里停下，不要继续。** 打印检查清单：commit hash、tag、lock 哈希、T1–T8 结果、烟测摘要、按烟测 calls/min 外推的 Stage 1 预计耗时，以及我需要执行的 push 命令（分支 probe1b + tags；评审需要我先 push）。然后等我说 "GO" 才进入 Phase 4。评审后如需修改，新建 prereg-1b-v2。

Phase 4（GO 之后）：Stage 1。期间只汇报基础设施健康指标。
Phase 5：运行 analyze_1b.py，输出 results_1b/{tables,figures,report.md}。report 必须包含：arms 表；主结果表（SR、CI、cost、安全违规，按 p）；PC 与 G_both 的 verdict 及对应的解释表行；次要估计量；机制指标；失败分析（含成功局基线）；"controller 权限梯度"图（按 p 分面，LLM arm 的 SR 与 CI，脚本线画成水平参照）；DEVIATIONS.md；局限性。把逐步 traces（动作/消息，不含完整 prompt）压缩成 traces_1b.jsonl.gz 提交进仓库，保证失败分析可复现。
Phase 6（可选，我明确说"跑跨模型"才开始；额度有限）：只用一个聚合路由 auto/GLM-5.3-Flash（先 GET /v1/models 确认名称，最多几次探测调用）；只跑 p=0.2；arms = base 与 both；最多 50 个 seed（3000–3049）；并发 1–2；遇 HTTP 429 做长间隔指数退避，持续 429 就直接放弃；记录实际使用的模型串。结果只当"跨模型一致性检查"，不做任何 verdict。

## 6. 做完后的汇报（中文，贴给我）
commit 与 tag；运行概况（episode 数、基础设施失败与修复数、实际 N）；PC 与 G_both 的 verdict；次要估计量；hint/both 的遵循率与 auto 的 override 率；失败分析要点（含成功局基线）；DEVIATIONS；需要我执行的 git push 命令（含 --tags）。不要在汇报里加入预注册之外的结论，事后发现一律标 exploratory。
