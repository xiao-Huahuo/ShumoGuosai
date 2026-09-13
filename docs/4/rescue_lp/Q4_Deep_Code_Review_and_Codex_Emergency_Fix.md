# Q4 深度 Code Review + Codex 紧急修复执行文档

> 适用项目：2026 高教社杯 C 题《微网与外部电网电力调控策略》问题四  
> 审查对象：`ShumoGuosai(8).zip`、问题四建模文档、当前 `result4-2.xlsx` 与 Q4-3 运行痕迹  
> 核心目标：在比赛时间预算内，修复问题四“结果异常 + 求解极慢 + 模型/代码颗粒度错位”的系统性问题，尽快得到可解释、可复现、能完整跑完的 `result4-2.xlsx` 与 `result4-3.xlsx`。

---

# 0. 给 Codex 的最高优先级指令

这是一次**紧急生产修复**，不是继续堆复杂度，也不是继续调 MIP gap。

当前旧 Q4-2 结果 `20,461,164.98 元` **不得作为最终结果使用**；当前 Q4-3 旧运行也**不要继续跑到底**。原因不是单纯“3% 精度不够”，而是当前正式运行绝大多数节点根本没有取得 3% 最优性证书，且代码允许把极端保守 fallback 作为正式策略落盘。

必须按以下优先级工作：

1. **先冻结并保留旧结果作为失败基线，不覆盖。**
2. **修复生产模式对 `limited` 解的接受机制。**
3. **把当前高维二进制精确反馈 MILP 改为可在比赛时间内完成的连续 LP / 低复杂度严格非预知模型。**
4. **修复跨日价格残差 forecast-origin 错位。**
5. **修复论文与代码中储能决策、尾部权重、残差窗口等颗粒度错位。**
6. 只做最少量 smoke / vertical slice，验证通过后立即跑全年；不要再做大规模消融、参数扫描或无关实验。
7. 修复后必须使用**全新输出目录**重新计算，禁止在旧 Q4 checkpoint 上续算。

本任务的原则是：

> **正确性 > 能跑完 > 模型复杂度。**  
> 保留问题四真正有价值的核心：严格因果电价预测、价格—净负荷联合残差、尾部保持、Wasserstein DRO、Q4-3 四时点滚动。  
> 删除目前导致数万二进制变量、但比赛交付价值有限的精确 `min/max` 反馈 MIP 结构。

---

# 1. 审查结论摘要

当前系统存在两个不同层次的问题。

第一层是**结果有效性问题**：Q4-2 正式 334 天没有任何一天达到要求的 3% gap；程序却因为 `allow_limited=True` 仍然把全部 334 天写入正式结果。大量日期在时间预算内没有得到好 incumbent，直接退化成“按场景最大净需求买电 + 禁止放电”的保守 seed。结果是储能几乎长期充满而不放电，大量计划购电付费后根本没有被调用。

第二层是**计算架构问题**：当前每个 Q4-2 日问题约含 46,657 个变量、17,280 个二进制变量和约 103,661 个约束；Q4-3 每个节点约含 23,365 个变量、8,640 个二进制变量和约 51,894 个约束。全年需要大约 1,670 次大型 MILP 求解。即使每次严格限制 30 秒，仅 solver 理论时间就接近 13.9 小时，还没有计入场景生成、bootstrap、I/O 和异常长尾。

因此，继续在当前架构上从 3% 调成 5%、减少少量场景或单纯增加线程，无法从根本上解决问题。

---

# 2. 当前结果的硬证据

## 2.1 Q4-2 正式 334 天求解质量

从 `outputs/q4/raw/full_q42_20260913/audit/*.json` 对 2025-02-01 至 2025-12-31 全部正式日审计：

| 指标 | 结果 |
|---|---:|
| 正式天数 | 334 |
| `reliable=True` | **0 / 334** |
| `status=limited` | **334 / 334** |
| 平均 gap | **37.13%** |
| 中位 gap | **35.47%** |
| 最大 gap | **62.68%** |
| constraint-generation 迭代次数 | **334 天全部为 1 次** |
| discharge cap 全日为 0 | **225 / 334 天** |
| 单日典型 solver 时间 | 约 30.4 秒 |

配置虽然写着：

```python
seconds = 30.0
gap = 0.03
```

但 `gap=0.03` 只是要求，并不意味着实际求解到了 3%。实际正式 334 天中没有一天达到该证书。

## 2.2 Q4-3 当前运行质量

压缩包中的 Q4-3 已经比截图继续运行得更远。对 2025-02-01 起已经完成审计的 175 个正式日、700 个节点：

| 指标 | 结果 |
|---|---:|
| 正式节点 | 700 |
| `reliable=True` | **102 / 700** |
| 未取得证书 | **598 / 700** |
| 平均 gap | **27.05%** |
| 中位 gap | **28.12%** |
| 最大 gap | **69.26%** |
| discharge cap 全节点为 0 | **413 / 700** |

另有一个非常危险的长尾：

`2025-07-25 12:00` 节点配置明明是 `30 s`，但 HiGHS 实际记录约：

```text
1090.25 s
```

即单节点约 **18 分钟**。

