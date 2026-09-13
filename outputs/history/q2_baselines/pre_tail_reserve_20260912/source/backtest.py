"""2.1.12–2.1.13：严格日前信息接口和真实评价；不替方案指定预测/调度器。"""

import numpy as np
import pandas as pd

from data import (CALENDAR, DT_HOURS, END, FORECAST_START, SERIES, SLOTS,
                  calendar_for_day, history_before)


def rolling_folds(frame, start=FORECAST_START, end=END):
    rows = []
    for origin in pd.date_range(start, end, freq="D"):
        history = history_before(frame, origin)
        actual = frame.loc[frame.date == origin]
        if history.empty or len(actual) != SLOTS or not actual.timestamp.equals(
                pd.Series(calendar_for_day(origin).timestamp.to_numpy(), index=actual.index)):
            raise ValueError(f"{origin.date()} 历史为空或目标日不完整/顺序不正确")
        rows.append({"origin": origin, "history_start": history.timestamp.iloc[0],
                     "history_end_exclusive": origin, "history_last_timestamp": history.timestamp.iloc[-1],
                     "history_points": len(history), "horizon_points": SLOTS,
                     "target_first": actual.timestamp.iloc[0], "target_last": actual.timestamp.iloc[-1],
                     "rule": "timestamp < origin", "window": "expanding", "unit": "kW"})
    return pd.DataFrame(rows)


def rolling_predict(frame, model_factory, start=FORECAST_START, end=END):
    """factory(series) 每日返回全新预测器；只获该变量历史和未来日历，不获真值。

    预测器为 callable(history[timestamp,value_kw], calendar) -> 长度144的功率数组。
    参数估计、缩放、调参和特征选择必须完全在传入历史内部进行。
    """
    rows = []
    folds = rolling_folds(frame, start, end)
    for fold in folds.itertuples(index=False):
        history = history_before(frame, fold.origin)
        prediction = calendar_for_day(fold.origin)
        prediction["origin"] = fold.origin
        for variable in ("load_kw", "pv_kw"):
            model = model_factory(variable)
            past = history[["timestamp", variable]].rename(columns={variable: "value_kw"}).copy(deep=True)
            values = np.asarray(model(past, prediction[list(CALENDAR)].copy(deep=True)), dtype=float)
            if values.shape != (SLOTS,) or not np.isfinite(values).all() or (values < 0).any():
                raise ValueError(f"{variable} 预测必须为 144 个有限非负 kW 值；不自动裁剪")
            prediction[f"predicted_{variable}"] = values
        prediction["predicted_net_load_kw"] = prediction.predicted_load_kw - prediction.predicted_pv_kw
        # 只有全部预测完成后才提取真值，不能给模型调用传递 actual。
        actual = frame.loc[frame.date == fold.origin, list(SERIES)]
        for variable in SERIES:
            prediction[f"actual_{variable}"] = actual[variable].to_numpy()
        rows.append(prediction)
    return pd.concat(rows, ignore_index=True)


def forecast_metrics(predictions):
    """三类功率 MAE/RMSE；按所有时段等权计算，不能平均每日 RMSE。"""
    if predictions.empty or predictions.timestamp.duplicated().any():
        raise ValueError("预测结果为空或时间重复")
    if predictions.date.isna().any() or predictions.timestamp.isna().any():
        raise ValueError("预测日期或时间戳不能缺失")
    for date, part in predictions.groupby("date"):
        expected_time = calendar_for_day(date).timestamp.to_numpy()
        if len(part) != SLOTS or not np.array_equal(pd.to_datetime(part.timestamp).to_numpy(), expected_time):
            raise ValueError("预测评价必须逐日按序包含完整144个目标时间戳")
    expected = list(SERIES)
    for prefix in ("predicted", "actual"):
        values = predictions[[f"{prefix}_{v}" for v in expected]].to_numpy(dtype=float)
        if not np.isfinite(values).all() or (values[:, :2] < 0).any():
            raise ValueError("预测/真实功率必须有限，负荷与光伏不能为负")
        if not np.allclose(values[:, 0] - values[:, 1], values[:, 2], rtol=1e-12, atol=1e-10):
            raise ValueError("净负荷必须由负荷减光伏得到")
    rows = []
    for label, group in [("all", predictions), *list(predictions.groupby("date"))]:
        for variable in SERIES:
            error = group[f"predicted_{variable}"] - group[f"actual_{variable}"]
            rows.append({"period": str(label), "series": variable, "n": len(error),
                         "mae_kw": float(error.abs().mean()), "rmse_kw": float(np.sqrt(np.mean(error**2)))})
    return pd.DataFrame(rows)


def dispatch_metrics(dispatch):
    """输入事后调度明细；只计费，不由净负荷误差猜测紧急电量。

    planned_grid_kwh 为 0:00 已制定计划；actual_supply_before_emergency_kw 是已执行供给
    （计及实际光伏、储能与弃电后的母线供给）。储能可行性须由后续调度模型验证。
    """
    required = ("timestamp", "date", "planned_grid_kwh", "price_yuan_per_kwh", "actual_load_kw",
                "actual_supply_before_emergency_kw")
    if dispatch.empty or any(c not in dispatch for c in required):
        raise ValueError("缺少事后调度明细字段")
    dispatch = dispatch.copy().sort_values("timestamp")
    time = pd.to_datetime(dispatch.timestamp)
    dates = pd.to_datetime(dispatch.date)
    if time.isna().any() or dates.isna().any() or time.duplicated().any() or not time.diff().dropna().eq(pd.Timedelta(minutes=10)).all():
        raise ValueError("调度时间必须唯一、连续且间隔 10 min")
    if not dates.eq((time - pd.Timedelta(minutes=10)).dt.normalize()).all():
        raise ValueError("调度日期必须为区间所属日")
    if not dispatch.groupby("date").size().eq(SLOTS).all():
        raise ValueError("调度评价必须覆盖完整的每日144时段")
    values = dispatch[list(required[2:])].to_numpy(dtype=float)
    if not np.isfinite(values).all() or (values[:, :3] < 0).any():
        raise ValueError("调度字段必须有限，计划电量、电价与负荷必须非负；实际净供给可为负")
    emergency = np.maximum(values[:, 2] - values[:, 3], 0) * DT_HOURS
    planned_cost = values[:, 0] * values[:, 1]
    emergency_cost = emergency * values[:, 1] * 5  # C题明确为交易时刻电价的5倍。
    active = emergency > 0
    event_start = active & ~np.r_[False, active[:-1]]
    return {"start": str(time.iloc[0]), "end": str(time.iloc[-1]), "days": int(dates.nunique()),
            "emergency_kwh": float(emergency.sum()), "emergency_intervals": int(active.sum()),
            "emergency_interval_rate": float(active.mean()), "emergency_events": int(event_start.sum()),
            "days_with_emergency": int(dates[active].nunique()), "planned_cost_yuan": float(planned_cost.sum()),
            "emergency_cost_yuan": float(emergency_cost.sum()), "total_cost_yuan": float((planned_cost + emergency_cost).sum()),
            "cost_period_label": "full_calendar_year" if time.iloc[0] == pd.Timestamp("2025-01-01 00:10") and
            time.iloc[-1] == pd.Timestamp("2026-01-01") else "evaluated_period_only"}
