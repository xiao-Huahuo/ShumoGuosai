# Q1 基于规范化能流、等价化简与精确 LP 松弛的周期型微网经济调度模型

## 1. 问题分析与总体思路

本题研究含光伏与储能系统的小区微网日内经济调度问题。目标是在满足负荷需求、储能容量、充放电功率及日内周期约束的前提下，利用富余光伏与分时电价制定 0:00 时刻的全天计划购电与储能调度方案，使全天外网购电费用最小。

若直接按照物理能流建模，通常需要分别刻画“外网供负荷、外网充电、光伏供负荷、光伏充电、储能放电、弃光”等能流，并通过 0-1 变量限制储能同一时段不能同时充、放电，从而形成混合整数线性规划（MILP）。但本题具有特殊的经济结构：外网购电价格非负、无向外网售电收益、储能充放电存在能量损耗，且电网电用于供负荷和用于充电采用相同电价。

基于这些条件，本文首先从原始物理能流模型出发，证明存在一个与其词典序最优值等价的 canonical flow representation：先用光伏就地抵消负荷，再将储能经济作用分解为“富余光伏时移”和“外网峰谷套利”。随后进一步证明，在该 canonical 模型中，即使删除充放电互斥的二元变量，LP 新增的同时充放电可行点也不可能成为词典序最优解。因此可以建立

$$
\boxed{
\operatorname{LexOpt}(\text{Physical MILP})
=
\operatorname{LexOpt}(\text{Canonical MILP})
=
\operatorname{LexOpt}(\text{Canonical LP})
}
$$

其中“等价”指词典序最优目标值与可实现的最优调度经济效果等价，而不是三个模型的完整可行域完全相同。

因此，本文的核心建模主线不是叠加更多算法，而是：

$$
\boxed{
\text{原始物理能流}
\rightarrow
\text{规范化等价化简}
\rightarrow
\text{Exact LP Relaxation}
\rightarrow
\text{词典序最优购电策略}
}
$$

在获得主调度结果后，再利用 LP 的连续结构进行解释性扩展：机制层分析富余光伏时移与外网峰谷套利的收益及 interaction；状态层分析 SOC 边际价值；动作层分析最优面中的动作必需性及动作排除反事实。这些分析用于增强结果解释，不作为独立算法创新。

# 2. 建模假设

为保证后续结构定理成立，作如下假设。

1. 一天划分为 144 个长度为 10 min 的调度时段，负荷、光伏、电价以及储能充放电控制指令在每个时段内均按分段常值处理。
2. 外网购电价格满足

$$
p_t\ge 0,\qquad t=1,\ldots,144.
$$

3. 不考虑向外网反向售电，也不存在负电价、售电补贴或强制充放电机制。
4. 电网购电用于直接供负荷或用于储能充电时采用相同购电价格。
5. 储能充电效率不依赖电能来源。
6. 光伏允许弃光。
7. 储能放电仅用于满足当前负荷，不允许储能反向向外网送电。
8. 题目给出的最大充放电功率 5000 kW 在主模型中解释为储能系统与交流微网母线之间的外部输入/输出功率上限，因此 10 min 内最大母线侧充、放电量均为 $5000\times \frac16$ kWh。若将该额定功率解释为电池内部功率，则需结合效率重新换算边界；本文在结果解释中说明这一口径。
9. 题目中的“充放电效率 90%”主模型解释为充、放电单程效率均为 90%，并另以“90% 为往返效率”的解释进行稳健性检验。

若实际题面存在负电价、售电收益或其他改变上述经济结构的机制，则本文关于规范化等价化简与精确 LP 松弛的结构结论需要重新检验。

# 3. 时间离散与能量换算

设一天的时间集合为

$$
\mathcal T=\{1,2,\ldots,144\},
\qquad
\Delta t=\frac16\ \mathrm h.
$$

附件给出的负荷和光伏均为功率。定义第 $t$ 个时段对应的负荷电量与光伏电量为

$$
l_t=L_t\Delta t,
$$

$$
s_t=P_t^{pv}\Delta t,
$$

其单位均为 kWh。

储能最大充放电功率为 5000 kW，因此每个 10 min 时段的最大母线侧充放电量为

$$
\boxed{
\bar q
=
5000\times\frac16
=
833.3333\ \mathrm{kWh}.
}
$$

由于负荷、光伏以及储能控制指令均在单个时段内按恒定功率执行，储能能量 $E(\tau)$ 在每个 10 min 区间内部为时间的仿射函数。

---

# 4. 从原始物理能流到规范化能流

## 4.1 原始物理能流表示

为避免直接将“光伏优先满足负荷”作为经验性规则，先考虑更一般的物理能流。对时段 $t$，记

$$
g_t^L\ge0
$$

为外网直接供负荷的电量，

$$
g_t^B\ge0
$$

为外网向储能充电的母线侧电量，

$$
v_t^L\ge0
$$

为光伏直接供负荷的电量，

$$
v_t^B\ge0
$$

为光伏向储能充电的母线侧电量，

$$
z_t\ge0
$$

为储能向负荷放电的母线侧电量，

$$
u_t\ge0
$$

为弃光量。

则原始物理能流至少满足

$$
\boxed{
g_t^L+v_t^L+z_t=l_t
}
$$

以及

$$
\boxed{
v_t^L+v_t^B+u_t=s_t.
}
$$

储能母线侧充电量为

$$
c_t=g_t^B+v_t^B,
$$

状态转移为

$$
E_t
=
E_{t-1}
+
\eta_c(g_t^B+v_t^B)
-
\frac{z_t}{\eta_d}.
$$

外网购电量为

$$
q_t^g=g_t^L+g_t^B.
$$

若显式要求储能同一时段不能同时充、放电，则还需引入二元变量形成原始物理 MILP。

