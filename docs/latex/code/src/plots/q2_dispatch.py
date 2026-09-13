"""第二问最终方案检验图；只读取已产生的CSV/JSON，未完成指标不画成0。"""

from pathlib import Path
import json

import numpy as np
import pandas as pd

from common import COLORS, setup, save


def create(run_path):
    run_path = Path(run_path)
    output = run_path/"processed/figures"
    output.mkdir(parents=True, exist_ok=True)
    plt, font = setup()
    generated = []
    metrics_path = run_path/"processed/experiments/forecast_metrics.csv"
    if metrics_path.exists():
        metrics = pd.read_csv(metrics_path)
        fig, axes = plt.subplots(1, 2, figsize=(11, 4.5), layout="constrained")
        labels = {"load_week": "负荷周季节基线", "load_lgb_1": "负荷LightGBM", "load_lgb_0": "负荷LightGBM", "pv_mean7": "光伏7日均值", "pv_dhr": "光伏谐波ARMA"}
        for ax, prefix, color in ((axes[0], "load_", COLORS["grid"]), (axes[1], "pv_", COLORS["pv"])):
            for i, name in enumerate(v for v in labels if v.startswith(prefix)):
                group = metrics[metrics.model == name].sort_values("horizon")
                if group.empty:
                    continue
                ax.plot(group.horizon+1, group.mae_kw, marker="o", ls="--" if name.endswith(("week", "mean7")) else "-",
                        label=labels[name], color=color if name.endswith(("week", "mean7")) else COLORS["discharge"])
            ax.set(xticks=[1, 2, 3], xlabel="前瞻日", ylabel="MAE / kW", title="负荷候选" if prefix == "load_" else "光伏候选")
            ax.legend(frameon=False)
        fig.suptitle("不同预测步长的样本外误差 · 2—12月事后评价", fontsize=14)
        save(fig, output, "forecast_horizons"); generated.append("forecast_horizons")
    variance_path = run_path/"processed/seasonal_difference_variance.csv"
    if variance_path.exists():
        frame = pd.read_csv(variance_path)
        fig, ax = plt.subplots(figsize=(8, 4.5), layout="constrained")
        names = {"load_kw": "负荷", "pv_kw": "光伏", "net_load_kw": "净负荷"}
        for i, (lag, color, label) in enumerate(((144, COLORS["grid"], "1日差分"), (1008, COLORS["charge"], "7日差分"))):
            part = frame[frame.lag == lag].set_index("series").loc[list(names)]
            bars = ax.bar(np.arange(3)+(i-.5)*.34, part.variance_ratio, .32, label=label, color=color)
            ax.bar_label(bars, fmt="%.3f", padding=3, fontsize=9)
        ax.axhline(1, color=COLORS["muted"], lw=1, ls="--")
        ax.set(xticks=np.arange(3), xticklabels=list(names.values()), ylabel="差分方差 / 同区间原始方差",
               title="季节差分对波动的压缩程度 · 事后诊断")
        ax.legend(frameon=False)
        save(fig, output, "seasonal_variance"); generated.append("seasonal_variance")
    residual_files = [run_path/f"raw/shadows/dhr/{date}_correlations.csv" for date in ("2025-03-20", "2025-06-21", "2025-09-23", "2025-12-21")]
    if all(path.exists() for path in residual_files):
        fig, axes = plt.subplots(4, 2, figsize=(12, 10), layout="constrained")
        for row, path in enumerate(residual_files):
            frame = pd.read_csv(path)
            for col, key in enumerate(("acf", "pacf")):
                ax = axes[row, col]
                ax.plot(frame.lag[1:], frame[key][1:], color=COLORS["pv"] if col == 0 else COLORS["grid"], lw=1)
                ax.axhline(0, color=COLORS["muted"], lw=.7)
                ax.set(title=f"{path.stem[:10]} · {key.upper()}", xticks=[1, 36, 72, 108, 144], ylabel="相关系数")
                if row == 3:
                    ax.set_xlabel("滞后 / 10 min")
        fig.suptitle("光伏谐波回归残差诊断 · 各预测时点仅用已实现历史", fontsize=14)
        save(fig, output, "dhr_residuals"); generated.append("dhr_residuals")
    daily_path = run_path/"processed/main/daily.csv"
    if daily_path.exists():
        daily = pd.read_csv(daily_path, parse_dates=["date"])
        if not daily.empty:
            fig, axes = plt.subplots(2, 1, figsize=(11, 7), layout="constrained", sharex=True)
            axes[0].plot(daily.date, daily.cost, color=COLORS["grid"])
            axes[0].set(ylabel="真实费用 / 元", title=f"已完成的主模型回放：{len(daily)}日")
            axes[1].plot(daily.date, daily.final_soc, color=COLORS["energy"])
            axes[1].axhline(1200, color=COLORS["muted"], ls="--", lw=.7)
            axes[1].axhline(10800, color=COLORS["muted"], ls="--", lw=.7)
            axes[1].set(ylabel="日末SOC / kWh", xlabel="源日期")
            save(fig, output, "real_rollout"); generated.append("real_rollout")
    (output/"manifest.json").write_text(json.dumps({"font": font, "figures": generated,
                                                   "formats": ["png", "svg"], "missing_metrics_not_zero": True},
                                                  ensure_ascii=False, indent=2), encoding="utf-8")
    return generated


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    print(create(parser.parse_args().run_dir))
