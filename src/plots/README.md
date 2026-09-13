# 集中管理的绘图脚本

本目录是项目自写绘图代码的唯一维护位置，覆盖第一问、第二问与第三问。技能包内示例和第三方论文模板不属于项目计算绘图实现，保留其原目录。原求解入口继续可用；`src/q1/report.py`、`src/q1/analysis_report.py`、`src/q2/figures.py`的绘图部分仅保留调用兼容函数。

[第一问论文图集](../../outputs/processed/figures/q1/index.html) · [全项目23组图预览](../../outputs/processed/figures/index.html) · [全图清单CSV](figure_registry.csv) · [验收说明](../../docs/plots/acceptance.md)

## 第一问怎么选图

以下“必选”指本文结果表达的建议，不是题面新增的强制提交条款。题目表1、表2及144时段计划CSV继续独立保留。

- **必选：02 最优购电计划与储能运行轨迹。** 直接回答求得了怎样的调度方案，包含购电对照、充放电、145点储电状态及实际状态条。
- **建议放正文：03 费用瀑布图。** 解释三种方案与两个嵌套增量节约，附购电、弃光、费用指标；费用更低不代表购电量更少。
- **可选：01 输入特征图。** 用于说明富余光伏和日内电价差。
- **可选：04 设备单变量敏感性；05 联合等值线。** 论文讨论设备瓶颈时选用；若篇幅有限，优先04，深入讨论联合制约时再用05。
- **可选：06 效率稳健性；07 输入扰动热力图。** 放在相应敏感性分析段落或附录。
- **备查：08 固定模式局部诊断。** 存在25项与原MILP双侧扰动不匹配，不建议放入核心结果，也不作为通用充停放规则。

第一问不增加算法流程图，也不加入无对应论证的雷达、三维曲面、小提琴、相关性或帕累托图。

## 复现命令

在项目根目录运行：

```sh
python3 src/plots/run.py q1
python3 src/plots/run.py q2
python3 src/plots/run.py all
```

统一入口分别调用两问已经固定的依赖环境。`q1`输出8张论文图到`outputs/processed/figures/q1/`，数值设备扫描按输入和代码哈希缓存；只改配色或布局不会重新求解133个点。`q2`从已验收CSV重新绘制11张图，输出到`outputs/processed/figures/q2/`。`all`顺序执行两者并更新总图集。

原Q1四张报告图可独立复现到指定目录：

```sh
uv run --with-requirements src/q1/requirements.txt python src/plots/replot_existing.py q1 --output /tmp/q1_replot
uv run --with-requirements src/q1/requirements.txt python src/plots/verify.py
```

这些命令不覆盖`outputs/q1_current`、`outputs/q2_current`的不可变生成代。原有论文材料ZIP也保留原版，论文配图优先从新图集取用。

## 文件职责

- `q1_paper.py`：8张第一问论文图及配套CSV、必要性说明、HTML预览、来源哈希。
- `q1_legacy.py`：第一问原有4张组合图的唯一实现，保持原报告外观。
- `q2.py`：第二问11张数据诊断图的唯一实现，保持原结果外观。
- `common.py`：第一问新论文图的中文字体、语义配色、费用色阶、PNG/SVG导出。
- `replot_existing.py`：加载已验收CSV/JSON，重绘任一问的原有图。
- `run.py`：按两问固定环境执行的统一命令。
- `catalog.py`与`figure_registry.csv`：登记全部图的脚本、来源、文件位置与必要性。
- `verify.py`：磁盘回读验收；检查144功率区间、145状态点、单位换算、瀑布金额、设备解及绘图代码集中化。

设备MILP扫描属于数值计算，保存在`src/q1/device_sensitivity.py`，其中没有绘图代码。以后新增绘图实现必须放在本目录，并通过`catalog.py`登记脚本与数据来源。

## 配色与输出

所有项目绘图只生成PNG和SVG，不生成PDF；旧运行代内已存在的PDF仅保留历史追溯。

负荷深灰`#41464D`、光伏橙`#E69F00`、购电蓝`#0072B2`、充电青绿`#009E88`、放电紫`#8B5FBF`。费用色阶由浅青到深蓝，颜色越深费用越高；曲线同时用线型、正负方向和直接标签帮助辨认。

