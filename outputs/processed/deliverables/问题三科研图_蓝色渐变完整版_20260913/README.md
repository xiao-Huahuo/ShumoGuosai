# 第三问科研图 ZIP

包含3张正文核心图和4张扩展备选图，每张提供400dpi PNG及SVG。主色为多强度蓝色；核心图按补充文档改为宋体与Times New Roman。

**图6-4（FIV/OUV）经用户明确要求取消。** 当前没有全年配对反事实数据，本包没有用预测误差、调整费用或示意数据替代，也没有为此启动新实验。

## 文件内容

| 路径 | 内容 |
|---|---|
| 核心图/ | 图6-1同目标预报误差增益、图6-2 B/P/C滚动窗口、图6-3同日预报—购电—储能三联图；正文优先使用 |
| 扩展备选图/ | A1高更新日实例、A2压力日分轴、A3月度费用、A4全年热图；可选用，不建议全塞正文 |
| 第三问科研图方案.md | 最终图组方案、客观选日规则、插入位置与统计范围 |
| 第三问_必须绘制的核心图及绘图细节.md | 用户提供的原始清单原样保存；其中图6-4被后续用户回复取消 |
| 图后分析与论文插入建议.md | 每张图的“看到什么—如何解释—支持什么”文字 |
| captions.md | 7张交付图的完整图注 |
| data/forecast_*.csv | 333共同日的31968条小时预报/真值配对与96格MAE/RMSE/Bias |
| data/revision_*.csv | 每节点1998条同目标旧/新配对与统计，18点近零绝对量保留 |
| data/typical_*.csv | 代表日144时段、145点SOC、当块小时预报及四日距离/标准化尺度 |
| data/pressure_*.csv、update_*.csv | 两个扩展实例日的真实运行、原始预报与节点政策 |
| data/formal_dispatch.csv | 正式334日×144段全量实际执行，含SOC、费用、g0与最终grid差值 |
| data/formal_daily.csv、monthly_costs.csv | 日度与月度结算汇总 |
| data/formal_solver_quality.csv | 1336节点求解状态；847认证、489限时可行 |
| data/local_sensitivity.csv | 已完成Q3三因素、四代表日的36条记录，含12条基准；按新清单以表交付，不额外堆敏感性图 |
| data/execution_config.json、provenance.json | 正式模型配置、来源及341项源文件SHA-256 |
| src/plots/ | 绘图、数据准备、核验及打包源码，均UTF-8 |
| requirements.txt | 原绘图环境版本 |
| manifest.json、verification.json、acceptance.md | 图目与文件映射、数值/导出校验、逐条需求验收 |
| index.html | 解压后可直接打开的离线图集 |
| file_manifest.csv | 包内逐文件SHA-256，校验运输完整性 |

## 口径与使用

正式费用及热图仅含2025-02-01至12-31共334日。预测比较采用共同333日起点；小时目标与真实小时右端点一致。核心图6-3日期3月20日由指定四日与全年中位运行状态的距离客观选择。

所有图展示已执行可行结果，存在489个未达到3%证书的节点，不宣称全节点严格最优。负调整费用是结算返还，不是总利润。18点夜间光伏近零，预测相对改善不能直接解释为经济信息价值。局部S保持用户批准的10/20/28，终端库存差异不能忽略。

PNG可直接插入文档，SVG文字已转曲，可缩放；SVG热图矩阵按原像素嵌入，文字及线条为矢量。请在论文最终插入尺寸下检查字号，避免过度缩小多面板图。

## 从本包数据重绘

在解压目录安装requirements.txt所列库后运行（不调用求解器）：

```sh
python -m src.plots.q3_paper_core --data-dir data --output-dir redraw/core
python -m src.plots.q3_paper_final --data-dir data --output-dir redraw/extended
```

核心图重绘需要本机安装Times New Roman与宋体Songti SC；现成PNG/SVG无需字体。扩展脚本会复现最初设计的七张图，实际交付只选A1–A4，映射见manifest；不据此恢复已取消的FIV/OUV图。

q3_paper_data和q3_paper_verify用于完整项目环境中的原始文件追溯，需原项目数据路径；本包足够离线重绘，无需重新优化。正式结果与之前交付ZIP均未覆盖。
