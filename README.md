# README

本项目保存数学建模题目资料、模型文档、输入输出、求解代码和论文模板。第一问入口为 `src/q1/run.py`；第二问新最终方案入口为 `src/q2/dispatch.py`，旧 `src/q2/run.py` 保留数据诊断。第三问[七小时比赛生产救援](docs/3/production_rescue/report.md)已完成：全年主轨迹实际用3小时18分39秒，正式结果334日、48,096行，[`result3.xlsx`](outputs/q3/raw/full_priority_rescue_7h_20260912/main/result3.xlsx)四表回读及全年物理验收通过。其1,336个正式节点有847个取得3%证书，489个只是经原物理与完整矩阵验证的限时可行解，不得写成3%解。

### 项目目录树（持续维护）

下列目录树逐文件覆盖题目资料、模型、输入、结果、源码和论文模板。技能包、技能来源说明、本机IDE配置和不可变运行历史按目录汇总；逐日期影子预测/求解审计与运行代按目录汇总，完整明细见第二问revision_work/file_inventory.csv；Git内部对象、Python缓存与系统缓存不属于核心文件。所有列出的文件和文件夹均附用途说明。

```text
ShumoGuosai/  # 数学建模项目根目录；两问计算与全项目科研绘图集中管理
├── README.md  # 项目总览与核心目录树；文件变化后持续同步
├── AGENTS.md  # 代理执行规则、需求逐项验收及UTF-8要求
├── CLAUDE.md  # 项目协作与代码修改规则
├── 数学建模开发规范.md  # 建模、代码目录、结果审查、绘图及变更记录规范
├── .gitignore  # 忽略本地技能、IDE配置、技能来源及根目录outputs计算输出
├── skills-lock.json  # 本地技能安装来源与版本锁定信息
├── docs/  # 题目资料、模型文档、使用说明和变更记录
│   ├── 1/  # 第一问文档；按最终、交付、中间、清理候选四类管理
│   │   ├── README.md  # 第一问逐文件分类说明与阅读导航
│   │   ├── final/  # 正式模型原稿；强化版为当前唯一执行依据，上一版保留追溯
│   │   │   ├── Q1最终优化模型-最终版.md  # 上一版MILP原稿；内容保留，当前执行强化版
│   │   │   └── 第一问_MILP_边际价值强化版.md  # 当前最新版；MILP、局部边际阈值、经济瓶颈与36组稳健性分析
│   │   ├── deliverables/  # 当前结果说明、复现文档和验收附件
│   │   │   ├── q1_implementation_acceptance.md  # 24条review验收、25项测试、P0–P3与假设及浏览器检查
│   │   │   ├── q1_results.md  # 正式计算结果、题目表1/表2及效率对比
│   │   │   ├── q1_run_guide.md  # 运行命令、输入输出路径、CSV字段和单位说明
│   │   │   ├── q1_source_line_traceability.csv  # 154个展示公式及5项行内判据到精确代码行、测试和运行证据
│   │   │   ├── q1_marginal_analysis.md  # 新版基准收益、边际机制、瓶颈及非预期敏感性趋势解释
│   │   │   ├── q1_code_review_resolution.csv  # 24条原review逐项处理、精确代码行、测试及当前运行证据
│   │   │   └── q1_paper_materials.md  # 第一问论文材料入口、题目逐项对应与本次整理验收
│   │   ├── intermediate/  # 历史模型与旧稿评审；不作为当前求解依据
│   │   │   ├── Q1_最终优化模型_结合comments.md  # 历史规范化能流、LP松弛与二级目标版本
│   │   │   ├── Q1_最终优化模型修订版_结合评审comments.md  # 历史LP路线的进一步修订稿
│   │   │   ├── Q1_精简修订版_公式兼容Obsidian.md  # 历史模型精简稿与Obsidian公式排版版本
│   │   │   ├── q1_compact_review_comments.md  # 当时精简稿的评审意见及实验说明
│   │   │   ├── 临时方案.md  # 早期方案；包含LP、KKT、对偶与敏感性分析
│   │   │   ├── 临时方案_严格审查报告.md  # 当时临时稿的审查意见与风险证据
│   │   │   ├── marginal_value_work/  # 强化版开发过程记录；完成后用于追溯
│   │   │   │   ├── notes.md  # 边际符号、分析范围、计算发现及限制记录
│   │   │   │   └── task_plan.md  # 强化版逐项实现计划与验收进度
│   │   │   └── code_review_work/  # 本轮review原件与修改前源码备份；不作为当前运行结果
│   │   │       ├── Q1_code_review_comments.csv  # 用户提供的24条审查意见原始CSV；其中XLSX建议被用户覆盖
│   │   │       └── pre_review_sources.tar.gz  # 本轮修改前源码和相关文档的备份；用于对照与追溯
│   │   └── cleanup_candidates/  # 已结束任务的过程笔记；候选清理但尚未删除
│   │       ├── notes.md  # 实现过程发现摘要；有效信息已进入交付文档
│   │       └── task_plan.md  # 已经全部完成的任务计划与过程记录
│   ├── CUMCM2026Problems/  # A至E题原题、随题附件和格式文件
│   │   ├── A题/  # A题原始题目资料
│   │   │   ├── 附件/  # A题随题提供的原始数据与附件
│   │   │   │   ├── 附件3/  # A题随题提供的结果模板目录
│   │   │   │   │   ├── result1.xlsx  # A题随题提供的result1结果模板；原件保留
│   │   │   │   │   ├── result2.xlsx  # A题随题提供的result2结果模板；原件保留
│   │   │   │   │   ├── result3.xlsx  # A题随题提供的result3结果模板；原件保留
│   │   │   │   │   └── result4.xlsx  # A题随题提供的result4结果模板；原件保留
│   │   │   │   ├── 附件1.xlsx  # A题原始附件1数据/说明文件
│   │   │   │   └── 附件2.xlsx  # A题原始附件2数据/说明文件
│   │   │   └── A题.pdf  # A题原始题面PDF
│   │   ├── B题/  # B题原始题目资料
│   │   │   ├── 附件/  # B题随题提供的原始数据与附件
│   │   │   │   ├── 附件1.docx  # B题原始附件1数据/说明文件
│   │   │   │   └── 附件2.docx  # B题原始附件2数据/说明文件
│   │   │   └── B题.pdf  # B题原始题面PDF
│   │   ├── C题/  # C题原始题目资料
│   │   │   ├── 附件/  # C题随题提供的原始数据与附件
│   │   │   │   ├── 附件5/  # 原题结果模板；当前Q1按用户要求改用CSV交付
│   │   │   │   │   ├── result1.xlsx  # C题随题提供的result1结果模板；原件保留
│   │   │   │   │   ├── result2.xlsx  # C题随题提供的result2结果模板；原件保留
│   │   │   │   │   ├── result3.xlsx  # C题随题提供的result3结果模板；原件保留
│   │   │   │   │   ├── result4-2.xlsx  # C题随题提供的result4-2结果模板；原件保留
│   │   │   │   │   └── result4-3.xlsx  # C题随题提供的result4-3结果模板；原件保留
│   │   │   │   ├── 附件1.xlsx  # 一天电价、负荷与光伏预测；当前Q1的原始数据来源
│   │   │   │   ├── 附件2.xlsx  # 2025年全年负荷与实际光伏数据；供后续问题使用
│   │   │   │   ├── 附件3.xlsx  # 不同发布时刻的未来24小时光伏预报；供后续问题使用
│   │   │   │   └── 附件4.xlsx  # 波动电价数据；供第四问使用
│   │   │   └── C题.pdf  # C题原始题面PDF
│   │   ├── D题/  # D题原始题目资料
│   │   │   ├── 附件/  # D题随题提供的原始数据与附件
│   │   │   │   ├── 附件2/  # D题随题提供的结果模板目录
│   │   │   │   │   ├── result1.xlsx  # D题随题提供的result1结果模板；原件保留
│   │   │   │   │   ├── result2.xlsx  # D题随题提供的result2结果模板；原件保留
│   │   │   │   │   ├── result3.xlsx  # D题随题提供的result3结果模板；原件保留
│   │   │   │   │   └── result4.xlsx  # D题随题提供的result4结果模板；原件保留
│   │   │   │   └── 附件1.xlsx  # D题原始附件1数据/说明文件
│   │   │   └── D题.pdf  # D题原始题面PDF
│   │   ├── E题/  # E题原始题目资料
│   │   │   ├── 附件/  # E题随题提供的原始数据与附件
│   │   │   │   ├── 附件2/  # E题随题提供的结果模板目录
│   │   │   │   │   ├── result2.xlsx  # E题随题提供的result2结果模板；原件保留
│   │   │   │   │   ├── result3.xlsx  # E题随题提供的result3结果模板；原件保留
│   │   │   │   │   └── result4.xlsx  # E题随题提供的result4结果模板；原件保留
│   │   │   │   └── 附件1.xlsx  # E题原始附件1数据/说明文件
│   │   │   └── E题.pdf  # E题原始题面PDF
│   │   └── format2026.doc  # 随题提供的2026格式文件
│   ├── CHANGE_HISTORY.md  # 按现状、实施方案、完成状态记录每次任务
│   ├── C题.md  # C题题面转写、各问要求与储能参数附录
│   ├── 数学建模技能清单.md  # 本地技能分类、用途与选用参考
│   ├── 2/  # 第二问最终修订方案、新实现记录与旧诊断阶段追溯
│   │   ├── README.md  # 唯一最终方案导航及新旧验收边界
│   │   ├── final/  # 用户原方案及其后授权的精度与等价执行提速修订
│   │   │   ├── 计算执行提速修订_延迟K1与基准复用.md  # 固定K2未通过；延迟K1与共享基准的依据和验收
│   │   │   ├── 求解精度执行修订_3pct.md  # 当前后续3%门槛；旧1%/2%前缀保留与正式续算验收
│   │   │   ├── 求解精度执行修订_2pct.md  # 后续2%求解门槛、旧结果保留及选择和验收证据
│   │   │   └── 第二问_最终建模思路_最高优先级修订版_修订后.md  # 新模型完整原文，逐字节归档
│   │   ├── revision_work/  # 新最终方案的实施、审查与验证
│   │   │   ├── task_plan.md  # 实现与真实实验进度
│   │   │   ├── notes.md  # 工程选择、求解瓶颈与真实发现
│   │   │   ├── run_guide.md  # prepare、run、具名实验、报告与续算说明
│   │   │   ├── linear_milp_equivalence.md  # 补算线性MILP的物理上界推导、等价证明及真实1%证书
│   │   │   ├── timing_audit.md  # 阶段耗时、主计算与实验分开计时及容量估算
│   │   │   ├── precision_pair_acceptance.md  # 本轮1%/3%小量对比的逐句、假设、结果和界面验收
│   │   │   ├── compute_change_acceptance.csv  # 用户试验、自动应用和持续运行要求逐句验收
│   │   │   ├── precision_change_acceptance.csv  # 用户精度调整逐句实现和实际验收对应
│   │   │   ├── acceptance.md  # 逐项、P0—P3、假设与实际界面审查
│   │   │   ├── tests.txt  # 当前全部Q2测试日志
│   │   │   ├── full_run_ui_smoke.json  # 全量队列实际浏览器29任务、依赖及并行进程验收
│   │   │   ├── full_run_acceptance.csv  # 用户本次自主全量要求逐句对应代码与真实证据
│   │   │   ├── ui_smoke.json  # 新报告真实浏览器、图片与CSV下载验证
│   │   │   ├── file_inventory.csv  # 新源码、文档与运行目录逐文件清单快照
│   │   │   ├── pre_full_run_sources.tar.gz  # 本轮存档恢复和追加预算入口修改前源码备份
│   │   │   └── pre_revision_sources.tar.gz  # 新建模开发前原实现与文档备份
│   │   ├── dierwen1.md  # 第二问2.1数据预处理与时间序列诊断的指定执行方案
│   │   ├── notes.md  # 实施决策、算法依据、实算发现与限制
│   │   ├── task_plan.md  # 逐项实施与验收计划、修复记录
│   │   ├── implementation_acceptance.md  # 逐句验收、P0–P3、假设与实际界面检查
│   │   ├── run_guide.md  # 完整运行命令、CSV字段、模型接入与严格信息边界
│   │   └── verification.json  # 最终文件、哈希、链接、目录与实际浏览器验收记录
│   ├── 3/  # 第三问v4实现、主计算恢复与独立检验
│   │   ├── Q3_第三问_最终建模_严格修订终稿_v4.md  # 唯一建模依据，原文保留
│   │   ├── task_plan.md  # 实现阶段、约束和错误修复记录
│   │   ├── notes.md  # Q2继承、用户确认标定、数据边界与计时发现
│   │   ├── implementation_report.md  # 执行口径、验收、P0—P3和运行命令
│   │   ├── source_line_acceptance.csv  # 模型全部非空行到实现及验收对应
│   │   ├── traceability_audit.json  # 模型/源码SHA及映射完整性
│   │   ├── tests.txt  # 数学性质、因果、真实组件、模板和续算测试
│   │   ├── ui_smoke.json  # 真实本地报告页面与图像验收
│   │   ├── full_run/  # 主计算优先、3%精度与全量启动验收
│   │   │   ├── task_plan.md  # 用户授权、检查点与启动验收计划
│   │   │   ├── notes.md  # 本轮运行约束和保存机制发现
│   │   │   ├── execution_protocol.md  # 当前3%规则、冻结运行、恢复命令与检验移交
│   │   │   ├── tests.txt  # 42项基础/并行/恢复的完整测试日志
│   │   │   ├── tests_base.txt  # 新恢复实现的基础32测试日志
│   │   │   ├── tests_recovery.txt  # 最初8项恢复核验日志
│   │   │   ├── tests_recovery_final.txt  # 含事件快照和监督强杀恢复的10测试
│   │   │   └── ui_smoke.json  # 正式主进度实际页面验证
│   │   ├── validation/  # 用户最终检验文档与独立检验队列
│   │   │   ├── Q3_第三问_模型检验与实验方案_最终版.md  # 用户原文，复制后逐字节验证
│   │   │   ├── source_manifest.json  # 原文件SHA与原样归档记录
│   │   │   ├── task_plan.md  # 模块接入、范围选择和主任务隔离
│   │   │   ├── notes.md  # 检验需求及解释边界
│   │   │   ├── report.md  # 模块、队列状态、抽样/全年口径说明
│   │   │   ├── source_acceptance.csv  # 383条非空源行到实现定位
│   │   │   ├── acceptance.json  # 归档/模块/范围与主隔离验收
│   │   │   ├── tests.txt  # 新检验4项有界测试日志
│   │   │   └── ui_smoke.json  # 主进度、待正式审计和预报图实际UI验收
│   │   ├── compute_rescue/  # 卡点等价编码优化、迁移恢复及实时看板
│   │   │   ├── task_plan.md  # 逐项实施与恢复验收
│   │   │   ├── notes.md  # 原卡点及等价编码依据
│   │   │   ├── report.md  # 等价证明、需求映射、实测与未完成项
│   │   │   ├── bottleneck_audit.json  # 旧卡点82.6分钟、主链06节点与FD耗时归因
│   │   │   ├── parallel_solver_report.md  # HiGHS1.15.1实际四线程、迁移与54项验收
│   │   │   ├── solver_comparison.csv  # 固定节点、方法、耗时、gap与真实证书对比
│   │   │   ├── tests_highs115.txt  # 新版数学与多核回调7测试
│   │   │   ├── tests_highs115_base.txt  # 新版环境基础23测试
│   │   │   ├── tests_highs115_recovery.txt  # 原恢复/并行/检验23测试
│   │   │   ├── tests_highs115_sigkill.txt  # 新版4线程强杀与恢复实测
│   │   │   ├── migration_smoke.txt  # 13日26节点完整迁移冒烟
│   │   │   ├── migration_smoke_initial_error.txt  # 初次缺包入口错误，修正后通过
│   │   │   ├── parallel_solver_verification.json  # 冻结源码、矩阵一致、运行与UI证据
│   │   │   ├── tests_fast.txt  # 5项数学/编码核验
│   │   │   ├── tests_integration.txt  # 快模型/恢复/检验19项测试
│   │   │   └── verification.json  # 当前源码、冻结摘要与实际界面验收
│   │   ├── production_rescue/  # 已完成的全年主轨迹救援、35/8秒硬墙与限时可行门禁
│   │   │   ├── task_plan.md  # 用户授权、时间预算、迁移启动与错误修正
│   │   │   ├── notes.md  # 旧现场、接受口径与后续补算边界
│   │   │   ├── report.md  # 冻结参数、全年完成、UB/LB/gap真实精度与P0—P3
│   │   │   ├── acceptance.json  # 365日收据、物理回放、四表回读与最终精度验收
│   │   │   └── tests.txt  # 7项救援门禁及原物理/Excel回读检查
│   │   ├── solver_acceleration/  # 用户随后叫停的Gurobi/v2/2-bit研究现场
│   │   │   ├── Q3_第三问_3pct_不改模型加速执行指令_Codex.md  # 用户原指令原字节归档
│   │   │   ├── source_manifest.json  # 原文件路径、SHA与解释边界
│   │   │   ├── task_plan.md  # 已完成、失败与被用户终止的阶段
│   │   │   ├── notes.md  # Gurobi许可证、v2和2-bit实测发现
│   │   │   └── equivalence_proof.md  # v2精确消元的历史推导；未用于当前生产
│   │   ├── parallel/  # 本轮4进程与SCIP线程改造、3.71倍实测及32测试
│   │   │   ├── task_plan.md  # 并行实现、测量与验收计划
│   │   │   ├── notes.md  # 资源/SCIP能力和默认配置依据
│   │   │   ├── report.md  # 并行范围、实测性能、限制和命令
│   │   │   ├── tests.txt  # 23原测试+9并行测试的完整日志
│   │   │   └── ui_smoke.json  # 实际并行报告AX/截图检查
│   │   └── file_inventory.csv  # 第三问逐文件清单与用途
│   └── plots/  # 论文图与集中管理的逐项验收记录
│       ├── acceptance.md  # 18项需求、P0—P3、假设、数值与视觉验收
│       ├── migration_verification.json  # 原15图PNG字节一致、128个原文件不变和49项测试结果
│       ├── q1_tests.txt  # 迁移后Q1全部25项测试通过的完整日志
│       ├── q1_traceability_check.json  # 当前代码167条公式映射重新生成检查
│       ├── q2_tests.txt  # 迁移后Q2全部24项测试通过的完整日志
│       ├── q2_traceability_check.json  # 当前代码265条句子映射及集中绘图位置检查
│       ├── requirements_acceptance.csv  # 18条逐句需求到代码行与实际证据的对应
│       ├── ui_smoke.json  # 浏览器8图与23图加载、CSV下载和窄视口检查
│       └── verification.json  # 8图时序、单位、收益、设备解、格式与源码集中化验收
├── inputs/  # 按照题号保存原始输入和预处理输入
│   ├── q1/  # 第一问当前输入别名；随q1_current统一切换
│   │   ├── processed/  # 经过时间映射和单位换算的求解输入
│   │   │   ├── parameters.json  # 储能参数、四种效率情景和用户确认的计算口径
│   │   │   └── timeseries.csv  # 144时段输入；含右端点映射与kW转kWh结果
│   │   └── raw/  # 原始数据副本与来源追溯记录
│   │       ├── attachment1.csv  # 原附件时间、电价、负荷功率、光伏功率的CSV副本
│   │       ├── attachment1.xlsx  # C题附件1原始工作簿副本；仅用于读取输入
│   │       └── manifest.json  # 原始附件路径、副本路径和SHA-256
│   ├── q3/  # 第三问按原始附件读取，不改写第二问预测
│   │   ├── raw/README.md  # 原始附件与Q2预测只读来源说明
│   │   └── processed/  # 因果输入及来源追溯
│   │       ├── actual_quality.csv  # 附件2结构、非负、连续时段核验
│   │       ├── prices.csv  # 附件1的144个时段电价
│   │       ├── pv_forecasts.csv  # issue+h重构的35040条整点预报
│   │       ├── q2_load_selection.csv  # 逐日继承Q2的负荷预测器
│   │       └── source_manifest.json  # 原始输入/影子预测/每日决策的SHA
│   └── q2/  # 第二问当前输入别名；随q2_current统一切换
│       ├── processed/  # 规范化功率长表与诊断方法设置
│       │   ├── settings.json  # 算法、单位、截止时点及用户确认的信息边界
│       │   └── timeseries.csv  # 52560行连续右端点长表；原始kW逐值保留
│       └── raw/  # 附件2只读副本及来源记录
│           ├── attachment2.xlsx  # 附件2原始XLSX只读副本；不作为结果格式
│           └── manifest.json  # 附件来源与SHA-256
├── outputs/  # 本机原始结果和整理后的交付结果；整体不纳入Git，跨设备另行同步
│   ├── processed/  # 面向阅读、论文及交付的整理结果
│   │   ├── q3_monitor/  # 第三问实时进度服务静态资源
│   │   │   ├── index.html  # 2秒刷新、PID存活、预热/正式与检查点
│   │   │   └── server.log  # 看板服务错误记录
│   │   ├── q1/  # 第一问当前正式CSV、HTML与图表别名；无XLSX交付
│   │   │   ├── daily_summary.csv  # 全日购电费、电量、损耗和首尾储电量
│   │   │   ├── dispatch.pdf  # 调度图的PDF矢量版本；旧运行产物，后续不再生成
│   │   │   ├── dispatch.png  # 输入功率、电价、购电、充放电和储量科研图
│   │   │   ├── dispatch.svg  # 调度图的SVG矢量版本
│   │   │   ├── efficiency.pdf  # 效率对比图的PDF矢量版本；旧运行产物，后续不再生成
│   │   │   ├── efficiency.png  # 效率情景成本与储电轨迹对比图
│   │   │   ├── efficiency.svg  # 效率对比图的SVG矢量版本
│   │   │   ├── efficiency_comparison.csv  # 四种效率情景的成本、能量与调度指标对比
│   │   │   ├── report.html  # 可展开查看完整输入、输出、对比与验证的报告
│   │   │   ├── result1.csv  # 正式主结果；144时段输入与G/C/D/E/W/u、SOC、费用
│   │   │   ├── summary.json  # 主模型汇总指标的JSON副本
│   │   │   ├── table1_purchase.csv  # 题目指定六个10分钟区间的购电量
│   │   │   ├── table2_storage.csv  # 题目指定六个4小时区间的充电量与放电量
│   │   │   ├── active_constraints.csv  # 36组×144时段的SOC上下界及充放电上限活跃标记
│   │   │   ├── analysis_summary.json  # 新版完整分析汇总、数值设置和经济机制指标
│   │   │   ├── arbitrage_thresholds.csv  # 四效率口径×144时段的未来价格阈值和盈利时段数
│   │   │   ├── baseline_comparison.csv  # No-ESS、PV-only、Full三种嵌套基准费用与电量
│   │   │   ├── bottleneck_analysis.pdf  # 资源瓶颈分析图的PDF矢量版本；旧运行产物，后续不再生成
│   │   │   ├── bottleneck_analysis.png  # 储能上下限及独立充放功率的三步长单位日价值图
│   │   │   ├── bottleneck_analysis.svg  # 资源瓶颈分析图的SVG矢量版本
│   │   │   ├── bottleneck_values.csv  # 36情景×4边界×3步长共432次放宽、稳定性与数值瓶颈
│   │   │   ├── incremental_benefits.csv  # 两步增量收益及总节约；不作唯一因果归因
│   │   │   ├── lp_diagnosis.csv  # LP松弛目标、整数间隙、分数模式与同时充放电统计
│   │   │   ├── marginal_analysis.pdf  # 边际机制分析图的PDF矢量版本；旧运行产物，后续不再生成
│   │   │   ├── marginal_analysis.png  # 局部阈值、嵌套基准费用与负荷/光伏敏感性科研图
│   │   │   ├── marginal_analysis.svg  # 边际机制分析图的SVG矢量版本
│   │   │   ├── marginal_report.html  # 边际价值完整报告、36情景表、局部阈值及CSV入口
│   │   │   ├── marginal_rhs_validation.csv  # 固定模式LP的288个母线/状态RHS双侧扰动与影子价检查
│   │   │   ├── marginal_values.csv  # 5184行局部μ/λ、充停放阈值、实际动作及模式限制
│   │   │   ├── normalized_sensitivity.csv  # 四种效率口径下负荷/光伏的8项归一化成本敏感度
│   │   │   ├── sensitivity_scenarios.csv  # 36情景费用、电量、边界、资源价值和调度变化汇总
│   │   │   └── milp_rhs_validation.csv  # 原MILP的288个RHS双侧共576次重求与固定影子价对照
│   │   ├── q1_paper/  # 第一问论文材料；目录按来源运行代与整理代码哈希标识
│   │   │   ├── run-ie6fkatf-d9b1d24a/  # 本次论文材料：144规划、题目表1/表2、结果比较、图及说明
│   │   │   │   ├── README.md  # 论文材料取用顺序、可引用结果段落、口径与局限
│   │   │   │   ├── baseline_comparison_paper.csv  # 嵌套基准与节约比较；结果分析或稳健性分析
│   │   │   │   ├── bottleneck_analysis.png  # 四类边界放宽的单位日价值；论文插图
│   │   │   │   ├── bottleneck_analysis.svg  # 四类边界放宽的单位日价值；论文插图
│   │   │   │   ├── boundary_values_paper.csv  # 主方案四类边界的三步长日价值；边际价值分析（可选）
│   │   │   │   ├── daily_indicators.csv  # 主方案全日指标；摘要、结果分析
│   │   │   │   ├── dispatch.png  # 主方案调度与储电轨迹；论文插图
│   │   │   │   ├── dispatch.svg  # 主方案调度与储电轨迹；论文插图
│   │   │   │   ├── efficiency.png  # 效率口径对费用和储电轨迹的影响；论文插图
│   │   │   │   ├── efficiency.svg  # 效率口径对费用和储电轨迹的影响；论文插图
│   │   │   │   ├── efficiency_comparison_paper.csv  # 效率口径比较；结果分析或稳健性分析
│   │   │   │   ├── index.html  # 论文表格及四张图的浏览器预览；144行可展开滚动
│   │   │   │   ├── marginal_analysis.png  # 基准比较、局部阈值及输入敏感性；论文插图
│   │   │   │   ├── marginal_analysis.svg  # 基准比较、局部阈值及输入敏感性；论文插图
│   │   │   │   ├── materials_index.csv  # 全部CSV/PNG/SVG的标题、行数、论文用途和图注
│   │   │   │   ├── model_parameters.csv  # 模型参数与计算口径；符号说明、参数设置
│   │   │   │   ├── provenance.json  # 来源62项哈希、整理代码和材料哈希及核验结果
│   │   │   │   ├── sensitivity_36_paper.csv  # 36组效率、负荷及光伏情景；稳健性分析或附录（可选）
│   │   │   │   ├── table1_purchase_paper.csv  # 表1 微网指定时段及全天购电结果；题目要求：论文正文
│   │   │   │   ├── table2_storage_paper.csv  # 表2 储能分区间充放电量及首尾储电量；题目要求：论文正文
│   │   │   │   └── table_144_dispatch.csv  # 完整最优方案：144个10分钟时段；附录或完整结果附件
│   │   │   ├── run-ie6fkatf-d9b1d24a.zip  # 本次21文件论文材料压缩包；可整体分享或解压使用
│   │   │   └── Q1_三份结果表.zip  # 仅含144时段规划、题目表1和题目表2的三个CSV
│   │   ├── q2/  # 第二问清洗数据、结构诊断CSV、报告与科研图
│   │   │   ├── evaluation_status.csv  # 后续实际预测和调度指标未计算的明确状态；非零值
│   │   │   ├── figures/  # 11类分析图，每类同时导出PNG和SVG
│   │   │   │   ├── acf_pacf.png  # 两类功率ACF/PACF的短期、日、周多尺度视图；PNG
│   │   │   │   ├── acf_pacf.svg  # 两类功率ACF/PACF的短期、日、周多尺度视图；SVG
│   │   │   │   ├── annual_heatmaps.png  # 负荷/光伏365×144全年日期时间热力图；PNG
│   │   │   │   ├── annual_heatmaps.svg  # 负荷/光伏365×144全年日期时间热力图；SVG
│   │   │   │   ├── daily_peaks.png  # 全年逐日峰值及峰值时刻迁移；PNG
│   │   │   │   ├── daily_peaks.svg  # 全年逐日峰值及峰值时刻迁移；SVG
│   │   │   │   ├── monthly_profiles.png  # 三类功率12个月平均日曲线；PNG
│   │   │   │   ├── monthly_profiles.svg  # 三类功率12个月平均日曲线；SVG
│   │   │   │   ├── monthly_stability.png  # 月度周期相关、日峰谷、波动与水平；PNG
│   │   │   │   ├── monthly_stability.svg  # 月度周期相关、日峰谷、波动与水平；SVG
│   │   │   │   ├── seasonal_moments.png  # 四种季节处理后的月均值和波动；PNG
│   │   │   │   ├── seasonal_moments.svg  # 四种季节处理后的月均值和波动；SVG
│   │   │   │   ├── spectra.png  # 原始与日曲线残差频谱及日/周位置；PNG
│   │   │   │   ├── spectra.svg  # 原始与日曲线残差频谱及日/周位置；SVG
│   │   │   │   ├── timeseries_30d.png  # 连续30天三类原始功率曲线；PNG
│   │   │   │   ├── timeseries_30d.svg  # 连续30天三类原始功率曲线；SVG
│   │   │   │   ├── timeseries_7d.png  # 连续7天三类原始功率曲线；PNG
│   │   │   │   ├── timeseries_7d.svg  # 连续7天三类原始功率曲线；SVG
│   │   │   │   ├── weekday_profiles.png  # 负荷/光伏星期一至星期日平均日曲线；PNG
│   │   │   │   ├── weekday_profiles.svg  # 负荷/光伏星期一至星期日平均日曲线；SVG
│   │   │   │   ├── weekday_weekend.png  # 周一至周五与周末平均日曲线对照；PNG
│   │   │   │   └── weekday_weekend.svg  # 周一至周五与周末平均日曲线对照；SVG
│   │   │   ├── full_year_acf_pacf.csv  # 全年事后诊断；0至2016阶FFT自相关与Burg偏自相关
│   │   │   ├── full_year_daily_statistics.csv  # 全年事后诊断；每日峰谷、波动、峰值时段、并列峰与零值
│   │   │   ├── full_year_lag_correlations.csv  # 全年事后诊断；六种关键滞后的原始/去平均日曲线相关
│   │   │   ├── full_year_monthly_stability.csv  # 全年事后诊断；月内日/周相关、均值、波动和日峰谷幅度
│   │   │   ├── full_year_profiles.csv  # 全年事后诊断；月份、星期及工作日/周末平均日曲线与n/std
│   │   │   ├── full_year_pv_zero_profile.csv  # 全年事后诊断；各槽位光伏零值数和比例，不推定固定夜间
│   │   │   ├── full_year_spectral_targets.csv  # 全年事后诊断；日/周目标频点与邻点、局部峰及Parseval验证
│   │   │   ├── full_year_spectrum.csv  # 全年事后诊断；原始与日曲线残差的全正频率功率谱
│   │   │   ├── full_year_stationarity_tests.csv  # 全年事后诊断；32条ADF/KPSS检验、c/ct、临界值与p值界限
│   │   │   ├── full_year_summary.csv  # 全年事后诊断；三类功率样本量、均值、波动、极值与零值
│   │   │   ├── full_year_transformed_monthly_moments.csv  # 全年事后诊断；四种变换的月均值、标准差和样本量
│   │   │   ├── full_year_transformed_series.csv  # 全年事后诊断；原始、日差分、周差分、日后周差分的实际序列
│   │   │   ├── initial_history_acf_pacf.csv  # 首次预测前4463点诊断；0至2016阶FFT自相关与Burg偏自相关
│   │   │   ├── initial_history_daily_statistics.csv  # 首次预测前4463点诊断；每日峰谷、波动、峰值时段、并列峰与零值
│   │   │   ├── initial_history_lag_correlations.csv  # 首次预测前4463点诊断；六种关键滞后的原始/去平均日曲线相关
│   │   │   ├── initial_history_monthly_stability.csv  # 首次预测前4463点诊断；月内日/周相关、均值、波动和日峰谷幅度
│   │   │   ├── initial_history_profiles.csv  # 首次预测前4463点诊断；月份、星期及工作日/周末平均日曲线与n/std
│   │   │   ├── initial_history_pv_zero_profile.csv  # 首次预测前4463点诊断；各槽位光伏零值数和比例，不推定固定夜间
│   │   │   ├── initial_history_spectral_targets.csv  # 首次预测前4463点诊断；日/周目标频点与邻点、局部峰及Parseval验证
│   │   │   ├── initial_history_spectrum.csv  # 首次预测前4463点诊断；原始与日曲线残差的全正频率功率谱
│   │   │   ├── initial_history_stationarity_tests.csv  # 首次预测前4463点诊断；32条ADF/KPSS检验、c/ct、临界值与p值界限
│   │   │   ├── initial_history_summary.csv  # 首次预测前4463点诊断；三类功率样本量、均值、波动、极值与零值
│   │   │   ├── initial_history_transformed_monthly_moments.csv  # 首次预测前4463点诊断；四种变换的月均值、标准差和样本量
│   │   │   ├── initial_history_transformed_series.csv  # 首次预测前4463点诊断；原始、日差分、周差分、日后周差分的实际序列
│   │   │   ├── jump_context.csv  # 29818个局部转折点的前后与历史同类上下文，保留不删除
│   │   │   ├── model_candidates.csv  # 仅依据首次回测前可见历史形成候选与条件
│   │   │   ├── quality_checks.csv  # 原始核验清单的报告下载副本
│   │   │   ├── report.html  # 可查看11张图、完整统计、滚动切分与下载的报告
│   │   │   ├── results.md  # 实算结论、星期异常特征、候选依据和阶段边界
│   │   │   ├── rolling_folds.csv  # 334日严格timestamp小于0:00的滚动切分与144段目标
│   │   │   ├── source_traceability.csv  # 254非空源行、265句到精确函数/测试行和产物的映射
│   │   │   └── timeseries.csv  # 便于报告下载的清洗后长表副本，52560行
│   │   └── figures/  # 集中图集；新论文图与项目原图导航
│   │       ├── index.html  # 全项目23组图预览与脚本入口
│   │       └── q1/  # 第一问8张新论文图、12份数据CSV及图目CSV
│   │           ├── 01_data_features.png  # 负荷、光伏与电价的日内变化特征；可选：背景说明；300dpi
│   │           ├── 01_data_features.svg  # 负荷、光伏与电价的日内变化特征；可选：背景说明；矢量路径
│   │           ├── 02_optimal_dispatch.png  # 最优购电计划与储能运行轨迹；必选：核心结果；300dpi
│   │           ├── 02_optimal_dispatch.svg  # 最优购电计划与储能运行轨迹；必选：核心结果；矢量路径
│   │           ├── 03_cost_waterfall.png  # 逐步放宽调度限制的购电费用变化；建议：结果解释；300dpi
│   │           ├── 03_cost_waterfall.svg  # 逐步放宽调度限制的购电费用变化；建议：结果解释；矢量路径
│   │           ├── 04_device_sensitivity.png  # 设备边界与最优购电费用；可选：瓶颈分析；300dpi
│   │           ├── 04_device_sensitivity.svg  # 设备边界与最优购电费用；可选：瓶颈分析；矢量路径
│   │           ├── 05_joint_contour.png  # 储电上限与共同功率上限的联合敏感性；可选：联合敏感性；300dpi
│   │           ├── 05_joint_contour.svg  # 储电上限与共同功率上限的联合敏感性；可选：联合敏感性；矢量路径
│   │           ├── 06_efficiency.png  # 储能效率变化下的费用与运行轨迹；可选：效率稳健性；300dpi
│   │           ├── 06_efficiency.svg  # 储能效率变化下的费用与运行轨迹；可选：效率稳健性；矢量路径
│   │           ├── 07_input_sensitivity.png  # 负荷与光伏输入扰动下的购电费用；可选：输入稳健性；300dpi
│   │           ├── 07_input_sensitivity.svg  # 负荷与光伏输入扰动下的购电费用；可选：输入稳健性；矢量路径
│   │           ├── 08_fixed_mode_diagnostic.png  # 固定模式边际价格的局部诊断；备查：局部诊断，不建议放正文；300dpi
│   │           ├── 08_fixed_mode_diagnostic.svg  # 固定模式边际价格的局部诊断；备查：局部诊断，不建议放正文；矢量路径
│   │           ├── baseline_metrics.csv  # 三种嵌套调度方案的全日指标
│   │           ├── cost_waterfall.csv  # 五段瀑布总量、增量与柱底费用
│   │           ├── data_features.csv  # 144段负荷、光伏、价格与富余光伏绘图数据
│   │           ├── device_joint_grid.csv  # 110个真实联合MILP网格点
│   │           ├── device_one_dimensional.csv  # 三条设备单变量曲线的36个数据点
│   │           ├── dispatch_power.csv  # 144段无储能及最优购电、充放电功率和实际状态
│   │           ├── efficiency_metrics.csv  # 四种效率口径的费用与能量指标
│   │           ├── efficiency_storage.csv  # 四种效率下各145个储电量点
│   │           ├── figure_index.csv  # 8张新图的必要性、脚本、CSV和准确图注
│   │           ├── fixed_mode_marginals.csv  # 主方案144个固定模式局部边际诊断
│   │           ├── index.html  # 按必选、建议、可选和备查排列的图集
│   │           ├── input_sensitivity.csv  # 主效率下9组负荷与光伏扰动
│   │           ├── milp_rhs_checks.csv  # 原MILP双侧扰动与固定影子价的288条对照
│   │           ├── provenance.json  # 新图源码、原运行来源、设备扫描与文件哈希
│   │           └── storage_145.csv  # 含日初的145个储电量边界点
│   ├── q1/  # 第一问当前求解、验收及历史审查的原始记录
│   │   ├── raw/  # 当前运行原始记录别名；历史review记录明确标注为历史
│   │   │   ├── q1_compact_review_acceptance.json  # 历史精简稿审查的验收记录
│   │   │   ├── q1_compact_review_evidence.json  # 历史精简稿审查的数值实验与完整轨迹
│   │   │   ├── q1_compact_review_run.json  # 历史精简稿审查的执行摘要
│   │   │   ├── run_manifest.json  # 本次运行命令、软件版本及输入/模型/代码/输出哈希
│   │   │   ├── schedule_eta085.csv  # 单程0.85效率情景的144时段轨迹
│   │   │   ├── schedule_eta095.csv  # 单程0.95效率情景的144时段轨迹
│   │   │   ├── schedule_main.csv  # 主模型144时段全量输入与决策变量
│   │   │   ├── schedule_roundtrip090.csv  # 对称往返0.9效率情景的144时段轨迹
│   │   │   ├── solution_eta085.json  # 双单程0.85效率情景的原始解
│   │   │   ├── solution_eta095.json  # 双单程0.95效率情景的原始解
│   │   │   ├── solution_main.json  # 主模型双单程0.9效率的原始解与最优性证书
│   │   │   ├── solution_roundtrip090.json  # 对称往返0.9效率情景的原始解
│   │   │   ├── tests.json  # 当前代码测试命令、退出状态与完整日志；独立子进程执行
│   │   │   ├── validation.json  # 四情景物理、最优性及CSV回读检查指标
│   │   │   ├── analysis_schedules.csv  # 36组×144时段的扰动输入与G/C/D/E/W/u完整轨迹
│   │   │   ├── analysis_solutions.json  # 36情景、基准、松弛、432次边界放宽及576次原MILP扰动解
│   │   │   ├── analysis_validation.json  # 全分析物理/最优性、双侧微扰及CSV回读证据
│   │   │   ├── temporary_plan_review_acceptance.json  # 旧临时方案审查验收结果
│   │   │   ├── temporary_plan_review_evidence.json  # 旧临时方案的对照数值实验
│   │   │   ├── temporary_plan_review_run.json  # 旧临时方案审查的运行记录
│   │   │   ├── figure_status.json  # 本次绘图成功、跳过或失败状态；失败不阻断正确CSV
│   │   │   ├── test_log.txt  # 当前代码25项测试的完整输出和故障注入记录
│   │   │   └── traceability_validation.json  # 154展示公式与5关键行内判据的覆盖、精确行锚点和源文哈希
│   │   └── figure_analysis/  # 绘图所需设备敏感性实算；按输入与源码哈希复用缓存
│   │       └── b6fbe67e925a/  # 本次133个不同参数点的已验收计算数据
│   │           ├── joint_grid.csv  # 110个储电上限与共同功率网格点的费用
│   │           ├── manifest.json  # 扫描范围、明示假设、来源哈希及回读验收
│   │           ├── one_dimensional.csv  # 三条单变量扫描共36行，包含基准及加100点
│   │           ├── solutions.npz  # 全部133个原始G/C/D/E/W/u解的压缩数组
│   │           └── solver_checks.csv  # 133个不同参数点、最优目标、Gap及物理残差
│   ├── .q1-runs/  # 保留当前、上一完整运行代及旧迁移验收目录；按目录汇总
│   ├── q1_current/  # 当前完整运行代的原子指针；数据在标准目录别名下逐文件列出
│   ├── .q2-runs/  # 保留当前与上一完整运行代；更早记录压缩归档至history
│   ├── q2/  # 第二问旧诊断别名与新调度独立运行
│   │   ├── precision_comparison/  # 1%/3%隔离配对测试，正式2%配置只读
│   │   │   └── 20260912_122315/  # Feb01/Mar20各两次；既有May05难例只读复用
│   │   │       ├── raw/  # 6组输入NPZ、24份策略NPZ、8日回放CSV、JSON实验/复核及逐句/界面验收
│   │   │       └── processed/  # report.html、comparison/summary/candidates.csv及tail_groups/tail_days.csv长尾统计
│   │   ├── dispatch_runs/  # 新模型运行代、逐日存档与求解界证据；未验收不替换q2_current
│   │   │   └── 20260911_224501/  # 本次真实输入、351个影子origin及正在自主续算的全量队列
│   │   │       ├── inputs/  # 原始附件逐值核验后的CSV、电价与来源
│   │   │       ├── deliverables/  # 用户要求的94天阶段快照：Excel、原始CSV、ZIP与验收清单
│   │   │       ├── raw/  # 冻结协议、影子库、源码哈希、失败/恢复收据、348日复核及隔离求解诊断
│   │   │       └── processed/  # 主回放、独立实验、图形、报告与逐句验收CSV/JSON
│   │   │           └── timing_audit/  # 逐日/逐候选/分段/worker耗时、首轮求解器及精度比较CSV与进度报告
│   │   └── raw/  # 当前完整生成代原始记录别名
│   │       ├── figure_manifest.json  # 11张科研图的配套CSV、字体、分辨率和范围
│   │       ├── quality_checks.csv  # 结构、日期、时段、数值和物理一致性核验
│   │       ├── run_manifest.json  # 原始附件、方案、源码、软件版本与全部产物哈希
│   │       ├── test_results.txt  # 24项当前源码测试与真实产物回读的完整日志
│   │       └── validation.json  # CSV回读、数值恒等式和逐句覆盖机器验收
│   ├── q3/  # 第三问全量进行中；正式result3待完成后验收导出
│   │   ├── active_run.json  # 当前主运行指针与切换状态
│   │   └── raw/  # 按独立测试运行保存，详细文件见docs/3/file_inventory.csv
│   │       ├── timing_20260912/  # 首次2个计时样本及历史零FD检查中断记录
│   │       ├── timing_verified_20260912/  # 精确反馈原初值12节点计时及诊断图
│   │       ├── timing_final_20260912/  # 改进可行初值后的12节点计时CSV/JSON/HTML与图
│   │       ├── extended_timing_20260912/  # 两个60秒实例、完整输入/策略和上下界
│   │       ├── component_smoke_20260912/  # 真实M0/M2组件、测试Excel和年末FIV边界
│   │       ├── parallel_20260912/  # 线程/进程计时CSV、策略JSON、吞吐与FD比较和HTML报告
│   │       ├── compute_rescue_20260912/  # 同卡点原/快策略、原始证书及计时
│   │       ├── solver_fix_20260912/  # 本次固定输入、逐方法短测、策略与迁移冒烟
│   │       ├── full_priority_rescue_7h_20260912/  # 当前35/8秒比赛生产救援主运行
│   │       │   ├── runtime/  # 冻结源码、HiGHS1.15.1依赖与main-only入口
│   │       │   ├── runtime_sources.json  # 26份源码、依赖及配置签名
│   │       │   ├── migration.json  # 25日、74节点、Jan26政策与FD迁移验收
│   │       │   ├── resume.sh  # 当前正确的七小时救援恢复命令
│   │       │   ├── launch.json  # 启动PID、35/8秒和25日续算记录
│   │       │   ├── progress.json  # 当前日期、接受状态、gap及正式日数
│   │       │   ├── supervisor.json  # 活动worker及重启历史
│   │       │   └── main/  # 日收据、节点快照、执行块、FD与最终result3
│   │       ├── full_priority_rescue_7h_20260912_prelaunch_superseded/  # 未启动的0.7秒容差旧冻结现场
│   │       ├── full_priority_parallel_20260912/  # 用户已停止的主运行；25日预热及检查点完整保留
│   │       │   ├── runtime/  # 24份冻结源码及完整requirements.txt
│   │       │   ├── runtime_sources.json  # 源码与依赖摘要
│   │       │   ├── migration.json  # 原22日与62节点逐项核验
│   │       │   ├── resume.sh  # 固定依赖和代码的当前恢复命令
│   │       │   ├── launch.json  # 2标定进程/4主求解线程启动参数
│   │       │   ├── progress.json  # 当前日期、gap、切片与完成日数
│   │       │   ├── supervisor.json  # 当前PID与重启记录
│   │       │   ├── stopped_by_user.json  # 停止时间、最后节点及恢复入口
│   │       │   └── main/  # 保留历史与新的原子快照、日收据、FD缓存
│   │       ├── full_priority_fast_20260912/  # 已迁移并完整保留的旧单线程紧凑运行
│   │       │   ├── runtime/  # 已冻结22文件主源码
│   │       │   ├── runtime_sources.json  # 冻结源码SHA
│   │       │   ├── migration.json  # 26旧节点精确签名与13日原样迁移
│   │       │   ├── migration_validation.json  # 迁移后15日物理费用回读
│   │       │   ├── resume.sh  # 当前正确的冻结运行恢复入口
│   │       │   ├── progress.json  # 活动日期、gap、切片与正式日数
│   │       │   ├── supervisor.json  # 活动worker及重启记录
│   │       │   └── main/  # 原子日收据、节点快照、执行块及FD缓存
│   │       ├── full_priority_20260912/  # 已停止并完整保留的旧主运行
│   │       │   ├── runtime/  # 不随工作区检验编辑改变的冻结主代码
│   │       │   ├── runtime_sources.json  # 19个冻结源文件SHA
│   │       │   ├── resume.sh  # 同一冻结环境的启动/故障后恢复命令
│   │       │   ├── execution.json  # 已批准参数、日期范围和来源
│   │       │   ├── supervisor.json  # 进程与重启记录
│   │       │   ├── progress.html  # 自动更新主进度页面
│   │       │   ├── progress.json  # 活动日期/节点、gap及切片
│   │       │   ├── worker.log  # 计算日志
│   │       │   └── main/  # 节点/切片、6小时块、逐日收据和FD缓存
│   │       └── validation_20260912/  # nice=10独立检验；先只读诊断，重型任务等主结果和范围确认
│   │           ├── runtime/  # 独立冻结的检验源码与绘图模块
│   │           ├── resume.sh  # 独立检验恢复命令
│   │           ├── request.json  # 抽样/全年范围与worker额度
│   │           ├── status.json  # 当前队列阶段
│   │           ├── report.html  # 检验状态及只读审计
│   │           ├── forecast/  # 已计算的误差CSV、PNG/SVG和相关性
│   │           └── prepared/  # 检验专属预处理副本，避免写主任务输入
│   ├── q2_current/  # 第二问当前完整运行代原子指针；正式路径下逐文件列出
│   └── history/  # 已清理运行代的轻量追溯记录和逐文件清理验收
│       ├── run_records_20260911.tar.gz  # 59份旧运行清单、配置、验收及日志的压缩归档
│       ├── cleanup_20260911.csv  # 429个清理文件的原路径、处理方式、大小与SHA-256
│       └── cleanup_20260911.json  # 保留范围、清理前后体积及完整性检查结果
├── src/  # 按题号组织的求解、导出、报告与测试源码
│   ├── q1/  # 当前第一问实现与保留的历史审查程序
│   │   ├── export.py  # CSV导出和关闭回读；逐行、六区间、日汇总与单位容差校验
│   │   ├── model.py  # 输入标准化、共享MILP/LP约束与独立物理/最优性复核
│   │   ├── report.py  # 第一问HTML和文字报告；绘图委托src/plots/q1_legacy.py
│   │   ├── requirements.txt  # 锁定NumPy、SciPy、openpyxl、Matplotlib版本
│   │   ├── review_compact_q1.py  # 历史精简稿审查实验；不是当前正式求解器
│   │   ├── run.py  # 正式入口；完整暂存求解、CSV/分析/报告及测试后统一发布
│   │   ├── test_q1.py  # 解析解、异常输入、压力与CSV篡改验收测试
│   │   ├── analysis.py  # LP/基准/边际、36情景432次边界放宽及576次原MILP扰动
│   │   ├── analysis_report.py  # 边际分析文字和HTML报告；绘图委托集中模块
│   │   ├── test_analysis.py  # 7项分析测试：解析符号、36情景、432次放宽及CSV检查
│   │   ├── golden_main.json  # 修改前官方输入SHA及主目标基线；不固定不唯一的调度
│   │   ├── pipeline.py  # 测试门禁、可选绘图隔离及整代结果原子发布
│   │   ├── test_review.py  # 本轮10项回归：新解、效率、PV来源、边际与失败发布
│   │   ├── traceability.py  # 公式、代码语句、测试和本代证据精确映射与验证
│   │   ├── prepare_paper_materials.py  # 从已验收Q1结果生成中文CSV论文表、图表材料包并独立核验
│   │   └── device_sensitivity.py  # 133个不同设备参数点的MILP实算、压缩原解与回读验收
│   ├── 问题1/  # 旧临时方案审查源码；历史中文目录保留
│   │   └── review_temporary_plan.py  # 旧临时方案的独立数值对照与漏洞验证
│   ├── q2/  # 第二问新最终建模实现；旧诊断入口保留
│   │   ├── deliverables/  # 已提交结果的只读阶段导出
│   │   │   └── export_partial.py  # 94日完整物理核验、Excel逐值回读及ZIP打包
│   │   ├── benchmarks/  # 隔离性能测量，不改变正式任务配置
│   │   │   ├── precision_pair.py  # 两真实日各两次的1%/3%完整选策、计时与策略存档
│   │   │   ├── precision_pair_report.py  # 输入、策略与费用复核、48日长尾核查及HTML对照表
│   │   │   └── precision_sweep.py  # 同日同算法的1%—5%精度与耗时比较
│   │   ├── backtest.py  # 严格滚动预测接口、三类预测指标和真实调度计费评价
│   │   ├── data.py  # 附件2核验、右端点长表、严格历史和突变上下文
│   │   ├── diagnostics.py  # 描述、2016阶相关、频谱、月度稳定性及ADF/KPSS
│   │   ├── figures.py  # 第二问原调用接口与LABELS兼容，绘图委托src/plots/q2.py
│   │   ├── report.py  # 基于历史的候选依据、实算解释与HTML报告
│   │   ├── requirements.txt  # 锁定第二问科学计算与绘图依赖版本
│   │   ├── run.py  # 全流程入口；暂存、数值回读、测试、统一结果切换
│   │   ├── test_q2.py  # 24项原始值、防前视、手算、频谱、假设与发布验收
│   │   ├── execution.py  # 显式精度修订、原协议身份和授权核验
│   │   ├── test_execution.py  # 精度传递、断点保留、失败记录和非法修订测试
│   │   ├── full_run.py  # Mac两工作进程全量队列、依赖/故障隔离、进程收据与实时进度
│   │   ├── checkpoint.py  # 完整日前缀、跨日SOC、冻结策略与摘要校验；提交中断恢复上一完整存档
│   │   ├── comparators.py  # 确定性证书、刚性计划与两类完全信息Oracle
│   │   ├── dispatch.py  # 新方案prepare/run/experiments与旧准备库封存入口
│   │   ├── experiments.py  # 27项论文验证；相同基准须独立核验后复用
│   │   ├── baseline_reuse.py  # 完整主基准及逐日预测输入/评分同一性核验、原子共享与追溯
│   │   ├── export_dispatch.py  # 真实CSV表、连续紧急区间及完整result2模板回读
│   │   ├── final_diagnostics.py  # 局部PV形状残差与同区间季节方差修正
│   │   ├── final_report.py  # 真实状态HTML/Markdown、资源与覆盖率汇总
│   │   ├── final_traceability.py  # 新原文每个非空源行/句子到代码、测试和真实证据
│   │   ├── forecast.py  # 固定特征LightGBM、局部DHR-ARMA及递推季节基线
│   │   ├── incumbent.py  # 同冻结策略类分段梯度可行初始解搜索，不作全局声明
│   │   ├── linear_policy.py  # 精确反馈/单调充电等值下界、完整初值及原策略执行证书
│   │   ├── optimization.py  # SCIP原生indicator MILP、SOC三段模型与上下界证书
│   │   ├── policy.py  # 不可变策略参数、单步非前瞻响应、物理和效率校验
│   │   ├── protocol.py  # 正式计算前冻结的工程配置、题设与工程设置边界
│   │   ├── relaxation.py  # 自由场景响应LP下界，仅用于证书、不执行recourse
│   │   ├── rolling.py  # 因果预热、K/S稳定性、首日冻结、等价延迟K1与授权精度下首次MILP路线
│   │   ├── scenarios.py  # 完整同origin联合误差块、窗口回退与尾部保护medoids
│   │   ├── shadows.py  # origin×horizon影子库、1月选参冻结及联合流程在线筛选
│   │   ├── test_dispatch.py  # 手算物理、因果、精确MILP与场景概率测试
│   │   ├── test_linear_policy.py  # 线性/原生MILP最优值、充电支配性、固定策略及完整初值测试
│   │   ├── test_baseline_reuse.py  # 完整334日共享回读、未选候选评分变化及禁止覆盖检查
│   │   ├── test_horizon_execution.py  # 16种候选可靠性/稳定性组合与固定K1回归
│   │   ├── test_full_run.py  # 全量任务依赖、故障隔离、重启进程识别和完成收据验收
│   │   ├── test_forecast_dispatch.py  # 预测冻结、证书、SOC分段、模板、篡改与续算回归
│   │   └── traceability.py  # 原方案逐行逐句到源码、测试和运行证据的映射
│   ├── q3/  # 第三问v4的因果随机滚动优化、全部实验及验收
│   │   ├── __init__.py  # Python模块入口
│   │   ├── config.py  # 题设参数、冻结配置、用户确认标定与源码签名
│   │   ├── data.py  # 原始附件、预报插值、Q2预测继承和完整历史边界
│   │   ├── checkpoint.py  # 文件锁、输入摘要和可行策略/下界快照
│   │   ├── full_run.py  # 主优先监督、120秒切片续算、异常重启与进度
│   │   ├── status_server.py  # 本机实时看板后端；核对PID与真实快照
│   │   ├── sampled.py  # 先前授权的小表入口；当前主以main-only运行
│   │   ├── validation.py  # 最终检验独立队列、审计、经济表、敏感性、M2与假设对照
│   │   ├── scenarios.py  # 条件历史池、尾部保持、PAM medoids及配对场景
│   │   ├── physics.py  # 聚合/lag反馈、能量守恒及净调整费用
│   │   ├── optimization.py  # 原精确编码/快编码、LP下界与原反馈证书
│   │   ├── fast_solver.py  # 单调等价矩阵、新版HiGHS原生多线程与快照
│   │   ├── solver_probe.py  # 固定困难输入的独立求解器对比与未采用试验
│   │   ├── gurobi_backend.py  # 同矩阵后端；当前尺寸受限许可证No-Go，不进入生产
│   │   ├── migrate_solver.py  # 逐节点验旧签名、保留日期与FD的求解器迁移
│   │   ├── migrate_rescue.py  # 25日前缀、Jan26政策与FD的七小时救援迁移
│   │   ├── parallel.py  # 有界spawn池、CPU额度、跨进程异常和40条独立SOC链调度
│   │   ├── parallel_benchmark.py  # 同输入串行/4进程/1—4线程的实测比较
│   │   ├── incumbent.py  # 原反馈的分段梯度可行初值改进，不替代全局求解
│   │   ├── terminal.py  # 历史有限差分、28日中位数和扰动检查
│   │   ├── rolling.py  # 四节点/OUV状态执行、18h FIV和原子续算
│   │   ├── multistage.py  # 条件四阶段树、共享决策MILP与真实分支回放
│   │   ├── analysis.py  # 预测误差、FIV/OUV、M0/M2和全套敏感性
│   │   ├── export.py  # 题目表1—3、真实CSV、完整模板导出和逐值回读
│   │   ├── run.py  # 默认parallel-benchmark；显式full才执行全年，支持workers/solver-threads
│   │   ├── requirements.txt  # Q2固定依赖及Q3专用highspy1.15.1
│   │   ├── test_q3.py  # 数学、信息边界、树、结算、模板与续算核验
│   │   ├── test_parallel.py  # 并行数值、状态隔离、FIV/FD、异常与并发额度核验
│   │   ├── test_full_run.py  # SIGKILL、节点恢复、原子保存和监督重启核验
│   │   ├── test_fast_solver.py  # 正残值/调整费、原最优值、固定策略和有效约束
│   │   ├── test_gurobi_backend.py  # 可选Gurobi同矩阵小模型回归；本轮未再运行
│   │   ├── test_solver_acceleration.py  # v2/2-bit历史研究测试；本轮未再运行
│   │   ├── test_production_rescue.py  # 35/8秒、可行门禁、恢复与冻结配置7测试
│   │   ├── test_validation.py  # 检验模块/优先级、真实单日经济表和只读审计
│   │   └── traceability.py  # 模型逐行映射和源码/模型摘要
│   └── plots/  # 全部项目自写绘图代码的唯一维护目录；既有入口保持兼容
│       ├── README.md  # 科研配色、必要性分类、统一命令和脚本职责说明
│       ├── catalog.py  # 生成全项目23组图清单与总图集
│       ├── common.py  # 中文字体、语义配色、费用色阶及300dpi PNG和SVG导出
│       ├── figure_registry.csv  # 23组图的脚本、数据、PNG/SVG位置和必要性
│       ├── q1_legacy.py  # 第一问原4组报告图的集中实现，外观保持一致
│       ├── q1_paper.py  # 第一问8张论文图、配套CSV和按必要性排序的图集
│       ├── q2.py  # 第二问原11张数据诊断图的集中实现
│       ├── q2_dispatch.py  # 新最终方案预测步长、残差、方差及真实回放图
│       ├── q3.py  # 第三问预报误差热图及运行级图目清单
│       ├── replot_existing.py  # 从已验收CSV和JSON重绘Q1或Q2原有图
│       ├── run.py  # 统一命令，分别使用两问固定依赖环境
│       └── verify.py  # 144/145时序、单位、收益、设备解、图形格式和集中化验收
├── .agents/  # 项目实际技能所在目录
│   └── skills/  # 360个技能包及各自SKILL.md、脚本和参考资料；按目录汇总
├── SKILLS/  # 28份技能来源与用途说明TXT；辅助资料按目录汇总
├── .idea/  # PyCharm项目与工作区配置；本机辅助配置按目录汇总
└── TASK_STATE.md  # 新第二问任务状态、活动计算与此前Q1/Q2追溯
```

