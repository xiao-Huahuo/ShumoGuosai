"""2.1.5–2.1.11：描述、时域/频域、稳定性与季节差分；不替代预测验证。"""

import warnings

import numpy as np
import pandas as pd
from scipy.signal import periodogram
from statsmodels.tsa.stattools import acf, adfuller, kpss, pacf_burg
from threadpoolctl import threadpool_limits

from data import SERIES, SHEETS

LAGS = (1, 6, 144, 288, 1008, 2016)
MAX_LAG = 2016
SETTINGS = {
    "scope": "full_year 为事后描述；initial_history 仅含首次回测前严格可见的观测",
    "continuous_curve_start": "2025-01-01（附件起点，非择优选取）",
    "key_lags": LAGS, "acf_pacf_max_lag": MAX_LAG,
    "acf": "FFT, adjusted=False；常数序列相关无定义",
    "pacf": "Burg, demean=True；直接计算至2016，不跳过周滞后",
    "correlation_interpretation": "报告效应量，不把高频相关当独立样本显著性；7日相关可能仅为日周期重复",
    "spectrum": "periodogram fs=144/day, boxcar, detrend=constant, density；保留所有正频率，不插值",
    "spectral_peak": "目标最近离散频点及其左右紧邻频点；局部峰不等于统计显著",
    "stability": "按原始月份；滞后两端均限制于当月；std ddof=1；不设稳定/不稳定硬阈值",
    "stationarity": "raw, diff144, diff1008, diff144_then1008；ADF默认Schwert上限+ BIC选滞后；KPSS auto",
    "stationarity_regression": "每种变换分别检验c（水平平稳）与ct（趋势平稳）；记录1%、5%、10%临界值",
    "stationarity_caveat": "ADF拒绝单位根不证明季节/方差稳定；KPSS表外p值按上下界标记；联合差分或过度差分",
    "outlier_policy": "所有局部转折点提供前后值与既往同星期同槽位上下文；只排序，不删除或平滑",
    "calendar": "weekday=1..7 按源日期；周末仅指周六周日，不推断法定节假日或调休",
    "pv_night": "统计零值占比与全零槽位；没有日出日落元数据，不能预设固定夜间窗口",
    "numeric_setting_role": "以上均为明确披露的计算/显示方法，不是新增题设或预测模型参数",
    "candidate_priority": "仅初始历史：日频局部峰、去日曲线后周频局部峰、残差周相关大于日相关三项一致时优先比较DHR_AR；仅比较证据，不等同统计显著性或最终选型",
}


def correlation(x, y):
    x, y = np.asarray(x), np.asarray(y)
    if len(x) < 2 or np.std(x) == 0 or np.std(y) == 0:
        return np.nan
    return float(np.corrcoef(x, y)[0, 1])


def describe(frame):
    profiles = []
    for variable in SERIES:
        for grouping in ("month", "weekday"):
            part = frame.groupby([grouping, "slot"])[variable].agg(["mean", "std", "count"]).reset_index()
            part = part.rename(columns={grouping: "group", "mean": "mean_kw", "std": "std_kw", "count": "n"})
            part["grouping"], part["series"] = grouping, variable
            profiles.append(part)
        part = frame.assign(day_type=np.where(frame.weekday <= 5, "weekday", "weekend"))
        part = part.groupby(["day_type", "slot"])[variable].agg(["mean", "std", "count"]).reset_index()
        part = part.rename(columns={"day_type": "group", "mean": "mean_kw", "std": "std_kw", "count": "n"})
        part["grouping"], part["series"] = "day_type", variable
        profiles.append(part)
    daily = []
    for date, group in frame.groupby("date", sort=True):
        for variable in SERIES:
            x = group[variable]
            peaks = group.loc[x == x.max()]
            daily.append({"date": date, "month": date.month, "weekday": date.dayofweek + 1,
                          "series": variable, "n": len(group), "mean_kw": x.mean(), "std_kw": x.std(),
                          "min_kw": x.min(), "max_kw": x.max(), "amplitude_kw": x.max() - x.min(),
                          "peak_first_slot": int(peaks.slot.iloc[0]), "peak_tie_count": len(peaks),
                          "zero_points": int((x == 0).sum()), "all_zero": bool((x == 0).all())})
    summary = pd.DataFrame([{"series": v, "n": len(frame), "mean_kw": frame[v].mean(),
                             "std_kw": frame[v].std(), "min_kw": frame[v].min(), "max_kw": frame[v].max(),
                             "zero_count": int((frame[v] == 0).sum())} for v in SERIES])
    zeros = frame.groupby("slot").pv_kw.agg(n="size", zero_points=lambda x: int((x == 0).sum())).reset_index()
    zeros["zero_fraction"] = zeros.zero_points / zeros.n
    return pd.concat(profiles, ignore_index=True), pd.DataFrame(daily), summary, zeros


