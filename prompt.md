你是 Claude Code。当前工作目录是一个全新的文件夹(项目根)。请在这里实现并运行一次「Dynamic House 受控重跑」,严格按下面的规格做。

目标不是证明"我们的 ledger 更好",而是在修好对照设计之后,量化两个开关各自带来多少成功率与成本变化:(R) 记忆表示,(P) 策略提示。正结果和负结果都要如实写进报告。

## 0. 背景(读懂即可,不用复述)
我之前跑过一轮 pilot(旧仓库,只读参考):
- https://github.com/gnk48lb/gate_dynamic_house   动态房间环境 + 4 个 agent + 1440 局
- https://github.com/gnk48lb/phase2   Plan-Bench 实验,本任务不碰
pilot 数据本身可信,但对照设计不成立,所以只当 pilot-v1(探索性),不作确证:
1. 臂混杂:ledger 臂 = 账本 + 约 6,000 字符的环境专用策略提示(系统提示共 7,388 字符);append-only 臂只有基础提示(1,342 字符)+ 一句话。p=0(世界静止,记忆不可能过期)时两者仍差约 10pp(100% vs 90%),说明差距来自提示而不是记忆结构。
2. 环境偏向"总是问人":不依赖巡检记忆的脚本"每个目标都问人再去拿"在旧环境里成功率 94–100%。
3. env.py 的 ask_human 用子串匹配,"book" 命中 "notebook",含 notebook 的目标永远问不了人(60 个种子里有 11 个)。
4. DeepSeek 额度已耗尽,只剩下面的主力模型,旧的双模型设计无法复现。
所以本任务 = 在新文件夹里重做:修环境 → 先用脚本策略定环境版本 → 对称提示 + 两个正交开关 → 预注册 → 重跑 → 报告。

## 1. 硬约束
- 机器:Windows(Surface Laptop 5,16GB,无 GPU)。不要假设 bash;路径用 pathlib;读写文件显式 utf-8。Python>=3.11,用 uv。依赖仅:标准库 + numpy + matplotlib + pytest;HTTP 用标准库 urllib(和旧客户端一致)。不装 torch,不装任何仿真器。
- `git init`,不加 remote,不 push。不提交任何 key;这个网关不需要真 key,占位值 `local` 从环境变量 MAGPIE_API_KEY 读。
- 旧仓库只读:`git clone https://github.com/gnk48lb/gate_dynamic_house _ref/gate_dynamic_house`,把 `_ref/` 写进 .gitignore,绝不修改它。clone 失败就停下来问我本地路径。
- 前置文件:项目根应有我放好的 `scripted_baselines.py`。没有就先停下告诉我(这是允许的第一个问题)。
- 正式跑要几个小时:在 PLAN.md 里提醒我把电源设为"插电时从不睡眠"。runner 必须"每局写盘才算完成"、可断点续跑。

