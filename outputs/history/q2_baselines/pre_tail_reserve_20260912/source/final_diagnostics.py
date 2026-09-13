"""新方案2.3的事后修正：局部PV日曲线残差及同评价区间的季节差分方差。"""

import numpy as np
import pandas as pd
import json

from data import write_csv
from forecast import _harmonic_design
from protocol import PROTOCOL


def descriptive_corrections(frame, output):
    local, differences = [], []
    for month, group in frame.groupby("month"):
        pv = group.pv_kw.to_numpy()
        mean_curve = group.groupby("slot").pv_kw.transform("mean").to_numpy()
        residual = pv-mean_curve
        for lag in (144, 1008):
            for name, values in (("raw_pv", pv), ("within_month_profile_residual", residual)):
                left, right = values[:-lag], values[lag:]
                correlation = float(np.corrcoef(left, right)[0, 1]) if left.std() > 0 and right.std() > 0 else np.nan
                local.append({"month": month, "series": name, "lag": lag, "pairs": len(left),
                              "correlation": correlation, "scope": "posthoc_month_never_online_features"})
    for variable in ("load_kw", "pv_kw", "net_load_kw"):
        values = frame[variable].to_numpy()
        for lag in (144, 1008):
            original, difference = values[lag:], values[lag:]-values[:-lag]
            raw_variance, variance = np.var(original, ddof=1), np.var(difference, ddof=1)
            differences.append({"series": variable, "lag": lag, "n": len(difference),
                                "raw_variance_kw2_same_target_times": raw_variance,
                                "difference_variance_kw2": variance,
                                "variance_ratio": variance/raw_variance if raw_variance else np.nan,
                                "scope": "posthoc_only_not_model_order_selection"})
    write_csv(output/"pv_local_residual_correlations.csv", pd.DataFrame(local))
    write_csv(output/"seasonal_difference_variance.csv", pd.DataFrame(differences))


def dhr_residual_stability(frame, shadows, output):
    """各origin当时窗口的均值漂移和白噪声诊断，不修改影子预测。"""
    actual = frame.pv_kw.to_numpy().reshape(365, 144)
    dates = pd.DatetimeIndex(pd.to_datetime(frame.date).unique())
    rows = []
    for d in range(14, len(dates)):
        record = json.loads((shadows/f"dhr/{dates[d].date()}.json").read_text(encoding="utf-8"))
        if record["status"] != "ok":
            continue
        values = actual[max(d-PROTOCOL["dhr_history_days"], 0):d].ravel()
        n = len(values)
        design = _harmonic_design(np.arange(n), record["selected"]["harmonics"], (n-1)/2, n)
        residual = values-design@np.linalg.lstsq(design, values, rcond=None)[0]
        rows.append({"origin": str(dates[d].date()), "history_days": n//144,
                     "first_half_mean_kw": float(residual[:n//2].mean()),
                     "second_half_mean_kw": float(residual[n//2:].mean()),
                     "first_half_std_kw": float(residual[:n//2].std(ddof=1)),
                     "second_half_std_kw": float(residual[n//2:].std(ddof=1)),
                     **{f"innovation_ljung_box_p_lag_{r['lag']}": r["lb_pvalue"] for r in record["ljung_box"]},
                     "use": "posthoc_diagnostic_only_does_not_change_orders_or_forecasts"})
    write_csv(output/"dhr_residual_stability.csv", pd.DataFrame(rows))
