# 第三问 3% 精度下“不改模型”的计算加速执行指令（给 Codex）

> 任务性质：生产计算救援 / 精确等价优化 / 求解器替换
>
> 目标：**在不改变第三问数学模型、信息边界、场景规模、真实执行规则和 3% 子问题最优性门槛的前提下，显著缩短全年主计算时间。**
>
> 当前最优路线：**同一 MILP 换更强的 MIP solver + 继续 exact reformulation（精确等价重构）**。
>
> 这不是重新建模。禁止为了加速改成更粗的近似模型。

---

## 0. 必须先读的文件

开始任何修改前，按以下顺序重新读取：

1. `数学建模开发规范.md`
2. `docs/3/Q3_第三问_最终建模_严格修订终稿_v4.md`
3. `docs/3/compute_rescue/report.md`
4. `docs/3/compute_rescue/task_plan.md`
5. `src/q3/optimization.py`
6. `src/q3/fast_solver.py`
7. `src/q3/physics.py`
8. `src/q3/config.py`
9. `src/q3/rolling.py`
10. `src/q3/full_run.py`
11. `src/q3/solver_probe.py`
12. `src/q3/test_fast_solver.py`
13. 当前 `outputs/q3/active_run.json` 指向的活动运行目录及其 `execution.json / progress.json / node checkpoint`

禁止只根据本指令凭印象改代码。必须对照当前源码重新确认。

---

# 1. 当前已确认的瓶颈

当前第三问不是“数据预处理慢”，也不是“场景聚类慢”，而是某些随机 MILP 节点尤其 **06:00 更新节点**存在严重 branch-and-bound 长尾。

当前快路径已经完成一轮精确重构：

- 自由 aggregate feedback 下，利用充电上限的单调支配关系，将 `charge_cap` 固定到设备上限；
- 保留原始 `physics.replay()` 作为最终可执行策略的唯一真实语义；
- 求解器内部允许的松弛轨迹只用于证明下界，不允许冒充真实执行；
- 原 Jan14 06:00 的二元变量已经由 6048 降至 2592；
- 同一节点由原长时间仍 5.9% gap 改进到约 128 s 达到 3%。

但当前主链仍有明显长尾。例如 06:00 节点可从几秒到数百秒甚至更长；120 s 在当前正式路径中是**检查点/切片尺度，不是总硬超时**。若 gap 未到 3%，求解会继续。

因此新的优化目标必须针对：

> **更快提升 valid global lower bound，减少 MIP 证明时间。**

不要把主要精力放在已经足够好的 incumbent 上。

---

# 2. 本轮绝对不可改变的模型不变量

以下项目全部冻结。任何一项被改动，本轮即判定失败：

1. 正式场景规模仍为 `S*=20`。
2. 尾部保持仍为 `S_tail=2`。
3. 历史窗口仍为 `28 -> 56 -> 84 -> all history`。
4. 预测量级条件匹配逻辑不变。
5. 联合负荷—光伏历史误差轨迹不变。
6. 时间粒度仍为 10 min，一日 144 槽。
7. 四个信息节点仍为 `0/6/12/18`。
8. 每个节点滚动时域仍为未来 24 h。
9. committed block / look-ahead proxy / continuation proxy 的逻辑不变。
10. 非对称调整结算不变：相对 0:00 原计划的 0.5/1.5 倍规则不变。
11. 紧急购电 5 倍价格不变。
12. 储能容量、SOC 上下界、充放电功率和 0.9 效率不变。
13. 终端储能价值 `lambda_E` 的计算逻辑不变。
14. 真实跨日 SOC 连续性不变。
15. 1 月 burn-in 不得跳过，不得人为重置 2 月 1 日 SOC。
16. 真实执行仍必须由 `src/q3/physics.py::replay()` 重算。
17. 正式接受条件仍为**原反馈真实目标值相对有效全局下界 gap <= 3%**。
18. 不得把 solver 内部 relaxation trajectory 当成真实充放电结果。
19. 不得使用未来真实负荷/光伏帮助当前节点优化。
20. 不得修改 FIV/OUV 的定义来换取计算速度。

特别禁止：

