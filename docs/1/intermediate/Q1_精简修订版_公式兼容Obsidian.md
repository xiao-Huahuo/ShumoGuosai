# Q1 基于规范化能流与精确 LP 松弛的周期型微网经济调度模型

## 1. 问题分析与建模约定

问题 1 要求在已知当日电价、小区负载和光伏预测功率的条件下，于 0:00 制定全天计划购电策略，使微网满足负荷需求并尽量降低购电费用，同时保证储能设备在 0:00 与 24:00 的储电量相同。

将一天划分为 144 个长度为 10 min 的调度时段，

$$
\mathcal T=\{1,\ldots,144\},\qquad 
\Delta t=\frac16\ \mathrm h .

$$

将附件给出的功率值视为对应 10 min 区间的代表功率，并采用零阶保持（zero-order hold）。定义

$$
l_t=L_t\Delta t,\qquad 
s_t=P_t^{pv}\Delta t ,

$$

其中 $l_t,s_t$ 分别为第 $t$ 个时段的负荷电量与光伏电量，单位为 kWh。

储能最大充放电功率为 $5000\,\mathrm{kW}$，若将其解释为交流母线侧功率上限，则单个时段最大充、放电量为

$$
\bar q=5000\times \frac16=833.3333\ \mathrm{kWh}.

$$

为使模型与题面保持一致，并保证后续结构结论成立，作如下约定：

1. 外网购电价格非负，即 $p_t\ge0$；
2. 题面未给出反向售电收益或强制消纳规则，因此不考虑向外网售电，无法被负荷或储能吸收的光伏允许弃电；
3. 电网电用于直接供负荷或用于储能充电时采用相同购电价格；
4. 储能充电效率与电能来源无关；
5. 储能放电仅用于满足当前负荷，不向外网反送电；
6. 主模型将“充放电效率 90%”解释为充、放电单程效率均为 0.9，即

$$
\eta_c=\eta_d=0.9 .

$$

   对“90% 为往返效率”的解释另作稳健性检验。

题面要求微网供电量“不低于”负荷。由于电价非负、无售电收益且允许弃光，任何无必要的超额供电均不会降低目标值，因此在最优解中可不失一般性地采用负荷严格平衡。

---

## 2. 原始物理能流模型

为说明后续化简不是经验性规定，先给出完整的物理能流模型。

对时段 $t$，定义：

$$
g_t^L\ge0

$$

为外网直接供负荷的电量；

$$
g_t^B\ge0

$$

为外网向储能充电的母线侧电量；

$$
v_t^L\ge0

$$

为光伏直接供负荷的电量；

$$
v_t^B\ge0

$$

为光伏向储能充电的母线侧电量；

$$
z_t\ge0

$$

为储能向负荷侧放电的母线侧电量；

$$
u_t\ge0

$$

为弃光量；

$$
E_t

$$

为第 $t$ 个时段结束时的储能内部电量。

负荷与光伏平衡分别为

$$
g_t^L+v_t^L+z_t=l_t,
\tag{1}

$$

$$
v_t^L+v_t^B+u_t=s_t.
\tag{2}

$$

储能状态转移为

$$
E_t
=
E_{t-1}
+\eta_c(g_t^B+v_t^B)
-\frac{z_t}{\eta_d}.
\tag{3}

$$

引入二元变量 $b_t\in\{0,1\}$ 表示充放电模式，则

$$
g_t^B+v_t^B\le \bar q\,b_t,
\tag{4}

$$

$$
z_t\le \bar q(1-b_t).
\tag{5}

$$

容量与周期约束为

$$
1200\le E_t\le10800,
\tag{6}

$$

$$
E_0=E_{144}=6000\ \mathrm{kWh}.
\tag{7}

$$

一级目标为最小化购电费用

$$
J
=
\sum_{t=1}^{144}
p_t(g_t^L+g_t^B).
\tag{8}

$$

当一级最优解不唯一时，在保持 $J=J^\star$ 的条件下最小化储能内部吞吐量

$$
T
=
\sum_{t=1}^{144}
\left[
\eta_c(g_t^B+v_t^B)
+\frac{z_t}{\eta_d}
\right].
\tag{9}

$$

