# PREREG — Dynamic House 受控重跑

**版本** prereg-v1 · **日期** 2026-11-17 · **状态** 冻结（第一次正式跑之前写好）

本文件在第一次正式跑（测试种子 1000 起）之前写好并打上 `git tag prereg-v1`。
开发种子 0–19 只用于修格式/合法性/解析问题，不进结果，也不允许根据它们的得分
回头修改 `P=C` 的文本或 `R` 的呈现方式。

---

## 1. 设计

6 个臂 = 记忆表示 R ∈ {window, append, ledger} × 策略提示 P ∈ {N (neutral), C (cost)}：

| 臂 | R | P |
|---|---|---|
| `win_N` | window | N |
| `app_N` | append | N |
| `led_N` | ledger | N |
| `win_C` | window | C |
| `app_C` | append | C |
| `led_C` | ledger | C |

- **核心臂（4 个）**：`app_N`、`led_N`、`app_C`、`led_C`。判定量只用核心臂。
- **辅助臂（2 个）**：`win_N`、`win_C`，用于「记忆本身的价值」的描述性比较。
- 除 R、P 两个开关外，臂与臂之间一个字符都不许不同（由 `tests/test_prompts.py` 强制）。
- 环境：5 房间 / 18 件物品 / 预算 60 / 最多 30 步 / `inspection_gap=8` /
  `n_targets = 2 + seed % 2` / 每局最多问人 1 次（`max_asks=1`）/ 问过的物品在抓住前不再被移动。
  环境版本由**脚本参考线**选定，不由 LLM 结果决定。
- 扰动率 p ∈ {0, 0.2, 0.4}；测试种子 1000–1059（N=60，与旧 pilot 的 0–59 不重叠）。
- 模型：`minimax-code-global/MiniMax-M3.1-Flash`，temperature=0，max_tokens=4000。

---

## 2. 指标

| 指标 | 定义 |
|---|---|
| `success` | 全部目标正确归位，且未因安全 / 预算 / 步数终止 |
| `cost` | 60 − 剩余预算 |
| `stale_pick` | 缺失 pick（抓空）次数 |
| `safety_violation` | 安全违规次数（−25 且立即失败） |
| `ask_count` | 有效问人次数 |
| `invalid_actions` | 被环境判为 INVALID 的动作数（0 预算，占 1 步） |
| `llm_calls` | 该局的 HTTP 请求数（含格式重发） |
| `tokens` | prompt + completion token 合计 |

`infra_failed`（基础设施失败）的回合**不进分析**，单独报告个数并在最后补跑。

---

## 3. 统计方法

- 所有对比**按种子配对**：同一 (seed, p) 下比较两个臂。
- 置信区间 = **对种子的配对 bootstrap**：
  重抽次数 **10000**；固定随机数种子 **20261117**（`numpy.random.default_rng`）；
  **同一种子的所有 p 与臂一起重抽**（即以种子为重抽单元，保持臂内配对）。
- 区间 = 2.5% / 97.5% 分位数（percentile bootstrap）。
- 记号：`SR(R_P, p)` = 臂 `R_P` 在扰动率 p 下的成功率（%）。

---

## 4. 判定量

**S（记忆结构效应，同提示下）** — 对 `P∈{N,C}`、`p∈{0.2,0.4}` 共 4 格取平均：

```
S = mean over {P∈{N,C}} × {p∈{0.2,0.4}} of  [ SR(led_P, p) − SR(app_P, p) ]
```

**S0（阴性对照）** — 对 `P∈{N,C}` 取平均：

```
S0 = mean over {P∈{N,C}} of [ SR(led_P, 0) − SR(app_P, 0) ]
```

p=0 时世界静止、记忆不会过期，**S0 的 95% CI 应包含 0**。
若 S0 的 CI 不含 0 → 记 **"control failed"**：先查格式 / 提示泄漏；
判定改用 `S_DiD = S − S0`，并在报告里标明。

**Π（策略提示效应，同记忆表示下）** — 对 `R∈{app,led}`、`p∈{0.2,0.4}` 共 4 格取平均：

```
Π = mean over {R∈{app,led}} × {p∈{0.2,0.4}} of [ SR(R_C, p) − SR(R_N, p) ]
```

p=0 时的 `C−N` 差**单独报告**，它衡量「过度核验」的代价，不进 Π。

---

## 5. 判定规则（δ = 10pp，沿用旧闸门的门槛）

