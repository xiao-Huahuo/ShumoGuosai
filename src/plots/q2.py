"""按科研绘图技能输出可独立导出的 PNG/SVG，所有图关联数值CSV。"""

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib import font_manager
import numpy as np
import warnings

from src.q2.data import SERIES

LABELS = {"load_kw": "小区负荷", "pv_kw": "光伏实际功率", "net_load_kw": "净负荷"}
COLORS = ("#0072B2", "#D55E00", "#009E73", "#AA3377", "#332288", "#117733", "#882255")
FORMS = {"raw": "原始", "diff144": "日差分", "diff1008": "周差分", "diff144_then1008": "日后周差分"}


def create_figures(frame, diagnostics, output):
    output.mkdir(parents=True, exist_ok=True)
    fonts = {f.name for f in font_manager.fontManager.ttflist}
    selected = next((f for f in ("PingFang SC", "Heiti TC", "Arial Unicode MS", "Noto Sans CJK SC", "Songti SC") if f in fonts), None)
    if not selected:
        raise RuntimeError("未找到中文字体；拒绝发布乱码图表")
    figures = []
    def save(fig, name, caption, sources):
        for suffix in ("png", "svg"):
            with warnings.catch_warnings():
                warnings.filterwarnings("error", message="Glyph .* missing from font")
                fig.savefig(output / f"{name}.{suffix}", dpi=220, facecolor="white")
        plt.close(fig)
        figures.append({"name": name, "caption": caption, "source_csv": sources, "font": selected,
                        "png_dpi": 220, "svg_text": "paths_for_portable_chinese", "scope": "full_year_retrospective"})
    with plt.rc_context({"font.family": selected, "font.size": 10, "axes.titlesize": 12,
                         "axes.unicode_minus": False, "axes.spines.top": False, "axes.spines.right": False,
                         "axes.grid": True, "grid.alpha": .18, "svg.fonttype": "path"}):
        for days in (7, 30):
            part = frame.iloc[:days * 144]
            fig, axes = plt.subplots(3, 1, figsize=(13, 8.5), sharex=True, layout="constrained")
            for i, (ax, variable) in enumerate(zip(axes, SERIES)):
                ax.plot(part.timestamp, part[variable], lw=.8, color=COLORS[i])
                ax.set(ylabel="功率 / kW", title=f"{chr(65+i)}  {LABELS[variable]}")
                ax.axhline(0, color="#777777", lw=.6)
            axes[-1].xaxis.set_major_formatter(mdates.DateFormatter("%m-%d"))
            axes[-1].set_xlabel("区间右端点（日期）")
            fig.suptitle(f"连续 {days} 天原始功率 · 从附件首日开始，无平滑", fontsize=15)
            save(fig, f"timeseries_{days}d", f"1月1日起连续{days}天负荷、光伏与净负荷；净负荷保留负值。", ["timeseries.csv"])

        fig, axes = plt.subplots(1, 2, figsize=(13, 8), layout="constrained")
        ticks = frame.drop_duplicates("month")["date"]
        for ax, variable in zip(axes, SERIES[:2]):
            matrix = frame.pivot(index="date", columns="slot", values=variable)
            im = ax.imshow(matrix, aspect="auto", interpolation="nearest", cmap="cividis", origin="upper",
                           extent=(0, 24, len(matrix), 0), vmin=0)
            ax.set(title=LABELS[variable], xlabel="区间内时刻 / h", ylabel="源日期（2025年）",
                   xticks=np.arange(0, 25, 4), yticks=[(d-frame.date.iloc[0]).days+.5 for d in ticks],
                   yticklabels=[d.strftime("%m-01") for d in ticks])
            ax.grid(False)
            fig.colorbar(im, ax=ax, label="功率 / kW（各面板独立色标）", shrink=.8)
        fig.suptitle("全年日期—时间热力图 · 每格为原始10分钟观测", fontsize=15)
        save(fig, "annual_heatmaps", "日期纵轴、日内时间横轴，原始365×144值，无插值；各变量使用独立且标明的色标。", ["timeseries.csv"])

        profiles = diagnostics["profiles"]
        for grouping, variables, name in (("month", SERIES, "monthly_profiles"),
                                           ("weekday", SERIES[:2], "weekday_profiles"),
                                           ("day_type", SERIES[:2], "weekday_weekend")):
            fig, axes = plt.subplots(len(variables), 1, figsize=(13, 3.8*len(variables)), layout="constrained")
            for ax, variable in zip(axes, variables):
                view = profiles.loc[(profiles.grouping == grouping) & (profiles.series == variable)]
                for i, (group, part) in enumerate(view.groupby("group", sort=True)):
                    label = (f"{int(group)}月" if grouping == "month" else "星期"+"一二三四五六日"[int(group)-1]
                             if grouping == "weekday" else "周一至周五" if group == "weekday" else "周六至周日")
                    ax.plot(part.slot/6, part.mean_kw, label=label, color=COLORS[i % 7],
                            linestyle=("-", "--", "-.", ":")[i // 3 % 4], lw=1.3)
                ax.set(title=LABELS[variable], ylabel="平均功率 / kW", xlabel="区间右端点 / h",
                       xticks=np.arange(0, 25, 2), xlim=(0, 24))
                ax.legend(ncols=2 if grouping == "month" else 1, fontsize=9, loc="upper left", bbox_to_anchor=(1.01, 1))
            fig.suptitle({"month": "12个月平均日曲线", "weekday": "星期平均日曲线 · 光伏星期效应仅据数据观察",
                          "day_type": "周一至周五与周末平均日曲线 · 不包含法定节假日推断"}[grouping], fontsize=15)
            save(fig, name, "同类源日期同槽位算术平均；原始功率未改值或填补，分组样本量与标准差见CSV。", ["full_year_profiles.csv"])

        curves = diagnostics["acf_pacf"]
        fig, axes = plt.subplots(4, 3, figsize=(14, 12), layout="constrained")
        for row, (variable, statistic) in enumerate((v, s) for v in SERIES[:2] for s in ("acf", "pacf")):
            view = curves.loc[curves.series == variable]
            for ax, maximum in zip(axes[row], (60, 432, 2016)):
                part = view.loc[(view.lag > 0) & (view.lag <= maximum)]
                ax.vlines(part.lag, 0, part[statistic], color=COLORS[row//2], lw=.7)
                ax.axhline(0, color="#555555", lw=.6)
                for lag in (144, 288, 432, 1008, 2016):
                    if lag <= maximum:
                        ax.axvline(lag, color="#AA3377", lw=.6, ls="--")
                ax.set(title=f"{LABELS[variable]} · {statistic.upper()} · 1–{maximum}",
                       xlabel="滞后 / 10 min", ylabel="相关系数", xlim=(0, maximum+1))
                ax.set_xticks({60: [0, 12, 24, 36, 48, 60], 432: [0, 144, 288, 432],
                               2016: [0, 288, 576, 1008, 1440, 2016]}[maximum])
        fig.suptitle("自相关与Burg偏自相关 · 三种滞后尺度，未把白噪声界限当季节显著性", fontsize=14)
        save(fig, "acf_pacf", "计算全部1至2016阶；短滞后、3日与14日视图展示衰减及日/周结构。", ["full_year_acf_pacf.csv"])

        spectra = diagnostics["spectrum"]
        fig, axes = plt.subplots(2, 2, figsize=(13, 8), layout="constrained")
        for row, variable in enumerate(SERIES[:2]):
            for col, form in enumerate(("raw", "daily_profile_residual")):
                part = spectra.loc[(spectra.series == variable) & (spectra.form == form)]
                positive = part.psd_kw2_per_cycle_per_day > 0
                ax = axes[row, col]
                ax.loglog(part.loc[positive, "frequency_per_day"], part.loc[positive, "psd_kw2_per_cycle_per_day"],
                          color=COLORS[row], lw=.8)
                for frequency, label in ((1, "1日"), (1/7, "7日")):
                    ax.axvline(frequency, color="#AA3377", ls="--", lw=.8, label=label)
                    ax.text(frequency, .97 if frequency == 1 else .87, label, transform=ax.get_xaxis_transform(), va="top")
                ax.set(title=f"{LABELS[variable]} · {'原始去均值' if col == 0 else '去除平均日曲线'}",
                       xlabel="频率 /（周期/日）（log）", ylabel="PSD / [kW²/(周期/日)]（log）")
        fig.suptitle("频谱验证 · 全部正频率，无补零或平滑；目标频点数值另附CSV", fontsize=14)
        save(fig, "spectra", "FFT周期图；两轴对数，仅正PSD可显示，零频不表示周期；完整频点与局部峰见CSV。", ["full_year_spectrum.csv", "full_year_spectral_targets.csv"])

        stability = diagnostics["monthly_stability"]
        fig, axes = plt.subplots(2, 2, figsize=(13, 8), layout="constrained")
        for i, variable in enumerate(SERIES[:2]):
            part = stability.loc[stability.series == variable]
            for lag, style in (("daily_lag_r", "-"), ("weekly_lag_r", "--")):
                axes[0, 0].plot(part.month, part[lag], color=COLORS[i], ls=style, marker="o" if i == 0 else "s",
                                label=f"{LABELS[variable]} · {'1日' if lag == 'daily_lag_r' else '7日'}")
            for ax, metric in ((axes[0, 1], "mean_daily_amplitude_kw"), (axes[1, 0], "std_kw"), (axes[1, 1], "mean_kw")):
                ax.plot(part.month, part[metric], color=COLORS[i], marker="o" if i == 0 else "s", label=LABELS[variable])
        for ax, title, ylabel in zip(axes.flat, ("当月日/周滞后相关", "平均日峰谷差", "月内波动", "月平均水平"),
                                    ("Pearson r", "功率差 / kW", "样本标准差 / kW", "平均功率 / kW")):
            ax.set(title=title, xlabel="源日期月份", ylabel=ylabel, xticks=np.arange(1, 13))
            ax.legend(fontsize=8)
        axes[0, 0].set_ylim(-1, 1)
        fig.suptitle("周期稳定性 · 滞后配对两端均在同月，不以全年均值代替局部证据", fontsize=14)
        save(fig, "monthly_stability", "按月比较日/周相关、日峰谷差、标准差及均值；没有预设稳定性阈值。", ["full_year_monthly_stability.csv"])

        moments = diagnostics["transformed_monthly_moments"]
        fig, axes = plt.subplots(4, 2, figsize=(13, 12), layout="constrained")
        for row, form in enumerate(FORMS):
            for i, variable in enumerate(SERIES[:2]):
                view = moments.loc[(moments.form == form) & (moments.series == variable)]
                for ax, metric in zip(axes[row], ("mean_kw", "std_kw")):
                    ax.plot(view.month, view[metric], color=COLORS[i], marker="o" if i == 0 else "s", label=LABELS[variable])
                    ax.set(title=f"{FORMS[form]} · {'均值' if metric == 'mean_kw' else '样本标准差'}",
                           xlabel="源日期月份", ylabel="功率 / kW", xticks=np.arange(1, 13))
                    ax.axhline(0, color="#888888", lw=.6)
        handles, labels = axes[0, 0].get_legend_handles_labels()
        fig.legend(handles, labels, loc="outside lower center", ncols=2, fontsize=10)
        fig.suptitle("季节处理后的月度均值与波动 · 联合差分仅作诊断，可能过度差分", fontsize=14)
        save(fig, "seasonal_moments", "原始、日差分、周差分与日后周差分均使用单侧历史运算；均值稳定不能替代方差稳定。", ["full_year_transformed_monthly_moments.csv", "full_year_stationarity_tests.csv"])

        daily = diagnostics["daily_statistics"]
        fig, axes = plt.subplots(2, 2, figsize=(13, 8), layout="constrained")
        for row, variable in enumerate(SERIES[:2]):
            part = daily.loc[daily.series == variable]
            axes[row, 0].plot(part.date, part.max_kw, color=COLORS[row], lw=.7)
            axes[row, 1].scatter(part.date, part.peak_first_slot/6, color=COLORS[row], s=5)
            for ax, title, ylabel in zip(axes[row], ("每日峰值", "每日峰值首次出现时刻"), ("功率 / kW", "右端点 / h")):
                ax.set(title=f"{LABELS[variable]} · {title}", ylabel=ylabel, xlabel="日期")
                ax.xaxis.set_major_formatter(mdates.DateFormatter("%m月"))
            axes[row, 1].set(ylim=(-.5, 24.5), yticks=np.arange(0, 25, 4))
        fig.suptitle("峰值水平与峰值时段迁移 · 并列峰值数量、连续低光伏见每日统计", fontsize=14)
        save(fig, "daily_peaks", "每个日期原始峰值及其首次右端点；并列峰值保留数量，不把全零日人为改值。", ["full_year_daily_statistics.csv"])
    return figures