- 把 S=20 改成 S=10；
- 把 3% 改成 5%；
- 把 24 h 改成 6 h/12 h；
- 把 10 min 改成小时；
- 删除 tail 场景；
- 删除 terminal value；
- 跳过 1 月；
- 用 M0 替换 M1；
- 直接给节点设 120 s 硬截止并接受未达 3% 的 incumbent；
- 重新定义 gap 分母；
- 只因为某策略“看起来差不多”就提交。

---

# 3. 关于“最终结果不变”的严格解释

本轮要求保持：

- **数学可行域不变；**
- **数学目标函数不变；**
- **真实执行语义不变；**
- **3% 证书标准不变；**
- **输出仍由原 `physics.replay()` 生成。**

必须明确：更换 MIP solver 或改变 branch-and-bound 搜索顺序后，在“3% gap 即停止”的条件下，最终被接受的 incumbent 可能不是逐元素完全相同的向量。

因此不得向用户声称“策略字节级必然完全一样”。正确目标是：

> **解的是完全同一个数学问题，并按完全相同的 3% 证书规则验收。**

如果新 solver 返回不同但合法的 3%-certified 策略，这是同模型的允许结果；必须记录 objective、lower bound、gap 和真实回放指标，不得隐瞒差异。

---

# 4. 总执行顺序

严格按以下优先级执行：

## Phase A：冻结现场 + 困难节点基准

先建立真实困难节点 shadow benchmark，**在新方案验证通过之前不得停止当前健康主计算**。

## Phase B：同一矩阵接入 Gurobi

这是第一优先级。只替换 MIP backend，不改变 `build_matrix()` 生成的数学问题。

## Phase C：Exact reformulation v2

继续删除已经被证明固定/冗余的变量和约束，并做安全 bound tightening。

## Phase D：真实困难节点 A/B 验收

只看真正困难的 06:00 节点，不用容易节点制造“提速很多”的假象。

## Phase E：通过后迁移正式主链

必须创建新的冻结运行副本；不得在旧活动目录中就地混写不同 solver/formulation 的 checkpoint。

---

# 5. Phase A：先构造可重复的困难节点测试集

## 5.1 不要重新造假数据

优先复用当前已有 `src/q3/solver_probe.py` 的 capture 机制，从真实已运行节点重建完全相同的输入。

至少冻结 3 个困难 06:00 节点。

优先顺序：

1. `2025-01-16 06:00`
2. `2025-01-22 06:00`
3. 当前活动运行中最新的困难 `06:00` 节点（例如 Jan23，如该节点输入已经完整形成）
4. Jan14 06:00 可作为已知历史对照

每个 benchmark 必须冻结：

- `scenes.load`
- `scenes.pv`
- `scenes.weights`
- `scenes.net`
- `prices`
- `initial_soc`
- `reference g0`
- `today`
- `terminal`
- 原始 seed policy
- request signature
- matrix digest

## 5.2 新增 matrix digest

对 `build_matrix()` 输出建立稳定 SHA256：

- objective
- bounds.lb / bounds.ub
- integer mask
- sparse matrix CSC 的 `indptr / indices / data`
- constraint lb / ub

生成：

`outputs/q3/raw/solver_accel_<timestamp>/matrix_manifest.json`

目的：证明不同 solver 真正解的是**同一个矩阵**。

---

# 6. Phase B：接入 Gurobi，但必须解完全同一个矩阵

## 6.1 先检查，不要假定机器已有许可

执行：

1. 检查 `import gurobipy`；
2. 记录版本；
3. 创建极小模型并 `optimize()`，确认 license 真正可用；
4. 如果只有 size-limited license，当前大 MILP 无法使用，则立即记录并跳过，不要浪费比赛时间研究许可证；
5. 若 academic/commercial license 可用，继续。

不要为了装 Gurobi 停止当前主计算。

---

## 6.2 新增独立 backend，不要先大重构整个项目

建议新增：

`src/q3/gurobi_backend.py`

核心入口类似：

```python
def solve_gurobi_matrix(
    objective,
    bounds,
    integer,
    constraints,
    *,
    seed_vector,
    gap,
    seconds,
    threads,
    assess,
    known_lower=None,
    progress=None,
):
    ...
```

第一版只负责：

