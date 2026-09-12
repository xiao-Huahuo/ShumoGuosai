# 问题二求解加速：Codex 执行任务书

## 0. 任务目标

当前项目正在完成 2026 年全国大学生数学建模竞赛 C 题问题二。

现状：

- 问题二主模型已经基本确定；
- 当前正式求解统一采用 `MIP gap = 3%`；
- 已经完成一轮全年主回放，当前主要矛盾是后续验证实验、敏感性实验和部分困难实例耗时过长；
- 现在不希望继续扩大实验规模，也不希望大幅修改数学模型；
- 当前目标是：**在不改变问题二论文主模型含义、不放松物理约束、不改变 3% 精度口径的前提下，尽可能缩短剩余实验时间，并清理不必要的重复求解。**

请先完整阅读：

1. 当前问题二最终建模文档；
2. `src/q2/` 下与 rolling / optimization / linear policy / relaxation / incumbent / full run 相关的代码；
3. 当前 `TASK_STATE.md`；
4. 与问题二计算执行、精度、加速相关的 docs；
5. 当前正式运行目录中已有的主结果、warm start、run status、审计记录。

本次任务优先级是：

> **先确认主结果一致性，再减少无必要实验，再优化求解流水线。**

禁止为了加速而随意修改数学模型。

---

# 1. 第一优先级：确认正式主结果的初始 SOC 一致性

当前代码、论文文档和旧实验记录中存在一个必须先确认的问题：

- 当前问题二最终模型文档规定：
  - 1 月只用于历史预热；
  - 1 月储能不主动调度；
  - `2025-02-01 00:00` 初始 SOC 为 `6000 kWh`。
- 当前源码中也已经出现 `evaluation_initial_soc_kwh = 6000.0`。
- 但是部分旧的 TASK_STATE / 加速文档 / 测试记录中仍然出现：
  - `8482.766385`
  - `initial_8482.77`

因此，在做任何重新求解之前，先只读核验正式 334 天主结果。

## 1.1 必须核验的内容

请检查正式主回放目录中的：

- `warm_start.json`
- `run_status.json`
- 首日相关结果文件
- 2025-02-01 的 dispatch / SOC 日志
- protocol signature
- precision revision
- 正式 result2 生成所依据的运行目录
- 当前源码 commit / snapshot（如果有记录）

必须明确回答：

> 已经完成的正式 334 日问题二主结果，2025-02-01 的初始 SOC 到底是 `6000` 还是 `8482.766385`？

## 1.2 处理规则

### 情况 A：正式主结果确实是 6000

则：

- 不重新跑主结果；
- 把 `8482.766385` 标记为旧实验遗留值；
- 清理当前仍会误导后续实验的硬编码；
- 禁止 baseline reuse / warm start 误用旧 initial SOC；
- 更新必要的文档和测试，使当前正式语义只保留 `6000 kWh`。

### 情况 B：正式主结果是 8482.766385

则：

- 立即停止继续做后续实验；
- 不要擅自重跑全年；
- 先报告：
  1. 哪些最终结果使用了旧初始 SOC；
  2. 哪些结果与当前论文模型不一致；
  3. 如果统一改为 6000，需要重跑哪些部分；
  4. 是否存在可以只重跑正式主回放而不重做其他资产的方案。

在我确认之前，不要大规模重跑。

---

# 2. 第二优先级：停止“27 项全部跑完”的旧验收逻辑

当前问题二最终论文模型已经明确：

模型检验只保留：

1. 预测与场景覆盖检验；
2. 物理可行性与数值一致性检验；
3. 经济结果评价。

当前论文不需要把所有开发阶段实验都跑成完整的 334 天全年 rollout。

因此，请检查 `full_run.py` 和相关实验注册逻辑。

---

# 3. 重构实验分类

请把现有实验显式区分为：

```text
required_for_paper
optional_diagnostics
legacy_or_development_only
```

## 3.1 required_for_paper

必须保留：

### A. 正式全年主结果

仅一个正式主方案。

如果已经完成且一致性验证通过：

> 不允许重新跑。

### B. 离线预测评价

直接使用正式滚动过程中已经保存的预测记录计算：

- Load MAE
- Load RMSE
- PV MAE
- PV RMSE
- Net-load MAE
- Net-load RMSE
- 80% scenario interval empirical coverage
- 90% scenario interval empirical coverage

这些应当：

> 不额外求解 MILP。

### C. 正式主结果物理一致性检查

