# Q1 边际价值强化版运行与输入输出说明

当前依据 [第一问_MILP_边际价值强化版.md](../final/第一问_MILP_边际价值强化版.md)。本次使用模型已声明的右端点、零阶保持、母线侧充放电量、双单程0.9效率、不售电和允许弃光假设。功率上限按5000/6准确计算；本轮遵从用户明确要求仅交付CSV，不采用review中的XLSX建议。没有增加电池损耗费用、售电、二级吞吐量目标或其他建模假设。

在项目根目录执行：

```sh
uv run --with-requirements src/q1/requirements.txt python src/q1/run.py
```

运行针对性验收：

```sh
uv run --with-requirements src/q1/requirements.txt python -m unittest discover -s src/q1 -p 'test_*.py' -v
```

首次运行由uv提供锁定版本的numpy、scipy、openpyxl、matplotlib。openpyxl仅在代码中读取题目原始附件；不调用Office，不生成Excel结果。所有结果表用CSV写入并关闭回读。本次环境为Python 3.12，具体版本与源文件SHA-256见 `outputs/q1/raw/run_manifest.json`。运行入口是 `src/q1/run.py`，根目录原有空文件 `main.py` 未改动。

| 文件 | 内容 |
|---|---|
| `inputs/q1/raw/attachment1.csv` | 原附件144行时间、电价、负荷功率、光伏预测功率的CSV副本 |
| `inputs/q1/processed/timeseries.csv` | 144时段映射及kW→kWh后的完整输入 |
| `inputs/q1/processed/parameters.json` | 模型参数、分量纲容差、CSV交付决定和分析口径 |
| `outputs/processed/q1/result1.csv` | 完整输入与六类决策变量、时段初末储量、SOC和费用，共144行 |
| `outputs/processed/q1/daily_summary.csv` | 全日电量、费用、充放电量、弃光、损耗及0:00/24:00储量 |
| `outputs/processed/q1/table1_purchase.csv` | 10、12、14、16、18、20点开始的六个10分钟区间购电量 |
| `outputs/processed/q1/table2_storage.csv` | 六个4小时区间的充电量和放电量 |
| `outputs/processed/q1/efficiency_comparison.csv` | 主模型、0.85、0.95、sqrt(0.9)四情景汇总 |
| `outputs/q1/raw/schedule_*.csv` | 各效率情景完整144时段轨迹 |
| `outputs/q1/raw/solution_*.json` | 原始求解变量、目标值、下界、gap和求解器设置 |
| `outputs/q1/raw/validation.json` | 四情景物理与最优性检查、CSV关闭后回读检查 |
| `outputs/q1/raw/tests.json` | 解析测试、压力测试与篡改拦截测试结果 |
| `outputs/processed/q1/dispatch.png/.svg` | 输入功率、电价、调度及储电量图 |
| `outputs/processed/q1/efficiency.png/.svg` | 效率成本对比和储电轨迹图 |
| `outputs/processed/q1/report.html` | 可直接打开的输入输出报告，表格可展开及滚动 |
| `docs/1/deliverables/q1_results.md` | 结果表与合理性说明 |
| `docs/1/deliverables/q1_implementation_acceptance.md` | 逐项验收、挖洞和假设审查 |
| `docs/1/deliverables/q1_source_line_traceability.csv` | 154个展示公式及关键行内公式与精确代码行、单元测试、本代证据的对应索引 |

CSV使用UTF-8无BOM、逗号分隔；小数点为英文句点，数值字段不使用千位分隔符。文件保留浮点求解精度，报告显示6位小数。CSV的最后一行 `23:50-24:00` 属于本日最后一个10分钟时段。

`result1.csv` 字段：