新图PNG为300 dpi；SVG使用矢量路径保存中文，不依赖阅读者本机字体。每张图有完整CSV来源和说明。没有置信区间数据就不绘制置信阴影；富余光伏填充明确说明含义。

## 设备敏感性口径

储电上限网格为6000至30000 kWh、步长2400 kWh；共同功率网格为1000至10000 kW、步长1000 kW，共110个真实MILP解。三条单变量曲线各12个点，共36行，含基准+100的局部点。共享重复参数后合计133个不同解；所有原始G/C/D/E/W/u保存在压缩NPZ，参数、费用、Gap和约束检查保存CSV。

扫描只改变指明边界，Emin=1200 kWh、首尾6000 kWh、两侧效率0.9及其他输入不变。Emax是储电上限；超过原额定容量的点仅为数学约束放宽实验，不能直接作为物理设备方案或投资建议。等值线仅在实际网格之间作绘图插值。

基准附近提高100 kWh储电上限节约65.504556元/日，提高100 kW充电功率节约5.646667元/日，提高100 kW放电功率节约0元/日。固定其余参数时，5000至10000 kW放电功率曲线平坦；储电上限在测试范围内仍有收益，不能声称已完全饱和。

## 第二问最终修订方案

`q2_dispatch.py`集中生成预测步长误差、季节方差、DHR残差、已完成真实回放4类图，格式仅PNG/SVG。命令：`python3 src/plots/run.py q2-dispatch --run-dir outputs/q2/dispatch_runs/20260911_224501`。读取本次独立运行CSV；部分回放明确标注完成天数，不将缺失日期补零。旧23图清单继续对应已验收的旧数据诊断与Q1图集，新4类图按运行目录figures/manifest.json登记。

## 第三问 v4

`q3.py` 根据第三问独立测试/正式运行目录中的 `diagnostics/forecast_metrics.csv` 绘制4×24预报误差热图，使用统一中文字体与PNG/SVG格式。每个运行目录的 `diagnostics/figures/manifest.json` 登记源码、原始CSV及SHA-256；不会改写既有两问图集。数据准备与图形复现入口：`python -m src.q3.run prepare --output outputs/q3/raw/diagnostics`。


## 问题二最终正文图（蓝色渐变版）

`q2_paper_data.py`从当前正式结果生成同预测起点统计、304共同日误差/PICP、真实压力日与全年矩阵；`q2_paper_final.py`按scientific-figure-making、scientific-visualization和matplotlib技能生成图5-1至5-5及附加热图，主色为多强度蓝色。PNG为400dpi，SVG中文转曲。`q2_paper_verify.py`核查原值、统计、SOC、计时对照与导出元数据。

图5-5经用户确认是4代表日的局部K对照，非全年。计时由`src/q2/benchmarks/horizon_for_figure.py`完成12个同机场景前缀实验，均3%认证；其他图不重求解。结果在`outputs/processed/figures/q2_paper_final_20260913/`，图集index.html、README、图注与源数据齐备。已通过catalog独立登记，不修改旧图集来源。

复现：`python -m src.plots.q2_paper_final --data-dir outputs/processed/figures/q2_paper_final_20260913/data --output-dir outputs/processed/figures/q2_paper_final_20260913`。本命令只重绘缓存数据。


## 第三问正文图与蓝色扩展图（2026-09-13）

`q3_paper_core.py`按用户补充文档输出图6-1/6-2/6-3（MAE同目标哑铃、B/P/C滚动窗口、客观代表日三联图）。用户已明确取消缺乏数据的FIV/OUV图6-4。`q3_paper_final.py`保留扩展图设计，交付选择高更新日、压力日分轴、月度费用和全年热图4张；敏感性仅以CSV交付。`q3_paper_data.py`按正式334日及预测共同333日准备数据，`q3_paper_verify.py`验证341原件SHA/物理/配对/导出；`q3_paper_package.py`汇集7图和README/方案/图注/CSV/源码。`catalog --register-manifest`现在按manifest的question登记Q3，默认Q2向后兼容。

缓存重绘：`python -m src.plots.q3_paper_core --data-dir outputs/processed/figures/q3_paper_final_20260913/data --output-dir outputs/processed/figures/q3_paper_final_20260913/core`。7张交付图的位置和数据见该目录delivery_manifest.json。