运行结果先在 `outputs/.q1-runs/` 中完整生成，全部数值检查和当前代码测试通过后，单次切换 `outputs/q1_current`。表格仅用CSV；HTML提供浏览器查看入口。

### 常用入口

- [第一问论文新图：必选／建议／可选／备查](outputs/processed/figures/q1/index.html)
- [全部绘图脚本集中管理](src/plots/README.md) · [23组图清单CSV](src/plots/figure_registry.csv) · [总图集](outputs/processed/figures/index.html)

- [数学建模开发规范](数学建模开发规范.md)
- [第一问文档分类导航](docs/1/README.md)
- [第一问论文材料包](docs/1/deliverables/q1_paper_materials.md)
- [当前最终模型](docs/1/final/第一问_MILP_边际价值强化版.md)
- [运行说明与CSV字段](docs/1/deliverables/q1_run_guide.md)
- [输入CSV](inputs/q1/processed/timeseries.csv) · [完整输出CSV](outputs/processed/q1/result1.csv) · [结果摘要](docs/1/deliverables/q1_results.md)
- [新版边际分析报告](outputs/processed/q1/marginal_report.html) · [36组情景CSV](outputs/processed/q1/sensitivity_scenarios.csv)
- [24条review处理CSV](docs/1/deliverables/q1_code_review_resolution.csv) · [本轮验收报告](docs/1/deliverables/q1_implementation_acceptance.md)
- [任务变更历史](docs/CHANGE_HISTORY.md)