直接从最终结果检查：

- SOC 始终位于 `[1200, 10800]`
- 充电功率限制
- 放电功率限制
- 不同时充放电
- 能量平衡残差
- `q_t > 0 => c_t = 0`
- SOC 递推一致性

这些应当：

> 不额外求解 MILP。

### D. 正式经济指标

直接从主结果计算：

- 计划购电量
- 计划购电费用
- 紧急购电量
- 紧急购电次数
- 紧急购电费用
- 总购电费用
- 紧急购电占比
- 未利用电量
- 累计充电量
- 累计放电量
- 指定日期结果

这些应当：

> 不额外求解 MILP。

---

# 4. 敏感性实验：不要再默认全年 334 天

对以下实验：

- horizon sensitivity
- scenario count sensitivity
- historical window sensitivity
- predictor sensitivity
- initial SOC sensitivity
- minimum sample size sensitivity
- deterministic comparison
- rigid comparison
- richer SOC
- oracle
- 其他开发性对照

不要默认全部做 334 天全年 rollout。

## 4.1 建议统一使用小型代表日集合

优先使用：

- 题目指定的 4 个日期：
  - 2025-03-20
  - 2025-06-21
  - 2025-09-23
  - 2025-12-21
- 再加 2~3 个此前已经识别出的高 emergency / 高波动困难日。

最终控制在：

```text
6 ~ 8 个代表日
```

只有当某个实验的论文结论必须依赖全年统计时，才允许做全年。

## 4.2 不允许

不要为了“实验完成度”继续把下列组合全部跑完：

```text
predictor × 334 days
window × 334 days
scenario count × 334 days
initial SOC × 334 days
minimum sample size × 334 days
```

如果一个结论用 6~8 个代表日已经能说明：

- 趋势；
- 稳定性；
- 定性一致性；
- 对正式策略影响不大；

则停止扩展。

---

# 5. 第三优先级：优化求解流水线

请重点 review 以下文件：

```text
src/q2/relaxation.py
src/q2/incumbent.py
src/q2/optimization.py
src/q2/linear_policy.py
src/q2/rolling.py
src/q2/full_run.py
```

重点不是重写数学模型，而是减少重复工作。

---

# 6. P0 优化：限制 pre-MILP refine 的隐藏耗时

当前重点检查：

```text
recourse_bound(...)
refine(...)
```

是否存在：

```text
refine default ≈ 90s
```

然后才进入：

```text
solve_linear_policy(... time_limit≈120s)
```

如果确实如此，则当前所谓“120 秒求解预算”实际 wall-clock 明显大于 120 秒。

## 6.1 修改目标

把启发式 refinement 从“长时间优化器”改为“短时 incumbent 改善器”。

建议：

```text
refine_seconds = 5 ~ 10 s
```

先做 5 秒版本。

不要一开始就取消 refine。

## 6.2 需要支持参数化

例如：

```python
refine_seconds: float
```

不要继续硬编码 90 秒。

## 6.3 验收

选：

- 3 个普通日
- 3 个历史困难日

比较：

```text
90s refine
10s refine
5s refine
```

统计：

- final objective
- certified gap
- MILP wall time
- total wall time
- 是否获得可靠 incumbent
- 是否触发 rescue

如果 5~10 秒版本结果几乎不变且总时间明显下降：

> 正式采用短 refine。

---

# 7. P0 优化：LP certificate 成立后不要再做无意义的 SCIP build/presolve

当前检查 `optimization.py` 中类似逻辑：

```python
bound_policy, bound_responses, bound = recourse_bound(...)

if bound["certified_gap"] <= solver_gap:
    ...
```

如果 LP lower bound 与可行策略 upper bound 已经证明：

```text
(U - L) / L <= 3%
```

则已经完成 3% optimality certificate。

若后面还只是为了：

- 报模型规模
- before presolve
- after presolve

再去：

```python
build_model(...)
model.presolve()
```

这属于非必要计算。

## 7.1 修改要求

LP certificate 成立时：

```text
直接接受当前 feasible policy
直接 replay
直接返回 certified result
```

不要再完整构造 SCIP MILP。

## 7.2 模型规模统计

模型规模不要逐日重复求。

可以：

```text
按 (K, S, formulation_version)
```

缓存一次：

- vars
- binaries
- constraints
- nonzeros

后续直接复用。

## 7.3 保持审计信息

必须继续记录：