> **把现有 `fast_solver.build_matrix()` 生成的完全相同矩阵交给 Gurobi。**

禁止第一版同时改数学矩阵，否则无法知道加速来自 solver 还是 reformulation。

---

## 6.3 Gurobi 模型映射规则

从 SciPy sparse matrix 原样构造变量与约束。

变量：

- `integer[i] == 1` -> binary；
- 其余 -> continuous；
- lower/upper bound 必须逐值来自现有 `Bounds`；
- objective coefficient 必须逐值来自现有 objective。

约束按当前 `LinearConstraint` 拆成：

- `lb == ub`：等式；
- 仅有限 `lb`：`A x >= lb`；
- 仅有限 `ub`：`A x <= ub`；
- 两边有限且不同：同时加入上下界。

不要重新手写第三问公式。

原因：

> solver backend 必须只是同一矩阵的另一种求解方式。

---

## 6.4 必须保留现有 warm start

当前 `seed_vector()` 已经把原反馈可行策略映射到 MILP 向量。

Gurobi 必须把同一个 seed 作为 MIP start。

提交前仍需先运行：

`matrix_error(seed, bounds, integer, constraints)`

必须满足原有容差。

禁止把未经 `matrix_error` 验证的向量直接塞入 solver。

---

## 6.5 Gurobi 参数：先少调参，再做 A/B

基础组：

- `MIPGap = 0.03`
- `TimeLimit = benchmark budget`
- `FeasibilityTol = 1e-8`
- `IntFeasTol = 1e-8`
- `OutputFlag = 0`（正式运行；基准可保留 log）

线程：

由于正式主链本身强顺序依赖，**单节点内部多线程现在是有价值的**。

测试：

- 1 thread
- 4 threads
- `min(8, 可用物理核心数)` threads

机器若同时还有其他正式重任务，不得过度订阅 CPU。

### 只额外测试一个重点参数组

当前主要问题是 lower bound 证明，而不是没有 incumbent，因此额外测试：

- Gurobi default
- `MIPFocus = 3`

不要在比赛期间无穷枚举几十种参数。

禁止一开始就乱改 Cuts/Heuristics/Presolve 等大量参数。

如果 default 或 `MIPFocus=3` 已明显胜出，立即停止无意义调参。

---

## 6.6 Gurobi callback 必须复用原证书逻辑

callback 负责：

1. 获得当前 best incumbent；
2. 获得当前 global bound；
3. 把 incumbent 向量交给**现有原始 `assess()` 逻辑**；
4. `assess()` 必须再次：
   - 重建 `Policy`；
   - 对全部 scenario 调用原 `physics.replay()`；
   - 计算原始真实 objective；
   - 验证 matrix feasibility；
   - 验证 integrality；
   - 验证 monotone projection；
   - 验证 solver lower bound 没有超过原反馈目标。
5. 只有当：

```text
original_replay_objective - valid_global_lower_bound
<= 0.03 * abs(original_replay_objective)
```

才允许标记 `reliable=True` 并停止求解。

### callback 频率

当前 HiGHS 路径约每 10 s 做一次完整 replay/checkpoint。

新版本改成：

- MIP solution 真改善时更新缓存；
- 完整 `assess + fsync checkpoint` 最多每 30 s 一次；
- 到达 120 s 整数倍时强制 durable snapshot；
- 达到 3% 时立即保存最终证书。

这样减少 Python callback 对 solver 的干扰。

---

# 7. Gurobi shadow benchmark 的硬性验收标准

对每个困难节点同时跑：

1. 当前 production HiGHS fast formulation；
2. Gurobi default；
3. Gurobi `MIPFocus=3`；
4. 每个 Gurobi 配置再测试合理线程数。

优先时间预算：

- 60 s
- 若未达 3%，继续至 120 s
- 最多用一个代表节点继续至 300 s

每次必须记录：

- solver
- solver version
- threads
- formulation version
- matrix digest
- wall seconds
- solver seconds
- incumbent original replay objective
- optimizer raw objective
- global lower bound
- certified gap
- reliable
- node count
- simplex/barrier iteration（若可得）
- matrix feasibility error
- integrality error
- monotone projection error
- policy SHA256

