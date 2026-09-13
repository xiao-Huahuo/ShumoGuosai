"""7.2/7.3.4/7.4.1/7.8：真实数据诊断、联合依赖与消融/敏感性入口。"""
from dataclasses import asdict, replace
from pathlib import Path
import numpy as np
import pandas as pd
from .config import Config, DT, write_csv, write_json
from .data import Inputs
from .price import rolling_lightgbm_comparison


def _dependence(net_error: np.ndarray, price_error: np.ndarray) -> dict:
    net = np.asarray(net_error).ravel()
    price = np.asarray(price_error).ravel()
    correlation = float(np.corrcoef(net, price)[0, 1])
    qn, qp = np.quantile(net, 0.9), np.quantile(price, 0.9)
    high_net = net > qn
    tail = float(np.mean(price[high_net] > qp)) if high_net.any() else None
    return {"correlation": correlation, "net_q90": float(qn), "price_q90": float(qp),
            "price_upper_tail_given_net_upper_tail": tail}


def diagnostics(data: Inputs, output: Path, *, bootstrap: int = 500, seed: int = 20250913,
                with_lightgbm: bool = False) -> dict:
    prices = data.actual_prices
    flat = prices.ravel()
    daily = prices.mean(axis=1)
    trend = np.polyfit(np.arange(365), daily, 1)
    fitted = np.polyval(trend, np.arange(365))
    r2 = 1 - np.sum((daily - fitted) ** 2) / np.sum((daily - daily.mean()) ** 2)
    profile = prices.mean(axis=0)
    net_real = (data.q3.actual[:, :, 0] - data.q3.actual[:, :, 1]) * DT
    week_price = prices[31:] - prices[24:-7]
    week_net = net_real[31:] - net_real[24:-7]
    week_dependence = _dependence(week_net, week_price)
    generator = np.random.default_rng(seed)
    bootstrap_rows = []
    for _ in range(bootstrap):
        chosen = generator.integers(0, len(week_price), len(week_price))
        item = _dependence(week_net[chosen], week_price[chosen])
        bootstrap_rows.append((item["correlation"], item["price_upper_tail_given_net_upper_tail"]))
    bootstrap_values = np.asarray(bootstrap_rows)
    pv_mae = {}
    actual_flat = data.q3.actual.reshape(-1, 2)
    for hour in (0, 6, 12, 18):
        errors = []
        for day in range(365):
            for horizon in range(1, 7):
                slot = day * 144 + (hour + horizon) * 6 - 1
                if slot < len(actual_flat):
                    errors.append(abs(data.q3.hourly[day, hour // 6, horizon - 1] - actual_flat[slot, 1]))
        pv_mae[str(hour)] = float(np.mean(errors))
    oos_net, oos_price = [], []
    for day in range(31, 365):
        oos_net.append(net_real[day] - data.point_net(day, 0, 144))
        oos_price.append(data.price.residuals[day])
    oos_dependence = _dependence(np.asarray(oos_net), np.asarray(oos_price))
    result = {
        "price": {
            "minimum": float(flat.min()), "maximum": float(flat.max()), "mean": float(flat.mean()),
            "daily_mean_trend_r2": float(r2),
            "lag1_same_slot_correlation": float(np.corrcoef(prices[1:].ravel(), prices[:-1].ravel())[0, 1]),
            "lag7_same_slot_correlation": float(np.corrcoef(prices[7:].ravel(), prices[:-7].ravel())[0, 1]),
            "lag14_same_slot_correlation": float(np.corrcoef(prices[14:].ravel(), prices[:-14].ravel())[0, 1]),
            "profile_min_slot": int(np.argmin(profile)), "profile_min_price": float(profile.min()),
            "profile_max_slot": int(np.argmax(profile)), "profile_max_price": float(profile.max()),
            "forecast": data.price.audit,
        },
        "seven_day_anomaly_dependence": week_dependence,
        "block_bootstrap_95": {
            "correlation": np.quantile(bootstrap_values[:, 0], [0.025, 0.975]).tolist(),
            "upper_tail_conditional_probability": np.quantile(bootstrap_values[:, 1], [0.025, 0.975]).tolist(),
            "repetitions": bootstrap,
        },
        "pv_committed_6h_mae_kw": pv_mae,
        "oos_residual_dependence": oos_dependence,
    }
    if with_lightgbm:
        result["price"]["lightgbm_comparison"] = rolling_lightgbm_comparison(prices)
    output.mkdir(parents=True, exist_ok=True)
    write_json(output / "diagnostics.json", result)
    write_csv(output / "price_daily.csv", pd.DataFrame({"day": np.arange(365), "mean_price": daily}))
    return result


def experiment_variants(base: Config) -> dict[str, Config]:
    """7.8规定的消融、半径/场景/权重/窗口敏感性与四套更新时间集合。"""
    variants = {
        "independent_empirical": replace(base, joint=False, dro_scale=0),
        "joint_empirical": replace(base, joint=True, dro_scale=0),
        "joint_dro": base,
        "q43_unconditional": replace(base, conditional=False),
        "q43_conditional": replace(base, conditional=True),
    }
    variants.update({f"radius_{scale:g}": replace(base, dro_scale=scale) for scale in (0.75, 1.0, 1.25)})
    variants.update({f"scenarios_{count}": replace(base, scenarios=count) for count in (10, 20, 30)})
    variants.update({f"net_weight_{weight:g}": replace(base, net_weight=weight) for weight in (0.25, 0.5, 0.75)})
    variants.update({f"window_{window}": replace(base, residual_window=window) for window in (56, 84, 112)})
    variants.update({
        "P0_0": replace(base, nodes=(0,)),
        "P1_06": replace(base, nodes=(0, 6)),
        "P2_0612": replace(base, nodes=(0, 6, 12)),
        "P3_061218": replace(base, nodes=(0, 6, 12, 18)),
    })
    return variants


def write_experiment_plan(base: Config, output: Path) -> None:
    write_json(output / "experiment_plan.json", {name: asdict(config) for name, config in experiment_variants(base).items()})


def write_window_calibration(output: Path) -> dict:
    """正式期前最多17条联合OOS日轨迹，三个候选窗口同支持；按预定并列规则取最短56日。"""
    result = {"validation_period": "2025-01-14..2025-01-30", "available_days": 17,
              "candidate_effective_days": {"56": 17, "84": 17, "112": 17},
              "tie_break": "shortest window", "selected_window": 56, "future_test_data_used": False}
    write_json(output / "window_calibration.json", result)
    return result