| 字段 | 含义/单位 |
|---|---|
| t | 1至144的时段编号 |
| source_excel_row | 原始附件行号（含表头） |
| source_endpoint | 原附件时间标签，原Excel time类型转换为文本后可能包含秒 |
| interval | 本时段半开区间 `[开始, 结束)` 的文本标签 |
| start_minute / end_minute | 自当日0:00起的分钟数 |
| price_yuan_per_kwh | 本时段购电单价，元/kWh |
| load_kw / pv_kw | 原始负荷功率/光伏预测功率，kW |
| load_kwh / pv_kwh | 零阶保持换算后的负荷/光伏电量，kWh |
| G_kwh | 外网购电量，kWh |
| C_kwh | 微网母线送入储能设备的电量，kWh |
| D_kwh | 储能设备送至微网母线的电量，kWh |
| E_kwh | 时段结束后的电池内部储电量，kWh |
| W_kwh | 弃光电量，kWh |
| u | 二元运行状态，1允许充电、0允许放电；空闲时可取任一值，保留求解器浮点表示 |
| E_start_kwh | 时段开始时的电池内部储电量，kWh |
| soc_fraction | E_kwh/12000；比例值，0.5即50% |
| cost_yuan | price_yuan_per_kwh×G_kwh，元 |

四小时区间内可以有不同10分钟时段分别充电和放电，因此表2中同一行充电总量与放电总量都为正不代表违反互斥。

程序将附件的缺失、负电价、负功率、时间重复、错位及非数值数据视为错误，不自动填补。所有输入副本、解、分析、CSV及生成文档在 `outputs/.q1-runs/run-*` 内暂存。数值检查、文件回读及当前代码测试通过后，单次 `os.replace` 切换 `outputs/q1_current` 链接。既有输入/输出路径与生成文档为该指针的固定别名，2026-09-11清理后，`.q1-runs`保留当前版、上一版和`legacy_before_atomic`；更早运行的必要记录压缩归档至`outputs/history/run_records_20260911.tar.gz`。此次为一次性清理，生成器仍会保留后续新运行代。程序内读取者应先resolve一次generation再读所有文件。失败运行不会标为本轮成功，旧结果仍可访问，须以manifest代号判断结果所属运行。首次迁移会保留旧目录到 `legacy_before_atomic`。

求解器使用HiGHS，要求MIP相对gap为0；原生整数、原始与对偶可行性容差均为1e-9，独立物理容差为1e-6 kWh、费用1e-6元、二元变量1e-8、相对Gap 1e-6、边际价值1e-6元/单位、无量纲比例1e-8。容差属于数值实现设置，不改变数学约束。最优性是针对该模型、该数据及已声明数值容差的证书；不表示最优策略唯一。

## 新版11.3–11.8分析交付

运行同一入口会完整生成以下分析。每种效率与负荷、光伏的−5%/0/+5%交叉组合，共36情景；每个情景都重新求解MILP、核验物理与最优性、固定最优模式提取边际量，并分别提高E_max、降低E_min、提高充电功率和放电功率。全部36情景均使用1/10/100三步长，共432次放宽实验；正式解的安全范围不改变。