在项目根目录运行第一问：

```sh
uv run --with-requirements src/q1/requirements.txt python src/q1/run.py
```

在项目根目录运行第二问数据清洗与分析：

```sh
uv run --with-requirements src/q2/requirements.txt python src/q2/run.py
```

第二问旧诊断阶段入口：[方案](docs/2/dierwen1.md) · [运行说明](docs/2/run_guide.md) · [分析报告与11张图](outputs/processed/q2/report.html) · [清洗后CSV](inputs/q2/processed/timeseries.csv) · [逐句验收](docs/2/implementation_acceptance.md)。第二问同样在全部检查通过后统一切换 `outputs/q2_current`；全文统计不能回流为历史预测信息。

按照开发规范，每次新增、移动或删除核心文件后，同步更新本目录树、对应注释及入口链接。目录树描述实际已有文件；历史审查、模板示例和已完成任务笔记均按其真实用途标注。


2026-09-11存储清理：保留两问当前版、上一版及旧迁移验收目录；旧运行必要记录见 [压缩归档](outputs/history/run_records_20260911.tar.gz)、[逐文件清单](outputs/history/cleanup_20260911.csv) 和 [验收记录](outputs/history/cleanup_20260911.json)。已清理目录不能作为完整运行代恢复；当前输入、数值结果和图表原样保留。此次为一次性清理，生成器尚未自动限制历史数量。

