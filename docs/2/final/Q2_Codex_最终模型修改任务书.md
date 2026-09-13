# Q2 最终模型代码修改任务书（交给 Codex）

## 1. 任务目标

当前时间有限，不重构问题二（Q2）的整体框架，不重新设计预测器，不做额外科研式消融。

请在现有 Q2 代码基础上，按照当前论文最终方法完成最小侵入式修改，并重新生成正式 `result2.xlsx`。

最终模型主线保持为：

> 滚动预测 → 联合历史误差场景 → 随机优化（stochastic MILP） → 非前瞻储能补救 → 真实逐日回放

本次只增加两个正式方法组件：

1. **单侧尾部场景分层（tail-aware scenario construction）**
2. **动态 SOC 安全裕度（dynamic SOC reserve）**

不要在代码或结果说明中写“修复旧模型”“原模型太激进”“修改前后”等开发过程。最终实现应直接视为论文正式模型。

---

## 2. 必须保持不变的核心框架

以下内容禁止修改：

- 5 倍紧急购电价格；
- 储能最大容量、SOC 上下界；
- 充放电效率；
- 最大充放电功率；
- 10 min 时间粒度；
- 能量平衡公式；
- 计划购电费用公式；
- 紧急购电费用公式；
- 负荷优先补救逻辑；
- predictor 本身；
- 当前预测流程；
- 当前滚动 horizon 选择机制；
- 当前 solver 与 MIP gap 策略；
- 原有 `result2.xlsx` 输出字段及题目要求。

目标函数继续保持：

\[
\min \quad C^{plan} + \mathbb E[C^{emergency}]
\]

即：

```text
min planned_purchase_cost + expected_emergency_cost
```

不要加入 CVaR，不要加入人为风险权重 λ，不要修改 5 倍紧急购电价格。

---

# 3. 修改一：单侧尾部场景分层

## 3.1 目标

现有历史联合误差场景继续保留，但需要确保对“实际净负荷高于预测”的危险尾部具有足够表示能力。

重点保护的风险是：

```text
净负荷持续被低估
→ 实际 SOC 比预测下降更快
→ 晚高峰前储能过早耗尽
→ 触发大量 5 倍紧急购电
```

因此不能只看单点最大误差，需要考虑误差轨迹对储能造成的**累计压力**。

---

## 3.2 净负荷误差

对历史 forecast-origin 的每个 10 min 时段，计算：

\[
e^N_{j,t}
=
\Delta t
\left[
(L^{real}_{j,t}-PV^{real}_{j,t})
-
(L^{pred}_{j,t}-PV^{pred}_{j,t})
\right]
\]

代码意义：

```text
e_net = dt * ((load_real - pv_real) - (load_pred - pv_pred))
```

其中：

- `e_net > 0` 表示模型低估了真实净负荷；
- 单位统一为 kWh；
- `dt = 1/6 h`。

---

## 3.3 历史误差块累计压力

对每一个 eligible historical error block `j`，定义：

\[
S_j
=
\max_k
\left[
\sum_{u=1}^{k} e^N_{j,u}
\right]_+
\]

实现上可写为：

```text
cum_error = cumsum(e_net_block)
S_j = max(0, max(cum_error))
```

`S_j` 表示该历史误差轨迹在整个预测窗口内对储能造成的最大累计额外压力。

如果使用多日前瞻场景，必须继续保持原有：

- predictor-consistent；
- forecast-origin consistent；
- horizon-specific；
- 负荷与 PV 联合误差结构；
- 日内连续性和跨日相关性。

禁止把历史误差拆成逐时独立噪声。

---

## 3.4 场景分层

对当天 0:00 可用的所有 eligible historical blocks：

1. 按 `S_j` 从小到大排序；
2. 压力最大的 20% 定义为：

```text
tail_pool
```

3. 其余定义为：

```text
body_pool
```

注意：

- 只能使用当天以前已经完整实现的历史数据；
- 禁止使用当天 actual；
- 禁止利用未来月份数据反向选择当天 tail block。

---

## 3.5 总场景数保持不变

保持当前正式模型总场景数 `S` 不变。

定义：

```text
S_tail = max(1, round(0.2 * S))
S_body = S - S_tail
```

抽样规则：

