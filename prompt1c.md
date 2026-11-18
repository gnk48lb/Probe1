# Probe 1c：冻结管线复现（led_C vs app_C，p=0.2）

你在 D:\code\ClaudeCode\Probe1 里工作。这是一个**复现实验**。Probe 1 里 led_C 在 p=0.2 得 67%，其余三个核心 arm（app_N、led_N、app_C）只有 56–57%；这是事后从 12 个次要对比里看到的，没有被确认（led_C − app_C = +10.0pp [-2, +22]，N=100）。Probe 1b 的 base（= led_C + 可见的 ask 次数）在新 seed 上又得 68%，但接口不同，不算复现。本实验用 **Probe 1 冻结的代码与接口**，在全新 seed 上做一次干净的、预注册的确认检验。对我的汇报用中文，仓库文档用英文。

## 0. 先读
PREREG.md、results/report.md、results/tables/paired_differences.md、src/dynhouse/{env,memory,prompts,agent,gateway,run,analyze,scripted}.py、DEVIATIONS.md（1b 的教训）、PREREG_1B.md 的 §4.5（判定规则怎么写）。

## 1. 硬性规则
1. 在新分支 `probe1c` 上工作，起点是 tag `probe1-final`（不是 probe1b）。src/dynhouse/{env,memory,prompts,agent,gateway,run,analyze,scripted}.py 与 prompts.lock 必须与 probe1-final 逐字节相同（`git diff probe1-final -- <这些文件>` 必须为空）。run.py 已支持 --seed-start / --seeds / --arms / --ps / --output-dir，直接用，不许改它。
2. 输出目录一律用新的 results_1c/，**绝不能写进 results/**（Probe 1 的冻结结果）。
3. 先预注册后跑数：PREREG_1C.md 与 prereg_1c.lock（对 analyze_1c.py、age_gate_reference.py 做 sha256；计算哈希的函数里先把 CRLF 统一成 LF，校验时同样处理，不要为此重写冻结文件——1b 里 lock 的哈希和 Windows 文件对不上就是这个原因）提交并打 tag `prereg-1c`，之后才允许跑任何 seed >= 4000。tag 不得改写。
4. 不偷看：Stage 1 期间只许看基础设施健康指标（完成数、错误率、格式失败、墙钟、token），不许看各 arm 的成功率；analyze_1c.py 只能在 Stage 1 完整结束后对真实数据运行（烟测数据只用来确认管线，不得算成功率差）。唯一依据结果做的决定，是 §3.4 的扩展规则和 §3.5 的 Stage 3 条件。
5. analyze_1c.py 及其单元测试在跑数前完成并锁定；跑数期间只许修真 bug，并记入 DEVIATIONS_1C.md。
6. 模型与参数与 Probe 1 完全相同：minimax-code-global/MiniMax-M3.1-Flash，temperature 0，run.py 的默认超时/重试/并发（10–12）。记录 run_manifest（模型串、时间、git hash）。不要调 Gemini（会导致封号），不要把 Antigravity 当实验模型。
7. 不要把 API key、邮箱写进仓库。电脑要保持唤醒，日志写文件，任务可恢复。

## 2. 设计
- 环境、记忆实现、提示、接口：与 Probe 1 一字不差（variant=main；问人次数在 state 里不可见；原 BASE_SYSTEM + C 提示；原 ledger / append 视图）。
- 臂：led_C、app_C。扰动率只有 p=0.2。n_targets 规则同 Probe 1（2 + seed % 2）。
- 种子：dev 0–4 只用于烟测（约 10 局，确认管线能跑）；测试种子 4000–4299（N=300，Stage 1）；扩展种子 4300–4599（Stage 2）。1000–1099、2000–2399、3000–3099 已被用过，不要用。
- 运行：分块（每块 50 个 seed，--seed-start 递增）依次调用 run.py，两臂在同一次调用里一起跑。这样随时中断都留下完整 seed。Stage 1 = 600 局，预计约 1.5 小时。
- 模型可能在这两天里被网关悄悄更新，所以**不拿 led_C 的绝对水平去和 Probe 1 的 67% 比**，只看同一批 seed、同时跑的两臂配对差值。

## 3. 估计量与判定（逐字写进 PREREG_1C.md，一字不改地执行）
3.1 主要（唯一 confirmatory）估计量：Δ = SR(led_C) − SR(app_C)，p=0.2；只用两臂都完整的 seed；按 seed 成对 bootstrap，10,000 次，RNG seed 20261119，95% 百分位 CI。基础设施失败先补跑（规则同 Probe 1，最多 2 次）；仍缺的 seed 对两臂一起剔除，并如实报告。
3.2 判定（δ=5pp）：REPLICATED：点估计 >= +5 且 CI 下界 > 0；NOT_REPLICATED：CI 上界 < +5；否则 INCONCLUSIVE。
3.3 背景（不参与判定）：Probe 1 的原估计 +10.0 [-2, +22]（N=100，事后挑出，不同 seed）。复现的估计放在旁边对照；不要把两次合并成一个 verdict。可以另给一个合并的描述性估计，但必须标 exploratory。
3.4 扩展规则：仅当 Stage 1 判为 INCONCLUSIVE，允许且仅允许一次扩展：对两臂追加 seeds 4300–4599，最终判定用 600 个 seed。若因时间被迫中止，只能由墙钟决定；用已完整的 seed 分析，按同一规则出 verdict，并如实标注 N。
3.5 Stage 3：仅当最终判定为 REPLICATED，且只描述、不下 verdict：在 seeds 4000–4299 上补跑 app_N 与 led_N（p=0.2），看 led_C 的优势是"ledger × 提示"的交互，还是只是 led_C 单臂偏高。完成后停下，不要继续做别的。
3.6 次要/描述性（预先列出，其余一律标 exploratory）：成功率、总花费、安全违规率、failure_reason 构成（预算耗尽 vs 安全违规）、invalid_count、ask_count、pick 失败率（按 evidence_age<=1 与 >=2 分开）、成功局与失败局的花费；每个指标给两臂的差和 CI。失败分析用非互斥标志，并同时给出成功局里同一标志的基线；共现不得写成因果。
3.7 脚本参照线：用冻结的 scripted.py 在 seeds 4000–4299、p=0.2 上算 trust_memory / observe_pick / ask_fetch / ledger_gate（main 版本）；再用 age_gate_reference.py（从 probe1b 分支取：`git show probe1b:age_gate_reference.py > age_gate_reference.py`）算 age_gate。放进报告作为参照线（不涉及 LLM，随时可算）。

## 4. 执行
Phase 0：建分支；核对冻结文件无改动；跑现有测试。
Phase 1：analyze_1c.py + 单元测试：用已知效应的合成数据检验估计量、成对 bootstrap 可复现、三种 verdict（含边界值）、"完整 seed"规则；另有一项检查：1c 的首步 system+user prompt 与 probe1-final 代码生成的逐字节相同（led_C 与 app_C 各取 seed 4000）。
Phase 2：烟测（dev seeds 0–4，两臂，约 10 局）：只确认管线正常。
Phase 3：写 PREREG_1C.md 与 prereg_1c.lock，提交，打 tag prereg-1c。打印一份预注册摘要（主要估计量、判定规则、种子、Stage 规则、预计耗时），然后**直接开始 Stage 1**；除非有任何检查失败（那就停下来汇报）。
Phase 4：Stage 1。期间约每 10 分钟汇报一行基础设施健康指标。
Phase 5：Stage 1 结束后才运行 analyze_1c.py，输出 results_1c/{tables,figures,report.md}（英文）。report 包含：设计与预注册摘要；主结果（两臂 SR、Δ 与 CI、verdict）；次要指标；脚本参照线；图（两臂 SR 与 CI，Probe 1 的原观测作为灰色参照点并标注"事后、不同 seed"，脚本线作水平参照）；DEVIATIONS_1C.md；局限性。把逐步 traces（不含完整 prompt）压缩成 traces_1c.jsonl.gz 提交进仓库。
之后严格按 §3.4 / §3.5 继续或停下。

## 5. 汇报（中文，贴给我）
commit 与 tag；运行概况（局数、基础设施失败与修复数、实际 N）；主要估计量与 verdict；次要指标；脚本参照线；DEVIATIONS；需要我执行的 git push 命令（分支 probe1c + tags）。不要加入预注册之外的结论；事后发现一律标 exploratory。