---

## 4.2 规范化等价化简

定义光伏就地满足负荷后形成的净负荷：

$$
\boxed{
d_t=(l_t-s_t)^+,
}
$$

以及富余光伏：

$$
\boxed{
r_t=(s_t-l_t)^+.
}
$$

其中

$$
(x)^+=\max(x,0).
$$

这里的“光伏优先满足当前负荷”不是额外施加的经验性调度规则，而是一种不损失词典序最优性的规范化经济记账方式。

首先，若某个可行方案中同时存在

$$
v_t^B>0,\qquad g_t^L>0,
$$

取

$$
\delta=\min(v_t^B,g_t^L)>0,
$$

并作能流交换

$$
v_t^{B\prime}=v_t^B-\delta,\qquad
v_t^{L\prime}=v_t^L+\delta,
$$

$$
g_t^{L\prime}=g_t^L-\delta,\qquad
g_t^{B\prime}=g_t^B+\delta.
$$

交换后：

- 负荷平衡不变；
- 光伏利用量不变；
- 储能总输入 $g_t^B+v_t^B$ 不变；
- SOC 轨迹不变；
- 外网总购电量 $g_t^L+g_t^B$ 不变；
- 一级购电费用与二级储能吞吐量均不变。

其次，若存在

$$
u_t>0,\qquad g_t^L>0,
$$

则可用等量原本被弃掉的光伏替代外网直接供负荷，使外网购电量不增加；当 $p_t>0$ 时费用严格下降，当 $p_t=0$ 时费用不变。因此至少存在一个一级最优解满足“有可用光伏时不同时弃光并从外网直接供给同一时段负荷”。

反复实施上述交换，可得到一个与原物理模型词典序最优值相同的规范化最优解，其中光伏先抵消当期负荷，其余部分才进入储能或被弃光。

---

## 4.3 定理 1：原始物理模型与 Canonical MILP 的词典序最优等价性

在第 2 节假设成立时，原始物理 MILP 至少存在一个词典序最优解，可以改写为以下 canonical representation：

$$
q_t^{gL}=d_t-z_t,
$$

$$
0\le z_t\le d_t,
$$

$$
0\le y_t\le r_t,
$$

其中

- $x_t$ 表示外网向储能充电；
- $y_t$ 表示富余光伏向储能充电；
- $z_t$ 表示储能向净负荷放电。

其外网购电量为

$$
q_t^g=d_t-z_t+x_t.
$$

因此有

$$
\boxed{
\operatorname{LexOpt}(\text{Physical MILP})
=
\operatorname{LexOpt}(\text{Canonical MILP}).
}
$$

### 证明思路

一方面，任一 canonical 可行解都可以映射回原始物理能流，因此 canonical 模型不会产生无法物理实现的最优经济结果。

另一方面，对任一原始物理词典序最优解，通过第 4.2 节的等价能流交换，可以在不增加一级费用、也不增加二级吞吐量的条件下得到 canonical 表示。因此原始物理模型至少存在一个 canonical 形式的词典序最优解。

故两者具有相同的词典序最优目标值。需要强调的是，这一结论并不意味着两个模型的完整可行域相同，而只说明对本题所关心的最优调度问题，canonical 化不会损失最优性。

---

## 4.4 两类储能经济服务

基于规范化表示，本文将储能经济作用划分为两类服务：

$$
\boxed{\text{富余光伏时移（Surplus-PV Shifting）}}
$$

与

$$
\boxed{\text{外网峰谷套利（Grid Price Arbitrage）}}.
$$

这里的分类是规范化经济记账下的服务定义，并不代表对电池内部真实电子来源进行物理追踪。

# 5. 决策变量

定义：

$$
x_t\ge0
$$

为时段 $t$ 外网向储能系统输入的母线侧电量；

$$
y_t\ge0
$$

为时段 $t$ 富余光伏向储能系统输入的母线侧电量；

$$
z_t\ge0
$$

为时段 $t$ 储能系统向负荷侧实际输出的母线侧电量；

$$
E_t
$$

为时段 $t$ 结束时电池内部储存的能量。

因此，外网直接满足当前净负荷的电量为

$$
q_t^{gL}=d_t-z_t,
$$

弃光量为

$$
q_t^{curt}=r_t-y_t.
$$

---

# 6. Canonical 周期型微网经济调度 LP

## 6.1 充电功率约束

$$
\boxed{
x_t+y_t\le \bar q.
}
\tag{1}
$$

## 6.2 放电功率约束

$$
\boxed{
z_t\le \bar q.
}
\tag{2}
$$

同时，储能放电不能超过当前净负荷：

$$
\boxed{
z_t\le d_t.
}
\tag{3}
$$

## 6.3 富余光伏约束

$$
\boxed{
y_t\le r_t.
}
\tag{4}
$$

## 6.4 储能状态转移

设充电效率和放电效率分别为

$$
\eta_c,\qquad \eta_d,
$$

主模型取

$$
\eta_c=\eta_d=0.9.
$$

则有

$$
\boxed{
E_t
=
E_{t-1}
+
\eta_c(x_t+y_t)
-
\frac{z_t}{\eta_d}.
}
\tag{5}
$$

## 6.5 储能容量约束

$$
\boxed{
1200\le E_t\le10800.
}
\tag{6}
$$

## 6.6 周期边界条件

根据题目给出的初始储电量，并满足 0:00 与 24:00 储能量相同的要求，设置

$$
\boxed{
E_0=E_{144}=6000\ \mathrm{kWh}.
}
\tag{7}
$$

## 6.7 非负约束

$$
\boxed{
x_t\ge0,\qquad y_t\ge0,\qquad z_t\ge0.
}
\tag{8}
$$

---

# 7. 一级目标：最小化全天购电费用