- `S_body` 从原本的近期历史主体场景池中抽取；
- `S_tail` 从 `tail_pool` 中抽取；
- 如果 body pool 中仍含 tail block，优先排除；
- 历史数据不足时允许合理 fallback；
- 不得因此增加总 MILP 场景规模。

---

## 3.6 场景概率

不要简单把所有分层后场景重新等权。

应使：

- body 层保留对应经验概率质量；
- tail 层保留对应经验概率质量；
- 层内均分。

例如尾部定义为最高 20%，则在数据足够时：

```text
total tail probability ≈ 0.20
total body probability ≈ 0.80
```

再分别在各层被抽取的代表场景中分配权重。

所有权重最终必须满足：

\[
\sum_s \pi_s = 1
\]

---

# 4. 修改二：动态 SOC 安全裕度

## 4.1 目标

原物理 SOC 下限仍然是：

\[
E_{\min}=1200 \text{ kWh}
\]

但调度不能总是把 1200 kWh 视为“可以放心一直放到这里”的运行目标。

需要根据历史预测误差，预留一部分动态安全电量，用于抵御当日后续可能出现的累计净负荷低估。

---

## 4.2 未来累计误差压力

对当天第 `t` 个 10 min 时段，对每一个历史净负荷误差轨迹 `j` 计算：

\[
B_{j,t}
=
\max_{k=t,\ldots,144}
\left[
\sum_{u=t}^{k} e^N_{j,u}
\right]_+
\]

代码逻辑：

```text
future_error = e_net_block[t:]
future_cum = cumsum(future_error)
B_j_t = max(0, max(future_cum))
```

它表示：

> 从当前时刻开始到当天结束，历史上最多曾出现多少“累计净负荷低估”。

---

## 4.3 动态安全裕度

对所有可用历史误差块的 `B[:, t]` 取 0.8 分位：

\[
R_t
=
\min
\left\{
E_{\max}-E_{\min},
\frac{Q_{0.8}(B_{j,t})}{\eta_d}
\right\}
\]

其中：

```text
Emin = 1200 kWh
Emax = 10800 kWh
eta_d = 0.9
```

即：

```text
R[t] = min(
    Emax - Emin,
    quantile(B[:, t], 0.8) / eta_d
)
```

要求：

- `R[t]` 必须在当天 0:00 一次性根据历史数据计算并冻结；
- 日内禁止使用当天未来 actual 更新 `R[t]`；
- `R[t]` 不是新的物理 SOC 下限；
- 真实物理约束仍然是 `[1200, 10800]`。

---

## 4.4 只对实际执行的第一个 24 h 启用

若当前滚动优化 horizon 为多天：

- 前 144 个 10 min 时段（当天真正执行的部分）使用动态 `R[t]`；
- 后续 proxy days 保持：

```text
R = 0
```

避免人为改变 continuation value 的定义和后续代理日结构。

---

## 4.5 修改放电可用量

原来最大可放电母线侧电量若为：

\[
\eta_d(E_{t-1}-E_{\min})
\]

统一改为：

\[
\eta_d
\left[
E_{t-1}-E_{\min}-R_t
\right]_+
\]

即：

```text
available_discharge =
    eta_d * max(E_prev - Emin - R[t], 0)
```

最终实际/场景放电：

```text
r[t] = min(
    r_plan[t],
    positive_gap[t],
    eta_d * max(E_prev - Emin - R[t], 0)
)
```

---

## 4.6 Scenario MILP 与真实 replay 必须完全一致

动态 SOC reserve 不能只存在于 replay。

必须同时修改：

1. scenario recourse / stochastic MILP 中的储能放电可用量；
2. 当天真实回放中的储能放电可用量。

两处公式必须一致。

否则优化器会基于“可以放到 1200”的假设做计划，而真实回放却按照更高的策略下限执行，导致模型与回放不一致。

---

## 4.7 不允许主动为安全裕度紧急购电

`R[t]` 只负责限制继续放电。

禁止写成：

```text
if SOC < Emin + R:
    emergency_purchase to recharge battery
```

动态安全裕度不是强制补库存机制。

允许 SOC 因历史状态处于 `Emin + R` 以下，此时仅：

```text
available_discharge = 0
```

不得为了恢复 `R[t]` 主动触发 5 倍紧急购电。

---

# 5. 计算性能要求

时间有限，请避免任何不必要的重新计算。

## 5.1 优先复用缓存

如果已有中间结果可以复用，必须优先复用：

