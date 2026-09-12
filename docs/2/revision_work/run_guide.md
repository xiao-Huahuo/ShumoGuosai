# 第二问最终修订方案运行说明

## 已验证并应用：延迟K1与相同基准复用（2026-09-12）

正式仍3%。固定K2在171天既有审计中未获支持（118组可靠对照中49组不稳定）；采用保持原选择规则的延迟K1，只有K2/K3均失败才计算K1。三个真实日期策略和实际回放一致，耗时由76.28/157.19/10.26秒降为66.07/31.93/8.49秒，不能外推全年倍数。84项测试及正式新提交日验证通过，旧995天分组存档保留。相同初态及28天窗口基准仅在完整输入/评分/物理核验后共享，其他全年比较继续。详见[执行补充](../final/计算执行提速修订_延迟K1与基准复用.md)。

主回放已于13:16提交全部334天，后处理因临时Python路径失效未能导出Excel，正在从完整结果修复导出；其他实验继续，无需重算主轨迹。证据raw/export_runtime_repair_20260912/。以下为历史记录，当前状态看TASK_STATE.md及progress.html。

## 最新生效：后续3%续算（2026-09-12 12:22）

用户明确“那就换成3%，继续跑”。[3%执行修订](../final/求解精度执行修订_3pct.md)覆盖以下历史1%/2%状态；旧主109日和其余实验完整前缀保留，6组462日离线回读与79项测试通过。新监督50957、主50991和H1 50992已以3%实际启动；进度HTML实际显示3%。K/S、10分钟、120+900秒预算及两进程不变。全年及全部必需实验仍计算中；已独立验收主110日、H1 139日，新3%提交正常且旧109/132日前缀逐值与SHA不变，证据raw/precision_3pct_official_validation.json。以下内容作为历史过程保留。


## 当前求解路线：2%首次120秒采用已验证等价MILP（2026-09-12 10:48）

2%门槛保持不变。已消除部分日期先耗满原生SCIP 120秒再切换HiGHS的开销：LP证书不足时，自由单段策略首轮直接用既有等价HiGHS MILP，整日全失败后才补900秒。旧1%入口、固定策略和三段SOC仍保留原生路线；物理、场景及选择规则不改。三个同实例120秒诊断和正式入口通过，78测试通过。主91日/H1 106日存档完整保留后安全重载，独立回读主92日/H1 107日；正式主May03与H1 May18都已采用首次线性路线，原前缀不变、物理和费用通过。证据raw/base_solver_revision.json（official_rollout_validated）及processed/timing_audit/base_solver_benchmark.csv。新监督42052，主42066、H1 42067。完整334日和其余实验尚未完成，仍继续；不能把样本速度推广为全年保证。


## 当前生效：用户授权后续求解gap≤2%（2026-09-12 10:07）

[精度执行修订](../final/求解精度执行修订_2pct.md)覆盖下面历史日志中的“保持1%”要求：后续采用2%，旧1%结果和失败记录保留，不重算已完成前缀。三个难例约2.6/5.9/8.7秒通过；正式主Apr27全部候选约21秒通过并已提交。77测试与旧前缀/新提交日独立回放验收通过。当前监督39642、主39652、固定K1 39653，双进程继续；完整334日及全部实验尚未完成。原最终建模文档、冻结预测库、物理约束和稳定性门槛不变。后续状态优先看TASK_STATE.md和progress.html，以下均是此前过程记录。


## 单调充电修复已验证并重排K3（2026-09-12 08:48）

src/q2/linear_policy.py已采用经过证明的单调充电下界：只允许求解中的场景轨迹少充，放电仍是原反馈；最终以同一共享策略执行原respond/replay。原反馈SOC不减、紧急购电和总费用不增，故最优费用相同，1%证书仍用有效全局下界和原反馈费用。固定策略和三段SOC继续精确编码。原轨迹差、单调投影、完整线性可行性、整数性与费用不增分别验收，不能把放松轨迹冒充执行结果。

73项当前源码测试全部通过（14.327秒），新增96条144步任意少充完整矩阵/原反馈投影和证书语义测试。真实K3 Apr19/K3/S26/初SOC3095.9222139171693经正式rolling._solve在140.779453秒达到U83977.52059742116/L83150.42232912692、gap0.9947012235%、投影0、行误差1.82e−12、整数差0；原900秒gap1.038408%失败与77日存档保留。证据raw/monotone_charge_revision.json、solver_diagnostics/apr19_horizon3_monotone_production.json及一般等价性说明。