这说明不能仅依赖 solver 内部 `time_limit` 保证比赛时间上界，正式运行需要外部 watchdog 或 subprocess 硬超时。

---

# 3. 为什么 `20,461,164.98 元` 不合理

当前 Q4-2 的全年真实回放汇总：

```text
计划购电量       24,949,272.36 kWh
实际调用计划电量 20,952,091.32 kWh
未调用计划电量    3,997,181.04 kWh
物理弃电量        3,045,451.74 kWh
全年充电量           22,515.09 kWh
全年放电量           18,237.22 kWh
紧急购电量           36,827.79 kWh
全年总费用       20,461,164.98 元
```

SOC 的表现更直接：

```text
99.638% 的正式 10 分钟时段，SOC = 10800 kWh（上限）
```

全年仅放电约 `1.82 万 kWh`。对于容量 12,000 kWh、最大充放电功率 5,000 kW 的储能系统，这相当于储能经济调节能力几乎被禁用。

当前算法实际形成了以下链条：

```text
大型 MIP 30 s 内难以得到好解
        ↓
退回确定性可行 seed
        ↓
seed 按所有场景的最大净需求买电
        ↓
seed 的 discharge_cap = 0
        ↓
大量日期电池不放电
        ↓
SOC 长期卡在 10800
        ↓
为规避紧急购电而大量超买计划电
        ↓
约 400 万 kWh 计划电已付费但未调用
        ↓
费用被推高到 2046 万元
```

## 3.1 一个非常重要的 sanity baseline

我用项目已有的最终问题二策略 `20260912_tail_reserve_final`，**不做任何问题四优化**，只把原 Q2 策略放在附件 4 的真实波动电价下重新回放结算，得到约：

```text
Q2 最终策略 + 附件4真实价格：14,836,427.92 元
紧急购电约：107,149.04 kWh
计划购电约：21,654,307.82 kWh
```

旧 Q2 版本对应约：

```text
14,655,757.13 元
```

当前 Q4-2：

```text
20,461,164.98 元
```

相对最终 Q2 baseline 高约：

```text
+37.91%
+5,624,737 元
```

这不是数学意义上严格证明 Q4 必须比 Q2 便宜，因为 DRO 可以为了尾部风险牺牲均值；但当前只把紧急购电从约 10.7 万 kWh 降到约 3.68 万 kWh，却多买约 329 万 kWh 的计划电，付出 560 多万元额外费用，经济上显然已经超出合理鲁棒代价范围。

因此必须设置 baseline regression gate：复杂 Q4 策略不能在没有显著尾部收益解释的情况下，比“原 Q2 策略直接按波动价格结算”贵几十个百分点。

---

# 4. P0：直接导致错误结果的代码问题

## P0-1：正式运行允许 `limited` 解直接落盘

文件：`src/q4/config.py`、`src/q4/run.py`、`src/q4/optimization.py`

默认配置本来是：

```python
allow_limited: bool = False
```

但当前正式运行的 `state.json` 实际保存：

```json
"allow_limited": true
```

`optimization.py` 中：

```python
if not valid or (not reliable and not config.allow_limited):
    raise LimitedSolve(audit)
```

于是只要命令行带 `--allow-limited`，即使 gap 30%、50%、60%，仍然可以成为正式结果。

### 修复要求

生产命令 `q42` / `q43` 必须强制：

```python
allow_limited = False
```

`--allow-limited` 只能用于 benchmark / smoke，不能用于正式全年输出。

更进一步：正式 LP 新模型中不应再存在“限时但仍作为正式结果”的语义。若 solver 未 `Optimal` / 没有可信最优性状态，应立即失败，不写正式日文件。

---

## P0-2：fallback seed 是“最大场景购电 + 完全禁止放电”

文件：`src/q4/optimization.py:348-364`

当前 seed：

```python
policy = Policy(
    np.maximum(scenarios.net.max(axis=0), 0),
    np.full(length, CAP),
    np.zeros(length)
)
```

含义：

```text
grid = 所有场景逐时最大净需求
discharge_cap = 0
```

它的目标只是“肯定可行”，并不是高质量经济策略。

当 HiGHS 在时间内没有接受 incumbent 时，`_run_master()` 会直接返回 seed：

```python
if info.primal_solution_status != feasible:
    ...
    return seed.copy(), info, solver
```

### 修复要求

1. 新正式模型取消该 fallback 进入生产结果的路径。
2. seed 可以作为 warm start，但绝不能在没有标记的情况下伪装成正式优化结果。
3. audit 必须记录：

```text
solution_source = optimal_solver / warm_start_only / fallback
```

正式输出只允许 `optimal_solver`。

---

## P0-3：当前 constraint generation 实际没有真正迭代

文件：`src/q4/optimization.py:367-423`

当前逻辑：

```python
remaining = config.seconds - elapsed
_run_master(..., seconds=remaining)
```

第一次 restricted master 直接拿走整个约 30 秒预算。

然后才做：

```python
worst_case_distribution(...)
```

再准备加 cut。

正式 Q4-2 的证据是：

```text
334 / 334 天 iterations = 1
```

因此当前所谓“Wasserstein constraint generation”实际近似：

```text
经验分布 restricted master 解到超时
→ 做一次 separation
→ 时间已经没了
→ 结束
```

