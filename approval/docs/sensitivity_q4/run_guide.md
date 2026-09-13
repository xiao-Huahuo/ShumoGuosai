# 第四问敏感性复现与验收

执行顺序：Q4-2半径8项 → Q4-2权重8项 → Q4-3半径4项；新增32节点。原始方案已逐字节归档。正式v2/v3源码、HiGHS1.15.1、固定随机种子20250913、W56/S20、3%配置及30秒节点预算保留，实际全部LP最优。

在项目根目录运行（UTF-8）：

```sh
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONUTF8=1
.venv/bin/python -u src/sensitivity/q4_experiment.py 4-2
.venv/bin/python -u src/sensitivity/q4_experiment.py 4-3
.venv/bin/python src/sensitivity/q4_report.py
```

已有20项结果时自动校验并复用收据，不重求解；缺失收据从该项重做，已完成项保留。输入/基准源文件hash不符会拒绝。求解失败保存failure.json并停止，不降低精度或使用替代策略。基准只重建场景和矩阵做一致性验收，不调用求解器。

验收步骤与证据：
1. 自动选日：representatives.json、两个selection_metrics CSV；四种/两种规则及去重，已在变体前保存。
2. 单因素冻结：baseline_hashes、12份frozen场景矩阵；rho两档指纹一致，权重八项全流程重建；每例audit保留base/test配置。
3. 实际运行：20份cases/dispatch.csv（各144行）+audit.json+result.json；Q4-3每例4节点。报告脚本独立重算结算、验证SOC、历史边界和证书。
4. 汇总：daily_results.csv共30行（20变体+10参数基准行），summary.csv九组中位数/最小/最大，solver_quality.csv32节点；空紧急分母不造百分比。
5. 界面：本地HTML实际浏览器检查20/20、32/32、三组范围、全表与报告链接，ui_smoke.json存记录。

已知解释限制：无预设稳定性数值门限；只支持4/2代表日局部结果；Q4-3风险日调整量显著响应。W/S可选项按第19节停止；未做全年/预测重训/消融/汇总bootstrap。

开发首轮在未启动任何变体前发现新脚本build_matrix返回值解包数不符，已按原函数六返回值修复，再次通过12个基准矩阵SHA；未改原生产代码、未放松验收、未丢弃任何不利实验。
