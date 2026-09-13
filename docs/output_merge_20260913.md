# 跨电脑 outputs 合并与编码验收（2026-09-13）

## 来源与优先级

- 外部来源：`D:/Softwares/Wechat/WechatChatMessages/xwechat_files/wxid_upurj1c0hwme22_9950/msg/file/2026-09/ShumoGuosai(1)/ShumoGuosai/outputs`。
- 最终目录：`D:/Projects/Python/ShumoGuosai/outputs`。
- 合并规则：本机是最终版本；外部独有文件补入，同相对路径文件不覆盖本机，不删除本机任何文件。
- 本机 `outputs/history/q2_baselines`、全部 Q2 正式运行和活动 Q4 运行均保留；外部缺少 baseline 不解释为需要删除或回退本机 baseline。

## 文件合并

- 合并前外部：18,655 文件、955,059,046 bytes；本机：27,133 文件、1,556,733,027 bytes。
- 相对路径比较得到外部独有6,251文件，其中 `q3` 6,249个、`processed/q3_monitor` 2个。
- 复制137.68 MiB，0失败、0 mismatch；合并后外部18,655个相对路径在本机全部存在。
- 合并后本机33,396文件，其中外部同路径18,655个、本机独有14,741个。
- 合并前同路径12,399个同大小文件逐一计算SHA-256，内容差异为0。
- 仅5个同路径文件大小不同，均为旧Q3计时样本/报告；按本机优先规则未覆盖：两个 `extended_timing` 节点JSON，以及 `timing_final` 的HTML、runtime projection CSV和timing report JSON。

## 编码处理

- 对外部独有的5,957个JSON/CSV/HTML/Markdown/TXT/LOG/SH/TOML文件进行严格UTF-8解码：0个非法UTF-8，0个常见正文乱码命中；因此原字节复制，没有批量转码。
- 发现两份旧Q2交付物文件名已发生UTF-8/GBK错解。根据 `docs/2/revision_work/file_inventory.csv` 恢复正确名称：
  - `第二问_94天结果及CSV.zip`，SHA-256 `5B5C47EAF05FFC93640279189D64601A20E15DA9DC886BF75E0DA9C2D1E71A19`；
  - `第二问_94天阶段结果_20250201-20250505.xlsx`，SHA-256 `7B0E8D4EB6C954940F4DDD74EC9246A289C6B2E6C5806F7CBF5D07223B578A44`。
- 正确名称文件与原乱码名称文件逐字节相同。原乱码别名暂时保留作为可恢复历史，不删除数据。
- 外部Q3历史审计中的Mac绝对路径保留原字节，避免破坏收据；`outputs/q3/active_run.json` 已单独改为本机最终运行路径。

## 第三问最终结果复核

- 正式结果：`outputs/q3/raw/full_priority_rescue_7h_20260912/main/result3.xlsx`。
- SHA-256：`BE09FFB1AC5088350CC2032F320166FCD2E161DB79D6CE557C353F216FABDC81`，与远程验收文档一致。
- `state.json` 含365日；1,095个逐日dispatch/audit/information收据SHA不匹配数为0。
- 正式CSV为334日、48,096行，覆盖2025-02-01至2025-12-31。
- 当前本机代码重新执行全年物理/SOC校验通过；`result3.xlsx` 四个工作表与CSV逐值回读通过。

## 最终状态

- 本机Q2 baseline仍有12,057个文件、586,149,322 bytes，未被外部缺失状态影响。
- Q3完整结果已经落到本机README规定的最终路径。
- Q4目录完全由本机保留；合并验收时4-3仍在原进程继续计算，没有被外部outputs覆盖。