### 修复要求

推荐直接取消 MIP constraint generation，改成**连续 LP 的 finite-support Wasserstein dual**，一次求解完成；S=20 时只增加约 S²=400 个 DRO 对偶约束，远比当前几万二进制变量便宜。

如果仍保留 CG，则第一轮 master 最多只能使用总预算的 30%—40%，必须给后续 separation 和 cuts 保留预算。但本次紧急修复不推荐继续 MIP-CG。

---

# 5. P0：模型描述与代码颗粒度直接不一致

## P0-4：论文说 `charge cap` 是决策变量，代码把它永久固定为最大值

建模文档 7.6.2 明确写：

```text
在 0:00 预先决定：
\bar c_{d,t} ≥ 0
\bar r_{d,t} ≥ 0
```

即充电反馈上限与放电反馈上限都应是事前优化变量。

但实际 Q4 调用：

```python
build_base_v2_free(...)
```

`src/q3/fast_solver.py:145-203` 明确：

```text
“不创建固定 cp/lc”
```

最终 Q4 policy 又写死：

```python
Policy(
    grid,
    np.full(length, CAP),
    discharge_cap
)
```

也就是：

```text
charge_cap ≡ 833.333 kWh / 10min
```

并不是论文中的优化变量。

### 修复要求

本次不建议为了恢复 `\bar c` 再增加一套二进制变量，那会更慢。

应直接把论文的储能策略部分改成与新的连续 LP 一致的**节点预先提交储能充放电计划**：

```text
c_t, r_t 在当前决策节点统一确定，
在 committed block 内不随未来场景改变；
Q4-3 到下一个 6h 节点后基于新信息重新优化。
```

这样既严格 non-anticipative，又不需要 `min()` 精确离散线性化。

---

# 6. P1：跨日价格 residual forecast-origin 错位

这是一个明确的数据口径 bug。

## 6.1 当前 price 结构

`src/q4/price.py`：

```python
values.shape = (365, 288)
residuals.shape = (365, 144)
```

`values[d]` 是第 d 日 0:00 时一次性生成的未来 48h 价格预测。

但 `residuals[d]` 只保存：

```python
actual[d] - values[d, :144]
```

即只保存第一个 24h residual。

## 6.2 当前错误做法

`src/q4/data.py:97-112`：

```python
price_flat = self.price.residuals.reshape(-1)
start = history_day * 144 + hour * 6
price_error = price_flat[start:start + length]
```

### Q4-2 的错误

Q4-2 当前中心预测是：

```text
历史日 j 的 0:00 一次性预测未来48h
```

正确历史 48h residual 应是：

```text
[真实 j 日 + j+1 日]
-
[j 日 0:00 生成的完整 48h forecast]
```

当前代码实际拼成：

```text
j 日 first-day residual
+
(j+1) 日自己 0:00 重新生成 forecast 的 first-day residual
```

两个 residual 的 forecast origin 不一致。

### Q4-3 的错误

例如历史日 j 的 12:00 节点需要未来 24h residual。正确应使用：

```text
actual[j 12:00 → j+1 12:00]
-
values[j, 12:00 → j+1 12:00]
```

当前 flatten residual 会在午夜后切换到 `j+1` 日自己的 0:00 residual，仍然错 origin。

### 修复要求

禁止再从 `residuals.reshape(-1)` 跨日切片。

新增严格函数，例如：

```python
def price_residual_path(origin_day: int, hour: int, length: int) -> np.ndarray:
    forecast = price.values[origin_day, hour*6:hour*6+length]
    actual = actual_price_flat[origin_day*144 + hour*6 : ...]
    return actual - forecast
```

历史场景只能使用满足“完整 residual 窗口在当前决策时刻之前已经实现”的历史 origin。

需要新增单测：

1. Q4-2 48h residual 与手工 `actual - values[origin,:288]` 完全一致。
2. Q4-3 6/12/18 节点跨午夜 residual 与同一 origin forecast 一致。
3. 修改下一日自己的 forecast 不得影响前一日 origin 的跨日 residual。

---

# 7. P1：尾部强制保留的概率权重与论文不一致

论文 7.4.5 规定：

> 被强制保留的尾部单轨迹按其原始经验质量计权。

但 `src/q4/scenarios.py:105-108` 当前先把所有历史样本分配到最近 representative：

```python
labels = np.argmin(distance[:, representatives], axis=1)
weights = np.bincount(labels, weights=prior, ...)
```

这会导致普通样本也被分到强制保留的 tail representative，tail representative 的权重可能远高于自身原始经验质量。

实际审计中，Q4-2 某些日期 tail representatives 总质量最多膨胀到其原始尾部经验质量约 **3.17 倍**；单个 tail representative 权重最高约 **14.5%**。

### 修复要求

尾部轨迹必须单独锁定：

```text
每个 forced-tail representative 的 weight = 它自己的 prior mass
```

普通样本只能在 ordinary medoids 之间分配；不能把普通样本质量吸到 forced-tail singleton 上。

权重最后归一，但必须保持总质量守恒。

新增测试：构造一个明显 tail 样本，验证 tail weight 等于原 prior，不吸收 ordinary cluster mass。

---