## 2. 模型与额度(我的原话)
模型与额度:通过本地 Magpie 网关(http://127.0.0.1:3425)调用模型。
主力无限额度模型:minimax-code-global/MiniMax-M3.1-Flash

规则:
- 开发、冒烟、正式实验一律只用这个模型。其他模型额度有限(DeepSeek 已耗尽):默认禁止;确需使用先停下来问我,并给出预计调用次数。
- 客户端:读 `_ref/gate_dynamic_house/agents.py` 里的 MagpieClient 并移植。它已经跑通过 1440 局:POST {base}/v1/chat/completions(OpenAI 协议),temperature=0,max_tokens=4000(推理耗尽预算或空文本时翻倍重试,上限 16000),单请求硬性墙钟超时 150s。不要重新发明协议。
- 先 `GET /v1/models` 确认该模型 ID 在列表里;不在就停下报告候选。
- 旧 README 的吞吐实测:该路由约 1.2 秒/请求(约 1.2k token 的 prompt),约 70 请求/分钟(默认每个 provider 账户 10 路并发)。估时先用这个数,M1 再实测。
- 基础设施失败(超时/空响应/5xx/限流)用指数退避重试到拿到有效回复,不算 agent 失败,记录重试次数。重试仍失败的回合标 infra_failed,不进分析,报告个数并在最后补跑。
- 实际模型 ID、日期、温度、max_tokens、并发写进 results/run_manifest.json。

## 3. 环境(src/dynhouse/env.py):复制旧 env.py,只改两处
(a) ask_human 的物品名匹配改成整词匹配的 `named_items(question)`("notebook" 不再命中 "book";物品名里的下划线或空格都算分隔,"coffee_mug" 和 "coffee mug" 都认)。
(b) 新增构造参数 `max_asks`,主版本取 1:第 2 次有效 ask_human 起返回 `INVALID: ask limit reached.`(0 预算,占 1 步,与其他 INVALID 一致)。无效的提问(没点名物品等)不计入次数。
其余语义一律不动:5 个房间、18 件物品(6 件 high_risk)、预算 60、最长 30 步、成本 move 2 / observe 3 / ask_human 10 / pick 1 / place 1、缺失 pick −15、high_risk 误抓或抓空 −25 且立即失败、inspection_gap=8、p∈{0,0.2,0.4}、`n_targets = 2 + seed % 2`、室友优先移动当前待办目标(随机移 18 件物品只有约 10% 命中目标,"过期"就几乎不会发生,所以保留这条,并在报告里作为已知设计选择披露)、被问过的物品在抓住前不再被移动。
稳健性变体 `nofreeze`(不冻结、不限 ask)只在主实验之后跑(见 §6)。
单测(pytest):每个 ITEMS 名字都能被问到(含 notebook、book、coffee mug);同 (seed,p) 完全确定;p=0 时室友从不移动物品;公共状态里没有真值;max_asks 语义;首个目标的巡检记忆在开局时已过期的比例,p=0.2 约 40–60%、p=0.4 约 60–80%(我用 1000 个种子测得 47% / 67%;旧 README 写 51% / 72%)。

## 4. 脚本参考线(零 LLM 成本;在任何 LLM 调用之前做完并冻结)
- 先对旧的原始 env.py 运行 `python scripted_baselines.py _ref/gate_dynamic_house/env.py --seeds 1000` 复现下表(几分钟)。它在内存里用文本补丁构造各变体,所以必须喂旧的原始 env.py,不能喂你改过的。
- 然后把四个策略(trust_memory / observe_pick / ask_fetch / ledger_gate)移植成直接跑在你新 env 类上的 `scripted.py`(不要文本补丁)。pytest 断言:新 env(max_asks=1)在 1000 个种子(n_targets=2+seed%2)上的 success 与下表相差 ≤2pp,cost 相差 ≤1.5。
- 另外在测试种子(1000 起)上也跑一遍这四个策略,和 LLM 臂同种子配对,用于 Pareto 图。

主版本(fixed + askcap1)参考表,success% / 平均成本:
```
policy         p=0          p=0.2         p=0.4
trust_memory   100 / 11.8   46.5 / 26.6   26.2 / 30.7
observe_pick   100 / 19.3   64.5 / 41.9   36.8 / 47.8
ask_fetch      100 / 26.3   66.3 / 43.4   46.3 / 47.4
ledger_gate    100 / 11.8   70.9 / 42.7   47.6 / 47.6
```
对照:旧环境原样里 ask_fetch = 100 / 96.1 / 94.2,这是旧闸门不可信的主因。nofreeze 变体里 ask_fetch = 100 / 61.0 / 50.6,ledger_gate = 100 / 63.3 / 44.2(trust_memory 与 observe_pick 两行不变)。
含义:主版本里没有任何脚本策略一招通吃(p=0.2 最高 71%,p=0.4 最高 48%)。环境版本按脚本参考线选定,不按 LLM 结果调整,论文里要写明。

## 5. LLM 臂:两个正交开关
记忆表示 R ∈ {window, append, ledger} × 策略提示 P ∈ {N (neutral), C (cost)},共 6 臂:win_N、app_N、led_N、win_C、app_C、led_C。不要复刻旧的四个 agent,也不要旧的 always_observe 强制护盾。
一致性铁律(旧 pilot 的教训):除 R、P 这两个开关外,臂与臂之间一个字符都不许不同。
- BASE_SYSTEM:6 个臂逐字相同。以旧 agents.py 的 BASE_SYSTEM(1,342 字符)为起点,补上旧版只告诉部分臂的规则:被问过的物品在抓住前不再被移动、每局最多问人 1 次、18 个物品的风险级别、disturbance_p 的含义。所有示例动作必须合法(单测:逐个示例构造状态,确认被 env 接受)。不得出现 "Where is the current_target item?" 这类旧版的非法示例。
- P=N:不追加任何内容。
- P=C:在 BASE_SYSTEM 末尾追加下面这段,逐字,所有 R 相同,不许改,也不许加环境专用微策略(旧提示里的"别来回走""观察后立刻抓""被拒后别再问"之类一律不要):
  "DECISION GUIDANCE. Information you hold may be out of date because the roommate keeps moving items while you act. For each decision, weigh how old your evidence is and how likely the item has moved against what a mistake would cost and what checking costs (observe: 3 plus the moves needed; ask_human: 10, at most once). Trust fresh evidence; verify old evidence when a mistake would be expensive; skip checks that are not worth their price."
- 用户消息 = {"state": 公共状态(字段同旧 state_context,各臂相同), "recent_history": 最近 4 步原始(动作, 结果)(各臂相同), "memory": 下面三选一}。memory 一律由代码确定性构造,不用 LLM 抽取:
  * window:"memory": [](无长期记忆,也看不到巡检记录)。
  * append:按时间顺序、只追加的原始记录。巡检 5 条 {"step":-8,"room":R,"items":[...]};之后每次 observe 一条 {"step":s,"room":R,"items":[...]};每次 ask_human 一条 {"step":s,"human_answer":{"item":I,"location":R}};每次失败的 pick 一条 {"step":s,"pick_failed":{"item":I,"room":R}}。不加任何评论性文字(例如"旧记录不会失效")。
  * ledger:每个物品一行 {"item","believed_room"(或 null),"last_verified_step","age"(= 当前 step − last_verified_step),"source"(inspection|observe|observe_absence|ask_human|pick_failed),"superseded_count",以及仅当 believed_room 为 null 时的 "last_room"}。更新规则照 `_ref/gate_dynamic_house/ledger.py`:正向看到 → 覆盖旧位置并累计 superseded;观察某房间时发现原本相信在此的物品不在 → 置 null;失败的 pick → 置 null。risk_level 不放进 ledger(已在 BASE 里)。
- 信息等价(pytest):随机生成 ≥200 条事件序列,断言 ledger 的每个字段都能只由 append 日志按规则重算(ledger 的信息不多于 append);二者都不含环境真值。
- 一致性测试(pytest,必须在任何 LLM 运行前通过):对同一 (seed,p,step),6 个臂的 system prompt 只在 P 后缀处不同,用户消息只在 "memory" 字段不同。把每臂 prompt 的字符数表写进 docs/PARITY.md。
- 回合流程:每步 1 次 LLM 调用,返回 JSON {"action": ...}。解析失败 → 同一请求重发最多 2 次(不占步数,记 format_retries);仍失败 → 当作一次 INVALID 动作(占 1 步,不扣预算)。每局的完整请求与回复原文落盘,方便审计。
- harness 侧另记"取证年龄"(对所有臂都记,不展示给非 ledger 臂):每次 pick 时该物品最近一次被证实位置的 age,以及 pick 是否成功,用于失败机制分析。

## 6. 规模、种子、顺序
- 开发种子 0–19:只用来修格式/合法性/解析问题,不进结果。禁止根据开发集得分调整 P=C 的文本或 R 的呈现方式。测试种子从 1000 起,冻结后一次性跑(旧 pilot 用的是 0–59,不重叠)。
- 主实验:p∈{0,0.2,0.4} × 6 臂 × 种子 1000–1059(N=60)= 1080 局。外层循环是种子(逐个),内层是 p × 臂,核心 4 臂(app_N、led_N、app_C、led_C)在前,win_N、win_C 在后。这样任何时候中断都有配对完整的数据;分析只用核心臂在三个 p 上都完整的种子。
- 估时:每局约 15 次调用,总计约 16k 次,按 70 请求/分钟约 4 小时。先用种子 1000–1001 试跑(36 局,配置与正式跑完全相同,结果保留并计入正式数据)量真实吞吐;若预计总时长 > 5.5 小时,停下来告诉我(建议把 N 降到 40),不要自行改设计。
- 预注册内唯一一次延伸:只在 §7 的决策表给不出结论时触发(S 为 INCONCLUSIVE;或 S 为 NOT_NEEDED 且 Π 为 INCONCLUSIVE),再跑种子 1060–1099(N=100)。
- 稳健性(主结论出来之后才跑,可选):变体 nofreeze,4 个核心臂 × p∈{0,0.2,0.4} × 种子 1000–1039。
- 每局一行 JSONL(逐步轨迹另存);全部失败局保留;不挑种子;不为了好看而重跑。运行期间只汇报进度、吞吐和 infra 失败率,不要去看各臂成功率并据此改动任何东西。

## 7. PREREG.md(第一次正式跑之前写好,并 `git tag prereg-v1`)
- 指标:success(全部目标正确归位,且未因安全/预算/步数终止)、cost(= 60 − 剩余预算)、stale_pick(缺失 pick 次数)、safety_violation、ask_count、invalid_actions、llm_calls、tokens。
- 所有对比按种子配对;置信区间 = 对种子的配对 bootstrap(≥10000 次,固定随机数种子;同一种子的所有 p 与臂一起重抽)。
- 记号:SR(R_P, p) 表示臂 R_P 在扰动率 p 下的成功率,如 SR(led_C, 0.2)。
- S(记忆结构效应,同提示下)= 对 P∈{N,C}、p∈{0.2,0.4} 共 4 格取平均的 SR(led_P,p) − SR(app_P,p)。
- 阴性对照 S0 = 对 P∈{N,C} 取平均的 SR(led_P,0) − SR(app_P,0)。p=0 时世界静止、记忆不会过期,S0 的 95% CI 应包含 0。S0 的 CI 不含 0 → 记"control failed":先查格式/提示泄漏;判定改用 S_DiD = S − S0,并在报告里标明。
- Π(策略提示效应,同记忆表示下)= 对 R∈{app,led}、p∈{0.2,0.4} 共 4 格取平均的 SR(R_C,p) − SR(R_N,p)。p=0 时的 C−N 差单独报告,它衡量"过度核验"的代价。
- 判定(δ = 10pp,沿用旧闸门的门槛):判定量(S 或 S_DiD 或 Π)≥ +δ 且 CI 下界 > 0 → HELPS;CI 上界 < +δ → NOT_NEEDED;其余 → INCONCLUSIVE。标签依次为 STRUCTURE_HELPS / STRUCTURE_NOT_NEEDED,以及 PROMPT_HELPS / PROMPT_NOT_NEEDED。
- 次要(只描述,不判定):cost 的配对差与 CI、stale_pick 率、安全违规率、问人次数、取证年龄分布;win 臂与 app/led 的差(= 记忆本身的价值);各臂相对脚本参考线的位置(Pareto 图)。成本占优:某臂 SR 不低于对照(差 ≥ −2pp)且 cost 配对差的 CI 上界 < 0,记为"成本占优",写进报告但不改变上面的判定。
- 决策表(原样写进 PREREG):
  | S | Π | 论文叙事 |
  | STRUCTURE_HELPS | 任意 | 同提示下结构仍然有效 → 继续这条线,补第二个模型/环境变体 |
  | STRUCTURE_NOT_NEEDED | PROMPT_HELPS | 提升来自成本感知提示而不是记忆结构 → 转成"何时信记忆、何时重新观察、何时问人"的成本感知策略研究 |
  | STRUCTURE_NOT_NEEDED | PROMPT_NOT_NEEDED | 负结果:过期记忆的伤害是真的,但结构与轻量提示都没解决 → 受控实证 + 失败分类 |
  | S 为 INCONCLUSIVE,或 S 为 NOT_NEEDED 且 Π 为 INCONCLUSIVE | | 做一次 N=100 延伸后再判;仍 INCONCLUSIVE 就如实写"效应小于 10pp 或无法分辨",按负结果叙事 |
- δ、bootstrap 次数、±2pp 容差都是我拍的;此后不许改。要改就保留原版本,并在报告里说明改了什么、为什么。
- 威胁有效性(写进报告):只有一个模型族(MiniMax-M3.1-Flash);文本玩具世界;记忆由代码确定性构造(无抽取噪声);室友偏向目标;P=C 是轻量的原则性提示,不代表重度工程化的提示;环境版本由脚本参考线选定。

## 8. 里程碑(顺序执行,每个里程碑 git commit)
M0 读旧仓库(agents.py 的客户端与 BASE_SYSTEM、run_benchmark.py 的并发与断点续跑、ledger.py),写 PLAN.md,然后直接开始,不要等我确认。建议布局:src/dynhouse/{env,scripted,memory,prompts,gateway,agent,run,analyze}.py、tests/、docs/、results/、PLAN.md、PREREG.md、README.md、pyproject.toml。
M1 网关探测 → docs/GATEWAY.md:/v1/models;同一请求体在并发 1/4/8/10/12 下的吞吐、延迟、错误率,选定最高的零错误并发;记录 usage 形态与是否有推理块。主力模型不稳就停下来报告,不要换模型。
M2 env + 单测 + 脚本参考线(对旧 env 复现上表,对新 env 一致)。
M3 记忆构造器、提示、一致性测试、agent 循环、runner(并发 + 断点续跑 + infra 重试)。
M4 开发种子冒烟:6 臂 × p=0.2 × 种子 0–4(30 局);人工读 ≥6 条完整转录;检查格式失败率 <3%、无非法示例、无真值泄漏;只修格式/解析/合法性。通过后把所有 prompt 模板与记忆格式代码的哈希写入 prompts.lock,runner 启动时校验,不一致就拒绝运行。
M5 写 PREREG.md → git tag prereg-v1 → 试跑量吞吐 → 正式跑(后台;每 10 分钟打一行进度)。
M6 analyze.py(`uv run python -m dynhouse.analyze` 一条命令复现全部表图):主表(臂 × p:SR 含 95% CI、cost、stale_pick、safety、asks、invalid、calls);配对差表;S0 对照检查;S/Π 判定;Pareto 图(每个 p 一个面板,含四条脚本线);取证年龄图;≥30 条失败局的失败分类(信了过期记忆 / 核验后目标又被移走 / 问人浪费 / 格式无效 / 预算或步数耗尽 / 其他)。
M7 results/report.md(中文):≤10 行 TL;DR + 决策表结论;与 pilot-v1 的差异;方法与一致性检查;威胁有效性;下一步。

## 9. 工作方式
- 只在以下情况停下来问我:(1) 网关或主力模型不可用;(2) 两轮修复后单测或脚本参考线仍对不上;(3) 预计总时长 > 5.5 小时;(4) 需要调用非主力模型;(5) 需要改动 §3 的环境语义或 §7 的判定规则。需要我动手的事(放文件、授权)一次性列成清单告诉我,不要一件件问。
- 数字一律来自真实日志;负结果如实写;不用 LLM 的结果去选环境版本或改提示;代码保持小,不要重建旧仓库那种大而全的结构。
- 结束时给 ≤15 行总结 + report.md 的路径。
