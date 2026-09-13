# 全项目补充科研图：12张

本包含12张400dpi PNG、12张SVG、逐图图注、方案、数据CSV及绘图源码。中文为Fandol宋体，数学及单位保留英文；使用纯色曲线与无边框浅色区域。

用户要求立即交付：12张均已完成渲染且无缺字/错误日志；数据准备中1942条预测区间覆盖计数与原正式结果逐条一致。本轮尚未完成12张图逐张目视终审，不将其描述为视觉终审通过。

## 图件内容

- 补充图S01 全文信息边界总览：S01_information_boundaries.png
- 补充图S02 最坏分布与场景损失：S02_worst_distribution.png
- 补充图S03 全年DRO半径与风险溢价：S03_dro_annual_diagnostics.png
- 补充图S04 问题二/三储能运行图谱：S04_storage_Q2_Q3.png
- 补充图S05 问题四双策略储能运行图谱：S05_storage_Q4-2_Q4-3.png
- 补充图S06 动态SOC裕度与风险事件：S06_dynamic_reserve_and_risk.png
- 补充图S07 极端日期风险贡献：S07_tail_risk_concentration.png
- 补充图S08 紧急事件持续时间与能量：S08_emergency_event_geometry.png
- 补充图S09 预测区间季节校准：S09_seasonal_interval_calibration.png
- 补充图S10 容量/功率边际收益：S10_capacity_power_marginal_gains.png
- 补充图S11 固定模式边际值与重优化核查：S11_marginal_value_validation.png
- 补充图S12 费用与跨日库存联动：S12_inventory_cost_coupling.png

## 其他文件

- captions.md：每张图的真实统计口径及不可推导的结论。
- 补充图方案.md：12张图设计方案及用户确认的中文语言。
- data/：全部绘图数据，provenance.json记录1020项原始来源哈希；重建与整理未启动优化求解。
- src/plots/：绘图与只读数据处理代码，字体辅助来自q4_paper_final.py。
- index.html/status.json：本机进度图集；如浏览器限制file协议读取JSON，请使用本地HTTP服务器。

这些补充图不替换各问原图。不同问题的电价、初始库存链、信息和策略不同，不直接用总费用做跨问优劣排序。DRO风险溢价不是实际收益；Q3仍有未认证节点。详见图注。SVG文字已转曲；现成图件不需要安装字体。源码重绘需原TeX字体及NumPy/Pandas/Matplotlib环境。