# 8. P1：所谓 `W ∈ {56,84,112}` 滚动验证实际上没有发生

论文写：

```text
W ∈ {56,84,112}
通过历史滚动验证选择
```

但 `src/q4/diagnostics.py:111-116` 是硬编码：

```python
candidate_effective_days = {"56": 17, "84": 17, "112": 17}
tie_break = "shortest window"
selected_window = 56
```

没有计算三个窗口的预测损失或调度损失。

### 紧急修复建议

不要为了补论文再跑一套昂贵全年实验。

直接把论文改成：

> 为兼顾近期季节适应性与历史样本数量，本文在正式计算前固定采用最近 56 日联合残差池；56 日属于预先设定的滚动窗口，不再声称由 56/84/112 全量调参得到。

同时删除或重写 `write_window_calibration()`，避免输出虚假的 calibration 语义。

---

# 9. P1：Q4 provenance / signature 不完整

## 9.1 Q4 signature 没有覆盖实际依赖的 Q3 solver 代码

`src/q4/config.py:58-63` 只 hash：

```text
Q4 建模文档
src/q4/*.py
```

但 Q4 优化直接 import：

```python
src.q3.fast_solver.build_base_v2_free
src.q3.fast_solver.linear_seed_v2_free
src.q3.physics.Policy
```

因此如果 `src/q3/fast_solver.py` 或 `src/q3/physics.py` 在 Q4 续跑期间发生变化，Q4 `state.json` 的 signature 可能仍然认为模型没变。

### 修复要求

新版本不再依赖 Q3 solver 是最佳方案。

若仍依赖任何 Q3/Q2 代码，signature 必须显式 hash 所有生产依赖文件。

## 9.2 source provenance 没有完整 hash Q2/Q3 输入来源

Q4 `source_manifest.json` 目前主要记录：

```text
q2_run 路径
附件4 hash
price.py hash
```

没有把 Q3 的 attachment2/3、Q2 shadow forecast、Q3 数据处理代码的实际 hash 全部纳入 Q4 source digest。

### 修复要求

把 `q3.provenance` 完整嵌入 Q4 provenance，最终 `sources` digest 必须由实际文件 SHA / predictor source SHA 生成，而不是只有路径字符串。

---

# 10. P1：Q4 绑定旧 Q2 run，虽然当前 predictor 恰好一致

`src/q4/config.py:12`：

```python
Q2_RUN = outputs/q2/dispatch_runs/20260911_224501
```

项目当前最终问题二是：

```text
outputs/q2/dispatch_runs/20260912_tail_reserve_final
```

我对两次 Q2 的 334 个正式日检查后发现，当前用于 load forecast 的 predictor 名称恰好全部相同，都是：

```text
load_lgb_1
```

因此这不是当前 2046 万结果的主因。

但 provenance 仍然错误，而且以后修改 Q2 后会埋雷。

### 修复要求

Q4 改用最终冻结 Q2 run，或把 predictor artifact 变成一个独立、明确版本的只读输入，不要硬编码过期 run 目录。

---

# 11. P1：Q4 与最终 Q2 的正式初始 SOC 口径不一致

当前最终 Q2 的正式计算口径记录为：

```text
2025-02-01 initial SOC = 6000 kWh
```

而当前 Q4 会先运行 1 月 warmup，并把 1 月 SOC 传到 2 月 1 日。当前 Q4-2 / Q4-3 的 `2025-02-01` audit 中：

```text
initial_soc = 10800 kWh
```

这使“波动电价下重新计算问题2/3”与最终 Q2/Q3 的起点不完全可比。

### 修复要求

比赛时间有限时，建议统一正式边界：

```text
正式期 = 2025-02-01 ~ 2025-12-31
2025-02-01 初始 SOC = 6000 kWh
```

不再为了 Q4 正式输出求解 Jan8-Jan31 warmup。

这样同时：

1. 与最终 Q2 口径一致；
2. 节省额外 24 天 Q4-2 + 96 个 Q4-3 节点求解；
3. 避免模型之间因 warmup 策略不同导致比较混杂。

如果论文最终坚持“Jan1 6000 并完整模拟到 Feb1”，则必须同时把 Q2/Q3 也统一到该定义；当前时间预算下不推荐再大规模重跑前题，因此推荐 Q4 跟随最终 Q2 的正式起点。

---

# 12. P1：traceability 测试是形式通过，不是真正模型—代码追溯

`src/q4/traceability.py` 当前逻辑：

```python
每一行按章节查 MAP
status = "mapped"
```

测试只验证：

```python
mapped_lines == nonempty_lines
```

这无法发现：

```text
论文有 charge cap 决策变量
代码却没有 charge cap 变量
```

### 修复要求

追溯表至少对核心公式增加 machine-checkable assertions：

```text
Q4-2/Q4-3 是否存在 g
是否存在储能决策变量
是否存在 SOC transition
是否存在 x <= g
是否存在 emergency 5p
是否存在 Q4-3 1.5 / 0.5 adjustment
是否使用同一 forecast-origin residual
是否为连续 LP / integer count = 0（新模型）
```

不要再把“文件名被映射”当作模型实现已经被验证。

---

# 13. 为什么当前计算这么慢

## 13.1 当前 MILP 规模