输出：

`outputs/q3/raw/solver_accel_<timestamp>/backend_benchmark.csv`

和：

`backend_benchmark.json`

---

## 7.1 允许迁移到正式 Gurobi 的条件

满足全部：

1. 小规模 gap=0 测试和原精确模型最优值一致；
2. 所有真实困难节点都通过原 `physics.replay()`；
3. matrix digest 与 HiGHS 基线完全一致；
4. 没有任何 future leakage / model parameter change；
5. 至少 2/3 困难节点在同预算下 gap 明显优于当前 HiGHS；
6. 最好至少 2/3 节点达到 `<=3%` 的时间显著缩短；
7. 未发现某个困难节点出现灾难性倒退。

如果 Gurobi 在 3 个节点上明显领先，不需要继续做大规模 solver 参数研究，直接进入生产迁移。

---

# 8. Phase C：Exact reformulation v2

这是第二条主线。

原则：

> **只删掉数学上已经被证明为常数、固定零、可代换或严格冗余的变量/约束。**

任何“看起来应该没事”的简化一律禁止。

---

# 9. Exact reformulation v2.1：物理删除固定的 `charge_cap`

当前 free aggregate fast model 中已经有：

```python
lo[cp] = CAP
```

即自由优化时 `cp` 实际已经固定为 `CAP`。

下一步不是“再固定一次”，而是：

> **在 free aggregate 专用 builder 中完全删除 `cp` 变量。**

所有 `c <= cp[t]` 直接改写为：

```text
c <= CAP
```

最终构建 `Policy` 时：

```python
charge_cap = np.full(T, CAP)
```

fixed-policy 路径不得使用这一简化；fixed policy 仍保留原来的 `cp`。

验收：

- free 模式变量数减少 T；
- 原 replay 目标不变；
- gap=0 小实例最优值与旧 fast formulation 一致。

---

# 10. Exact reformulation v2.2：删除 free 模式下固定为 0 的 `lc` 变量

当前 `build_base()` 先创建 3 组 charge selector：

```text
lc[0], lc[1], lc[2]
```

但 free charge 模式下随后：

```python
hi[lc] = 0
integer[lc] = 0
```

这些列在数学上已经固定为 0。

新 free builder 中：

> **不要创建这 3*S*T 个变量。**

同时删除只服务于 `lc` 的约束。

这不会改变可行域，因为旧 formulation 里它们本来就固定为 0。

在 `S=20, T=144` 时，可直接删掉：

```text
3 * 20 * 144 = 8640
```

个固定连续变量。

这项应优先实现，风险低。

---

# 11. Exact reformulation v2.3：消去 `z`

当前 free 模式存在：

```text
z = lr0 + lr1 + lr2
0 <= z <= 1
```

且 `lr0/lr1/lr2` 为 binary。

因此 `z` 可以被精确代换为：

```text
z := lr0 + lr1 + lr2
```

新 formulation：

1. 删除全部 `z[j,t]` 连续变量；
2. 删除 `sum(lr)-z=0` 等式；
3. 新增：

```text
lr0 + lr1 + lr2 <= 1
```

4. 所有原来出现 `z` 的地方，代换为 `lr0+lr1+lr2`。

例如原：

```text
c + CAP*z <= CAP
r - CAP*z <= 0
```

替换为：

```text
c + CAP*(lr0+lr1+lr2) <= CAP
r - CAP*(lr0+lr1+lr2) <= 0
```

必须逐条符号检查，不允许靠手感改。

在 `S=20,T=144` 下再删除：

```text
20 * 144 = 2880
```

个连续变量，并删除同量级等式。

---

# 12. v2.1～v2.3 的预期模型瘦身

当前 free fast builder 仍按：

```text
3*T + 12*S*T
```

创建列。

其中 `cp`、`z`、3 组 `lc` 在 free 模式可直接消除。

当 `S=20,T=144`：

- 删除 `cp`：144 列；
- 删除 `z`：2880 列；
- 删除 `lc`：8640 列；

合计至少删除：

```text
11664 个连续变量
```

注意：

> 这一步主要减少模型尺寸和 presolve 负担；核心 discharge selector binary 数量暂时不变。