```text
upper_bound
lower_bound
certified_gap
certificate_source = "LP_BOUND"
```

不要因为跳过 SCIP presolve 导致审计信息丢失。

---

# 8. P1 优化：rescue 不要每次重新从零开始

当前检查失败后的 rescue 流程。

目标：

第一次 base attempt 已经生成的内容尽量复用：

- feasible incumbent
- first-stage policy
- lower bound
- scenario assets
- prediction assets
- reserve
- medoids
- model-independent preprocessing

不要 rescue 再完整从头做一次。

## 8.1 最低要求

如果 base attempt 已经有一个可行解：

```text
rescue 必须使用它作为 seed / MIP start / incumbent
```

如果 base attempt 已经有 LP lower bound：

```text
rescue 应继承和记录该 bound
```

---

# 9. P1 优化：非核心敏感性实验禁止 900 秒无限阻塞

当前如果所有实验都共享：

```text
normal solve -> fail -> 900s rescue
```

则一个可选实验就可能阻塞十几分钟。

请区分：

```text
main_result
required_sensitivity
optional_diagnostic
```

建议：

### main_result

允许：

```text
standard solve
+
long rescue
```

### required_sensitivity

允许：

```text
standard solve
+
moderate rescue
```

### optional_diagnostic

默认：

```text
standard solve
+
short rescue or no rescue
```

如果失败：

```text
record timeout
record incumbent
record gap
continue
```

不要让一个 optional day 卡住整个批次。

---

# 10. P1 优化：线程数参数化并做小规模 A/B

当前重点检查 HiGHS / SCIP 是否硬编码：

```text
threads = 1
```

以及 rolling worker 是否固定：

```text
WORKERS = 2
```

不要直接把每个 solver threads 开到最大。

请先做：

```text
2 workers × 1 solver thread
2 workers × 2 solver threads
2 workers × 3 solver threads
```

在同一批：

- 3 个普通日
- 3 个困难日

比较：

- total wall time
- solver time
- memory peak
- timeout 数
- 最终 gap
- final objective

如果当前机器是 10 logical CPU / 16GB RAM 左右：

优先考虑：

```text
2 × 2
2 × 3
```

不要尝试：

```text
2 × 8
```

除非实测证明内存和 CPU 调度稳定。

---

# 11. P2 优化：scenario-size continuation / warm start

当前如果 S=10、20、40 被当作完全独立问题：

请考虑：

```text
S10 solution -> seed S20
S20 solution -> seed S40
```

至少 first-stage：

```text
g
c^p
r^p
```

可以继承为更大场景模型的初始解。

注意：

> 不改变最终目标函数，不减少 S40 的场景，只用前一级结果作为 warm start。

---

# 12. P2 优化：缓存不随求解参数变化的日级资产

检查多实验重复计算：

- forecast
- predictor selection
- shadow errors
- scenario candidate pool
- dynamic SOC reserve
- historical block ranking
- medoids / clustering
- date feature construction
- static matrices

如果相同：

```text
day
forecast origin
predictor
K
window
scenario generation revision
```

下资产完全一样，则不要重复计算。

建议建立显式 cache key，例如：

```text
(day, K, predictor_id, residual_pool_revision, window, scenario_seed, S)
```

不同层级分别缓存：

```text
forecast cache
residual block cache
reserve cache
scenario cache
model-shape cache
```

缓存只能用于加速：

> 禁止引入未来信息或破坏 rolling causality。

---

# 13. 当前不要做的事情

本轮禁止主动做以下修改：

## 13.1 不改变 3% gap

当前正式口径继续：

```text
MIP relative gap = 3%
```

不要改成：

```text
4%
5%
```

除非作为单独性能诊断实验，并且不覆盖正式结果。

## 13.2 不改数学模型核心

不要擅自修改：

- 5 倍紧急购电价格；
- 80% 临界分位理论；
- 动态 SOC reserve 定义；
- tail calibration；
- predictor-conditioned residual；
- non-anticipative execution；
- 充放电效率；
- SOC 物理边界；
- 负荷优先逻辑；
- 第一阶段/第二阶段语义。

## 13.3 不为了加速减少物理约束

禁止：

- 删除 SOC 下限；
- 删除 SOC 上限；
- 删除充放电功率限制；
- 删除 energy balance；
- 允许同一时段真实同时充放电；
- 放松 `q > 0 => c = 0`；
- 把紧急购电价格改低。

## 13.4 不把 GPU 当作本轮重点

