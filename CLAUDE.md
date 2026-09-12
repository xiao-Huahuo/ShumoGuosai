CLAUDE.md

**最优先规则**: 对用户提供的 TODO，必须逐句建立可验证的实现与验收对应关系,必须自己根据TODO反复逐句修改,绝对禁止自己随便实现一个长得像TODO但不符合用户的TODO的某一句的事情发生,每一句用户TODO都要在代码中有迹可循,每一句TODO都要遵守开发规范。禁止将任何一项降级为 MVP、替代实现或视觉近似；如无法复用用户指定组件，必须先说明阻塞并征得用户同意。完成前必须逐项进行实际界面冒烟验证，并报告未完成项。


用于减少常见 LLM 编码错误的行为指南。可根据需要与项目特定说明合并。



\*\*权衡：\*\*这些指南偏向谨慎而非速度。对于简单任务，请自行判断。



1\. 编码前先思考



不要假设。不要掩盖困惑。明确权衡。



在实现之前：



明确陈述你的假设。如果不确定，就提问。

如果存在多种理解方式，列出来——不要默默选择一个。

如果存在更简单的方法，说出来。在必要时提出反对意见。

如果有不清楚的地方，停下来。指出哪里不清楚，并提问。

2\. 简单优先



用最少的代码解决问题。不要做任何推测性的扩展。



不添加未被要求的功能。

不为一次性代码设计抽象。

不加入未被要求的“灵活性”或“可配置性”。

不为不可能发生的情况添加错误处理。

如果你写了 200 行但可以用 50 行解决，就重写。



问问自己：“资深工程师会觉得这过于复杂吗？”如果是，简化。



3\. 手术式修改



只改必要的部分。只清理你自己的改动带来的问题。



在修改已有代码时：



不要“顺便”改进相邻代码、注释或格式。

不要重构没有问题的部分。

保持现有风格，即使你有不同偏好。

如果发现无关的死代码，指出来——不要删除。



当你的修改产生遗留问题时：



移除因你的改动而变得未使用的导入/变量/函数。

不要删除原本就存在的死代码，除非被要求。



检验标准：每一行修改都应该能直接对应用户的请求。



4\. 目标驱动执行



定义成功标准。循环直到验证完成。



将任务转化为可验证的目标：



“添加校验” → “为非法输入编写测试，然后让测试通过”

“修复 bug” → “编写能复现 bug 的测试，然后让其通过”

“重构 X” → “确保修改前后测试均通过”



对于多步骤任务，给出简要计划：



1\. \[步骤] → 验证方式：\[检查点]

2\. \[步骤] → 验证方式：\[检查点]

3\. \[步骤] → 验证方式：\[检查点]



强有力的成功标准能让你独立推进。弱标准（例如“让它能用”）会导致频繁需要澄清。



当这些指南生效时：

代码差异中不必要的修改更少，因过度复杂而重写的情况更少，并且在出错前会先提出澄清问题。



5\. 每次开始编写代码,都必须先阅读`数学建模开发规范.md`.只允许符合开发规范的代码,禁止一切不符合开发规范的代码.
编码规范：本项目所有文件必须使用 UTF-8（推荐 UTF-8 no BOM）读写和保存，避免因 Windows PowerShell 5.1、系统默认代码页（如 CP936/GBK/ANSI）或工具链隐式编码导致中文、日文、emoji、特殊标点等字符乱码。修改文件时不得依赖 PowerShell 的默认 `Get-Content`、`Set-Content`、`Out-File` 编码行为；如必须使用 PowerShell，应显式指定 UTF-8 编码，或优先使用 Python/Node.js 等明确以 UTF-8 读写文件的方式。提交前请确保 VS Code、Git、终端和脚本均按 UTF-8 处理文本，避免将已经乱码的内容再次写回文件。


# Compact Instructions

When compacting context, preserve the following information with highest priority:

1. Current task goal and acceptance criteria.
2. User's explicit requirements and constraints.
3. Current implementation plan.
4. Files already modified and why they were modified.
5. Files that still need changes.
6. Important architecture decisions and rejected alternatives.
7. Known bugs, failed attempts, and reasons for failure.
8. Commands that were run and their important results.
9. Any unresolved questions or risks.

Do not discard user constraints, architecture decisions, or task progress.
If context is near the limit, update TASK_STATE.md before continuing.


所有的Skill不在.claude/或.codex/中,而是在.agents/中.凡是要用到Skill都应该到.agents/中去找.