不要为了“二元变量看起来少”贸然采用更弱的编码。

---

# 13. Exact reformulation v2.4：安全 reachable-bound tightening

当前很多变量仍使用全局范围：

```text
E_MIN <= SOC <= E_MAX
0 <= c,r <= CAP
```

对每个 scenario `s`、时槽 `t`，利用：

- 当前初始 SOC；
- 前一槽可达 SOC 上下界；
- 当前净负荷 `n[s,t]`；
- 当前 `g_upper[t]`；
- 最大充放电量 CAP；

递推安全的：

```text
E_lower[s,t]
E_upper[s,t]
```

并据此收紧：

```text
SOC[s,t]
r[s,t]
c[s,t]
```

的上下界。

### 必须满足

这是**可达性包络**，必须包含所有原策略的真实反馈轨迹。

不能根据某一个 incumbent 的 SOC 去缩界。

不能根据未来真实附件 2 数据缩界。

只能使用当前场景矩阵已经包含的信息。

---

## 13.1 推荐递推思路

对给定 scenario 净负荷 `n_t`，令上一时刻安全区间为：

```text
[L_{t-1}, U_{t-1}]
```

最深放电方向可以由：

```text
min(CAP, max(n_t, 0))
```

和 SOC 可用量共同限制；最大充电方向可以由：

```text
min(CAP, max(g_upper_t - n_t, 0))
```

限制。

得到新的安全 SOC 包络后，直接写入变量 bounds，而不是额外加很松的 Big-M。

完成后必须用随机大量原 `physics.replay()` 轨迹检查：

> 所有原轨迹都落在新 bounds 内。

---

# 14. 暂时不要把 3 个 discharge selector 强行改成 2 bit

当前 discharge 是：

```text
min(discharge_cap, deficit, available_energy)
```

理论上 3 个最小值分支可以研究 logarithmic / 2-bit encoding。

但当前瓶颈是：

> **global lower bound 太弱，而不是 binary count 单独太大。**

二进制数减少不代表更快；如果 LP relaxation 变弱，可能反而更慢。

因此本轮顺序必须是：

1. 先做 Gurobi；
2. 先删除固定连续变量；
3. 先做 safe bound tightening；
4. 再考虑 2-bit encoding。

若测试 2-bit，必须同时报告：

- root relaxation lower bound；
- 60 s lower bound；
- 60 s gap；
- binary count；
- node count。

若 binary 少了但 lower bound 更差，立即放弃。

---

# 15. 当前已有 `discharge_hull()`：不要直接提升为生产版本

`src/q3/fast_solver.py` 已有 `discharge_hull()`，`solver_probe.py` 也支持 hull probe。

已有真实 Jan22 隔离测试没有显示 hull 在 60 s 下明显改善 lower bound。

因此：

- 保留它作为研究候选；
- 不要因为名字叫“hull”就默认更快；
- 只有在 Gurobi 或 reformulation v2 下新的困难节点实测显著改善，才允许采用。

比赛时间有限，不把它列为第一优先级。

---

# 16. 不要重复优化已经解决的问题

以下方向当前不是首要瓶颈：

- k-medoids；
- terminal cache；
- CSV/Excel 写出；
- FD 标定；
- 普通 00/12/18 节点；
- 增加外层 workers。

主链存在 SOC 顺序依赖：

```text
previous executed block -> current SOC -> next node
```

因此把 `workers=4` 改成 `workers=8` 不会让同一条主轨迹变成 8 倍快。

真正值得并行的是：

> 单个困难 MILP 内部的求解器线程。

---

# 17. 必须新增的测试

至少新增以下测试文件或等价测试：

## 17.1 `test_gurobi_backend.py`

覆盖：

1. same-matrix digest；
2. gap=0 小实例与原精确 solver 最优 objective 一致；
3. positive terminal；
4. asymmetric adjustment；
5. E_MIN / mid SOC / E_MAX 三类初态；
6. fixed policy 不走自由简化；
7. seed 可行；
8. 原 replay certificate。

若机器无 Gurobi license，测试必须明确 skip，而不是失败或偷偷回退。

## 17.2 reformulation v2 测试

必须比较：

```text
old fast formulation
vs
new exact formulation v2
```