第 $t$ 个时段的外网总购电量为

$$
q_t^g
=
d_t-z_t+x_t.
$$

因此全天购电费用为

$$
J
=
\sum_{t=1}^{144}
p_t(d_t-z_t+x_t).
$$

一级优化目标为

$$
\boxed{
J^\star
=
\min
\sum_{t=1}^{144}
p_t(d_t-z_t+x_t).
}
\tag{9}
$$

其中 $p_t$ 单位为元/kWh，因此 $J$ 的单位为元。

由于

$$
\sum_t p_td_t
$$

为常数，因此储能调度实质上通过：

1. 低价时段从电网充电；
2. 富余光伏时段利用免费光伏充电；
3. 高价净负荷时段放电；

实现跨时电量配置，从而降低全天外网购电费用。

---

# 8. Exact LP Relaxation：充放电互斥的最优性结构

第 4 节已经证明，原始物理 MILP 与 Canonical MILP 在词典序最优意义下等价。下面只需继续证明：Canonical MILP 中用于限制“同一时段不能同时充、放电”的二元变量在词典序最优解上是冗余的。

换言之，本节研究的是

$$
\text{Canonical MILP}
\longrightarrow
\text{Canonical LP}
$$

这一步的精确松弛。

## 定理 2：Canonical LP 词典序最优解的自然充放电互斥性

在以下条件同时成立时：

$$
p_t\ge0,
$$

$$
0<\eta_c,\eta_d<1,
$$

不存在向外网售电收益，

$$
z_t\le d_t,
$$

$$
y_t\le r_t,
$$

电网购电价格与具体用途无关，

充电效率与能源来源无关，

且采用后文定义的词典序目标

$$
\min J\succ\min T,
$$

则删除充放电互斥二元变量后的 Canonical LP，其任一词典序最优解均满足

$$
\boxed{
(x_t+y_t)z_t=0,\qquad \forall t.
}
\tag{10}
$$

即任一词典序最优解均不存在同时充、放电现象。

### 证明

首先，若

$$
y_t>0,
$$

则由

$$
y_t\le r_t
$$

可知

$$
r_t>0.
$$

根据

$$
r_t=(s_t-l_t)^+,
$$

有

$$
s_t>l_t,
$$

从而

$$
d_t=(l_t-s_t)^+=0.
$$

再由

$$
z_t\le d_t
$$

可得

$$
z_t=0.
$$

因此

$$
y_tz_t=0.
$$

下面考虑 $x_t$ 与 $z_t$。

反设某个时段满足

$$
x_t>0,\qquad z_t>0.
$$

取足够小的

$$
0<\varepsilon
\le
\min\left(
x_t,
\frac{z_t}{\eta_c\eta_d}
\right),
$$

构造新解

$$
x_t'=x_t-\varepsilon,
$$

$$
z_t'=z_t-\eta_c\eta_d\varepsilon.
$$

则该时段 SOC 变化量的改变为

$$
\eta_c(-\varepsilon)
-
\frac{-\eta_c\eta_d\varepsilon}{\eta_d}
=0.
$$

因此储能状态轨迹完全不变，其余时段的所有约束均不受影响。

外网购电量变化为

$$
\begin{aligned}
\Delta q_t^g
&=
(x_t'-z_t')-(x_t-z_t)\\
&=
-(1-\eta_c\eta_d)\varepsilon\\
&<0.
\end{aligned}
$$

若

$$
p_t>0,
$$

则一级购电费用严格下降，与一级最优性矛盾。

若

$$
p_t=0,
$$

则一级购电费用保持不变，但储能吞吐量变化为

$$
\begin{aligned}
\Delta T
&=
-\eta_c\varepsilon
-\frac{\eta_c\eta_d\varepsilon}{\eta_d}\\
&=
-2\eta_c\varepsilon\\
&<0,
\end{aligned}
$$

因此二级目标严格改善，同样与词典序最优性矛盾。

故不存在

$$
x_t>0,\qquad z_t>0.
$$

结合 $y_tz_t=0$，得到

$$
(x_t+y_t)z_t=0.
$$

证毕。

---

## 8.1 “Exact”的严格含义

删除 Canonical MILP 的充放电互斥整数约束后，Canonical LP 的完整数学可行域确实更大，其中仍可能存在同时充放电的普通可行点。

因此，本文不声称 Canonical MILP 与 Canonical LP 的**完整可行域相同**。

本文所证明的是：

> 虽然 LP relaxation 扩大了可行域，但新增的同时充放电可行点不可能成为词典序最优解。因此 Canonical LP 与 Canonical MILP 具有相同的词典序最优目标值，并且 Canonical LP 的任一词典序最优解自然满足原互斥约束。

即：

$$
\boxed{
\operatorname{LexOpt}(\text{Canonical MILP})
=
\operatorname{LexOpt}(\text{Canonical LP}).
}
$$

结合定理 1，进一步得到

$$
\boxed{
\operatorname{LexOpt}(\text{Physical MILP})
=
\operatorname{LexOpt}(\text{Canonical MILP})
=
\operatorname{LexOpt}(\text{Canonical LP}).
}
$$

因此本文最终求解 LP 即可获得满足原物理模型互斥要求的词典序最优调度。

---

## 8.2 该结构结论的边界

上述 exactness 依赖于非负电价、无售电收益、有损储能、用途同价以及词典序最小吞吐等条件。若后续问题引入负电价、外网售电收益、补贴、强制充放电或其他改变套利结构的机制，则不能直接沿用本定理，而需重新检查松弛是否仍然精确。

# 9. 二级目标：最小储能内部吞吐量

一级购电成本最优解可能不唯一。为排除成本相同但包含无意义能量循环的调度方案，在一级目标最优的基础上进一步最小化电池内部实际吞吐量。