def seasonal_transforms(x):
    x = pd.Series(np.asarray(x, dtype=float))
    return {"raw": x, "diff144": x.diff(144), "diff1008": x.diff(1008),
            "diff144_then1008": x.diff(144).diff(1008)}


def lag_analysis(frame, scope):
    keys, curves = [], []
    for variable in SHEETS:
        x = frame[variable].to_numpy()
        # 以本scope的平均日曲线去除日内形状，仅供本scope描述；不传入预测器。
        residual = x - frame.groupby("slot")[variable].transform("mean").to_numpy()
        for form, values in (("raw", x), ("daily_profile_residual", residual)):
            for lag in LAGS:
                keys.append({"scope": scope, "series": variable, "form": form, "lag": lag,
                             "lag_days": lag / 144, "n_pairs": max(len(x) - lag, 0),
                             "pearson_r": correlation(values[lag:], values[:-lag])})
        limit = min(MAX_LAG, len(x) // 2 - 1)
        if np.std(x) == 0:
            a, p = np.full(limit + 1, np.nan), np.full(limit + 1, np.nan)
        else:
            a = acf(x, nlags=limit, fft=True, adjusted=False, missing="raise")
            with threadpool_limits(limits=1):
                p, _ = pacf_burg(x, nlags=limit, demean=True)
        curves.extend({"scope": scope, "series": variable, "lag": lag, "lag_days": lag / 144,
                       "acf": a[lag], "pacf": p[lag], "n": len(x)} for lag in range(limit + 1))
    return pd.DataFrame(keys), pd.DataFrame(curves)


def spectral_analysis(frame, scope):
    curves, targets = [], []
    for variable in SHEETS:
        x = frame[variable].to_numpy()
        for form, values in (("raw", x), ("daily_profile_residual", x - frame.groupby("slot")[variable].transform("mean").to_numpy())):
            frequency, density = periodogram(values, fs=144, window="boxcar", detrend="constant", scaling="density")
            total_variance = density.sum() * (frequency[1] - frequency[0])
            curves.extend({"scope": scope, "series": variable, "form": form, "frequency_per_day": f,
                           "period_days": 1 / f, "psd_kw2_per_cycle_per_day": d}
                          for f, d in zip(frequency[1:], density[1:]))
            for days in (1, 7):
                i = int(np.argmin(abs(frequency - 1 / days)))
                local = bool(density[i] > density[i - 1] and density[i] > density[i + 1])
                targets.append({"scope": scope, "series": variable, "form": form, "target_period_days": days,
                                "target_frequency_per_day": 1 / days, "frequency_resolution_per_day": frequency[1],
                                "nearest_frequency_per_day": frequency[i], "nearest_period_days": 1 / frequency[i],
                                "target_psd": density[i], "left_psd": density[i - 1], "right_psd": density[i + 1],
                                "local_peak": local, "bin_variance_fraction": density[i] * frequency[1] / total_variance if total_variance > 0 else np.nan,
                                "integrated_psd_kw2": total_variance, "population_variance_kw2": np.var(values),
                                "interpretation": "descriptive_not_significance_test"})
    return pd.DataFrame(curves), pd.DataFrame(targets)


def stability_analysis(frame, scope):
    rows = []
    for month, part in frame.groupby("month"):
        for variable in SERIES:
            x = part[variable].to_numpy()
            daily = part.groupby("date")[variable].agg(["max", "min"])
            average_profile = part.groupby("slot")[variable].mean()
            rows.append({"scope": scope, "month": month, "series": variable, "n": len(x),
                         "mean_kw": np.mean(x), "std_kw": np.std(x, ddof=1),
                         "daily_lag_r": correlation(x[144:], x[:-144]),
                         "weekly_lag_r": correlation(x[1008:], x[:-1008]),
                         "daily_pairs": max(0, len(x) - 144), "weekly_pairs": max(0, len(x) - 1008),
                         "mean_daily_amplitude_kw": (daily["max"] - daily["min"]).mean(),
                         "mean_profile_amplitude_kw": average_profile.max() - average_profile.min(),
                         "cv": np.std(x, ddof=1) / abs(np.mean(x)) if np.mean(x) != 0 else np.nan})
    return pd.DataFrame(rows)


def stationarity_analysis(frame, scope):
    tests, moments, transformed = [], [], []
    with threadpool_limits(limits=1):
        for variable in SHEETS:
            for form, values in seasonal_transforms(frame[variable]).items():
                mask = values.notna().to_numpy()
                x = values.dropna().to_numpy()
                view = frame.loc[mask, ["date", "timestamp", "month"]].copy()
                view["value_kw"], view["series"], view["form"], view["scope"] = x, variable, form, scope
                transformed.append(view)
                for month, part in view.groupby("month"):
                    moments.append({"scope": scope, "series": variable, "form": form, "month": month,
                                    "n": len(part), "mean_kw": part.value_kw.mean(), "std_kw": part.value_kw.std()})
                for regression in ("c", "ct"):
                    for test in ("ADF", "KPSS"):
                        base = {"scope": scope, "series": variable, "form": form, "test": test,
                                "regression": regression, "input_n": len(x)}
                        if len(x) < 10 or np.std(x) == 0:
                            tests.append({**base, "status": "undefined_constant_or_short", "warning": "不强行检验"})
                            continue
                        with warnings.catch_warnings(record=True) as caught:
                            warnings.simplefilter("always")
                            if test == "ADF":
                                stat, p, lag, nobs, critical, bic = adfuller(x, regression=regression, autolag="BIC")
                                bound = "approximate"
                            else:
                                stat, p, lag, critical = kpss(x, regression=regression, nlags="auto")
                                nobs, bic = len(x), np.nan
                                bound = "less_than" if p == 0.01 else "greater_than" if p == 0.1 else "interpolated"
                        tests.append({**base, "status": "ok", "statistic": stat, "p_value": p, "p_value_type": bound,
                                      "selected_lags": lag, "test_n": nobs, "bic": bic,
                                      "critical_1pct": critical["1%"], "critical_5pct": critical["5%"],
                                      "critical_10pct": critical["10%"],
                                      "reject_null_1pct": bool(stat < critical["1%"] if test == "ADF" else stat > critical["1%"]),
                                      "reject_null_5pct": bool(stat < critical["5%"] if test == "ADF" else stat > critical["5%"]),
                                      "reject_null_10pct": bool(stat < critical["10%"] if test == "ADF" else stat > critical["10%"]),
                                      "warning": " | ".join(str(w.message) for w in caught)})
    return pd.DataFrame(tests), pd.DataFrame(moments), pd.concat(transformed, ignore_index=True)


def analyze_scope(frame, scope):
    print(f"{scope}: {len(frame)} 点，描述与相关诊断", flush=True)
    profiles, daily, summary, zeros = describe(frame)
    lags, correlation_curves = lag_analysis(frame, scope)
    spectrum, spectral_targets = spectral_analysis(frame, scope)
    stability = stability_analysis(frame, scope)
    print(f"{scope}: ADF/KPSS 原始、日差分、周差分、联合差分", flush=True)
    tests, moments, transforms = stationarity_analysis(frame, scope)
    return {"profiles": profiles, "daily_statistics": daily, "summary": summary, "pv_zero_profile": zeros,
            "lag_correlations": lags, "acf_pacf": correlation_curves, "spectrum": spectrum,
            "spectral_targets": spectral_targets, "monthly_stability": stability,
            "stationarity_tests": tests, "transformed_monthly_moments": moments, "transformed_series": transforms}
