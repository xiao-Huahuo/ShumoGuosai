# 图注与数据来源

## 图5-1 源荷结构与预测特征依据组合图

全年2025年数据的事后结构展示。工作日指周一至周五；分位带是跨日25%–75%范围。光伏以每月×时刻均值去周期，未将全样本统计用于滚动预测。负荷为配对Pearson相关；残差带为逐点Bartlett参考带。

数据：fig51_weekday_profiles.csv, fig51_seasonal_pv.csv, fig51_load_lag_correlation.csv, fig51_pv_residual_acf.csv, fig51_pv_deseasonalized.csv

## 图5-2 不同前瞻日的误差分布与场景校准

仅使用三个前瞻日均有正式场景且目标真值完整的304个共同预测起点，每个h为43,776时段。误差为同forecast-origin真实净负荷减点预测，单位kWh/10min。箱线须为1.5IQR，点保留全部离群值；PICP由覆盖数/样本数计算。

数据：fig52_paired_errors.csv, fig52_error_quantiles.csv, fig52_paired_coverage.csv, fig52_all_available_coverage.csv

## 图5-3 非前瞻滚动调度的信息时序

横向时间轴区分日前冻结与日内反馈。G为计划购电，Cp/Dp为事前反馈上限，R为历史给定安全裕度；C/D/B为实际充电/放电/紧急购电。当前映射不访问未来真实轨迹。真实日末SOC传至下一日，不重置。

数据：

## 图5-4 压力代表日真实购电与储能运行

2025-03-20在题目四个指定日期中紧急量最高（53.567333kWh）。Z为储能之前净负荷正部，单位kWh/10min；红柱为真实紧急量，淡红时段仅标事件位置、不放大能量。充电为正、放电为负，SOC含日初共145点。

数据：fig54_real_dispatch.csv, fig54_storage_145.csv, fig54_candidate_dates.csv

## 图5-5 前瞻长度的局部费用与耗时权衡

经用户确认改为当前模型4个代表日局部比较，纵轴不是全年费用。K1/2/3采用相同S26联合72h场景的前缀、同一各日日初SOC/R和同机3%预算，均独立计时。日末库存不同，较低当日费不等于更优跨日经济性。

数据：fig55_horizon_summary.csv, fig55_horizon_cases.csv

## 附加图 全年源荷日期—时刻热力图

52560个原始10分钟记录逐格呈现，不做平滑或缺失补值。日期自上而下，负荷/PV顺序色标，净负荷发散色标以0为中心；三个色标各自标明原始kW。SVG中的热图为栅格图元，坐标和中文标签为矢量路径。

数据：figS1_annual_arrays.npz