当前 Q4 复用了 `build_base_v2_free()`。

该 formulation 的二进制 selector 数量约为：

```text
3 × S × T
```

### Q4-2

```text
S = 20
T = 288（48h）
```

实际典型：

```text
variables   ≈ 46,657
binaries    = 17,280
constraints ≈ 103,661
```

### Q4-3

```text
S = 20
T = 144（24h）
```

实际典型：

```text
variables   ≈ 23,365
binaries    = 8,640
constraints ≈ 51,894
```

### 全年求解次数

```text
Q4-2：334 天 × 1 = 334 个大 MILP
Q4-3：334 天 × 4 = 1336 个大 MILP
合计：1670 个 MILP
```

如果平均每个只用 30 秒：

```text
1670 × 30 s ≈ 13.9 h
```

这还没算 bootstrap、场景缩减、文件 I/O 和异常超时。

因此当前模型从架构层面就不适合比赛最后阶段完整回放。

---

## 13.2 100 次 Wasserstein bootstrap × 每节点一个 transport LP

`src/q4/scenarios.py` 每个节点做：

```python
for _ in range(config.bootstrap_repetitions):  # 100
    _transport_distance(...)
```

`_transport_distance()` 每次都重新：

1. 构造 transport equality sparse matrix；
2. 调一次 `scipy.optimize.linprog(method="highs")`。

完整 1670 节点理论上约：

```text
167,000 次小型 transport LP
```

这不是当前 30 秒 MILP 的第一大瓶颈，但在改成快速 LP 后会成为第二级瓶颈。

### 修复要求

先完成主模型 LP 化，再 benchmark 场景构造。

如果场景构造占总运行时间 >30%，做以下两项：

1. 固定 `count` 后缓存 transport `A_eq` 稀疏结构；
2. 比赛紧急配置可把 bootstrap 从 100 改成 30—50，并在论文如实写实际 B，不再声称 100。

不要先花时间优化这里而保留 17,280 个二进制变量。

---

## 13.3 k-medoids 是 Python 多重循环局部交换

`src/q4/scenarios.py:25-47` 的 medoids：

```text
while
  for representative position
    for candidate
      重算距离目标
```

历史窗口最多 56 日，本身不算巨大，但全年节点重复执行很多次。

修复优先级 P2。主 LP 修好后若 profiling 显示明显，再优化或缓存。

---

## 13.4 每天大量 `fsync + SHA256 + JSON/CSV` 写盘

`write_json()` / `write_csv()` 每次：

```python
flush()
os.fsync()
replace()
```

`run_period()` 每日还重新计算两个文件 SHA256。

这保证审计性，本身不是坏事，但比赛紧急期可：

```text
保留原子写入
把非关键 debug audit 降频
不要删除每日正式 receipt
```

不建议为了几秒速度牺牲 checkpoint 可靠性。

---

# 14. 推荐的生产救火模型：连续、严格非预知、保留 Wasserstein DRO

这是本轮最重要的架构修改。

## 14.1 删除当前 `min/max` 精确反馈 MILP

不要再让每个 scenario × slot 产生 3 个 binary selector。

将储能策略改为：

> 在每一个正式决策节点，统一决定未来 horizon 的购电结算量与储能充/放电计划；只有 committed block 真正执行。储能计划在当前节点确定后不随未来完整场景变化，因此天然满足 non-anticipativity。Q4-3 在下一个 6h 节点获得新信息后重新优化。

这比“每个场景自由 recourse”更严格，不存在 wait-and-see 泄漏。

## 14.2 连续 LP 变量

对 horizon `t=1..T`：

### 节点统一决策变量

```text
g_t >= 0           计划/有效购电结算量
c_t >= 0           节点预先提交的充电量
r_t >= 0           节点预先提交的放电量
E_t                储能状态
```

### 每个联合场景 j 的即时平衡 recourse

```text
x_jt >= 0          从已结算购电额度中实际调用的电量
h_jt >= 0          紧急购电
w_jt >= 0          物理弃电/富余
```

其中 recourse 只是在给定已经提交的 `g,c,r` 后完成物理平衡，不允许改变储能计划。

## 14.3 约束

```text
0 <= g_t <= grid_upper_t
0 <= c_t <= CAP
0 <= r_t <= CAP
c_t + r_t <= CAP              # 防止同时大充大放

E_t = E_{t-1} + eta_c*c_t - r_t/eta_d
E_MIN <= E_t <= E_MAX

0 <= x_jt <= g_t
x_jt + r_t + h_jt = n_jt + c_t + w_jt
h_jt, w_jt >= 0
```

由于附件 4 电价均为正，并加 `c+r<=CAP`，不应出现有经济意义的同时充放电。

可以在目标中加极小 tie-break：

```text
epsilon * sum(c_t + r_t), epsilon ~ 1e-7
```

只用于消除退化，不影响元级费用结果。

## 14.4 Q4-2 成本

场景 j：

```text
Phi_j = sum_t p_jt * (g_t + 5*h_jt)
```

保留 48h continuation 也可以，因为现在是 LP，不再需要为了速度删 48h。

最终只提交前 144 个时段。

## 14.5 Q4-3 adjustment

