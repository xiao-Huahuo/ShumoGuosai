# 问题四科研图：蓝莲花渐变与LaTeX字体

包含6张完整科研图，各有400dpi PNG和SVG，另附做图方案、逐图图注、图后分析、数据及重绘代码。选取用户ThemeDisplayer中的Blue Lotus与月白深蓝配色；中文直接采用TeX Live的Fandol宋体，英文/数字Latin Modern，数学Computer Modern，未使用微软雅黑。

## 图件

| 文件名（均有PNG/SVG） | 内容 | 正文建议 |
|---|---|---|
| fig7_1_joint_dro_mechanism | 严格因果预测、联合误差DRO、双机制窗口、结算与物理执行流程 | 推荐正文 |
| fig7_2_price_clock_and_density | 24小时电价时钟与48096点预测密度 | 电价预测章节 |
| fig7_3_cost_change_bridge | 费用分项变化桥图与334日配对差ECDF | 推荐正文 |
| fig7_4_energy_flow_and_entitlement | 实际电量守恒流带及调用/未用额度拆分 | 物理语义或附录 |
| fig7_5_high_risk_panorama | 7月1日价格、采购、净充放电、SOC四行全景 | 推荐正文 |
| fig7_6_radius_cost_risk_paths | 0.75/1/1.25ρ*的局部成本—紧急风险轨迹 | 敏感性章节 |

## 文档与数据

- `问题四科研图方案.md`：配色、字体、图形选择、真实数据范围与验收标准。
- `captions.md`、`图后分析与使用建议.md`：完整图注、可用的图后分析及结论边界。
- `ThemeDisplayer.html`：用户提供的配色页原件，图件只引用其中颜色。
- `index.html`：解压后直接打开的离线预览图集。
- `data/dispatch_4-2.csv`、`dispatch_4-3.csv`：两套正式334日×144段全量轨迹。
- `data/daily_*.csv`、`daily_cost_pairs.csv`、`strategy_summary.csv`：每日结算、逐日费用差与总量。
- `data/hourly_prices.csv`、`price_clock.csv`：每小时6个时段均值及334日分位汇总。
- `data/energy_flow.csv`：全年真实母线流入/流出AC侧电量；未调用额度另见strategy_summary。
- `data/riskday_*.csv`、`riskday_soc_*.csv`：两策略7月1日原始轨迹及各自含日初的145点SOC。
- `data/local_sensitivity.csv`：已做Q4半径与联合权重实验共30行含基准；图7-6只取18条半径记录。
- `data/solver_quality.csv`：1670个正式最优节点，保留场景数、半径、ESS、初态和执行长度。
- `data/provenance.json`：来源、模型配置、统计口径、选日规则和682个原始文件SHA-256。
- `manifest.json`：各图与CSV/脚本的映射；`verification.json`：独立数值与导出检查；`acceptance.md`：逐项需求与视觉审查。
- `src/plots/`：UTF-8源代码；`requirements.txt`：绘图环境版本。
- `file_manifest.csv`：包内每个文件的SHA-256，便于完整性核验。

## 口径

正式范围为2025年2月1日至12月31日，共334日。4-2使用完成并验收的v2结果，4-3使用v3结果，全部1670节点Optimal。两套策略初始SOC都为6000，但各自库存链不同、最终库存也不同，因此费用差是完整策略实际表现，不是纯信息价值FIV/OUV。

图7-4中未调用额度unused不是实际弃电spill，不进入物理能量母线；流图不虚构来源到具体设备的分配。日内时钟分位带是跨日分布范围，非置信区间。敏感性为少量代表日局部实验，不能外推全年参数稳健。

PNG可直接插入论文。SVG文字已转曲，不依赖本机字体；渐变色带等包含高分辨率栅格填充，轮廓/坐标/文字为矢量。图中透明色已按白底导出。请在最终插图尺寸检查字号，勿过度缩小多面板。

## 重绘

安装requirements所列库后，在解压目录执行：

```sh
python -m src.plots.q4_paper_final --data-dir data --output-dir redraw
```

脚本优先读取解压目录下`assets/q4_fonts/FandolSong-Regular.otf`和`assets/q4_fonts/lmroman10-regular.otf`，否则读取本机`/usr/local/texlive/2026/`同名字体。字体文件不包含在ZIP内；可使用自己的TeX Live字体。现成PNG/SVG不需要安装字体。

数据准备与原始文件验证脚本需要完整项目路径，离线重绘只需本包data目录；不调用求解器。此前所有结果和ZIP均未覆盖。
