"""最终方案2.4：有限候选、仅历史拟合、forecast-origin内递推。"""

import itertools
import warnings

import numpy as np
import pandas as pd
from lightgbm import LGBMRegressor
from statsmodels.tsa.statespace.sarimax import SARIMAX
from statsmodels.tsa.stattools import acf, pacf
from statsmodels.stats.diagnostic import acorr_ljungbox

from protocol import PROTOCOL
from policy import DT


def seasonal(history, horizon):
    """history仅含源日期早于origin的完整日；未来PV均值递推使用自身预测。"""
    history = np.asarray(history, dtype=float)
    if history.ndim != 3 or history.shape[1:] != (144, 2) or len(history) < 7:
        raise ValueError("季节基线需要至少7个完整历史日")
    if not np.isfinite(history).all() or (history < 0).any():
        raise ValueError("负荷/光伏历史无效")
    buffer = list(history.copy())
    output = []
    for _ in range(horizon):
        day = np.column_stack((buffer[-7][:, 0], np.mean([v[:, 1] for v in buffer[-7:]], axis=0)))
        buffer.append(day); output.append(day)
    return np.asarray(output)


def load_features(past_load, target_date):
    if len(past_load) < 7:
        raise ValueError("负荷特征缺少7日历史")
    recent = np.asarray(past_load[-7:])
    weekday = pd.Timestamp(target_date).dayofweek
    return np.column_stack((np.arange(1, 145), np.full(144, weekday), np.full(144, weekday < 5),
                            past_load[-1], past_load[-2], past_load[-7], recent.mean(0), recent.std(0, ddof=1)))


def lightgbm_forecast(history, origin, horizon, configuration):
    """固定八个主特征；训练样本及未来递推均不能访问当日/未来真实量。"""
    past = np.asarray(history)[:, :, 0]
    first_date = pd.Timestamp(origin) - pd.Timedelta(days=len(past))
    if len(past) < 8:
        raise ValueError("LightGBM没有带完整滞后的训练日")
    x = np.concatenate([load_features(past[:d], first_date+pd.Timedelta(days=d)) for d in range(7, len(past))])
    y = past[7:].ravel()
    model = LGBMRegressor(**configuration, objective="regression", n_jobs=1, random_state=0,
                         deterministic=True, force_col_wise=True, verbosity=-1)
    model.fit(x, y, categorical_feature=[1, 2])
    buffer, output = list(past.copy()), []
    for h in range(horizon):
        features = load_features(buffer, pd.Timestamp(origin)+pd.Timedelta(days=h))
        prediction = np.maximum(model.predict(features, validate_features=False), 0)
        output.append(prediction); buffer.append(prediction)
    return np.asarray(output)


def _harmonic_design(indices, harmonics, center, scale):
    indices = np.asarray(indices)
    trend = (indices-center)/scale
    columns = [np.ones(len(indices)), trend]
    for k in range(1, harmonics+1):
        for wave in (np.sin(2*np.pi*k*indices/144), np.cos(2*np.pi*k*indices/144)):
            columns.extend((wave, trend*wave))
    return np.column_stack(columns)


def harmonic_forecast(history, horizon):
    """局部日内谐波及缓慢线性振幅漂移；无年度傅里叶/未来额定功率上界。"""
    values = np.asarray(history)[-PROTOCOL["dhr_history_days"]:, :, 1].ravel()
    n = len(values)
    indices = np.arange(n)
    future = np.arange(n, n+144*horizon)
    candidates, best = [], None
    for harmonic in PROTOCOL["dhr_harmonics"]:
        design = _harmonic_design(indices, harmonic, (n-1)/2, n)
        beta = np.linalg.lstsq(design, values, rcond=None)[0]
        residual = values-design@beta
        for p, q in itertools.product(PROTOCOL["dhr_ar_orders"], PROTOCOL["dhr_ma_orders"]):
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                fit = SARIMAX(residual, order=(p, 0, q), trend="n",
                              enforce_stationarity=True, enforce_invertibility=True).fit(
                                  disp=False, maxiter=PROTOCOL["dhr_max_iterations"])
            converged = bool(fit.mle_retvals.get("converged", False))
            bic = float(fit.bic + design.shape[1]*np.log(n))
            aic = float(fit.aic + 2*design.shape[1])
            record = {"harmonics": harmonic, "p": p, "q": q, "bic": bic, "aic": aic,
                      "converged": converged, "warnings": "; ".join(str(w.message) for w in caught)}
            candidates.append(record)
            key = (bic, aic, harmonic+p+q)
            if converged and np.isfinite([bic, aic]).all() and (best is None or key < best[0]):
                mean = _harmonic_design(future, harmonic, (n-1)/2, n)@beta
                forecast = np.maximum(mean+np.asarray(fit.forecast(len(future))), 0).reshape(horizon, 144)
                best = (key, forecast, record, residual, np.asarray(fit.resid))
    if best is None:
        return None, {"status": "all_order_fits_failed", "candidates": candidates}, None
    _, forecast, chosen, residual, innovations = best
    max_lag = min(144, n//2-1)
    residual_acf, residual_pacf = acf(residual, nlags=max_lag, fft=True), pacf(residual, nlags=max_lag, method="burg")
    white = acorr_ljungbox(innovations, lags=[6, 144], model_df=chosen["p"]+chosen["q"], return_df=True)
    diagnostics = {"status": "ok", "selected": chosen, "candidates": candidates,
                   "residual_mean_kw": float(residual.mean()), "residual_std_kw": float(residual.std()),
                   "first_half_residual_std_kw": float(residual[:n//2].std()),
                   "second_half_residual_std_kw": float(residual[n//2:].std()),
                   "ljung_box": white.reset_index(names="lag").to_dict("records"),
                   "annual_harmonics": False, "adf": "not_invoked_fixed_stationary_error_candidate"}
    correlations = pd.DataFrame({"lag": np.arange(max_lag+1), "acf": residual_acf, "pacf": residual_pacf})
    return forecast, diagnostics, correlations


def economic_metrics(actual, prediction, prices):
    """统计及决策代理损失；不使用调度费用选模。actual/prediction最后轴为L、PV。"""
    error = np.asarray(prediction)-np.asarray(actual)
    net_error = error[..., 0]-error[..., 1]
    actual_d = np.maximum((actual[..., 0]-actual[..., 1])*DT, 0)
    predicted_d = np.maximum((prediction[..., 0]-prediction[..., 1])*DT, 0)
    delta = predicted_d-actual_d
    return {"econ": float(np.mean(prices*(np.maximum(delta, 0)+4*np.maximum(-delta, 0)))),
            "net_mae": float(np.abs(net_error).mean()), "net_rmse": float(np.sqrt(np.mean(net_error**2))),
            "load_mae": float(np.abs(error[..., 0]).mean()), "load_rmse": float(np.sqrt(np.mean(error[..., 0]**2))),
            "pv_mae": float(np.abs(error[..., 1]).mean()), "pv_rmse": float(np.sqrt(np.mean(error[..., 1]**2)))}


def select_pipeline(scores, tolerance=None):
    """预注册逐级容差筛选；基线排在首位，近似平局保留简单流程。"""
    tolerance = PROTOCOL["selection_relative_tolerance"] if tolerance is None else tolerance
    remaining = list(scores)
    for metric in ("econ", "net_mae", "net_rmse", "load_mae", "load_rmse", "pv_mae", "pv_rmse"):
        best = min(scores[key][metric] for key in remaining)
        remaining = [key for key in remaining if scores[key][metric] <= best + tolerance*max(abs(best), 1e-8)]
        if len(remaining) == 1:
            break
    return remaining[0]
