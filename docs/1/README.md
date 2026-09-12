# 第一问文档导航

本目录已按用途分为四类。判断依据是用户最后确认的模型和已经运行的代码，不按文件名中是否出现“最终”来判断。当前唯一执行依据是边际价值强化版；上一模型及历史稿均保留。

[第一问论文材料包：144时段规划表、题目表1/表2与图表](deliverables/q1_paper_materials.md)

[第一问论文新图与必要性说明](../../outputs/processed/figures/q1/index.html) · [集中绘图脚本](../../src/plots/README.md)

**日常阅读顺序：最终模型 → 计算结果 → 运行说明。验收与逐行追溯文件在需要核验时查看。**

| 分类 | 目录 | 使用原则 |
|---|---|---|
| 最终文档 | `final/` | 强化版为当前依据；上一版仅供追溯 |
| 结果交付文档 | `deliverables/` | 当前结果、复现说明和验收附件 |
| 中间文档 | `intermediate/` | 保留方案演变、当时评审及修改前备份 |
| 可清理文档 | `cleanup_candidates/` | 已结束任务的工作笔记；尚未删除 |

## 最终文档

| 文件 | 定位 |
|---|---|
| [第一问_MILP_边际价值强化版.md](final/第一问_MILP_边际价值强化版.md) | 当前唯一执行依据：主MILP、LP诊断、嵌套基准、局部边际阈值、资源瓶颈与输入敏感性。 |
| [Q1最终优化模型-最终版.md](final/Q1最终优化模型-最终版.md) | 上一版本，原文保留用于追溯；当前实现以强化版为准。 |

执行时还需同时遵守用户后续明确确认的两点：Qmax按5000/6准确计算，833.3333只作显示；本轮按用户明确要求仅交付CSV，执行关闭后回读验证。模型正文已同步效率参数化、PV来源、上下限边际、多步长判据、原MILP双侧校验与分量纲容差。

## 结果交付文档

| 文件 | 定位 | 何时阅读 |
|---|---|---|
| [q1_marginal_analysis.md](deliverables/q1_marginal_analysis.md) | 新版经济机制、瓶颈与36组敏感性解释 | 查看新增分析结论 |
| [q1_results.md](deliverables/q1_results.md) | 正式计算结果摘要：题目表1、表2、全天费用/电量、效率比较与合理性分析 | 查看答案、整理论文结果 |
| [q1_run_guide.md](deliverables/q1_run_guide.md) | 运行命令、目录、CSV字段和单位说明 | 复现计算或读取输入输出 |
| [q1_implementation_acceptance.md](deliverables/q1_implementation_acceptance.md) | 实现验收：要求对应、实际检查、问题修复、假设边界和界面验证 | 审核实现是否符合模型 |
| [q1_source_line_traceability.csv](deliverables/q1_source_line_traceability.csv) | 154个展示公式及5项关键行内公式/判据的精确代码行、测试和本代证据索引 | 查某句原文对应的函数与证据；属于验收附件，不是论文正文 |

[24条代码review逐项处理CSV](deliverables/q1_code_review_resolution.csv) 保留原评论，明确用户对CSV的要求，并逐条给出代码、测试与当前运行证据。

真正的数据、代码和图表遵守项目目录规范，不搬入文档目录：

- [预处理输入CSV](../../inputs/q1/processed/timeseries.csv)
- [完整输出result1.csv](../../outputs/processed/q1/result1.csv)
- [全天结果汇总CSV](../../outputs/processed/q1/daily_summary.csv)
- [全部效率对比CSV](../../outputs/processed/q1/efficiency_comparison.csv)
- [输入输出可视报告](../../outputs/processed/q1/report.html)
- [求解程序入口](../../src/q1/run.py)

新版过程记录位于 `intermediate/marginal_value_work/task_plan.md` 和 `notes.md`，保留开发阶段与检查发现，不作为最终结果引用。

## 中间文档

| 文件 | 归类原因 | 保留价值 |
|---|---|---|
| [临时方案.md](intermediate/临时方案.md) | 采用LP及必要时MILP的求解路线，含KKT、对偶、额外敏感性等内容，已被当前最终稿取代 | 方案探索与后续论证素材 |
| [Q1_最终优化模型_结合comments.md](intermediate/Q1_最终优化模型_结合comments.md) | 虽名为“最终”，仍是规范化能流、精确LP松弛及词典序二级目标路线 | 旧版建模思路 |
| [Q1_最终优化模型修订版_结合评审comments.md](intermediate/Q1_最终优化模型修订版_结合评审comments.md) | 对上一条路线进一步修订，仍非当前六变量单目标MILP准绳 | 旧版推导与评审修改记录 |
| [Q1_精简修订版_公式兼容Obsidian.md](intermediate/Q1_精简修订版_公式兼容Obsidian.md) | 旧LP松弛路线的精简、公式排版版本 | 旧稿表达及排版参考 |
| [临时方案_严格审查报告.md](intermediate/临时方案_严格审查报告.md) | 对当时临时稿的审查；当前临时稿已修改，旧行号不一定对应现稿 | 历史风险与修复依据 |
| [q1_compact_review_comments.md](intermediate/q1_compact_review_comments.md) | 对精简稿的历史审查，数值为当时审查实验 | 旧模型审查证据 |

旧稿有不同目标、变量或分析范围，不能与当前最终稿拼接后声称已经实现。两份旧审查报告中的问题只针对当时被审稿件，不代表当前最终实现仍然存在这些问题。

## 哪些算“垃圾文档”

没有发现空文件或字节完全相同的副本。下面两份属于已完成任务的临时工作记录，可以优先清理；本次移入清理候选目录，保留原文。

| 文件 | 可清理原因 |
|---|---|
| [notes.md](cleanup_candidates/notes.md) | 任务中的发现摘要；有效结论已写入结果、运行说明、验收报告及CHANGE_HISTORY |
| [task_plan.md](cleanup_candidates/task_plan.md) | 所有步骤已完成的过程清单；任务结束后不再作为当前待办 |

中间稿不是现行交付文件，但仍保留独立的推导或评审信息，因此归档而不列为无价值文件。体积较大的逐行CSV是可再生成的验收索引，本次保留在交付附件中。

## 整理与后续维护

历史整理阶段只移动文件；本轮代码review修订了正式模型、代码与交付报告。生成文档通过current generation链接发布到 `deliverables/`，历史稿及清理候选保持原样。以往CHANGE_HISTORY保留当时路径，此目录表提供现址。

分类与移动清单、移动前后哈希、结果CSV不变性验证见 [整理验收记录](../../outputs/.q1-runs/legacy_before_atomic/raw/docs_organization_manifest.json)。以后新增探索稿放入 `intermediate/`；正式结果说明放入 `deliverables/`；当前模型必须在导航中唯一指定，保留的上一版本不得标为同时有效。

代码review原始CSV及修订前源码备份位于 `intermediate/code_review_work/`；本轮24条处理结果见交付验收文档。