至少在几十组随机小实例上用 `gap=0` 比较最优值。

容差建议：

```text
abs(obj_old - obj_new) <= 1e-5
```

同时随机生成大量合法 Policy，用原 `physics.replay()` 验证新 bounds 不排除任何真实轨迹。

---

# 18. 困难节点验收不能只看 solver 自己的 ObjVal

每个候选解都必须做：

```text
solver vector
    -> Policy
    -> physics.replay(all scenarios)
    -> original objective
    -> valid global lower bound
    -> certified gap
```

最终报告的 objective 必须是：

> 原 `physics.replay()` 真实反馈语义下的目标。

不是 solver 内部 relaxation trajectory 的 objective。

---

# 19. 正式迁移规则

新 solver/reformulation 验收通过前：

> **不要杀当前健康主进程。**

验收通过后：

1. 冻结当前活动 run；
2. 创建新的 run directory，例如：

```text
outputs/q3/raw/full_priority_gurobi_v2_<timestamp>/
```

3. 新目录记录：
   - solver backend；
   - solver version；
   - threads；
   - formulation version；
   - source SHA；
   - matrix builder SHA；
   - 3% gap；
   - S=20/tail=2 等冻结配置；
4. 已完成日期不得重算后覆盖旧结果；
5. 逐日复核：
   - request signature；
   - policy SHA；
   - executed block；
   - day-end SOC；
   - cost；
6. 只有完全一致的已提交前缀允许迁移；
7. 当前未完成节点从最后可靠 checkpoint 之后重新求解；
8. 保留旧目录，禁止删除。

不要把不同 solver 生成的未完成节点内部搜索状态假装成可恢复搜索树。

可恢复内容只有：

- 已验收 incumbent policy；
- valid lower bound（仅当数学问题完全相同且有清晰来源）；
- executed blocks；
- day receipts；
- SOC；
- terminal cache；
- input/signature。

---

# 20. Gurobi 与 HiGHS 下界共享规则

不同 solver 之间可以共享一个 lower bound 的前提非常严格：

1. matrix digest 完全相同；
2. lower bound 是该完整 MILP 的**有效全局下界**；
3. 不是固定 `g` 子问题的下界；
4. 不是某个 relaxation 被错误当成原问题的下界；
5. 数值容差和目标常数处理一致；
6. 审计文件明确记录来源。

不满足任意一项，则不得跨 solver 复用 lower bound。

宁可不共享，也不能用错误下界制造假的 3% 证书。

---

# 21. 生产 solver 选择策略

最终生产推荐做成显式 backend：

```text
auto
highs
gurobi
```

但本轮不要根据每个节点的结果动态“挑一个看起来最好”的 solver，从而形成难以审计的隐藏选择逻辑。

推荐：

1. shadow benchmark 完成后冻结一个正式 backend；
2. 若 Gurobi 明显胜出，全年后续统一 Gurobi；
3. 若 Gurobi license 不稳定或无显著优势，继续统一 HiGHS + reformulation v2。

如果必须 fallback，只允许在：

- solver 无法启动；
- license 错误；
- 明确异常退出；

时回退，并把 fallback 写进 audit。

不能“Gurobi 60 s 没快就切 HiGHS，再把两个搜索结果偷偷拼一起”而不记录。

---

# 22. 当前最值得尝试的 Gurobi A/B 组合

为了节约时间，只做下列组合：

| 组 | Solver | Threads | MIPFocus | 目的 |
|---|---|---:|---:|---|
| A | 当前 HiGHS | 1 | - | baseline |
| B | Gurobi | 1 | 0 | 比较 solver 本体 |
| C | Gurobi | 4 | 0 | 看单节点多线程收益 |
| D | Gurobi | 4 | 3 | 针对 lower-bound bottleneck |
| E | Gurobi | min(8,物理核) | 3 | 若 D 已有明显收益再测 |

不要一开始测试几十组参数。

---

# 23. 提速是否成功的核心指标

不要只报“跑了多少秒”。

每个困难节点至少画/输出：

```text
time -> incumbent UB
time -> valid LB
time -> certified gap
```

我们真正关心：

> **LB 上升速度。**