当天当前日尚未执行部分仍以 0:00 baseline `g0_t` 为结算基准。

设辅助变量 `a_t` 表示 adjustment 增量费用对应的等效购电量：

```text
a_t >= 1.5 * (g_t - g0_t)
a_t >= 0.5 * (g_t - g0_t)
a_t >= -0.5 * g0_t
```

这样：

```text
当前日 settlement quantity = g0_t + a_t
```

等价于：

```text
增购：g0 + 1.5(g-g0)
减购：g0 - 0.5(g0-g)
```

跨到下一日的 continuation 时段仍正常按 `g_t` 计费，不施加本日 adjustment penalty。

## 14.6 Wasserstein DRO 直接对偶 LP

保留论文核心 finite-support Wasserstein：

```text
min lambda*rho + sum_i pi_i*alpha_i
```

约束：

```text
alpha_i >= Phi_j - lambda*d_ij    for all i,j
lambda >= 0
```

因为 `Phi_j` 在新模型中是线性的，整个模型仍然是**连续线性规划**。

不再使用 constraint generation；S=20 时 `i,j` 只有 400 条 DRO coupling constraints，完全可以直接解。

### 关键验收

新 Q4 solver 必须满足：

```text
integer variable count = 0
```

这是本轮性能修复是否真正完成的核心标志。

---

# 15. 对 `src/q4/physics.py` 的修改要求

不要再把 Q4 policy 直接复用成 Q3 的 `Policy(grid, charge_cap, discharge_cap)`。

新建 Q4 自己的 dataclass，例如：

```python
@dataclass
class DispatchPolicy:
    grid: np.ndarray
    charge: np.ndarray
    discharge: np.ndarray
```

真实回放：

```text
balance_need = net + charge - discharge
called = min(grid, max(balance_need, 0))
unused = grid - called
emergency = max(balance_need - called, 0)
spill = max(-balance_need + called, 0)
SOC 按固定 charge/discharge 更新
```

必须验证：

```text
called + discharge + emergency
=
net + charge + spill
```

以及 SOC、CAP、非负约束。

Q4-3 每个节点只执行 committed block 内的 `charge/discharge`，然后把真实 SOC 传给下一节点。

---

# 16. 场景构造修复要求

保留：

```text
严格因果 point forecast
同日绑定 price/net OOS residual
56 日最近窗口
prefix conditioning（Q4-3）
tail preservation
finite-support Wasserstein
```

必须修改：

1. forecast-origin residual 正确跨日；
2. forced tail singleton 不吸收普通样本质量；
3. `W=56` 改成预先固定，不再伪装 56/84/112 calibration；
4. 如果 LP 后仍太慢，bootstrap 从 100 降到 30—50，但必须同步文档与 audit。

暂时不要做：

```text
10/20/30 场景全年敏感性
56/84/112 全年比较
0.75/1/1.25 rho 全年比较
大量消融全年实验
```

比赛交付先完成正式结果。

---

# 17. 生产时间控制

## 17.1 外层 hard timeout

不要只信 HiGHS `time_limit`。

每个正式 solve 建议运行在独立 worker/subprocess，外层 watchdog 设：

```text
LP 节点 hard timeout：建议 15~30 秒
```

正常情况下新 LP 应远低于此值。

若触发 hard timeout：

```text
该节点失败
不允许 fallback 正式提交
保存 failure audit
中止或重试一次
```

绝不能再次产生 1090 秒单节点。

## 17.2 线程

LP 场景下优先：

```text
HiGHS threads = 1 或 2
```

全年可以通过日期/任务层并行，而不是每个小 LP 开太多 solver 线程导致 CPU 抢占。

先单进程验证，再考虑 Q4-2/Q4-3 分进程并行。

---

# 18. 最小实验计划——不要浪费比赛时间

只做以下三阶段。

## Stage A：单元与 synthetic

目标：5 分钟内完成。

必须过：

1. 连续 LP `integer_count == 0`。
2. 1 场景 × 4 时段手算物理平衡。
3. 2 场景 × 4 时段 Wasserstein `rho=0` 与经验期望一致。
4. Q4-3 adjustment 三种情况：增购、减购、不变。
5. 48h / 跨午夜 price residual origin 测试。
6. tail singleton 权重测试。
7. 所有 causal boundary 测试。

## Stage B：短 vertical slice

不要跑几十天。

建议：

```text
Q4-2：2025-02-01 起连续 3 天
Q4-3：2025-02-01 起连续 2 天 × 4 节点
```

或者额外单独对题目给出的代表日期做不提交 smoke：

```text
2025-03-20
2025-06-21
2025-09-23
2025-12-21
```

验收条件：

```text
无 solver limited
无 hard timeout
物理残差 <= 1e-6
SOC 全程合法
无未来数据访问
每节点运行时间达到可全年完成的数量级
```

## Stage C：直接全年

通过 Stage B 后立刻：

```text
Q4-2 334 天
Q4-3 334 天 × 4 节点
```

不要再插入新的参数实验。

---

# 19. 正式结果 sanity gates

这些不是数学定理，而是防止再出现明显坏解的工程门槛。

## Gate 1：solver validity

```text
Q4-2：334/334 日全部 optimal / certified
Q4-3：1336/1336 节点全部 optimal / certified
limited = 0
fallback formal = 0
```