只将K3重新排队，旧监督32358换为35653（启动35648），主28187和K2 34303同一attempt持续运行；full_run_horizon3_monotone_reload.json保存整份旧状态与失败。实际IAB tab14核到主81日、K2 77日、K3排队77日、K1隔离85日、29任务/依赖等待。K3官方Apr19尚待工作位后实际执行，不能把场景目标当当日电费。报告tab15已实际验收新证明链接和精确/单调编码区分，数值与四张已目视图仍为73日快照；1820条逐句映射按当前代码重新生成。

K1 Apr27可达SOC精确候选900秒仍gap1.176189%，未采用；复用旧全局界及SCIP矩阵候选也均未达1%。当前唯一运行诊断为同一因果准备的单调模型长算，最多7200秒，正式预算仍120/900秒，未放宽1%。若只在超900秒后通过，须显式保留旧执行与失败再建立补充执行版本，不能称原预算已过。完整334日、其余25项必需实验、result2仍未完成；自动跟进继续。

## K2卡点已正式通过，新增完整348日验收（2026-09-12 08:36）

主80日、固定K2 74日持续计算，监督32358未改。K2的Apr15已正式补算77.69秒达gap0.999846%、反馈误差0，并实际执行：日费用36161.289905元、紧急5.806210kWh、末SOC8313.319409；原预算失败保留。五组348日（80/85/74/77/32）通过已提交字节复制后的原数据、电价、连续日、跨日SOC、冻结策略、物理及费用独立核验。证据raw/full_run_autonomous_validation.json和branch_cuts_revision.json；实际IAB隐藏tab13确认主80日算Apr22、K2 74日算Apr16、两个失败实验隔离与29任务/依赖等待。

K3在Apr19的正式900秒仍gap1.038408%，77日保留，正在隔离验证已有单调充电候选。K1 Apr27复用全局下界再算900秒仍gap1.017276%；SCIP同一候选矩阵300秒gap1.156557%，均未采用。继续同一因果准备的单调模型较长诊断（最多7200秒）及原精确模型的可达SOC边界诊断（900秒、7既有测试通过）；诊断不代表生产修复，正式源码/71项测试摘要/120与900秒执行协议/1%门槛均未改。原最终文档与7个冻结文件保持不变。主334日、其余25项必需实验和result2仍未完成。

## 当前补算求解实现

单段自由策略补算新增充电上限支配性预处理，固定策略与三段SOC不使用该简化。初值两阶段共享30秒：先在原cp范围改善，再投影到最大cp并继续改善。正式MIP保持全部响应分支自由。4月16日K1正式场景入口272.45秒达到0.999909% gap、映射误差0，证据raw/charge_dominance_revision.json；该日队列真实回放也已在206.03秒补算后通过，真实费用36066.545058元。

原生SCIP保持120秒主路径；整日全候选失败后，新的工作进程使用900秒HiGHS等价线性MILP补算，物理边界逐项推导与真实验证见[等价性说明](linear_milp_equivalence.md)。原SCIP失败记录保留，1%门槛不变。已经在运行的旧进程不会自动加载新实现；已失败实验已重新排队。SOC三段诊断继续原生SCIP，并新增策略CSV和逐日可验收恢复。


## 2026-09-12：已授权并启动Mac全量计算

用户已明确要求自动开始、自动验收与修复，仅需最终结果或致命问题；覆盖此前等待命令。队列已于2026-09-11T17:02:13 UTC启动。运行状态以raw/full_run_state.json为准，最近的故障与恢复交接见项目根目录TASK_STATE.md。

- 全量队列src/q2/full_run.py已经实际运行：主模型、27项必需实验及预测诊断，共29任务，最多两个独立计算进程。两个已完成的结构对照经过原数据与全期物理验证后复用。
- 当前71项测试通过；已有340个已提交日检查点重新独立验证物理、费用、原始输入与冻结策略。重启不会把已完成日重算，也不会跳过失败日。
- raw/full_run_execution.json冻结补充执行协议：原SCIP每次120秒，整日全候选受限时追加每次900秒，gap仍1%。失败证据、补算日数和原预算是否通过分别记录；补算不冒充原预算通过，不修改原文或预测库。
- processed/progress.html每15秒自动刷新真实存档日数、活动日期/K/预算及独立日志。已在实际应用内浏览器检查29任务、两个并行工作进程及主结果依赖阻塞显示。report.html仍是生成时的验收快照。
- 自动跟进已创建：第二问全量计算自主验收（automation），每15分钟检查任务并自主处理可修复问题，正常推进时保持安静。计算由独立进程执行，自动跟进负责后续排查和最终验收。
- 未完成：主回放其余日期、其余必需实验及最终模板/全年验收。尚未发布result2.xlsx，不将启动成功当作题目结果完成。