- forecast；
- shadow forecast；
- historical residual；
- predictor selection；
- 已完成的数据清洗结果；
- 其他与此次修改无关的缓存。

不要因为修改 scenario selection / SOC reserve 而重新训练全部预测模型。

---

## 5.2 不增加 scenario 总数

总场景数保持当前正式设置。

本次只改变：

```text
scenario composition
```

而不是扩大：

```text
scenario count
```

---

## 5.3 正式运行必须支持断点续跑

334 天正式计算必须支持：

```text
--resume
```

并实现：

- 每完成一天立即 checkpoint；
- 每完成一天立即保存 daily result；
- 中断后从最后成功日期继续；
- 禁止每次从 2025-02-01 重新开始。

建议目录保存：

```text
checkpoints/
daily_results/
solver_logs/
```

---

# 6. 不再执行的实验

时间有限，以下实验全部取消，不需要实现或重新运行：

- Oracle / perfect-foresight test；
- 1% / 2% / 3% MIP-gap matched experiment；
- CVaR 实验；
- 10% / 20% / 30% tail 比例敏感性；
- 0.75 / 0.80 / 0.90 reserve 分位敏感性；
- 28 / 56 / 84 天窗口全套敏感性；
- K=1 / 2 / 3 新一轮 horizon 实验；
- 初始 SOC 敏感性；
- deterministic baseline；
- rigid-storage ablation；
- Tail-only / Reserve-only 消融；
- 其他不影响最终结果文件的科研式扩展实验。

不要为了这些实验阻塞正式 `result2.xlsx` 的生成。

---

# 7. 论文真正需要保留的结果检查

只保留以下三类。

---

## 7.1 正式全年主结果

完整运行：

```text
2025-02-01 ~ 2025-12-31
```

重新生成：

```text
result2.xlsx
```

统计全年：

- `planned_grid_kwh`
- `emergency_kwh`
- `planned_cost`
- `emergency_cost`
- `total_cost`
- `emergency_events`
- `unused_kwh`
- `charge_kwh`
- `discharge_kwh`
- `final_soc`

同时单独输出题目要求的四天：

```text
2025-03-20
2025-06-21
2025-09-23
2025-12-21
```

用于论文表 1、表 2、表 3。

---

## 7.2 最终物理一致性检查

只对最终结果做 post-process，不需要重新优化。

必须检查：

### SOC

```text
1200 <= SOC <= 10800
```

### 充放电互斥

同一个 10 min 时段不得同时：

```text
charge > 0 and discharge > 0
```

### 功率约束

单个 10 min 充放电量不得超过题目功率上限对应电量：

```text
5000 kW × 1/6 h = 833.333... kWh
```

### 能量平衡

每个时段检查：

```text
planned_grid
+ discharge
+ emergency
=
net_load
+ charge
+ unused
```

残差应仅为浮点误差量级。

### 紧急购电时不得充电

检查：

```text
emergency > 0 => charge == 0
```

输出：

```text
final_validation.json
```

至少包含：

```text
soc_min
soc_max
soc_violation_count
simultaneous_charge_discharge_count
power_violation_count
max_energy_balance_residual
emergency_and_charge_count
overall_pass
```

---

## 7.3 最终预测与场景覆盖统计

不重新求解。

利用正式滚动过程中已经保存的：

- prediction；
- scenarios；
- actual；

计算：

- load MAE；
- load RMSE；
- PV MAE；
- PV RMSE；
- net-load MAE；
- net-load RMSE；
- PICP80；
- PICP90。

输出：

```text
final_calibration.csv
final_calibration.json
```

不要求为了把覆盖率调到严格等于 80% / 90% 再进行参数搜索。

这里仅作为论文中的最终不确定性描述和模型有效性说明。

---

# 8. 最终输出文件

正式运行结束后，请提供：

1. 修改后的完整代码仓库；
2. `result2.xlsx`；
3. `summary.json`；
4. `final_validation.json`；
5. `final_calibration.csv`；
6. `final_calibration.json`；
7. 四个指定日期的论文表格数据；
8. solver 运行统计。

solver 运行统计至少包括：

```text
total_runtime
mean_daily_runtime
median_daily_runtime
max_daily_runtime
requested_mip_gap
achieved_mip_gap_mean
achieved_mip_gap_max
days_completed
```

---

