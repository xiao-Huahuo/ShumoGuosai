# 第三问自由 aggregate 快模型 v2 精确等价说明

## 适用范围

本证明只适用于 `feedback=aggregate`、自由优化的单段参数策略以及非负终端残值。`fixed policy`、`lag-one-slot`、M2 场景树和 `gap=0` 原精确模型继续使用原编码。场景、目标函数、结算、真实执行和 3% 接受规则均不变。

## 一、已有单调充电等价关系

给定购电向量 (g)、放电上限 (r^p) 和任一净负荷场景，原反馈一步映射为

\[
E^+=E+\eta c-r/\eta,
\]

其中充电与放电均为题面规定的饱和最小值。把自由策略的充电上限提高到设备上限 `CAP` 后，下一状态不减，后续状态由归纳仍不减，紧急购电不增。正常购电和非对称调整项只依赖 (g)，且终端项为非负系数乘终端 SOC 的负值，因此该映射不会增加目标。

旧 fast formulation 允许内部充电轨迹低于原饱和轨迹，但保留精确放电最小值。任一整数 fast 解映射为 `Policy(g, CAP, rp)` 并由原 `physics.replay()` 回放时，有

\[
E^{replay}_{s,t}\ge E^{matrix}_{s,t},\qquad
q^{replay}_{s,t}\le q^{matrix}_{s,t},
\]

所以原 replay 目标不高于矩阵目标。反向地，每个原饱和反馈轨迹都能嵌入 fast formulation 且目标相同。由两方向包含关系可得 fast formulation 与原自由策略问题的最优目标相同；solver 内部轨迹不作为实际输出。

## 二、删除固定 `cp`

旧 free builder 已施加

\[
lb(cp_t)=ub(cp_t)=CAP.
\]

因此 `cp` 不是决策自由度。v2 删除这 (T) 个固定列，并用 `c` 本身的 `CAP` 上界表达原 `c<=cp`。最终政策始终重建为 `Policy(g, full(CAP), rp)`。这是固定变量代换；fixed-policy 路径不使用该代换。

## 三、删除固定零 `lc`

旧 free builder 中三组 charge selector 均有

\[
lb(lc)=ub(lc)=0,
\]

且所有使用它们的约束只存在于 fixed-policy 分支。v2 不创建这些 (3ST) 个零列。其值和任何剩余约束、目标都没有变化。

## 四、消去 `z`

旧 free builder 有三组二元放电 selector，并满足

\[
z_{s,t}=lr^0_{s,t}+lr^1_{s,t}+lr^2_{s,t},\qquad 0\le z_{s,t}\le1.
\]

v2 逐处以 (Z=lr^0+lr^1+lr^2) 代换 `z`，删除 `sum(lr)-z=0`，并显式保留 `sum(lr)<=1`；当净负荷为负时三组 selector 的列上界均固定为 0。替换后的六类约束为：

\[
\begin{aligned}
c+CAP\,Z&\le CAP,\\
r-CAP\,Z&\le0,\\
q-dZ&\le0,\\
w+sZ&\le s,\\
r+q-dZ&\le0,\\
c+w+sZ&\le s,
\end{aligned}
\]

其中 (d=\max(n,0))，(s=\max(g^{upper}-n,0))。这是一一代换，不改变整数可行点、目标或二元变量数。`sum(lr)<=1` 替换原等式和 `z` 上界，因此 z 消元本身不宣称净减同数量的约束行。

满规模 (S=20,T=144) 时，v2 删除 `cp` 的 144 列、`z` 的 2,880 列以及 `lc` 的 8,640 列，共 11,664 个连续变量；放电 selector 仍为 8,640 个二元变量。

## 五、安全可达界

对场景 (s) 和时槽 (t)，若前一状态安全区间为 ([L,U])，只使用当前场景净负荷 (n)、当前矩阵的购电上界 (g^{upper})、设备参数和效率定义

\[
d=\min(CAP,\max(n,0)),\qquad
s=\min(CAP,\max(g^{upper}-n,0)).
\]

旧 fast 约束已蕴含 (r\le d)、(c\le s)。结合 SOC 方程与容量界，得到

\[
\begin{aligned}
c&\le\min\{s,(E_{max}-L)/\eta\},\\
r&\le\min\{d,\eta(U-E_{min})\},\\
L^+&=\max\{E_{min},L-d/\eta\},\\
U^+&=\min\{E_{max},U+\eta s\}.
\end{aligned}
\]

从 (L=U=E_0) 递推。这些界由旧 LP 的已有约束直接推出，所以不仅包含原 replay 轨迹，也包含旧 fast 的全部 LP/MIP 可行点。实现用 `nextafter` 向外放宽一个浮点单位，避免恰落边界的合法点因舍入被排除；原物理约束仍在，故不会扩大原数学可行域。

## 六、有效下界与 3% 证书

v2 是旧 fast 矩阵的固定列删除、精确代换和隐含界收紧，因此

\[
OPT_{v2}=OPT_{legacy}=OPT_{original\ policy}.
\]

HiGHS 对 v2 完整矩阵给出的 global dual bound 是原自由策略问题的有效全局下界。外部自由场景 recourse LP 仍只作为解析上有效的原问题下界，审计中单独标记来源。不同 matrix digest 的旧 MIP 下界默认不迁移；只迁移经原 replay 重算的 Policy。

设原 replay 目标为 (U)，有效下界为 (L)。无论目标为正、负或接近零，唯一接受条件仍是

\[
L\le U+TOL,
\qquad
U-L\le\max\{TOL,0.03|U|\}.
\]

展示用 gap 为 `max(0,U-L)/max(abs(U),1e-10)`。不使用 solver raw MIPGap 替代该判据，也没有目标常数偏移。

## 七、检查点边界

v2 内部向量维度与 legacy 不同，不能恢复旧 raw vector 或分支树。跨 formulation 只迁移 `Policy(g,CAP,rp)`、已执行区块、日收据、SOC、终端缓存和输入签名；未完成节点的旧 MIP 下界明确丢弃。v2 新快照记录 `formulation_version`、`matrix_digest`、`bound_sources` 和 `objective_offset=0`，随后只在相同配置和摘要下恢复。

以上解析等价性由 gap=0 随机小实例、原精确 SCIP 对照、固定策略隔离、负目标证书、随机真实 replay 可达界和真实困难节点矩阵验收共同验证；数值测试是回归证据，不取代上述推导。