全量队列已经在后台运行，以下命令仅用于监督进程意外退出后的恢复；不要同时开启第二个队列。锁会拒绝重复监督进程，并识别仍存活的原工作进程。

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MPLBACKEND=Agg caffeinate -i uv run --with-requirements src/q2/requirements.txt python src/q2/full_run.py --run-dir outputs/q2/dispatch_runs/20260911_224501
```

存档保护已模拟多个文件替换位置的进程中断并验收，尚未做真实断电实验；正在求解的单日内部搜索树未存盘，中断最多重算该实验尚未提交的当天。机器闲置自动睡眠由caffeinate保持唤醒。


## 执行依据与假设

唯一执行文档为 `docs/2/final/第二问_最终建模思路_最高优先级修订版_修订后.md`，与用户提供附件逐字节一致。旧 `dierwen1.md` 仅用于复用原始数据诊断，旧阶段验收不代表新模型完成。

按本次用户“全权依靠新方案”执行源日 `j<d` 的完整历史日边界。1月1—7日储能停机积累历史，1月8—31日固定季节预测、48小时确定性同策略类求解，产生2月1日基准初态。该初态不可解释为恢复了未知真实运行历史；6000、1200、10800及预热初态的敏感性独立运行。10分钟回放是实时控制的区间聚合近似。

`protocol.py` 中区分题设参数与工程预注册：双侧效率0.9，SOC 1200—10800 kWh，母线侧每段功率上限5000/6 kWh；最低14个完整误差块，28→56→84→expanding窗口回退，M≤40全保留，M>40才比较10/20/40个medoids；gap 1%、SCIP每次120秒，目标稳定1%、首日购电稳定2%，分位/完整池紧急费用偏差容差5%。这些数值设置在本次正式数据计算前固定，不能用全年费用调参。

## 环境

从项目根目录运行，使用 `uv` 按 `src/q2/requirements.txt` 锁定依赖。新增 PySCIPOpt 6.2.1 / SCIP 10.0.2、LightGBM 4.7.0、scikit-learn 1.9.1。macOS 的 LightGBM 需要 `libomp`，本机已通过 Homebrew 安装。

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MPLBACKEND=Agg uv run --with-requirements src/q2/requirements.txt python src/q2/dispatch.py prepare
```

准备步骤读取附件1电价、附件2全年实际负荷/PV，生成带origin×horizon的三维DAT影子预测库。1月15—31日比较LightGBM配置，2月1日冻结配置，后续每天仅在历史数据上重新拟合模型参数。预测源码、方案、原始输入及生成DAT/CSV均有哈希核验。改变预测源码或冻结参数必须重新prepare，禁止混用缓存。