当前主要瓶颈是：

```text
MILP branch-and-bound
LP relaxation
presolve
integer search
```

不要花时间做 CUDA / GPU 迁移。

---

# 14. 测试要求

修改完成后，至少增加/更新以下测试。

## 14.1 SOC 初始值一致性测试

确保正式 protocol：

```text
Feb-1 initial SOC == 6000
```

并阻止旧的 `8482.766385` 意外进入正式路径。

## 14.2 LP certificate fast path 测试

构造一个：

```text
LP gap <= 3%
```

实例。

验证：

- 返回成功；
- 不进入完整 MILP；
- 不进入 SCIP presolve；
- certificate 数据完整；
- final policy replay 可行。

## 14.3 refine budget 测试

确认：

```text
refine_seconds
```

可以参数化。

## 14.4 rescue inheritance 测试

确认已有 incumbent 可以进入 rescue。

## 14.5 optional experiment timeout 测试

optional 实验超时后：

```text
记录状态
不中断整个 batch
```

---

# 15. 需要生成的 benchmark

请新增一个轻量 benchmark，不允许直接跑全年。

固定：

```text
3 个普通日
3 个困难日
```

对比：

### Baseline

当前实现。

### Variant A

```text
refine = 5~10s
```

### Variant B

```text
A + LP-certified fast return
```

### Variant C

```text
B + rescue reuse
```

### Variant D

```text
C + best thread setting
```

输出 CSV：

```text
date
variant
K
S
solver
status
wall_seconds
pre_solver_seconds
milp_seconds
refine_seconds
rescue_seconds
upper_bound
lower_bound
gap
objective
emergency_kwh
final_soc
memory_if_available
```

最后生成一份简短 Markdown：

```text
docs/2/final/求解加速benchmark.md
```

只需要回答：

1. 哪个改动省时最多；
2. 是否改变最终目标值；
3. 是否改变 3% certificate；
4. 是否有数值或可行性回归；
5. 推荐正式采用哪组设置。

---

# 16. 建议的最终运行策略

如果测试通过，正式流程建议变成：

```text
prepare day assets
↓
LP relaxation / recourse bound
↓
short refine
↓
if 3% certified:
    replay + validate + return
else:
    MILP with incumbent
↓
if timeout:
    required?
        yes -> rescue using incumbent
        no  -> record + continue
```

而不是：

```text
长时间 refine
↓
MILP
↓
SCIP build/presolve
↓
失败
↓
从头再做 900 秒
```

---

# 17. 完成标准

本任务完成必须满足：

## P0

- 已明确证明正式 334 日主结果使用的 Feb-1 initial SOC；
- 若一致，则保留现有主结果，不重跑；
- `8482.766385` 不再能污染正式路径。

## P1

- 实验被拆成 paper-required / optional；
- 后续不再以“27/27”为论文完成条件；
- 无必要的全年敏感性 rollout 被取消。

## P2

- refine 时间显著缩短；
- LP certificate 后不再做无必要完整 MILP/presolve；
- rescue 能继承 base incumbent。

## P3

- 用 6 日 benchmark 给出真实 wall-time 对比；
- 不改变 3% gap；
- 不改变数学模型；
- 不出现新的物理违规；
- 主结果 objective / emergency / SOC 没有异常回归。

---

# 18. 提交形式

不要只告诉我“已优化”。

完成后请给出：

## A. 修改摘要

按：

```text
P0 / P1 / P2
```

列出实际修改。

## B. 修改文件

逐个说明：

```text
file
function
change
reason
```

## C. Benchmark

给出：

```text
修改前
修改后
加速比例
```

## D. 行为一致性

确认：

```text
数学模型是否改变
3% gap 是否改变
场景数是否改变
物理约束是否改变
正式主结果是否重新计算
```

## E. 剩余任务

明确告诉我：

```text
现在为了数学建模论文真正还必须跑什么
哪些已经可以不跑
预计剩余总时间
```

---

# 19. 最重要的执行原则

当前是数学建模竞赛收尾阶段。

优先级不是：

> 把整个科研型实验框架做到最完整。

优先级是：

> 用最少的额外计算，产出模型一致、数值可信、论文能够解释和复现的最终结果。

如果一个实验不会影响：

- 最终 `result2.xlsx`
- 核心模型正确性
- 论文中的必要验证
- 主要结论

则默认不要继续跑 334 天。

先完成 P0 一致性核验，再开始修改求解流水线。