如果新方法只是更快找到同一个 incumbent，但 LB 仍不动，它不能解决当前主问题。

---

# 24. 明确的 Go / No-Go 规则

## Go：立即迁移正式计算

当满足：

- 3 个困难节点都语义验证通过；
- 2/3 以上节点的 3% certificate 时间显著下降；
- 无节点出现明显灾难性回退；
- 所有单元测试、集成测试通过；
- checkpoint/restart 验证通过；

则不需要再问用户，直接按本指令建立新冻结运行并恢复主链。

## No-Go：保留当前生产版本

若：

- Gurobi 无可用 license；或
- 同预算 lower bound 没明显改善；或
- reformulation 不能严格证明等价；或
- 任一原 replay 验证失败；

则不迁移。

必须保留失败实验及原因，不能为了“看起来做了优化”强行上线。

---

# 25. 比赛时限下的立即执行顺序

现在不要先花数小时做漂亮重构。

按下面顺序：

### Step 1：15 分钟内完成 solver 可用性检查

- Gurobi 是否安装；
- license 是否可用；
- 能否加载当前 Jan22 困难矩阵。

### Step 2：直接用**完全同一个 build_matrix**做 Jan22 60 s A/B

先比较：

```text
HiGHS-1
Gurobi-4 default
Gurobi-4 MIPFocus=3
```

若 Gurobi 60 s 下 LB/GAP 已明显领先，继续 Jan16 + 当前困难节点。

### Step 3：若 Gurobi 真实显著胜出，先接入生产

不要等 reformulation v2 全部写完才恢复全年。

先用 same-matrix Gurobi 继续主线，因为风险最低、收益最直接。

### Step 4：production 继续跑时，再在 shadow 分支做 reformulation v2

优先：

1. 删除 `lc`；
2. 删除 `cp`；
3. 消去 `z`；
4. reachable bounds。

### Step 5：v2 再通过困难节点后，才进行第二次迁移

如果 Gurobi 已经足够快，不要为了追求理论最漂亮模型中断稳定主计算。

---

# 26. 不允许做的“伪加速”

以下任何一种都不得算作本轮成功：

1. 只把 `MIPGap` 从 3% 改大；
2. 只缩短 TimeLimit；
3. 未达 3% 直接接受 incumbent；
4. 用更少 scenario；
5. 只拿容易节点做 benchmark；
6. 只报 UB 不报 LB；
7. 只看 solver raw objective，不做原 replay；
8. 用固定策略子问题下界冒充全局下界；
9. 修改目标常数后用新的相对 gap 偷偷提前停止；
10. 通过未来真实数据缩变量界；
11. 把不同 formulation 的 checkpoint 混入同一 run；
12. 关闭 checkpoint 来换一点速度而让崩溃后重新算数小时；
13. 删除 validation/FIV/OUV 数学代码并声称模型没变。

---

# 27. Checkpoint 优化

当前完整 replay/checkpoint 过于频繁时会干扰 solver。

允许做以下**不改变模型**的优化：

- solver 内部持续搜索；
- MIP solution 改善时只更新内存 candidate；
- 每 30 s 最多做一次完整原 replay + durable save；
- 每 120 s 强制落一个 archival slice；
- 达 3% 立即最终保存；
- 进程退出前最终 fsync。

必须继续保留：

- crash 后的可行 incumbent；
- valid bound 来源；
- day/node receipts；
- executed block；
- SOC。

---

# 28. 最终需要产生的文件

本次 Codex 任务完成后至少产出：

```text
docs/3/solver_acceleration/
├── task_plan.md
├── report.md
├── equivalence_proof.md
├── benchmark.csv
├── benchmark.json
├── acceptance.json
└── tests.txt
```

源码建议：

```text
src/q3/
├── gurobi_backend.py          # 若 Gurobi 可用
├── fast_solver.py             # 保留 public API，必要时 dispatch
├── solver_probe.py            # 扩展 benchmark
└── test_gurobi_backend.py     # 新增
```

如果实现 formulation v2，建议明确单独命名：

```text
build_matrix_v2_free()
```

在验证完成前不要直接删除旧 `build_matrix()`。

旧 formulation 必须可以通过测试开关继续调用，用于回归比较。