当前运行目录为 `outputs/q2/dispatch_runs/20260911_224501`。这是全量队列持续续算的独立运行代；完整验收前不替换旧 `outputs/q2_current`。以下是单任务入口示例，队列运行时不得对相同输出目录重复启动。

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MPLBACKEND=Agg uv run --with-requirements src/q2/requirements.txt python src/q2/dispatch.py run --run-dir outputs/q2/dispatch_runs/20260911_224501
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MPLBACKEND=Agg uv run --with-requirements src/q2/requirements.txt python src/q2/dispatch.py experiments --run-dir outputs/q2/dispatch_runs/20260911_224501
```

主回放按日期顺序执行。重启时核对完整日前缀、跨日SOC、实际净负荷、电价、冻结参数、费用、审计及校准记录。CSV摘要不匹配时拒绝续算；不会直接重封存掩盖损坏。旧准备库只在独立重读附件后执行一次 `seal-prepared` 迁移，本次迁移已完成，记录明确其为生成后封存。

实验支持 `--only horizon_1` 等具名执行。可用名称包括 `forecast`、`structure_separate`、`structure_direct_net`、`deterministic`、`rigid`、`window_28/56/84/expanding`、`horizon_1/2/3`、`scenario_10/20/40`、`minimum_14/21/28`、`initial_1200/6000/8482.77/10800`、`oracles`、`richer_soc`，以及 `predictor_week_mean7/week_dhr/lgb_mean7/lgb_dhr` 四条固定联合预测流程的事后经济对照。初态名称仅为目录标签，运算使用未舍入的原值。独立实验可各自续算；相同输出目录不要并发写入。刚性/确定性对照、共同门槛初态与Oracle依赖完整主回放。

## 求解与有效性

主模型用SCIP原生indicator约束精确绑定min/max响应，场景响应量不是自由第二阶段控制。求解前可计算自由场景响应LP下界L，并搜索同一冻结反馈策略的可行上界U。仅 `(U-L)/max(|L|,1e-8)≤1%` 时用证书接受；否则继续原生MILP。可行策略搜索没有全局最优声明，LP自由响应从不进入实际执行。FAST单轮presolve和关闭对称性只改变求解器实现设置，不改变模型。

当某个K/S无法在预算内通过，按照方案显式记录计算受限并使用允许的可靠候选；所有候选都失败则该实验停止，不能输出伪造正式解。SCIP内部gap与外部LP下界证书分别保存。三段SOC对照保留半开区间真实执行，以闭区间松弛给下界、严格回放给上界；失败不得标记对照通过。

## 输出与验收

- `inputs/processed/`：52560条原始数据长表、电价、质量核验与来源清单。
- `raw/`：预注册协议、冻结影子库DAT、DHR诊断、源码版本与运行状态。
- `processed/main/`：真实逐10分钟执行、逐日汇总、校准、每个日期完整冻结策略与逐候选求解审计。
- `processed/experiments/`：预测/分位数诊断、对照与敏感性；`status/`逐实验记录完成或失败原因。
- `processed/solver_records.csv` / `solver_resource_summary.csv`：M/S/K、前后模型规模、求解时间、gap与可靠性。
- `processed/source_sentence_traceability.csv`：全部1553个非空原文行拆成1820条记录，含句子、公式行和排版标记；代码定位、测试定位与真实验收分列。映射覆盖100%不等于实验验收100%。
- `processed/report.html` / `report.md` / `acceptance.json`：真实结果与未完成状态。未完成指标不能填零或外推全年。

数据表默认CSV，三维预测库DAT，图为PNG/SVG。方案规定的 `result2.xlsx` 仅在完整334日的真实回放通过日期、单位、物理、费用和模板回读后生成；原题模板不修改。原模板144个计划标签偏移10分钟，输出按实际00:00—24:00重建并留存原标签审计。未完成的主回放不会产生正式XLSX。

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MPLBACKEND=Agg uv run --with-requirements src/q2/requirements.txt python src/q2/final_report.py --run-dir outputs/q2/dispatch_runs/20260911_224501
python3 src/plots/run.py q2-dispatch --run-dir outputs/q2/dispatch_runs/20260911_224501
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 Q2_GENERATION=outputs/q2_current MPLBACKEND=Agg uv run --with-requirements src/q2/requirements.txt python -m unittest discover -s src/q2 -p 'test_*.py' -v
```

报告可在回放期间生成；它明确标记快照范围。真实主回放及所有必需实验完成前，不得宣称本方案完整验收通过。当前问题、测试与浏览器证据见同目录 `acceptance.md`、`tests.txt`、`ui_smoke.json`。

全量代码验收并生成报告：在final_report命令末尾加`--verify`，会将当前源码哈希与全部测试结果保存在raw/test_manifest.json（当前71项）。原始数据与预测库哈希通过但当前源码测试摘要缺失时，整体验收不能标记通过。

原预算下的早期停止记录保存在failed_attempts。补算后主模型已推进至73日，4月13日及14日均已实际通过并落盘。固定K1的4月16日已实际通过并推进至82日；固定K3旧SCIP失败后保留71日存档并重新排队，其他健康工作进程继续。实际进度以队列状态为准，不能因个别实例通过就断言全部计算限制已解决。

## 存档保护与追加预算

全量队列已经按用户最新授权运行。监控时不能对活动工作目录直接调用read_checkpoint或recover_checkpoint；应先复制摘要一致的已提交CSV及对应审计/策略到临时目录，再独立复核。

逐日存档新增checkpoint_previous上一份完整备份和checkpoint_transaction.json事务标记。中断恢复仅在事务标记存在时触发，普通摘要不符仍拒绝。中途退出至多需要重算未提交日；不会恢复SCIP内部搜索树。同一实验用Mac文件锁限制单写入者。

run和experiments可显式传入--rescue-seconds 900：仅原120秒预算下整日全候选失败时，追加900秒预算，仍维持1%gap。原失败保存在failed_attempts，追加成功仍标记原预算受限。补算已经在真实数据上使用，执行版本见raw/full_run_execution.json及raw/supplemental_solver_revision.json；不能追认原预算已通过。

当前源码门禁为71项测试，日志和源码SHA见raw/test_manifest.json。后续代码变化必须重做相应验证；未改代码的正常运行监控不重复执行同一套测试。

4月24日K1的追加求解仍以gap1.000626%失败，保持82日存档。新增原反馈分支隐含的四条有效约束后，正式场景入口37.03秒达到gap0.962789%、响应误差0，71项当前源码测试通过；已保留失败并续算；该日已在官方队列实际提交，补算27.19秒，真实日费用34585.290331元。证明见linear_milp_equivalence.md，运行证据raw/branch_cuts_revision.json；未改变预测、场景、预算或1%精度，其他健康工作进程持续运行。
