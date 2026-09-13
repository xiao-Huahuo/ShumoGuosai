# Q1 基于规范化能流与精确 LP 松弛的周期型微网经济调度模型

## 1. 问题分析与总体思路

本题研究含光伏与储能系统的小区微网日内经济调度问题。目标是在满足负荷需求、储能容量、充放电功率及日内周期约束的前提下，合理利用富余光伏与分时电价，最小化全天外网购电费用。

传统储能经济调度常通过 0-1 变量显式限制储能在同一时段内不能同时充、放电，从而构成混合整数线性规划（MILP）。但本题具有特殊的经济结构：外网购电价格非负、无向外网售电收益、储能充放电存在能量损耗，并采用“购电成本优先、储能吞吐量次优”的词典序目标。基于这些条件，可以证明：虽然删除充放电互斥约束后 LP 可行域会扩大，但新增的“同时充放电”可行解不可能成为词典序最优解。因此，原 MILP 的 LP 松弛在词典序最优解意义下是 exact 的。

在此基础上，本文进一步构造规范化源–荷–储能流，将储能作用划分为“富余光伏时移”和“外网峰谷套利”两类经济服务，并利用 LP 的连续结构，从机制、状态和动作三个尺度解释储能经济价值。

整体分析链条为：

$$
\boxed{
\text{规范化能流}
\rightarrow
\text{最优性结构证明}
\rightarrow
\text{Exact LP Relaxation}
\rightarrow
\text{词典序经济调度}
\rightarrow
\text{机制价值归因}
\rightarrow
\text{SOC 边际价值}
\rightarrow
\text{动作结构必需性与反事实分析}
}
$$

---

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
6. 光伏允许弃光；光伏向储能充电仅来自当期富余光伏。
7. 储能放电仅用于满足当前净负荷，不允许储能反向向电网送电。
8. 题目给出的最大充放电功率 5000 kW 解释为储能系统与交流微网母线之间的外部输入/输出功率上限。

若实际题面存在负电价、售电收益或其他改变上述经济结构的机制，则本节关于精确 LP 松弛的结构结论需要重新检验。

---

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

# 4. 规范化源–荷–储能流

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

需要强调，这里的“光伏优先满足当前负荷”不是额外施加的经验性规则，而是一种不损失最优性的规范化经济记账方式。

假设某个可行方案中同时存在：

$$
PV\rightarrow Battery
$$

和

$$
Grid\rightarrow Load.
$$

在“无售电收益、电网电用途同价、充电效率与能源来源无关”的条件下，可以交换等量能流为：

$$
PV\rightarrow Load,
$$

$$
Grid\rightarrow Battery.
$$

交换后：

- 外网总购电量不变；
- 光伏总利用量不变；
- 储能输入量不变；
- SOC 轨迹不变；
- 总购电费用不变。

因此，至少存在一个最优解可以写成上述 canonical flow representation。

基于这一规范化表示，本文将储能经济作用划分为两类服务：

$$
\boxed{\text{富余光伏时移（Surplus-PV Shifting）}}
$$

与

$$
\boxed{\text{外网峰谷套利（Grid Price Arbitrage）}}.
$$

这里的分类是规范化经济记账下的服务定义，并不代表对电池内部真实电子来源进行物理追踪。

---

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

# 6. 周期型微网经济调度 LP

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

传统模型一般引入二元变量限制储能同一时段不能同时充、放电。本文不直接加入该整数约束，而证明 LP relaxation 在词典序最优解意义下是 exact 的。

## 命题 1：词典序最优解的自然充放电互斥性

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

则 LP relaxation 的任一词典序最优解均满足

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

删除充放电互斥整数约束后，LP 的数学可行域确实比原 MILP 更大，LP 中仍可能存在同时充放电的普通可行点。

因此，本文不声称两个模型的**完整可行域相同**。

本文所证明的是：

> 虽然 LP relaxation 扩大了可行域，但新增的同时充放电可行解不可能成为词典序最优解，因此 LP relaxation 与原互斥 MILP 具有相同的词典序最优目标值，并且 LP 的任一词典序最优解自然满足原模型的物理互斥要求。

