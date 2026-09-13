# Q2旧baseline结果恢复

2026-09-13为减少项目体积，将原 `results/` 完整归档为 `results.tar.gz`。78份源码、`baseline_manifest.csv` 与 `baseline_summary.json` 仍保持原字节。归档含11977个文件，每个文件均与清理前SHA-256一致；正式运行 `outputs/q2/dispatch_runs/20260912_tail_reserve_final/` 不依赖此归档。

压缩包SHA-256：`c1c0a7b996719be6b269b80fd2ed25a57ee115effe48a88abc1380fc8fa13136`。

在项目根目录执行以下命令，可恢复原 `results/` 路径；如该目录已存在，应先核对其用途，避免覆盖后续数据。

```sh
tar -xzf outputs/history/q2_baselines/pre_tail_reserve_20260912/results.tar.gz -C outputs/history/q2_baselines/pre_tail_reserve_20260912
```

恢复后的历史清单与数据对应关系保持不变。完整清理记录见 [清理报告](../../../../docs/storage_cleanup_20260913.md)。