# 9. result2.xlsx 要求

保持题目要求的原模板结构。

## 计划购电量

保存：

```text
2025-02-01 ~ 2025-12-31
```

每天每 10 min 的全天计划购电量，单位 kWh。

## 充放电量

保存：

- 指定时间段实际充电量；
- 指定时间段实际放电量；
- 每日 0:00 SOC；
- 每日 24:00 SOC。

必须填写真实 replay 的执行值，而不是 scenario 内计划值。

## 紧急购电量

将连续满足：

```text
emergency_kwh > 0
```

的 10 min 时段合并为连续区间，并汇总该区间电量。

不能为了套模板固定行数而删除事件。

---

# 10. 代码实现要求

## 10.1 最小侵入修改

优先在已有模块中增加功能，不要重构整个项目。

预计修改范围主要应该集中在：

```text
scenario generation
historical residual utilities
dispatch / recourse
real replay
config
result summary
checkpoint/resume
```

如果某模块与上述两项方法修改无关，不要顺手重构。

---

## 10.2 配置必须显式记录

建议增加类似配置：

```text
tail_fraction = 0.20
reserve_quantile = 0.80
dynamic_soc_reserve = true
tail_stratification = true
```

但正式运行时直接固定为论文采用值。

这些参数必须写入最终 `summary.json` 或配置快照，确保结果可复现。

---

## 10.3 关键诊断字段

建议每日保存：

```text
date
initial_soc
final_soc
min_soc
planned_grid_kwh
emergency_kwh
planned_cost
emergency_cost
total_cost
unused_kwh
charge_kwh
discharge_kwh
scenario_count
tail_scenario_count
body_scenario_count
max_reserve_kwh
mean_reserve_kwh
requested_mip_gap
achieved_mip_gap
runtime_seconds
solver_status
```

方便后续论文直接整理。

---

# 11. 验收条件

修改完成后不能只说明“代码已实现”，必须先完成以下检查。

## 代码层

- Tail scenario selection 使用的全是过去数据；
- `R[t]` 使用的全是过去误差；
- scenario 与 real replay 的 reserve 公式一致；
- 总 scenario 数没有增加；
- predictor 没被修改；
- 费用定义没被修改；
- 原有能量平衡没有被修改；
- 5 倍 emergency 价格没有被修改。

## 最终结果层

- 334 天全部完成；
- `result2.xlsx` 无缺失日期；
- 物理一致性检查全部通过；
- 无同一时段同时充放电；
- 无 emergency 时充电；
- SOC 始终在物理边界内；
- final summary 可以复算总费用；
- 四个指定日期数据完整。

---

# 12. Codex 执行优先级

严格按照以下顺序执行。

### P0：代码修改

1. 实现净负荷历史误差与累计压力 `S_j`；
2. 实现 body/tail scenario stratification；
3. 保持总 scenario 数不变；
4. 实现场景概率；
5. 实现 `B[j,t]`；
6. 计算 `R[t]`；
7. 修改 scenario recourse 放电约束；
8. 修改 real replay 放电逻辑；
9. 添加 checkpoint / resume。

### P1：小规模正确性检查

不要立即跑 334 天。

先选 1 个普通日期和 1 个历史上 emergency 较大的日期，确认：

- solver 能正常求解；
- energy balance 正确；
- reserve 被正确应用；
- replay 与 scenario 逻辑一致；
- 输出格式没有被破坏。

这里只是 smoke test，不是论文实验。

### P2：正式全年运行

确认 P1 无误后立即运行：

```text
2025-02-01 ~ 2025-12-31
```

开启 checkpoint。

### P3：结果整理

全年完成后自动生成：

```text
result2.xlsx
summary.json
final_validation.json
final_calibration.csv
final_calibration.json
paper tables
```

---

# 13. 最重要的限制

本任务目标不是继续研究模型，而是尽快得到一个：

> 数学上自洽、物理上可行、能够合理处理预测尾部风险、可完整生成问题二正式结果的最终模型。

因此：

- 不要继续扩大实验范围；
- 不要擅自引入新算法；
- 不要换 predictor；
- 不要加入 RL；
- 不要加入 MPC；
- 不要加入神经网络；
- 不要加入新的风险参数体系；
- 不要为了“看起来更先进”增加复杂度。

只完成本文档明确要求的两项方法增强，并尽快产出最终正式结果。