对判定量 S（或 S_DiD）与 Π 分别判定：

| 条件 | 标签 |
|---|---|
| 判定量 ≥ +δ **且** CI 下界 > 0 | **HELPS** |
| CI 上界 < +δ | **NOT_NEEDED** |
| 其余 | **INCONCLUSIVE** |

标签命名：

- S → `STRUCTURE_HELPS` / `STRUCTURE_NOT_NEEDED` / `STRUCTURE_INCONCLUSIVE`
- Π → `PROMPT_HELPS` / `PROMPT_NOT_NEEDED` / `PROMPT_INCONCLUSIVE`

---

## 6. 次要指标（只描述，不判定）

- `cost` 的配对差与 CI。
- `stale_pick` 率、安全违规率、问人次数、无效动作次数、调用数、token 数。
- **取证年龄**：每次 pick 时该物品最近一次被证实位置的 age，以及 pick 是否成功（对所有臂记录，
  但不展示给任何非 ledger 臂）。用于失败机制分析。
- `win` 臂与 `app` / `led` 的差 = **记忆本身的价值**（描述性）。
- 各臂相对脚本参考线（`trust_memory` / `observe_pick` / `ask_fetch` / `ledger_gate`）的位置 → Pareto 图。
- **成本占优**：某臂 SR 不低于对照（差 ≥ −2pp）且 cost 配对差的 CI 上界 < 0 → 记为「成本占优」，
  写进报告，但**不改变**上面的判定。

---

## 7. 决策表（原样）

| S | Π | 论文叙事 |
|---|---|---|
| STRUCTURE_HELPS | 任意 | 同提示下结构仍然有效 → 继续这条线,补第二个模型/环境变体 |
| STRUCTURE_NOT_NEEDED | PROMPT_HELPS | 提升来自成本感知提示而不是记忆结构 → 转成"何时信记忆、何时重新观察、何时问人"的成本感知策略研究 |
| STRUCTURE_NOT_NEEDED | PROMPT_NOT_NEEDED | 负结果:过期记忆的伤害是真的,但结构与轻量提示都没解决 → 受控实证 + 失败分类 |
| S 为 INCONCLUSIVE,或 S 为 NOT_NEEDED 且 Π 为 INCONCLUSIVE | | 做一次 N=100 延伸后再判;仍 INCONCLUSIVE 就如实写"效应小于 10pp 或无法分辨",按负结果叙事 |

**预注册内唯一一次延伸**：只在 §7 的决策表给不出结论时触发（S 为 INCONCLUSIVE；或 S 为 NOT_NEEDED
且 Π 为 INCONCLUSIVE），再跑种子 1060–1099（N=100）。

---

## 8. 冻结声明

δ = 10pp、bootstrap 次数 = 10000、bootstrap 随机种子 = 20261117、脚本参考线容差
（success ±2pp、cost ±1.5）**在预注册后一律不得修改**。若必须修改，保留原版本，
并在报告里说明改了什么、为什么。

---

## 9. 威胁有效性（写进报告）

1. **只有一个模型族**（MiniMax-M3.1-Flash），不能外推到其他模型的能力结构。
2. **文本玩具世界**：5 房间 18 物品，规则完全已知；与真实家居环境的差距没有估计。
3. **记忆由代码确定性构造**（无抽取噪声），因此不测「LLM 抽取记忆时的错误」这一失败来源；
   这是有意简化，让 R 的效应可归因。
4. **室友偏向目标**：随机从 18 件物品里移动只有约 10% 命中目标，「过期」几乎不会发生，
   所以保留「优先移动当前待办目标」这条（并作为已知设计选择披露）。
5. **P=C 是轻量的原则性提示**，不代表重度工程化的提示（不是 few-shot、不是 CoT、不是工具增强）。
6. **环境版本由脚本参考线选定**：主版本里没有任何脚本策略一招通吃
   （p=0.2 最高 70.9%，p=0.4 最高 47.6%），环境因此具备分辨力。
7. **BASE_SYSTEM 里已经含有一句 `Be economical but do not risk stale high_risk picks`**（沿用旧版，
   六个臂都有）——它略微削弱了 P=C 的相对优势，这一点在报告里如实说明。
8. **单一研究者、无重复实验**：bootstrap CI 只覆盖种子抽样带来的不确定性，不覆盖
   「换一批种子/换一个提示写法」的不确定性。
