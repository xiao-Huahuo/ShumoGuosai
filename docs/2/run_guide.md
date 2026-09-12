# 第二问2.1阶段运行与交付说明

## 实施口径（先于结果）

依据 `dierwen1.md` 完整实现数据清洗、结构诊断和分析图。用户补充确认“主要用到附件2，清洗附件2的数据并做分析图”，并明确严格排除时间戳等于当日0:00的观测。原方案止于预测模型建立前，真实预测器和购电调度模型不是本文件预设内容。

全年数据用作事后描述；首次模型候选依据只用2月1日前4463个可见点。1月31日最后一段的右端点为2月1日0:00，按确认口径排除。法定节假日、日出日落与天气信息未给出，不推定标签。不新增异常清洗阈值或模型超参数。

## 运行

项目根目录执行（依赖通过uv隔离，不修改全局Python）：

```sh
uv run --with-requirements src/q2/requirements.txt python src/q2/run.py
```

流水线读取并核验原始附件副本，计算两种信息范围的全部诊断，生成CSV及11张PNG/SVG图，执行当前源码测试与磁盘回读后发布。中文字体缺失或任一数值/测试失败会阻止发布。全部源码/方案/输入和产物哈希保存在运行清单。

独立测试：

```sh
uv run --with-requirements src/q2/requirements.txt python -m unittest discover -s src/q2 -p 'test_*.py' -v
```

独立测试没有暂存生成代时会跳过1项产物回读测试；正式流水线设置 `Q2_GENERATION`，必须全部执行而非跳过。

## 结果入口

- [浏览器报告](../../outputs/processed/q2/report.html) · [结果说明](../../outputs/processed/q2/results.md)
- [清洗后长表](../../inputs/q2/processed/timeseries.csv) · [核验清单](../../outputs/processed/q2/quality_checks.csv)
- [逐句映射](../../outputs/processed/q2/source_traceability.csv) · [验收报告](implementation_acceptance.md)
- [11张分析图目录](../../outputs/processed/q2/figures) · [突变上下文](../../outputs/processed/q2/jump_context.csv)
- [模型候选依据](../../outputs/processed/q2/model_candidates.csv) · [334日回测切分](../../outputs/processed/q2/rolling_folds.csv)
- [算法设置](../../inputs/q2/processed/settings.json) · [运行清单](../../outputs/q2/raw/run_manifest.json)

CSV均为UTF-8无BOM、17位有效数字，不用显示舍入替代计算值。原始XLSX仅作为读取副本；不产出Office结果。

`inputs/q2`、`outputs/q2/raw`、`outputs/processed/q2`统一指向 `outputs/q2_current` 当前完整生成代。只在全流程成功后切换。2026-09-11清理后，`.q2-runs`保留当前与上一完整生成代，更早运行的必要清单、测试和失败日志已压缩归档至`outputs/history/run_records_20260911.tar.gz`，对应预检及大体积结果已删除。此次为一次性清理，生成器仍会保留后续新运行代。不要直接修改生成代，应修改源码后重跑。

## 数据字段和时间归属

| 字段 | 定义 |
|---|---|
| date | 附件原始日期，即区间所属日；不使用右端点的自然日代替 |
| interval | 00:00-00:10至23:50-24:00 |
| timestamp | 10分钟区间右端点；最后一段为次日0:00 |
| slot | 日内序号1至144 |
| weekday / weekday_name | 源日期星期一=1至星期日=7；附中文星期 |
| month | 源日期月份 |
| load_kw / pv_kw | 原始负荷和光伏功率，kW |
| net_load_kw | load_kw-pv_kw，允许为负，kW |

没有发现格式以外需要改值的数据，因此清洗结果逐值保留原始观测。明显结构/物理错误会留下失败记录并中止，不自动修正。`jump_context.csv`是所有局部转折点的人工复核上下文，按偏离邻点程度排序；其`action=retain_review_only`不表示已判异常。历史同类比较按过去相同星期、相同槽位计算，缺少既往历史时CSV留空，不能填0冒充观测。

## 诊断CSV约定

所有带 `full_year_` 前缀的统计是全年事后描述；带 `initial_history_` 的统计只使用首次回测之前可见数据。

| 后缀 | 内容 |
|---|---|
| summary | 三种功率的样本量、均值、标准差、极值、零值数 |
| profiles | 12个月、7个星期及工作日/周末平均日曲线；含n与样本标准差，不当作置信区间 |
| daily_statistics | 每日均值/波动/峰谷差/峰值首现槽位/并列数/零值数；全零日标记 |
| pv_zero_profile | 每槽位光伏零值数与比例；不冒充天文夜间定义 |
| lag_correlations | 1、6、144、288、1008、2016阶Pearson相关；原始与去平均日曲线残差各一组 |
| acf_pacf | 0–2016阶FFT ACF与Burg PACF；0阶用于数值记录，图显示1阶起 |
| spectrum | 全部正频率周期图，频率为周期/日，PSD单位kW²/(周期/日) |
| spectral_targets | 1日与7日最近离散频点、两侧邻点、局部峰、格点能量占比和Parseval核验 |
| monthly_stability | 每月日/周相关、日峰谷幅度、均值、标准差及变异系数；配对两端均在月内 |
| transformed_series | 原始、日差分、周差分、日后周差分；仅删除因定义不存在的前置滞后部分 |
| transformed_monthly_moments | 每种变换每月的均值与标准差 |
| stationarity_tests | ADF/KPSS × 4种变换 × c/ct × 2种功率；p值/上下界、临界值、滞后、警告 |

1月仅有约4个完整周，周频率分辨率有限。候选优先级需要日频峰、去日曲线后的周频峰及残差周相关强于日相关共同支持；不把一个局部峰当成统计显著，不把本轮证据规则当最终模型选型。ADF/KPSS的c和ct分别对应常数项与常数加线性趋势；两种原假设相反，不能只看一项p值。

## 后续预测和调度接入

`backtest.rolling_predict(frame, model_factory)`：每日为负荷与光伏分别调用全新预测器。`model_factory(series)`返回可调用对象，接受只含`timestamp,value_kw`的过去观测，以及只含日历字段的未来144段，返回144个有限非负kW值。参数估计、缩放、特征选择、超参数比较必须全在所获历史内进行，调用方不得通过闭包或文件另读未来值。预测完成后才拼接真值用于`forecast_metrics`。

`forecast_metrics`输出三种功率的MAE/RMSE以及每日与评价期统计，不平均每日RMSE。`dispatch_metrics`须由后续真实调度模型提供以下完整10分钟明细：

| 字段 | 单位/口径 |
|---|---|
| timestamp / date | 区间右端点 / 区间所属源日期 |
| planned_grid_kwh | 0:00已制定的计划购电量，kWh，未用部分也计费 |
| price_yuan_per_kwh | 交易时刻正常电价 |
| actual_load_kw | 事后实际负荷，kW |
| actual_supply_before_emergency_kw | 储能与弃电等实际执行后、紧急购电前的母线净供给，kW；可因充电需求而为负 |

紧急电量为正供给缺口×1/6小时；按正常电价5倍计费。频次同时给时段数、时段比例、连续事件数、发生天数；跨午夜连续缺口算一个连续事件。该评价器不验证储能物理可行性，须由后续调度模型验证，不能当调度优化器使用。仅覆盖2–12月时不得称全年费用。

本阶段 `evaluation_status.csv` 里的实际预测/调度指标为空且有未计算原因；空值不是0。测试使用手算/合成样本，只验证接口，未作为附件2预测结果发布。