因此理论目标采用严格词典序

$$
\min J\succ \min T.
\tag{10}

$$

其中 $T$ 仅用于成本等价最优解之间的 tie-breaking，不表示额外的电池退化费用。

---

## 3. 最优性保持的规范化能流

定义净负荷与富余光伏

$$
d_t=(l_t-s_t)^+,
\qquad
r_t=(s_t-l_t)^+,
\tag{11}

$$

其中 $(x)^+=\max(x,0)$。

### 命题 1：Canonicalization 的最优性保持

在上述假设下，原始物理 MILP 至少存在一个词典序最优解，可规范化为：

- 光伏优先就地抵消当期负荷；
- 仅富余光伏可进入储能；
- 储能仅对净负荷放电。

若某时段同时存在 $v_t^B>0$ 与 $g_t^L>0$，取

$$
\delta=\min(v_t^B,g_t^L)

$$

并将等量光伏由储能侧转至负荷侧、同时将等量电网电由负荷侧转至储能侧。该交换不改变负荷平衡、光伏利用量、储能总输入、SOC 轨迹及外网总购电量，因此 $J$ 与 $T$ 均不变。

若同时存在弃光与外网供负荷，即

$$
u_t>0,\qquad g_t^L>0,

$$

则可用等量弃光替代外网供电；当 $p_t>0$ 时 $J$ 严格下降，当 $p_t=0$ 时 $J$ 不变。

最后，若 $s_t\ge l_t$ 而仍有 $z_t>0$，该放电并不能降低当期购电量。由于 $E_{144}=E_0$，这部分释放的内部能量必须在日内由其他充电动作补回。对该“无净负荷放电—补偿充电”库存循环作等量循环消去，可保持终端 SOC 与能量平衡，同时使 $J$ 不增加而 $T$ 严格下降，与二级最优性矛盾。因此至少存在一个词典序最优解满足

$$
s_t\ge l_t\quad\Longrightarrow\quad z_t=0.
\tag{12}

$$

据此定义

$$
x_t\ge0

$$

为外网向储能充电量，

$$
y_t\ge0

$$

为富余光伏向储能充电量，

$$
z_t\ge0

$$

为储能向净负荷放电量。

于是

$$
q_t^{gL}=d_t-z_t,
\tag{13}

$$

$$
q_t^{curt}=r_t-y_t,
\tag{14}

$$

$$
q_t^g=d_t-z_t+x_t.
\tag{15}

$$

这里的等价仅指词典序最优目标值及可实现经济效果保持不变，并不表示两个模型的完整可行域相同。

---

## 4. Canonical MILP 与最终 LP

规范化后的约束为

$$
x_t+y_t\le \bar q\,b_t,
\tag{16}

$$

$$
z_t\le \bar q(1-b_t),
\tag{17}

$$

$$
0\le y_t\le r_t,
\tag{18}

$$

$$
0\le z_t\le d_t,
\tag{19}

$$

$$
E_t
=
E_{t-1}
+\eta_c(x_t+y_t)
-\frac{z_t}{\eta_d},
\tag{20}

$$

$$
1200\le E_t\le10800,
\tag{21}

$$

$$
E_0=E_{144}=6000.
\tag{22}

$$

一级目标为

$$
J
=
\sum_{t=1}^{144}
p_t(d_t-z_t+x_t).
\tag{23}

$$

---

## 5. Exact LP Relaxation

Canonical MILP 表面上仍需二元变量 $b_t$ 保证同一时段不能同时充放电，但在本题结构下该整数约束对最优解是冗余的。

### 定理 1：严格正电价下的自然互斥

若

$$
p_t>0,\qquad
0<\eta_c,\eta_d<1,

$$

则删除 $b_t$ 后得到的 LP 的任一一级成本最优解均满足

$$
(x_t+y_t)z_t=0,\qquad \forall t.
\tag{24}

$$

若 $y_t>0$，则 $r_t>0$，从而 $d_t=0$。由 $z_t\le d_t$ 得 $z_t=0$，故 $y_tz_t=0$。

再反设某时段 $x_t>0,z_t>0$。取足够小的

$$
0<\varepsilon
\le
\min
\left(
x_t,\frac{z_t}{\eta_c\eta_d}
\right),