即：

$$
\boxed{
\text{LP relaxation is exact in the lexicographic-optimum sense.}
}
$$

这一结构使问题无需整数变量即可获得满足储能互斥要求的最优调度。

---

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

# 18. Active-Action Exclusion：动作不可替代性的全局反事实

对于已经确认实际存在的储能动作，进一步使用动作排除反事实分析其对于全局最低购电成本的重要性。

## 18.1 充电动作排除

若某时段存在有效充电，则强制

$$
x_t+y_t=0
$$

并允许全天其余所有决策重新优化，得到新的一级最优成本

$$
J_{t,-ch}^{\star}.
$$

定义

$$
\boxed{
\Delta J_t^{ch}
=
J_{t,-ch}^{\star}
-
J^\star.
}
\tag{31}
$$

## 18.2 放电动作排除

若某时段存在有效放电，则强制

$$
z_t=0
$$

重新优化全天，得到

$$
J_{t,-dis}^{\star}.
$$

定义

$$
\boxed{
\Delta J_t^{dis}
=
J_{t,-dis}^{\star}
-
J^\star.
}
\tag{32}
$$

$\Delta J_t^{act}$ 的含义是：

> 如果禁止该时段执行原有储能动作，并允许其他全部时段自由重新调度，系统最低购电成本至少增加多少。

因此，该指标刻画的是 system dependence / indispensability，而不是局部电量的直接经济贡献。

若

$$
\Delta J_t^{act}=0,
$$

说明该时段动作并不是实现最低购电成本所不可替代的；系统存在其他调度方案可以在不增加一级成本的情况下替代该动作。

---

# 19. 动作结构与反事实结果的联合解释

词典序最优面分析与 AAE 分别回答不同问题。

### 最优面动作区间

$$
a_t^{\min},\ a_t^{\max}
$$

回答：

> 该时段动作是否在所有词典序最优方案中都必须存在？

### Active-Action Exclusion

$$
\Delta J_t^{act}
$$

回答：

> 如果彻底禁止这一时段实施该动作，最低购电成本会增加多少？

因此可以形成如下分类：

| 类型 | 最优面条件 | AAE 结果 | 解释 |
|---|---|---|---|
| 结构必需且经济关键 | $a_t^{\min}>0$ | $\Delta J_t^{act}>0$ | 所有最优方案都依赖该动作，禁止后成本上升 |
| 结构必需但成本退化 | $a_t^{\min}>0$ | $\Delta J_t^{act}=0$ | 理论上通常需进一步检查 tolerance 或模型定义 |
| 可替代动作 | $a_t^{\min}=0<a_t^{\max}$ | 常见 $\Delta J_t^{act}=0$ | 某些最优方案采用，但并非不可替代 |
| 非最优动作 | $a_t^{\max}=0$ | 不计算 | 任何词典序最优方案均不执行 |

该分析避免把 solver 任意返回的一个最优解误当成唯一调度结构。

---

# 20. 机制—状态—动作的多尺度经济解释

经过上述建模，可以将储能经济解释组织为三个互补尺度，但论文中不将三种成熟工具分别包装成独立算法创新，而以“结构发现 → exact LP relaxation → 利用 LP 连续结构完成解释”为主线。

## 20.1 机制层

使用

$$
\phi_{PV},\qquad
\phi_G,\qquad
I_{PV,G}
$$

回答：

> 富余光伏时移和外网峰谷套利分别解释多少总体经济收益，两者之间是协同还是替代？

## 20.2 状态层

使用

$$
V_t^{SOC}
$$

回答：

> 在某个时刻，电池中额外 1 kWh 库存对未来系统的边际经济价值是多少？

## 20.3 动作层

使用

$$
a_t^{\min},\qquad
a_t^{\max},\qquad
\Delta J_t^{act}
$$

回答：

> 哪些 10 min 充放电动作是所有最优调度都必须执行的，以及禁止某动作会给系统带来多大的全局成本损失？

三者分别对应

$$
\boxed{
\begin{array}{ccc}
\text{机制} & \text{状态} & \text{动作}\\
\downarrow & \downarrow & \downarrow\\
\text{收益归因} &
\text{库存边际价值} &
\text{结构必需性/系统依赖度}
\end{array}
}
$$