定义

$$
\boxed{
T
=
\sum_{t=1}^{144}
\left[
\eta_c(x_t+y_t)
+
\frac{z_t}{\eta_d}
\right].
}
\tag{11}
$$

理论上的第二阶段优化问题为

$$
\boxed{
T^\star
=
\min T
}
\tag{12}
$$

subject to

$$
\boxed{
J=J^\star
}
\tag{13}
$$

以及全部原 LP 约束。

因此理论模型采用严格词典序：

$$
\boxed{
\min J\succ\min T.
}
$$

需要强调，$T$ 仅用于成本等价最优解之间的 tie-breaking，不代表真实电池寿命退化费用，也不是题目新增的经济目标。

### 数值实现

在计算机求解时，由于浮点数和求解器容差的存在，可采用

$$
J\le J^\star+\varepsilon_{\mathrm{num}}
$$

代替严格等式，其中 $\varepsilon_{\mathrm{num}}$ 仅是计算实现参数，而不是理论模型参数。

---

# 10. 周期能量一致性

由

$$
E_{144}=E_0
$$

以及 SOC 动态式，有

$$
\sum_{t=1}^{144}
\eta_c(x_t+y_t)
=
\sum_{t=1}^{144}
\frac{z_t}{\eta_d}.
$$

即

$$
\boxed{
\sum_t\eta_c(x_t+y_t)
=
\sum_t\frac{z_t}{\eta_d}.
}
\tag{14}
$$

从而

$$
T^\star
=
2\sum_t\eta_c(x_t+y_t)
=
2\sum_t\frac{z_t}{\eta_d}.
$$

式 (14) 可作为数值求解的重要一致性检查。

---

# 11. 零电价时段的规范化记账退化

若某时段同时满足

$$
p_t=0,
\qquad
r_t>0,
$$

且储能需要充入固定总量

$$
x_t+y_t=c_t,
$$

则一级目标中

$$
p_tx_t=0,
$$

而二级目标仅与 $x_t+y_t$ 有关。

因此，不同的 $(x_t,y_t)$ 分解可能具有完全相同的 $J^\star$ 和 $T^\star$。

这说明零电价情况下，完整模型中的“电网充电/光伏充电”来源分解可能存在等价最优退化。

该退化：

- 不影响全天最优购电成本；
- 不影响储能总吞吐量；
- 不影响四个 coalition 的最优成本；
- 但可能影响某个具体最优解中 $x_t$ 与 $y_t$ 的来源分配。

因此，本文将两类服务定义为**规范化且可复现的经济服务定义**，而不声称其对应物理电子来源的唯一追踪。

如果实际数据不存在零电价，则无需进一步处理。

若存在零电价且必须输出唯一 source-resolved schedule，可在保持

$$
J=J^\star,
\qquad
T=T^\star
$$

的基础上增加第三级纯记账规则：

$$
\boxed{
\max\sum_t y_t.
}
\tag{15}
$$

其作用仅是 canonicalization：在所有经济效果和电池循环均完全相同的解中优先记为富余光伏充电，而不赋予额外经济意义。

---

# 12. 时段内部 SOC 合法性

由于负荷、光伏以及储能充放电控制功率均在每个 10 min 时段内保持恒定，因此单个时段内部 SOC 满足常斜率变化。

根据命题 1，词典序最优解在任一时段内不会同时充放电，因此 $E(\tau)$ 在单个调度区间内只可能：

- 单调增加；
- 单调减少；
- 保持不变。

因此，只要

$$
E_{t-1},E_t\in[E_{\min},E_{\max}],
$$

则整个区间内部必有

$$
E(\tau)\in[E_{\min},E_{\max}].
$$

故离散节点容量约束即可保证时段内部 SOC 不越界。

---

# 13. 机制层：两类储能经济服务的价值归因

## 13.1 四种反事实情景

定义四种机制组合下的**一级最优购电成本**。

### 情景 0：储能关闭

$$
C_{\varnothing}.
$$

令

$$
x_t=y_t=z_t=0.
$$

### 情景 PV：仅允许富余光伏时移

$$
C_{PV}.
$$

约束

$$
x_t=0.
$$

### 情景 G：仅允许外网峰谷套利

$$
C_G.
$$

约束

$$
y_t=0.
$$

### 情景 PV,G：两种服务均允许

$$
C_{PV,G}.
$$

由可行域包含关系，理论上应满足

$$
\boxed{
C_{PV,G}\le C_{PV}\le C_{\varnothing},
}
\tag{16}
$$

以及

$$
\boxed{
C_{PV,G}\le C_G\le C_{\varnothing}.
}
\tag{17}
$$

---

## 13.2 顺序对称边际贡献

若仅比较

$$
C_{\varnothing}-C_{PV}
$$

与

$$
C_{\varnothing}-C_G,
$$

则得到的是两类服务分别“先进入系统”时的独立收益。

但由于两种服务共享同一储能容量和充放电功率资源，其边际收益具有进入顺序依赖。

因此定义顺序对称边际贡献：

$$
\boxed{
\phi_{PV}
=
\frac12
\left[
(C_{\varnothing}-C_{PV})
+
(C_G-C_{PV,G})
\right].
}
\tag{18}
$$

$$
\boxed{
\phi_G
=
\frac12
\left[
(C_{\varnothing}-C_G)
+
(C_{PV}-C_{PV,G})
\right].
}
\tag{19}
$$

其数学形式等价于二参与者 Shapley value。

使用该方法的原因并不是 Shapley 本身具有算法创新性，而是它对

$$
PV\rightarrow G
$$

与

$$
G\rightarrow PV
$$

两种进入顺序取平均，从而消除人为选择进入顺序产生的归因偏差。

同时满足