## Gate 2：物理

```text
最大能量平衡残差 <= 1e-6 kWh
SOC ∈ [1200,10800]
charge, discharge <= 833.333333 kWh / 10min
emergency >= 0
called <= grid
```

## Gate 3：经济 sanity

保留以下 baseline：

```text
final Q2 policy + Attachment4 realized price
≈ 14,836,427.92 元
```

若新 Q4-2 年费用仍高于 baseline 15% 以上，必须自动报警并停止正式发布，检查：

```text
计划电量是否异常大
unused 是否异常大
SOC 是否长期卡边界
储能是否几乎不用
DRO 半径/尾部权重是否异常
```

不要仅因为 workbook 能生成就视为成功。

## Gate 4：储能利用 sanity

禁止再次出现：

```text
SOC >99% 时间卡在 10800
全年放电只有约 1.8 万 kWh
```

不规定必须达到某个固定放电量，但如果出现边界长期饱和，必须明确诊断。

## Gate 5：文件

只有当正式 334 天完整且所有 gate 通过时，才生成：

```text
result4-2.xlsx
result4-3.xlsx
```

旧失败结果必须重命名为：

```text
result4-2_FAILED_legacy_limited.xlsx
```

或留在旧输出目录，禁止误提交。

---

# 20. 需要修改的文件清单

## `src/q4/optimization.py`

必须：

- 删除/停用生产 `build_base_v2_free` MIP 路径；
- 新增连续 LP formulation；
- finite-support Wasserstein 使用直接 dual LP；
- 正式模式不接受 limited；
- audit 记录 `integer_variables=0`；
- audit 记录 solution source；
- 不再需要大型 constraint generation。

## `src/q4/physics.py`

必须：

- 增加 Q4 自己的 `DispatchPolicy(grid, charge, discharge)`；
- 新增与连续 LP 一致的真实 replay；
- 保留购电结算量与实际调用量分离。

## `src/q4/data.py`

必须：

- 修复跨日 price residual origin；
- Q2_RUN 改为最终 frozen run；
- Q4 provenance 嵌入 Q3/Q2 输入 hash；
- 正式起点与 Q2 统一为 Feb1 SOC=6000（按本任务推荐方案）。

## `src/q4/scenarios.py`

必须：

- forced tail singleton 权重不吸收 ordinary mass；
- bootstrap transport 矩阵可缓存；
- 如有必要降低 bootstrap repetition；
- 继续保持同日联合残差，不独立重排生产版本。

## `src/q4/rolling.py`

必须：

- 正式期直接从 Feb1 开始；
- Q4-3 每节点提交固定 `charge/discharge` committed block；
- 新输出目录；
- 不接受 limited；
- hard timeout / failure semantics；
- 不再把旧 Jan warmup SOC 混入 Feb1。

## `src/q4/config.py`

必须：

- production config 中 `allow_limited` 不可打开；
- signature 覆盖所有生产依赖；
- Q2_RUN 更新；
- 如固定 `W=56`，去掉“必须属于候选调参”的误导语义。

## `src/q4/diagnostics.py`

必须：

- 删除虚假的 window calibration；
- 新增 baseline sanity check；
- 新增 solver reliability summary；
- 新增 SOC boundary fraction、unused ratio、storage throughput 指标。

## `src/q4/traceability.py`

必须：

- 从“章节→文件映射”升级到核心公式/变量 assertions；
- 新模型应该明确验证 `binary=0`、storage schedule、DRO dual、adjustment settlement。

## `src/q4/test_q4.py`

必须补：

- cross-origin residual test；
- tail weight test；
- production limited forbidden；
- continuous LP no-integer test；
- Q42/Q43 short sequential replay test；
- baseline regression alarm test。

## 问题四建模文档

必须同步：

- 把“事前反馈 cap + min 精确线性化”改为“节点提交储能充放电计划 + committed block receding”；
- 保留结算量/实际调用量分离；
- 保留 Wasserstein DRO；
- W=56 改为预设窗口，不再声称滚动比较三档；
- 正式起点 SOC 与最终 Q2 对齐；
- tail singleton 权重描述与实现一致；
- 不再写 Big-M/指示约束；新模型为 LP。

---

# 21. 不能做的事情

Codex 不要：

1. 不要继续跑旧 `full_q43_20260913` 到年底。
2. 不要把 MIP gap 从 3% 改 5% 然后声称问题解决。
3. 不要单纯增加 `seconds=60/120/300`。
4. 不要通过把 `scenarios=20` 暴力降成 2—3 来掩盖架构问题。
5. 不要关闭 Wasserstein / joint residual 后仍让论文声称存在。
6. 不要保留论文里的 `\bar c` 决策变量但代码里没有。
7. 不要再使用 `allow_limited=True` 生成正式 workbook。
8. 不要覆盖旧结果；必须新目录重新计算。
9. 不要跑 20 多组消融和敏感性分析。
10. 不要为了追求所谓“精确反馈”重新引入成千上万 binary。

---

# 22. 推荐的新运行目录和版本策略

例如：

```text
outputs/q4/raw/rescue_lp_q42_20260913/
outputs/q4/raw/rescue_lp_q43_20260913/
```

