# 第二问尾部分层与动态 reserve 运行说明

## 当前正式成果

运行目录：

`outputs/q2/dispatch_runs/20260912_tail_reserve_final`

核心文件：

- `processed/main/result2.xlsx`
- `processed/main/summary.json`
- `processed/main/final_validation.json`
- `processed/main/final_calibration.csv`
- `processed/main/final_calibration.json`
- `processed/main/solver_statistics.json`
- `processed/main/paper_table1.csv`
- `processed/main/paper_table2.csv`
- `processed/main/paper_table3.csv`
- `processed/report.html`

## 复用预测缓存

```powershell
python src/q2/dispatch.py reuse-prepared `
  --source-run outputs/q2/dispatch_runs/20260911_224501 `
  --run-dir outputs/q2/dispatch_runs/<new-run>
```

该命令逐摘要核验输入和影子预测，只复用与场景分层/reserve 修改无关的缓存，不复制旧主回放。

## 正式运行与断点续跑

首次运行：

```powershell
python src/q2/dispatch.py run `
  --run-dir outputs/q2/dispatch_runs/<new-run> `
  --rescue-seconds 900
```

中断后：

```powershell
python src/q2/dispatch.py run `
  --run-dir outputs/q2/dispatch_runs/<new-run> `
  --rescue-seconds 900 `
  --resume
```

未指定 `--resume` 时，若已有逐日结果则拒绝覆盖。每完成一天立即更新 `dispatch.csv`、`daily.csv`、`calibration.csv` 和 `checkpoint.json`。

## 最终报告与测试

```powershell
python src/q2/final_report.py `
  --run-dir outputs/q2/dispatch_runs/<new-run> `
  --verify
```

正式配置固定为：tail fraction 20%、reserve quantile 80%、2 月 1 日 SOC 6000 kWh、MIP gap 3%、refine 5 秒、solver thread 1。额外 27 项开发型全年实验不再默认运行。