$$
\boxed{
\phi_{PV}+\phi_G
=
C_{\varnothing}-C_{PV,G}.
}
\tag{20}
$$

---

# 14. 两类储能服务的 Interaction

定义单服务收益：

$$
B_{PV}=C_{\varnothing}-C_{PV},
$$

$$
B_G=C_{\varnothing}-C_G,
$$

联合收益：

$$
B_{PV,G}=C_{\varnothing}-C_{PV,G}.
$$

进一步定义

$$
\boxed{
I_{PV,G}
=
B_{PV,G}-B_{PV}-B_G.
}
\tag{21}
$$

等价地，

$$
\boxed{
I_{PV,G}
=
C_{PV}+C_G-C_{\varnothing}-C_{PV,G}.
}
\tag{22}
$$

若

$$
I_{PV,G}>0,
$$

则说明两类服务联合运行表现出超加性，即存在经济协同。

若

$$
I_{PV,G}<0,
$$

则首先只能说明两类服务之间存在收益替代或收益重叠，不能仅凭该符号直接断言原因是储能容量或功率竞争。

---

## 14.1 资源竞争的约束放松反事实

若希望进一步判断负 interaction 是否由储能共享资源竞争引起，仅观察 binding constraint 仍不足以构成严格因果证据。

因此在基准模型之外设置约束放松反事实。

### 容量放松

适当增大

$$
E_{\max}
$$

后重新计算四个 coalition，并得到

$$
I_{PV,G}^{(E_{\max}\uparrow)}.
$$

### 功率放松

适当增大

$$
\bar q
$$

后重新计算

$$
I_{PV,G}^{(\bar q\uparrow)}.
$$

如果原模型中

$$
I_{PV,G}<0,
$$

而随着容量或功率约束放松，

$$
I_{PV,G}
$$

明显向 0 移动，则说明共享容量或功率瓶颈是两类服务收益替代的重要机制。

该反事实只用于解释 interaction 的来源，不改变主模型的题目参数。

---

# 15. 状态层：参数化 LP 的 SOC 边际价值

为刻画某时刻储能库存本身的经济价值，定义从时刻 $t$ 开始的续接价值函数：

$$
\boxed{
\mathcal V_t(e)
=
\min
\sum_{\tau=t}^{144}
p_\tau(d_\tau-z_\tau+x_\tau)
}
\tag{23}
$$

subject to 后续所有 LP 约束，并设置

$$
E_{t-1}=e,
$$

$$
E_{144}=6000.
$$

由于这是以 RHS 参数 $e$ 为参数的线性规划，其最优价值函数

$$
\mathcal V_t(e)
$$

为分段线性凸函数。

当 $e$ 位于某个线性区间内部时，定义 SOC 条件边际价值：

$$
\boxed{
V_t^{SOC}
=
-\mathcal V_t'(e).
}
\tag{24}
$$

单位为元/kWh。

其经济含义为：

> 在允许未来调度重新优化的条件下，时刻 $t$ 开始时额外拥有 1 kWh 电池内部能量，能够降低多少未来最优购电成本。

由于 $\mathcal V_t(e)$ 为凸函数，其斜率随 $e$ 单调不减，因此

$$
-\mathcal V_t'(e)
$$

随储能库存增加呈非增加趋势，即额外库存的边际经济价值具有递减结构。

---

# 16. SOC 折点与单侧有限差分验证

参数化 LP 的价值函数在折点处不可导，因此不能统一使用中心有限差分并要求其与求解器 dual 精确一致。

对给定状态 $e$，定义左侧有限差分价值：

$$
\boxed{
V_{t,-}^{FD}
=
-
\frac{
\mathcal V_t(e)-\mathcal V_t(e-\delta)
}{\delta}.
}
\tag{25}
$$

定义右侧有限差分价值：

$$
\boxed{
V_{t,+}^{FD}
=
-
\frac{
\mathcal V_t(e+\delta)-\mathcal V_t(e)
}{\delta}.
}
\tag{26}
$$

并取多个扰动尺度，例如

$$
\delta\in\{1,5,10\}\ \mathrm{kWh}.
$$

若 $e$ 位于光滑线性区间，则应有

$$
V_{t,-}^{FD}
\approx
V_{t,+}^{FD}.
$$

此时 solver dual 与该共同斜率应基本一致。

若 $e$ 位于折点，则通常有

$$
V_{t,-}^{FD}
\ne
V_{t,+}^{FD}.
$$

此时求解器返回的 dual multiplier 可能对应 subgradient 集合中的某个值，因此不要求其与中心差分相等，而检查其是否与左右边际价值所确定的 subgradient 区间相容。

同时，由于不同求解器对等式约束 dual multiplier 的符号约定可能不同，应首先通过有限差分结果校准 dual 的符号，再进行经济解释。

---

# 17. 动作层：词典序最优面的动作结构分析

一级成本最优且二级吞吐量最优后，调度解仍可能不唯一。因此不能仅根据求解器返回的某一个最优解判断某时段动作是否是最优系统必需的。

设

$$
J^\star
$$

和

$$
T^\star
$$

分别为一级和二级最优值。

在词典序最优面

$$
\mathcal F^\star
=
\left\{
(x,y,z,E):
J=J^\star,\ 
T=T^\star,\ 
\text{所有物理约束成立}
\right\}
$$

上进一步分析每个时段动作的最小、最大可能规模。

---

## 17.1 充电动作最优面区间

定义母线侧总充电量

$$
c_t=x_t+y_t.
$$

分别求解

$$
\boxed{
c_t^{\min}
=
\min_{\mathcal F^\star}(x_t+y_t)
}
\tag{27}
$$

和

$$
\boxed{
c_t^{\max}
=
\max_{\mathcal F^\star}(x_t+y_t).
}
\tag{28}
$$