每个 state 必须记录：

```text
model_version = q4_rescue_lp_v1
source hashes
input hashes
Q2 frozen source
price forecast version
scenario config
bootstrap repetitions
W
S
solver version
integer_variables = 0
```

旧目录完全只读。

---

# 23. Codex 完成任务后必须给出的报告

不要只说“代码改好了”。必须输出一个最终修复报告，至少包含：

```text
1. 修改了哪些文件
2. 数学模型发生了什么必要简化
3. 哪些核心机制保持不变
4. price residual origin bug 如何修复
5. tail weight 如何修复
6. 新 LP 单节点变量/约束规模
7. 是否 integer_variables=0
8. 3天 Q42 vertical slice 时间
9. 2天 Q43 vertical slice 时间
10. 所有测试结果
11. baseline sanity 结果
12. 是否可以立即跑全年
13. 预计全年时间
14. 全年完成后 Q4-2/Q4-3 的总费用、紧急购电量、SOC、unused、storage throughput
15. result4-2.xlsx / result4-3.xlsx 的路径和模板回读验收
```

任何一项失败，都不能写“正式结果已完成”。

---

# 24. Review Comments（按严重程度）

| ID | Severity | Review Comment | 影响 | 必须动作 |
|---|---|---|---|---|
| Q4-R01 | BLOCKER | 正式运行 `allow_limited=True`，334/334 Q4-2 日均未达到 3% gap 仍落盘 | 最终结果没有要求的最优性证书 | 正式禁用 limited |
| Q4-R02 | BLOCKER | fallback seed 使用逐时场景最大净需求且 `discharge_cap=0` | 极端超买、储能失效、费用异常 | fallback 不得进入正式结果 |
| Q4-R03 | BLOCKER | 当前 MILP 每日 17,280 binaries，Q4-3 每节点 8,640 binaries | 全年 1670 次大 MIP，时间不可控 | 改连续 LP |
| Q4-R04 | BLOCKER | 30 秒全部给第一轮 restricted master，CG 几乎不迭代 | 付出 DRO-CG 复杂度却未收敛 | 直接 dual LP |
| Q4-R05 | HIGH | 论文 `charge cap` 是决策变量，代码固定为 CAP | 模型—代码不一致 | 改论文/模型为节点储能计划 |
| Q4-R06 | HIGH | 48h / 跨午夜 price residual 使用错误 forecast origin | 联合场景统计口径错误 | 按 origin 直接算 residual path |
| Q4-R07 | HIGH | forced tail representative 会吸收 ordinary mass | 尾部概率可被人为放大 | tail singleton 权重锁定 |
| Q4-R08 | HIGH | `W=56` 所谓 calibration 是硬编码 | 论文实验陈述不成立 | 固定 56 并改文稿 |
| Q4-R09 | HIGH | Q4 signature 不 hash `q3.fast_solver/q3.physics` | 续算可能混用实现 | 完整依赖 hash / 去 Q3 solver 依赖 |
| Q4-R10 | HIGH | provenance 未完整 hash Q2/Q3 实际输入 | 可复现性不完整 | 嵌入 q3 provenance |
| Q4-R11 | HIGH | Q4 用旧 Q2 run | 版本口径不统一 | 指向 final frozen Q2 |
| Q4-R12 | HIGH | Q4 Feb1 SOC=10800，而最终 Q2 Feb1=6000 | “重新计算 Q2”起点不一致 | 正式起点统一 |
| Q4-R13 | HIGH | Q4-3 出现 1090 秒节点，内部 30s time limit 不可靠 | 单节点可拖垮全赛程 | 外层 hard watchdog |
| Q4-R14 | MEDIUM | traceability 只检查“章节映射到文件” | 无法发现变量缺失 | 公式级 assertions |
| Q4-R15 | MEDIUM | 100 bootstrap × 每节点 transport LP | LP 化后会成为明显耗时 | 缓存 Aeq / 必要时 B=30~50 |
| Q4-R16 | MEDIUM | Python k-medoids 交换循环重复运行 | 额外 CPU 开销 | profiling 后再优化 |
| Q4-R17 | LOW | 每日大量 fsync/hash | 轻微 I/O 开销 | 保留正式 receipt，减少 debug 写盘 |

---

# 25. 最终目标定义

本次修复不是追求“数学模型越复杂越好”。

比赛最终要的是：

```text
信息边界正确
+ 物理正确
+ 结算正确
+ 联合不确定性有理论支撑
+ 实际能够全年算完
+ 结果经济上可解释
+ 论文与代码一一对应
```

问题四真正值得保留的创新链条应是：

```text
严格因果价格预测
→ 同日价格—净负荷 OOS 联合残差
→ 尾部保持场景缩减
→ finite-support Wasserstein DRO
→ Q4-2 日前鲁棒调度 / Q4-3 四时点 receding horizon
→ 真实价格逐时回放结算
```

不需要为了“精确 saturated feedback”牺牲整个比赛交付。

当前最关键的修复判断标准只有一句：

> **修复后的 Q4 正式 solver 不再包含成千上万个二进制变量，并且不允许任何未取得正式求解成功状态的策略进入最终 Excel。**