---

# 29. `report.md` 必须回答的 10 个问题

1. Gurobi 是否真的可用？版本与 license 状态？
2. Gurobi 与 HiGHS 是否使用完全相同 matrix digest？
3. 三个困难 06:00 节点分别用了多久？
4. 60/120 s 时 UB、LB、gap 分别是多少？
5. 哪个 backend/参数组合实际最好？
6. reformulation v2 删除了多少变量/约束/二元变量？
7. root relaxation / 60 s LB 是否更强？
8. gap=0 小实例是否与原精确模型最优值一致？
9. 原 `physics.replay()` 是否全部通过？
10. 是否已经安全迁移正式主链？迁移后的真实运行目录、PID、当前日期/节点是什么？

---

# 30. 开发规范要求的最终审查

完成代码后必须执行项目规范要求的三轮审查。

## 30.1 语句 to 语句审查

逐条核对本文件“模型不变量”和“验收规则”。

## 30.2 挖洞式审查

至少检查：

- lower bound 是否真的对原问题有效；
- MIP start 是否可能不可行；
- Gurobi 与 HiGHS gap 定义是否一致；
- 目标为负或接近 0 时 certificate 是否按现有原逻辑处理；
- callback 是否读取了未完成 solution；
- checkpoint 是否可能把 relaxation state 当真实 policy；
- free formulation 是否错误影响 fixed/lag/M2；
- z 消元符号是否写反；
- reachable bounds 是否误删合法原反馈轨迹；
- solver 多线程是否导致整个机器过度订阅；
- 迁移是否覆盖旧正式结果；
- 不同 solver/formulation 是否错误共享无效 lower bound。

按 P0/P1/P2/P3 输出发现。

## 30.3 假设与决断审查

本轮不允许增加新的建模假设。

任何 solver 参数只是计算实现选择，不得在论文里冒充新的数学假设。

---

# 31. 论文同步要求

如果最终正式采用 Gurobi 或新的 exact reformulation，需要在第三问论文实现描述中补一小段即可：

> 为降低有限场景 MILP 的计算规模，本文在不改变可行域、目标函数和真实反馈映射的前提下，利用支配关系、固定变量消元及可达状态界进行精确等价重构，并使用成熟 MIP 求解器求解。所有候选策略均重新代入原始饱和反馈模型进行场景回放，仅当原反馈目标值相对于有效全局下界满足预设最优性间隙时接受。

不要在论文中写具体开发过程、Codex、bug 修复史或“从 HiGHS 换成 Gurobi”的叙事。

论文只描述最终采用的计算实现。

---

# 32. 最终 Codex 汇报格式

完成后只需要向用户清晰汇报：

## A. 是否加速成功

- 原困难节点耗时；
- 新困难节点耗时；
- 加速倍数；
- 3% 是否严格通过。

## B. 有没有改模型

逐项明确：

- S=20：未改；
- tail=2：未改；
- 24h：未改；
- 144 slots：未改；
- 成本：未改；
- terminal：未改；
- 真实 replay：未改；
- 3%：未改。

## C. 正式任务状态

- 新 run 目录；
- 已迁移多少天；
- 当前日期/节点；
- 当前 gap；
- worker 是否正常。

## D. 风险

只汇报真实存在的剩余长尾风险，不作“全年一定多少分钟完成”的虚假承诺。

---

# 33. 本轮最高优先级结论

本轮不要继续围绕“如何找更好的 incumbent”做大量工作。

核心问题是：

```text
好解通常已经很早找到
        ↓
全局下界提升太慢
        ↓
3% certificate 卡住
```

因此最优先路线是：

```text
同一 build_matrix
    ↓
Gurobi / 更强 MIP backend
    ↓
多线程 + bound-oriented search
    ↓
原 physics.replay 重新验收
    ↓
3% certificate
```

随后才是：

```text
exact reformulation v2
    ↓
删固定 cp
删固定 lc
消去 z
收紧 reachable bounds
    ↓
再次用困难节点验证 LB 提升速度
```

**只要 same-matrix Gurobi 已经在真实困难节点上取得显著收益，就先安全迁移生产主链，不要为了追求更漂亮的重构继续让全年主计算停着。**