$$

构造

$$
x_t'=x_t-\varepsilon,
\qquad
z_t'=z_t-\eta_c\eta_d\varepsilon.

$$

SOC 变化量保持不变：

$$
\eta_c(-\varepsilon)
-
\frac{-\eta_c\eta_d\varepsilon}{\eta_d}
=0.

$$

因此储能状态轨迹与容量约束不变，而外网购电量变化为

$$
\Delta q_t^g
=
-(1-\eta_c\eta_d)\varepsilon<0.

$$

当 $p_t>0$ 时购电费用严格下降，与最优性矛盾。因此 $x_tz_t=0$，结合 $y_tz_t=0$ 得式 (24)。

### 推论：非负电价下的词典序精确松弛

若允许 $p_t=0$，上述扰动在零电价时段可能不改变 $J$，但吞吐量变化为

$$
\Delta T
=
-2\eta_c\varepsilon<0.

$$

因此在

$$
\min J\succ\min T

$$

下仍不可能出现同时充放电。

记 Physical MILP、Canonical MILP 与 Canonical LP 的词典序最优目标值分别为

$$
(J_P^\star,T_P^\star),
\qquad
(J_C^\star,T_C^\star),
\qquad
(J_L^\star,T_L^\star),

$$

则有

$$
\boxed{
(J_P^\star,T_P^\star)
=
(J_C^\star,T_C^\star)
=
(J_L^\star,T_L^\star)
}.
\tag{25}

$$

因此最终只需求解连续线性规划

$$
\min J
=
\sum_{t=1}^{144}
p_t(d_t-z_t+x_t)
\tag{26}

$$

subject to

$$
x_t+y_t\le\bar q,
\tag{27}

$$

$$
0\le y_t\le r_t,
\tag{28}

$$

$$
0\le z_t\le \min(\bar q,d_t),
\tag{29}

$$

$$
E_t
=
E_{t-1}
+\eta_c(x_t+y_t)
-\frac{z_t}{\eta_d},
\tag{30}

$$

$$
1200\le E_t\le10800,
\tag{31}

$$

$$
E_0=E_{144}=6000.
\tag{32}

$$

一级求得 $J^\star$ 后，再固定 $J=J^\star$ 并最小化

$$
T
=
\sum_t
\left[
\eta_c(x_t+y_t)
+\frac{z_t}{\eta_d}
\right].
\tag{33}

$$

数值实现时可使用 $J\le J^\star+\varepsilon_{\rm num}$ 处理浮点容差。

---

## 6. 周期能量一致性与时段内部 SOC

由 $E_{144}=E_0$ 可得

$$
\sum_t\eta_c(x_t+y_t)
=
\sum_t\frac{z_t}{\eta_d}.
\tag{34}

$$

因此

$$
T^\star
=
2\sum_t\eta_c(x_t+y_t)
=
2\sum_t\frac{z_t}{\eta_d}.
\tag{35}

$$

式 (34) 可作为重要数值一致性检验。

在零阶保持假设下，单个 10 min 时段内充放电功率恒定。又由于最优解不存在同时充放电，$E(\tau)$ 在每一时段内部单调变化或保持不变。因此只要相邻离散节点均满足 SOC 上下界，整个时段内部也不会越界。

---

## 7. 结果解释：只保留有信息增益的部分

主模型的任务是得到最优购电与储能策略。解释性分析仅在能够直接解释结果时使用，不作为独立算法创新。

### 7.1 两类储能经济服务

在 canonical flow 下，将储能作用分为

$$
\text{富余光伏时移（PV）}

$$

与

$$
\text{外网峰谷套利（G）}.

$$

定义四种情景的一级最优成本：

$$
C_{\varnothing}:x_t=y_t=z_t=0,

$$

$$
C_{PV}:x_t=0,

$$

$$
C_G:y_t=0,

$$

$$
C_{PV,G}:\text{两种服务均允许}.

$$

理论上应满足

$$
C_{PV,G}\le C_{PV}\le C_{\varnothing},
\qquad
C_{PV,G}\le C_G\le C_{\varnothing}.
\tag{36}

$$

若需要分解总体经济收益，可计算两参与者的顺序对称边际贡献