若

$$
c_t^{\min}>0,
$$

则说明该时段充电行为在**所有词典序最优方案中均必须存在**，称其为结构必需充电动作。

若

$$
c_t^{\min}=0,
\qquad
c_t^{\max}>0,
$$

则说明该时段充电只出现在部分最优方案中，属于可替代动作。

若

$$
c_t^{\max}=0,
$$

则说明任何词典序最优方案均不会在该时段充电。

---

## 17.2 放电动作最优面区间

类似地，定义

$$
\boxed{
z_t^{\min}
=
\min_{\mathcal F^\star}z_t
}
\tag{29}
$$

和

$$
\boxed{
z_t^{\max}
=
\max_{\mathcal F^\star}z_t.
}
\tag{30}
$$

若

$$
z_t^{\min}>0,
$$

则该时段放电属于所有词典序最优方案共同具备的**结构必需放电动作**。

因此，相比仅观察单个 solver solution，$(a_t^{\min},a_t^{\max})$ 能够区分：

$$
\boxed{
\text{某个最优解中出现的动作}
}
$$

与

$$
\boxed{
\text{所有最优解中都必须出现的动作}.
}
$$

---

# 18. Lexicographic Active-Action Exclusion：动作不可替代性的两级反事实

最优面动作区间回答“某动作是否出现在所有词典序最优方案中”，但不能量化禁止该动作后的损失。为此，对候选关键动作进行两级动作排除反事实。

设待排除动作统一记为 $a_t$：对充电动作有 $a_t=x_t+y_t$，对放电动作有 $a_t=z_t$。

---

## 18.1 一级：购电成本排除损失

对充电动作，强制

$$
x_t+y_t=0;
$$

对放电动作，强制

$$
z_t=0.
$$

在保留其余全部物理约束的条件下重新最小化一级购电成本，记为

$$
J_{t,-act}^{\star}.
$$

定义

$$
\boxed{
\Delta J_t^{act}
=
J_{t,-act}^{\star}-J^\star
\ge0.
}
\tag{31}
$$

其含义为：

> 如果禁止时段 $t$ 的该类动作，并允许其他全部时段自由重新调度，系统最低购电费用至少增加多少。

若

$$
\Delta J_t^{act}>0,
$$

则该动作对实现最低购电费用本身就是不可替代的，称为**一级经济必需动作**。

若

$$
\Delta J_t^{act}=0,
$$

则说明仍存在不使用该动作、但一级购电成本保持 $J^\star$ 的替代调度。此时不能立即认定该动作“不重要”，还需继续比较二级吞吐量。

---

## 18.2 二级：成本等价条件下的吞吐量排除损失

仅当

$$
\Delta J_t^{act}=0
$$

时，在“动作被禁止”以及

$$
J=J^\star
$$

的约束下继续最小化储能吞吐量，得到

$$
T_{t,-act}^{\star}.
$$

定义

$$
\boxed{
\Delta T_t^{act}
=
T_{t,-act}^{\star}-T^\star
\ge0.
}
\tag{32}
$$

其含义为：

> 在最低购电费用仍可保持不变的前提下，禁止该动作至少会额外增加多少储能内部吞吐量。

因此，

$$
\boxed{
(\Delta J_t^{act},\Delta T_t^{act})
}
$$

构成一个与原词典序目标完全一致的两级动作不可替代性指标。

若

$$
\Delta J_t^{act}=0,\qquad
\Delta T_t^{act}>0,
$$

说明该动作并非“最低购电费用”所必需，但却是实现“最低购电费用 + 最小吞吐量”这一完整词典序最优目标所必需的。

若

$$
\Delta J_t^{act}=0,\qquad
\Delta T_t^{act}=0,
$$

则说明至少存在一个不执行该动作、但仍达到 $(J^\star,T^\star)$ 的词典序最优方案，因此该动作不是词典序结构必需动作。

---

## 18.3 与最优面动作区间的一致性

若最优面分析得到

$$
a_t^{\min}>0,
$$

理论上不可能同时出现

$$
\Delta J_t^{act}=0,\qquad
\Delta T_t^{act}=0,
$$

因为后者意味着存在一个动作取 0 且仍达到 $(J^\star,T^\star)$ 的可行解，与 $a_t^{\min}>0$ 矛盾。

因此该关系还可作为模型实现与求解容差的交叉校验。

# 19. 动作结构与反事实结果的联合解释

词典序最优面分析与 Lexicographic AAE 回答的是互补问题。

### 最优面动作区间

$$
a_t^{\min},\ a_t^{\max}
$$

回答：

> 该时段动作是否在所有词典序最优方案中都必须存在？

### 两级动作排除反事实

$$
(\Delta J_t^{act},\Delta T_t^{act})
$$

回答：

> 如果彻底禁止这一时段的动作，首先最低购电费用是否上升；若费用仍可保持最优，达到相同最低费用至少要付出多少额外储能吞吐量？

由此可形成严格一致的分类：

| 类型 | 最优面条件 | 一级排除损失 | 二级排除损失 | 解释 |
|---|---|---:|---:|---|
| 一级经济必需动作 | $a_t^{\min}>0$ | $\Delta J_t^{act}>0$ | 无需计算 | 禁止后最低购电费用上升 |
| 词典序必需但成本可替代 | $a_t^{\min}>0$ | $\Delta J_t^{act}=0$ | $\Delta T_t^{act}>0$ | 仍可保持最低费用，但必须付出更高吞吐量 |
| 词典序可替代动作 | $a_t^{\min}=0<a_t^{\max}$ | $\Delta J_t^{act}=0$ | $\Delta T_t^{act}=0$ | 某些最优方案采用，但至少存在一个完整词典序最优方案不采用 |
| 非最优动作 | $a_t^{\max}=0$ | 不计算 | 不计算 | 任何词典序最优方案均不执行 |