| 路径（项目根目录起） | 行数/用途 |
|---|---|
| `outputs/processed/q1/baseline_comparison.csv` | 3个嵌套基准的成本与电量 |
| `outputs/processed/q1/incremental_benefits.csv` | 两步增量收益与总节约；不是唯一因果归因 |
| `outputs/processed/q1/lp_diagnosis.csv` | LPR目标、整数间隙、分数u、同时充放电数 |
| `outputs/processed/q1/marginal_values.csv` | 5184行：36×144局部μ、λ、充放阈值、实际动作、模式限制和边界活跃 |
| `outputs/processed/q1/marginal_rhs_validation.csv` | 288个等式方向，各有±0.01kWh两侧差分、状态和影子价格区间复核 |
| `outputs/processed/q1/milp_rhs_validation.csv` | 288项原MILP双侧重求：576次允许模式变化的求解及固定影子价匹配标记 |
| `outputs/processed/q1/bottleneck_values.csv` | 432次单边界放宽的原/新成本、节约、单位日价值、活跃时段及瓶颈判定 |
| `outputs/processed/q1/sensitivity_scenarios.csv` | 36组J/G/C/D/W、SOC边界、价格倍率、四类边界价值、动作与轨迹差异 |
| `outputs/processed/q1/normalized_sensitivity.csv` | 8行：四种效率下的负荷和光伏归一化成本敏感度 |
| `outputs/processed/q1/active_constraints.csv` | 5184行：每个情景每个时段的四种边界活跃标记 |
| `outputs/processed/q1/arbitrage_thresholds.csv` | 576行：四种效率下当前价格、未来价格阈值、当天未来可盈利时段数 |
| `outputs/q1/raw/analysis_schedules.csv` | 5184行：各情景真实扰动输入和G/C/D/E/W/u全量输出 |
| `outputs/q1/raw/analysis_solutions.json` | 基准、LPR、36情景、固定模式LP及432个放宽MILP的完整原始解 |
| `outputs/q1/raw/analysis_validation.json` | 物理/最优性、LP原始对偶检查、双侧差分和CSV回读记录 |
| `outputs/q1/raw/test_log.txt` | 本轮全部单元和集成测试日志；含36情景、432次放宽、576个RHS重求结果及故障注入 |
| `outputs/processed/q1/analysis_summary.json` | 完整分析汇总与数值设置 |
| `outputs/processed/q1/marginal_report.html` | 可展开的边际价值报告、36情景表和全部CSV入口 |
| `outputs/processed/q1/marginal_analysis.png/.svg` | 阈值、基准费用和负荷×光伏热力图 |
| `outputs/processed/q1/bottleneck_analysis.png/.svg` | 四种边界、三种放宽步长的价值对照图 |
| `docs/1/deliverables/q1_marginal_analysis.md` | 经济解释、非预期趋势和局限 |

情景名如 `eta085_l95_pv105` 表示单程效率0.85、负荷为原输入95%、光伏为105%。`analysis_schedules.csv` 的G/C/D/E/W单位为kWh，u为0/1；前缀输入字段单位与主结果一致。`*_value`和`value_per_unit_day`中容量为元/(kWh·日)、功率为元/(kW·日)，两种单位不可直接比较设备投资优先级。`multistep_stable`表示三步单位价值极差≤边际数值容差；`numerical_bottleneck`表示活跃且多步长稳定正值。`economic_bottleneck`为空，`economic_significance`明确未判定：没有设备成本或题目规定的经济门槛，不能将数值非零当成经济显著。

`mu_yuan_per_kwh`是增加母线需求的局部成本，`lambda_yuan_per_kwh`是状态等式额外内部注入的局部价值；后者是状态等式右端项导数的负值。`charge_threshold=eta_c*lambda`，`discharge_threshold=lambda/eta_d`。固定模式只允许一个动作方向；`mode_blocks_tendency=1`说明严格阈值倾向指向当前模式不允许的方向。等号处用`indifferent_boundary`标注，不强制归为实际待机。

活跃容差为1e-6kWh。RHS差分的空值表示该方向不可行，相应status=2；status=0表示最优。固定模式LP的非光滑处检验负向斜率≤影子价≤正向斜率（仅检验可行方向），不强制两侧相等。容量/功率结果来自重求完整MILP，不把固定模式影子价格当成全局设备扩容价值。

全部数值设置见 `inputs/q1/processed/parameters.json` 的 `analysis_settings`。主CSV与分析CSV使用真实附件输入，不掺入测试用合成算例。


原MILP值函数不假设凸性：`milp_rhs_validation.csv`保留两侧原始差分以及换算后的μ/λ；λ为状态RHS导数的负值。`fixed_shadow_matches_milp_both_sides=0`表示该点不能同时通过两侧比较，不能把其固定模式阈值解释为原MILP的唯一整体阈值。

绘图采用独立临时目录，失败会删除半成品图形，在 `figure_status.json` 和两份HTML报告中给出原因，正确的数值结果照常通过测试后发布。运行纯数值流程：

```sh
uv run --with-requirements src/q1/requirements.txt python src/q1/run.py --no-plots
```

本地字体缺失时安装可用中文字体后重跑默认命令即可补齐图形。默认完整图形需要Matplotlib；数值入口和报告不在模块导入阶段加载它。审查与实测状态见 [逐条处理记录](q1_implementation_acceptance.md)。

绘图格式按用户要求统一为PNG和SVG，不再生成PDF。当前旧运行代中的PDF是历史产物，不是后续交付要求。