$$
\phi_{PV}
=
\frac12
\left[
(C_{\varnothing}-C_{PV})
+
(C_G-C_{PV,G})
\right],
\tag{37}

$$

$$
\phi_G
=
\frac12
\left[
(C_{\varnothing}-C_G)
+
(C_{PV}-C_{PV,G})
\right],
\tag{38}

$$

并满足

$$
\phi_{PV}+\phi_G
=
C_{\varnothing}-C_{PV,G}.
\tag{39}

$$

进一步定义

$$
I_{PV,G}
=
C_{PV}+C_G-C_{\varnothing}-C_{PV,G}.
\tag{40}

$$

若 $I_{PV,G}<0$，只能说明两类服务存在收益重叠或替代。若需判断是否由容量或功率竞争导致，应分别放松 $E_{\max}$ 与 $\bar q$ 后重新求解，而不能仅凭约束是否取等号作因果判断。

### 7.2 可选结构分析

若最终结果存在明显时段结构，可进一步采用：

- **SOC 边际价值**：固定某时刻 SOC 为 $e$，重新优化后续调度，通过价值函数 $\mathcal V_t(e)$ 的局部斜率衡量额外 1 kWh 库存的未来经济价值；
- **动作排除反事实**：对关键时段强制 $x_t+y_t=0$ 或 $z_t=0$，重新求解并比较

$$
\Delta J_t^{act}=J_{t,-act}^\star-J^\star.

$$

若这些分析没有产生非平凡结论，则放入附录，不占正文主要篇幅。

---

## 8. 模型验证与稳健性

至少进行以下检验：

### 8.1 SOC 动态残差

$$
\max_t
\left|
E_t-E_{t-1}
-\eta_c(x_t+y_t)
+\frac{z_t}{\eta_d}
\right|
\approx0.
\tag{41}

$$

### 8.2 周期边界

$$
|E_{144}-6000|
\approx0.
\tag{42}

$$

### 8.3 周期能量一致性

$$
\left|
\sum_t\eta_c(x_t+y_t)
-
\sum_t\frac{z_t}{\eta_d}
\right|
\approx0.
\tag{43}

$$

### 8.4 互斥性

$$
\max_t (x_t+y_t)z_t
\approx0.
\tag{44}

$$

### 8.5 Coalition 单调性

检验式 (36) 是否成立。

### 8.6 效率解释稳健性

主模型采用

$$
(\eta_c,\eta_d)=(0.9,0.9),

$$

对应往返效率 $0.81$。

若将题面的 90% 理解为整体往返效率，则在进一步假设充、放电损失对称时取

$$
(\eta_c,\eta_d)
=
(\sqrt{0.9},\sqrt{0.9}).

$$

比较两种解释下的最低购电成本、SOC 轨迹及主要经济结论，以判断结果是否依赖效率定义。

---

## 9. 核心创新与求解流程

本文不将 Shapley、dual 或反事实分析本身作为新算法，核心创新集中在两点。

### 创新 1：最优性保持的规范化能流

从一般源—荷—储能物理能流出发，通过能流交换与无收益库存循环消去，证明至少存在一个词典序最优解可规范化为

$$
\text{光伏先抵消当前负荷}
\rightarrow
\text{富余光伏进入储能}
\rightarrow
\text{储能仅对净负荷放电}.

$$

因此 canonical flow 不是经验性调度规则，而是对最优解结构的化简。

### 创新 2：充放电互斥约束的精确松弛

利用非负电价、储能损耗、无售电收益及用途同价等结构，证明删除充放电互斥二元变量后，LP 的词典序最优解仍自然满足物理互斥条件。因此原本的 MILP 可在本题条件下精确化简为连续 LP。

最终求解流程为

$$
\boxed{
\text{数据离散与能量换算}
\rightarrow
\text{Canonicalization}
\rightarrow
\text{Canonical LP}
\rightarrow
\text{一级最小购电成本}
\rightarrow
\text{二级最小吞吐量}
\rightarrow
\text{结果验证与必要解释}
}.

$$

最终输出 144 个 10 min 时段的计划购电量、储能充放电量及 SOC 轨迹，并按题目要求汇总指定时段结果。