特别地，

$$
a_t^{\min}>0,\quad
\Delta J_t^{act}=0,\quad
\Delta T_t^{act}=0
$$

在精确数学模型中不应出现；若数值计算出现这一组合，应优先检查求解器 tolerance、$J^\star/T^\star$ 固定方式与动作阈值设置。

该分析避免把 solver 任意返回的一个最优解误当成唯一调度结构，也避免将“一级成本可替代”错误解释为“完整词典序目标下也可替代”。

# 20. 主模型之外的解释性扩展

本题的核心建模贡献已经在“规范化等价化简 + Exact LP Relaxation”中完成。以下机制、状态与动作分析均建立在主 LP 的最优结果之上，用于解释“为什么这样调度”，而不将成熟分析工具本身包装成新的优化算法。

## 20.1 机制层：储能收益来源

使用

$$
\phi_{PV},\qquad
\phi_G,\qquad
I_{PV,G}
$$

回答：

> 富余光伏时移和外网峰谷套利分别解释多少总体经济收益，两者之间是协同、替代还是收益重叠？

其中 Shapley 形式仅作为顺序对称的收益归因工具；若 interaction 接近 0，则不对其作过度解释。只有当 interaction 明显偏离 0 时，才进一步通过容量或功率约束放松反事实分析其来源。

## 20.2 状态层：SOC 边际价值

使用

$$
V_t^{SOC}
$$

回答：

> 在允许未来调度重新优化的条件下，某时刻额外 1 kWh 电池内部库存可以降低多少后续最优购电成本？

该分析用于解释关键 SOC 区间和时段；若实际数据中边际价值曲线缺乏明显结构，则可作为附录而不占用正文主要篇幅。

## 20.3 动作层：最优结构与不可替代性

使用

$$
a_t^{\min},\qquad
a_t^{\max},\qquad
\Delta J_t^{act},\qquad
\Delta T_t^{act}
$$

回答：

> 哪些 10 min 充放电动作是所有词典序最优调度共同具备的；禁止某动作后，系统究竟损失一级购电经济性，还是仅损失二级最小吞吐结构？

三者分别对应

$$
\boxed{
\begin{array}{ccc}
\text{机制} & \text{状态} & \text{动作}\\
\downarrow & \downarrow & \downarrow\\
\text{收益来源} &
\text{库存边际价值} &
\text{结构必需性/两级系统依赖度}
\end{array}
}
$$

论文正文应优先报告能显著解释实际调度结果的分析；若某一扩展没有产生非平凡现象，则不将其强行作为主要亮点。

# 21. 模型可信性验证

为避免仅依赖求解器输出结果，建立如下数值验证体系。

## 21.1 SOC 动态残差

$$
\boxed{
\max_t
\left|
E_t-E_{t-1}
-\eta_c(x_t+y_t)
+\frac{z_t}{\eta_d}
\right|
\approx0.
}
\tag{33}
$$

## 21.2 周期边界残差

$$
\boxed{
|E_{144}-6000|
\approx0.
}
\tag{34}
$$

## 21.3 周期能量一致性

$$
\boxed{
\left|
\sum_t\eta_c(x_t+y_t)
-
\sum_t\frac{z_t}{\eta_d}
\right|
\approx0.
}
\tag{35}
$$

## 21.4 Coalition 单调性

$$
\boxed{
C_{PV,G}\le C_{PV}\le C_{\varnothing},
}
\tag{36}
$$

$$
\boxed{
C_{PV,G}\le C_G\le C_{\varnothing}.
}
\tag{37}
$$

## 21.5 两级动作排除一致性

理论上应满足

$$
\boxed{
\Delta J_t^{act}\ge0.
}
\tag{38}
$$

若

$$
\Delta J_t^{act}=0,
$$

则进一步应满足

$$
\boxed{
\Delta T_t^{act}\ge0.
}
\tag{39}
$$

并且若

$$
a_t^{\min}>0,
$$

则理论上至少有

$$
\Delta J_t^{act}>0
$$

或

$$
\Delta T_t^{act}>0.
$$

若计算结果显著违反上述关系，应优先检查求解器 tolerance、动作零阈值、$J^\star$ 与 $T^\star$ 的固定方式以及基准最优值保存精度。

## 21.6 LP 最优性验证

检查：

$$
\text{primal feasibility},
$$

$$
\text{dual feasibility},
$$

以及

$$
\text{primal-dual gap}\approx0.
$$

同时数值验证词典序最优解满足

$$
(x_t+y_t)z_t\approx0,\qquad \forall t,
$$

以与定理 2 的理论结论相互校验。

## 21.7 SOC 边际价值验证

在光滑区间检查：

$$
V_{t,-}^{FD}
\approx
V_{t,+}^{FD}
\approx
V_{t,\mathrm{dual}}^{SOC}.
$$

在折点处则检查 solver dual 是否与左右边际值对应的 subgradient 区间相容，而不要求与中心差分精确相等。

# 22. 效率解释的稳健性检验

题目中的“充放电效率 90%”可能存在两种解释。

主模型解释为充、放电单程效率均为 90%：

$$
(\eta_c,\eta_d)=(0.9,0.9).
$$

此时往返效率为

$$
\eta_{rt}=0.81.
$$

作为稳健性检验，再考虑“90% 表示整体往返效率”的解释：

$$
(\eta_c,\eta_d)
=
(\sqrt{0.9},\sqrt{0.9}).
$$

比较两种效率解释下的：

- 最低购电成本；
- SOC 轨迹；
- 富余光伏时移收益；
- 外网峰谷套利收益；
- interaction；

以判断模型结论是否依赖效率定义。

---

