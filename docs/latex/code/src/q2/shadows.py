"""预测流程条件化的影子库；持久保存origin×horizon×slot预测，不重算历史预测。"""

import itertools
from pathlib import Path

import numpy as np
import pandas as pd

from data import write_csv, write_json
from forecast import (economic_metrics, harmonic_forecast, lightgbm_forecast, seasonal,
                      select_pipeline)
from protocol import PROTOCOL
from scenarios import history_window, joint_blocks

MODEL_IDS = ("load_week", "load_lgb_0", "load_lgb_1", "pv_mean7", "pv_dhr")


def fit_day(history, origin, active_load_ids):
    baseline = seasonal(history, 3)
    output = {"load_week": baseline[..., 0], "pv_mean7": baseline[..., 1]}
    for index in active_load_ids:
        output[f"load_lgb_{index}"] = lightgbm_forecast(history, origin, 3, PROTOCOL["lightgbm_candidates"][index])
    pv, diagnostics, correlation = harmonic_forecast(history, 3)
    if pv is not None:
        output["pv_dhr"] = pv
    return output, diagnostics, correlation


def freeze_lightgbm(store, actual):
    """只使用1月影子h=0真值；保留每个配置自身的历史影子预测以保证流程一致。"""
    rows = []
    for index in range(len(PROTOCOL["lightgbm_candidates"])):
        prediction = store[f"load_lgb_{index}"][14:31, 0]
        valid = np.isfinite(prediction).all(axis=1)
        if not valid.all():
            raise ValueError("1月LightGBM候选影子不完整，不能冻结或用2月真值选参")
        error = prediction-actual[14:31, :, 0]
        rows.append({"configuration": index, "mae_kw": float(np.abs(error).mean()),
                     "rmse_kw": float(np.sqrt(np.mean(error**2))), "origins": 17,
                     "first_origin": "2025-01-15", "last_origin": "2025-01-31"})
    chosen = min(rows, key=lambda r: (r["mae_kw"], r["rmse_kw"], r["configuration"]))["configuration"]
    return chosen, rows


def build_shadow_library(actual, dates, output, *, boundary):
    """调用预测器时仅传入actual[:d]副本；存储三维原始float64 DAT及显式形状。"""
    if boundary != "source_date_before_origin":
        raise ValueError("完整日边界尚未确认；不能擅自对缺失末段作填补")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    shape = (len(dates), 3, 144)
    store = {}
    for name in MODEL_IDS:
        store[name] = np.memmap(output/f"{name}.dat", mode="w+", dtype="<f8", shape=shape)
        store[name][:] = np.nan
    write_json(output/"shape.json", {"shape": shape, "dtype": "<f8", "axes": ["origin", "horizon", "slot"],
                                    "first_origin_date": str(dates[0]), "model_ids": MODEL_IDS,
                                    "boundary": boundary, "missing": "NaN=no_forecast_not_zero"})
    chosen = None
    for d in range(14, len(dates)):
        if d == 31:
            chosen, scores = freeze_lightgbm(store, actual[:31])
            write_json(output/"frozen_lightgbm.json", {"index": chosen, "configuration": PROTOCOL["lightgbm_candidates"][chosen],
                                                       "freeze_origin": "2025-02-01", "scores": scores})
        active = list(range(len(PROTOCOL["lightgbm_candidates"]))) if d < 31 else [chosen]
        predictions, diagnostic, correlations = fit_day(actual[:d].copy(), dates[d], active)
        for name, prediction in predictions.items():
            store[name][d] = prediction
            store[name].flush()
        write_json(output/f"dhr/{pd.Timestamp(dates[d]).date()}.json", diagnostic)
        if correlations is not None:
            write_csv(output/f"dhr/{pd.Timestamp(dates[d]).date()}_correlations.csv", correlations)
        write_json(output/"progress.json", {"last_origin": str(dates[d]), "days_done": d-13,
                                           "complete": d == len(dates)-1})
        print(f"影子预测 {pd.Timestamp(dates[d]).date()}，仅使用此前{d}个完整日", flush=True)
    return store, chosen


def open_library(output):
    import json
    output = Path(output)
    meta = json.loads((output/"shape.json").read_text(encoding="utf-8"))
    progress = json.loads((output/"progress.json").read_text(encoding="utf-8"))
    if not progress["complete"]:
        raise ValueError("影子库未完整计算")
    store = {name: np.memmap(output/f"{name}.dat", mode="r", dtype=meta["dtype"], shape=tuple(meta["shape"])) for name in MODEL_IDS}
    frozen = json.loads((output/"frozen_lightgbm.json").read_text(encoding="utf-8"))
    return store, frozen["index"]


def combined(store, pair):
    return np.stack([store[pair[0]], store[pair[1]]], axis=-1)


def choose_day(store, frozen, history, current, horizon, prices, *, minimum=14, window="auto", fixed_pair=None):
    """所有联合候选在共同已实现origin上比较代理损失，禁止使用反事实调度费用。"""
    candidates = list(itertools.product(("load_week", f"load_lgb_{frozen}"), ("pv_mean7", "pv_dhr")))
    if fixed_pair is not None:
        candidates = [tuple(fixed_pair)]
    usable = {}
    for pair in candidates:
        forecasts = combined(store, pair)
        if not np.isfinite(forecasts[current, :horizon]).all():
            continue
        try:
            origins, chosen_window = history_window(forecasts, current, horizon, minimum, window)
        except ValueError:
            continue
        usable[pair] = (forecasts, origins, chosen_window)
    if not usable:
        raise ValueError("没有满足最低完整历史块门槛的预测流程；需要基线回退期")
    common = sorted(set.intersection(*(set(v[1]) for v in usable.values())))
    if not common:
        raise ValueError("在线联合候选没有共同已实现样本外评价区间")
    scores = {pair: economic_metrics(history[common], values[0][common, 0], prices) for pair, values in usable.items()}
    pair = select_pipeline(scores)
    forecasts, origins, chosen_window = usable[pair]
    blocks = joint_blocks(history, forecasts, origins, horizon)
    metadata = {"pipeline": list(pair), "origin_indices": origins.tolist(), "window_days": chosen_window,
                "common_scored_origins": common, "scores": {"|".join(k): v for k, v in scores.items()},
                "selection_uses_dispatch_cost": False, "minimum_blocks": minimum}
    return forecasts[current, :horizon].copy(), blocks, metadata