集中绘图：`python3 src/plots/run.py q1`重绘第一问8张新论文图；`python3 src/plots/run.py q2`重绘第二问11张分析图；`all`执行两者。项目自写绘图实现统一保存在`src/plots/`，原求解入口保留兼容调用；新图PNG为300 dpi、SVG为矢量路径，数据表用CSV。8张新图按论文必要性标注，运行结果图为核心必选，费用对比建议，其余按论证选用。详见[本轮验收](docs/plots/acceptance.md)。

绘图输出格式：所有项目绘图脚本统一只生成PNG和SVG；已取消旧Q1脚本的PDF导出。目录树中的绘图PDF是旧运行代遗留文件。

第二问新最终方案：[原文](docs/2/final/第二问_最终建模思路_最高优先级修订版_修订后.md) · [新运行说明](docs/2/revision_work/run_guide.md) · [审查与未完成项](docs/2/revision_work/acceptance.md) · [真实执行报告快照](outputs/q2/dispatch_runs/20260911_224501/processed/report.html)。主程序：`python src/q2/dispatch.py run --run-dir outputs/q2/dispatch_runs/20260911_224501`（使用uv固定环境，详见运行说明）。新报告的计算限制停止标识与未完成实验必须保留，完整验收前不能当作最终全年结果。

当前启动状态：用户已明确授权并启动Mac全量计算。84项检查通过，两个独立工作进程按日存档并继续已有进度；每15分钟自动跟进排查。实时页面：[全量计算进度](outputs/q2/dispatch_runs/20260911_224501/processed/progress.html)。补算预算另行记录，正式后续采用3%精度，已有1%及2%结果保留；主334天已计算提交，Excel后处理与其余论文验证单独验收；当前状态见TASK_STATE.md。

第二问1%/3%小量对比：[HTML表格](outputs/q2/precision_comparison/20260912_122315/processed/report.html) · [对照CSV](outputs/q2/precision_comparison/20260912_122315/processed/comparison.csv) · [验收](docs/2/revision_work/precision_pair_acceptance.md)。2个普通日期各档重复2次，全部24候选合格；新增历史48日长尾核查：7个补算日占68%推进时间，当前样本不足以估计全任务提速。正式仍为2%。
