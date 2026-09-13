"""7.3：共享参数 Elastic Net 周季节残差的严格滚动预测。"""
from dataclasses import dataclass
import numpy as np
from sklearn.linear_model import ElasticNet
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler


HYPERPARAMETERS = tuple(
    (alpha, ratio)
    for alpha in (1e-4, 1e-3, 1e-2)
    for ratio in (0.1, 0.5, 0.9)
)


def feature_matrix(history: np.ndarray, day: int) -> np.ndarray:
    """所有列在目标日0:00前已知；允许用已递推预测日构造第二天特征。"""
    if day < 14:
        raise ValueError("Elastic Net 特征至少需要14日历史")
    p1, p7, p8, p14 = history[day - 1], history[day - 7], history[day - 8], history[day - 14]
    slots = np.arange(144, dtype=float)
    weekday = day % 7
    columns = (
        p1,
        p7,
        p14,
        p7 - p14,
        p1 - p8,
        np.roll(p7, 1) - p7,
        np.roll(p7, -1) - p7,
        np.full(144, p1.mean()),
        np.full(144, p7.mean()),
        np.full(144, p1.std()),
        np.full(144, p7.std()),
        np.sin(2 * np.pi * slots / 144),
        np.cos(2 * np.pi * slots / 144),
        np.sin(4 * np.pi * slots / 144),
        np.cos(4 * np.pi * slots / 144),
        np.full(144, np.sin(2 * np.pi * weekday / 7)),
        np.full(144, np.cos(2 * np.pi * weekday / 7)),
    )
    result = np.column_stack(columns)
    if not np.isfinite(result).all():
        raise ValueError("价格特征含非有限值")
    return result


def training_rows(prices: np.ndarray, start: int, end: int) -> tuple[np.ndarray, np.ndarray]:
    days = range(max(14, start), min(end, len(prices)))
    matrices = [feature_matrix(prices, day) for day in days]
    if not matrices:
        return np.empty((0, 17)), np.empty(0)
    return np.vstack(matrices), np.concatenate([prices[day] - prices[day - 7] for day in days])


def fit(prices: np.ndarray, end: int, alpha: float, ratio: float):
    x, y = training_rows(prices, 14, end)
    if len(y) == 0:
        return None
    model = make_pipeline(
        StandardScaler(),
        ElasticNet(alpha=alpha, l1_ratio=ratio, max_iter=20000, tol=1e-6, selection="cyclic"),
    )
    model.fit(x, y)
    return model


def tune_january(prices: np.ndarray) -> tuple[tuple[float, float], list[dict]]:
    """1月内时间有序训练(14—23日)/验证(24—30日)，并列取更简单的较大alpha。"""
    x_train, y_train = training_rows(prices, 14, 24)
    x_valid, y_valid = training_rows(prices, 24, 31)
    records = []
    for alpha, ratio in HYPERPARAMETERS:
        model = make_pipeline(
            StandardScaler(),
            ElasticNet(alpha=alpha, l1_ratio=ratio, max_iter=20000, tol=1e-6, selection="cyclic"),
        )
        model.fit(x_train, y_train)
        error = model.predict(x_valid) - y_valid
        records.append({"alpha": alpha, "l1_ratio": ratio, "mae": float(np.mean(abs(error))),
                        "rmse": float(np.sqrt(np.mean(error ** 2)))})
    best = min(records, key=lambda row: (row["rmse"], row["mae"], -row["alpha"], row["l1_ratio"]))
    return (float(best["alpha"]), float(best["l1_ratio"])), records


@dataclass
class Forecasts:
    values: np.ndarray  # origin day × next 288 slots
    residuals: np.ndarray  # realized daily price - OOS first-day forecast
    audit: dict


def rolling_forecasts(prices: np.ndarray) -> Forecasts:
    prices = np.asarray(prices, dtype=float)
    if prices.shape != (365, 144) or not np.isfinite(prices).all() or (prices <= 0).any():
        raise ValueError("附件4价格必须为365×144个正有限值")
    (alpha, ratio), tuning = tune_january(prices)
    values = np.full((365, 288), np.nan)
    residuals = np.full_like(prices, np.nan)
    for origin in range(7, 365):
        # 1月仅用于预热和超参数时序验证；不得用月底验证结果反向污染1月SOC轨迹。
        model = fit(prices, origin, alpha, ratio) if origin >= 31 else None
        extended = np.full((367, 144), np.nan)
        extended[:origin] = prices[:origin]
        for step in range(2):
            target = origin + step
            if target < 14 or model is None:
                prediction = extended[target - 7].copy()
            else:
                prediction = extended[target - 7] + model.predict(feature_matrix(extended, target))
            extended[target] = np.maximum(prediction, 0.0)
            values[origin, step * 144:(step + 1) * 144] = extended[target]
        residuals[origin] = prices[origin] - values[origin, :144]
    formal = np.arange(31, 365)
    error = residuals[formal]
    seasonal = prices[formal - 7] - prices[formal]
    audit = {
        "information_boundary": "daily origin uses only days strictly before origin; day+1 is recursive",
        "feature_count": 17,
        "selected_alpha": alpha,
        "selected_l1_ratio": ratio,
        "tuning": tuning,
        "elastic_net_mae": float(np.mean(abs(error))),
        "elastic_net_rmse": float(np.sqrt(np.mean(error ** 2))),
        "seasonal_mae": float(np.mean(abs(seasonal))),
        "seasonal_rmse": float(np.sqrt(np.mean(seasonal ** 2))),
    }
    return Forecasts(values, residuals, audit)


def rolling_lightgbm_comparison(prices: np.ndarray) -> dict:
    """7.3.4同一rolling-origin边界下的严格因果LightGBM比较器；不进入正式调度。"""
    from lightgbm import LGBMRegressor
    predictions = np.full_like(prices, np.nan)
    for origin in range(31, 365):
        x, y = training_rows(prices, 14, origin)
        model = LGBMRegressor(n_estimators=120, learning_rate=0.05, num_leaves=15,
                              min_child_samples=40, subsample=1.0, colsample_bytree=1.0,
                              reg_lambda=1e-3, random_state=20250913, n_jobs=1, verbosity=-1)
        model.fit(x, y)
        predictions[origin] = np.maximum(prices[origin - 7] + model.predict(feature_matrix(prices, origin)), 0)
    error = predictions[31:] - prices[31:]
    return {"mae": float(np.mean(abs(error))), "rmse": float(np.sqrt(np.mean(error ** 2))),
            "information_boundary": "same features; train target days strictly before each origin",
            "used_for_dispatch": False}