# 23. 核心创新与解释性亮点

## 23.1 核心创新：从物理 MILP 到 Canonical LP 的结构化精确化简

本文的主要创新不是使用更多优化算法，而是识别本题特殊经济结构，并建立完整的两步等价链：

$$
\boxed{
\text{Physical MILP}
\overset{\text{canonicalization}}{\Longrightarrow}
\text{Canonical MILP}
\overset{\text{exact relaxation}}{\Longrightarrow}
\text{Canonical LP}.
}
$$

第一步通过能流交换证明：在无售电、用途同价、来源无关效率等条件下，至少存在一个词典序最优解可以写成“光伏先抵消当期负荷”的 canonical representation，因此不会因为规范化而损失最优性。

第二步利用非负购电价格、储能损耗及二级最小吞吐规则证明：Canonical LP 中新增的同时充放电可行点不可能成为词典序最优解，因此无需二元变量即可获得满足物理互斥要求的最优调度。

核心结论为

$$
\boxed{
\operatorname{LexOpt}(\text{Physical MILP})
=
\operatorname{LexOpt}(\text{Canonical MILP})
=
\operatorname{LexOpt}(\text{Canonical LP}).
}
$$

该结构发现同时提高了模型的求解简洁性、理论透明度与后续可解释性。

## 23.2 配套亮点：规范化的两类储能经济服务

在 canonical flow 下，将储能作用定义为：

$$
\boxed{\text{富余光伏时移}}
$$

与

$$
\boxed{\text{外网峰谷套利}}.
$$

该划分来自等价能流表示，而不是经验性地给电能贴标签，因此能够作为后续收益归因与 interaction 分析的可复现基础。

## 23.3 解释性扩展：利用 LP 连续结构回答“为什么这样调度”

在主模型求解完成后，进一步使用成熟工具进行解释：

- 机制层：四 coalition、顺序对称边际贡献与 interaction；
- 状态层：参数化 LP 的 SOC 边际价值及有限差分验证；
- 动作层：lexicographic-optimal face 上的动作区间，以及 $(\Delta J_t^{act},\Delta T_t^{act})$ 两级动作排除反事实。

这些方法的价值在于与主模型形成统一解释链，而不将 Shapley、dual、subgradient 或 optimal-face analysis 本身宣称为新的算法创新。

因此全文的创新主线收敛为：

$$
\boxed{
\text{题目结构识别}
\rightarrow
\text{规范化最优等价}
\rightarrow
\text{Exact LP Relaxation}
\rightarrow
\text{基于 LP 的结果解释}
}
$$

# 24. 最终求解流程

为避免将 Q1 写成多个高级工具的简单堆叠，最终计算流程分为“主模型求解”和“解释性扩展”两层。

## 24.1 主模型求解流程

$$
\boxed{
\begin{array}{c}
\textbf{Step 1：读取 144 个时段的电价、负荷与光伏预测功率}\\
\downarrow\\
\textbf{Step 2：将功率统一转换为 10 min 电量}\\
\downarrow\\
\textbf{Step 3：由原始物理能流构造 canonical flow}\\
\downarrow\\
\textbf{Step 4：求解 Canonical LP 的一级最低购电费用 }J^\star\\
\downarrow\\
\textbf{Step 5：固定 }J=J^\star\textbf{，求二级最小吞吐量 }T^\star\\
\downarrow\\
\textbf{Step 6：输出 10 min 购电策略、分时段充放电量与 SOC 轨迹}\\
\downarrow\\
\textbf{Step 7：完成物理残差、周期一致性及互斥性验证}
\end{array}
}
$$

其中 Step 3 的最优等价性由定理 1 保证，Step 4–5 删除二元互斥变量的合理性由定理 2 保证。

## 24.2 解释性扩展流程

在主调度结果已经得到后，根据实际数据是否呈现明显结构，有选择地进行：

1. **机制层**：计算四个 coalition 成本，得到 $\phi_{PV}$、$\phi_G$ 与 $I_{PV,G}$；仅当 interaction 明显时进一步做容量/功率约束放松反事实。
2. **状态层**：计算关键时刻的参数化 LP SOC value，并用左右有限差分校验 dual/subgradient。
3. **动作层**：对关键时段计算 $a_t^{\min},a_t^{\max}$，必要时执行两级动作排除，得到 $(\Delta J_t^{act},\Delta T_t^{act})$。

解释性扩展不改变题目的主优化目标，也不影响最终在线计划购电策略；其作用是说明主模型得到该调度结果的经济机制与结构原因。

# 25. 模型结论定位

本模型的核心不在于采用更多优化算法，而在于识别题目所具有的特殊经济结构，并将这一结构转化为可证明的模型化简。

首先，从一般物理能流出发，通过等价能流交换证明至少存在一个词典序最优解可以规范化为 canonical source-load-storage flow，从而在不损失最优性的前提下，将储能作用清晰分解为“富余光伏时移”和“外网峰谷套利”。

其次，在 canonical 模型中，利用非负电价、无售电收益、储能损耗以及二级最小吞吐规则，证明同时充放电点不可能成为词典序最优解，从而得到

$$
\boxed{
\operatorname{LexOpt}(\text{Physical MILP})
=
\operatorname{LexOpt}(\text{Canonical MILP})
=
\operatorname{LexOpt}(\text{Canonical LP}).
}
$$

因此，原本表面上需要整数变量处理充放电互斥的储能调度问题，可以在本题条件下精确化简为连续线性规划。

在主模型求解之后，再利用 coalition attribution、参数化 LP、最优面分析与两级动作排除反事实，对收益来源、SOC 边际价值和关键动作不可替代性进行解释。上述扩展服务于结果分析，而不改变本文“结构发现—等价化简—Exact LP Relaxation”的核心创新主线。