---

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

## 21.5 Action exclusion 单调性

理论上应满足

$$
\boxed{
\Delta J_t^{act}\ge0.
}
\tag{38}
$$

如果显著为负，则应优先检查模型实现、求解器 tolerance 或基准最优值保存方式。

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

---

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

# 23. 模型主要亮点

## 亮点 1：规范化能流下的储能服务辨识

本文不是直接经验性规定“光伏优先供负荷”，而是在无售电、用途同价及来源无关效率条件下，通过等价能流交换说明存在不损失最优性的 canonical flow representation，由此建立规范化且可复现的“富余光伏时移”和“外网峰谷套利”服务定义。

## 亮点 2：基于最优性结构的 Exact LP Relaxation

传统建模需要二元变量显式限制充放电互斥。本文结合非负购电价格、储能能量损耗、规范化能流约束及二级最小吞吐规则，证明 LP relaxation 中新增的同时充放电点不可能成为词典序最优解。

因此，无需使用整数变量即可获得满足原物理互斥要求的词典序最优调度。

该结论不是“两个模型完整可行域相同”，而是：

$$
\boxed{
\text{LP relaxation 在词典序最优解意义下 exact}.
}
$$

## 亮点 3：利用 LP 连续结构进行多尺度经济解释

在完成结构化简后，不再人为构造离散充放电模式，而利用 LP 的连续性质进行后续解释：

- 机制层：顺序对称边际贡献与 interaction；
- 状态层：参数化 LP 的 SOC 边际价值；
- 动作层：lexicographic-optimal face 上的动作区间与 AAE 反事实。

因此全文的创新主线为：

$$
\boxed{
\text{结构发现}
\rightarrow
\text{Exact LP Relaxation}
\rightarrow
\text{利用 LP 结构进行经济解释}
}
$$

而不是多个高级方法的简单堆叠。

---

# 24. 最终求解流程

最终 Q1 的计算流程如下：

$$
\boxed{
\begin{array}{c}
\textbf{Step 1：读取 144 个时段负荷、光伏与电价}\\
\downarrow\\
\textbf{Step 2：功率转换为 10 min 电量}\\
\downarrow\\
\textbf{Step 3：构造 canonical source-load-storage flow}\\
\downarrow\\
\textbf{Step 4：求解一级最低购电费用 }J^\star\\
\downarrow\\
\textbf{Step 5：固定 }J=J^\star\textbf{ 求二级最小吞吐 }T^\star\\
\downarrow\\
\textbf{Step 6：验证 LP relaxation 的互斥性质与数值残差}\\
\downarrow\\
\textbf{Step 7：求四个 coalition 成本}\\
\downarrow\\
\textbf{Step 8：计算 }\phi_{PV},\phi_G,I_{PV,G}\\
\downarrow\\
\textbf{Step 9：必要时做容量/功率约束放松反事实}\\
\downarrow\\
\textbf{Step 10：计算参数化 LP 的 SOC value}\\
\downarrow\\
\textbf{Step 11：用左右有限差分验证 dual/subgradient}\\
\downarrow\\
\textbf{Step 12：在 }J=J^\star,T=T^\star\textbf{ 上计算动作 min/max}\\
\downarrow\\
\textbf{Step 13：对关键动作执行 Active-Action Exclusion}\\
\downarrow\\
\textbf{Step 14：完成物理、经济与数值可信性检验}
\end{array}
}
$$

---

# 25. 模型结论定位

本模型的核心不在于采用更多优化算法，而在于识别本题的特殊经济结构。

原问题表面上需要通过二元变量处理储能充放电互斥，而在规范化能流、非负电价、无售电收益和有损储能条件下，可以证明 LP relaxation 在词典序最优意义下是 exact 的。

这一结构发现进一步使模型能够直接利用线性规划的对偶、参数敏感性与最优面结构，对储能的机制收益、库存边际价值以及关键动作不可替代性进行统一分析，从而同时提高模型的求解简洁性、理论严谨性与结果可解释性。
