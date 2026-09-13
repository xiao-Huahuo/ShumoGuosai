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


def write_window_policy(output: Path) -> dict:
    """56日为正式计算前预设，无窗口比较实验。"""
    result = {"selected_window": 56, "selection": "preset_before_formal_run", "calibration_performed": False}
    write_json(output / "window_policy.json", result)
    return result


def baseline_metrics(data: Inputs) -> dict:
    """冻结Q2实际策略按附件4逐时重新结算，不重选、不优化。"""
    import hashlib
    source = Path(data.provenance['q2_run']) / 'processed/main/dispatch.csv'
    frame = pd.read_csv(source, float_precision='round_trip')
    prices = data.actual_prices[31:].ravel()
    expected = pd.date_range('2025-02-01 00:10', periods=334 * 144, freq='10min')
    if len(frame) != len(prices) or not np.array_equal(pd.to_datetime(frame.timestamp), expected):
        raise ValueError('Q2冻结基准时序不完整')
    return dict(source=str(source), sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                C_realized=float(np.sum(prices * (frame.grid + 5 * frame.emergency))),
                E_emergency=float(frame.emergency.sum()), grid=float(frame.grid.sum()),
                initial_soc=float(frame.initial_soc.iloc[0]), method='frozen_Q2_policy_repriced_attachment4')


def sanity_metrics(frame: pd.DataFrame, baseline_cost: float) -> dict:
    from .config import E_MIN, E_MAX, TOL
    cost = float(frame.total_cost.sum())
    upper = float(np.mean(frame.soc >= E_MAX - TOL))
    return dict(C_realized=cost, baseline_cost=baseline_cost, cost_ratio=cost / baseline_cost,
                economic_pass=cost <= 1.15 * baseline_cost, soc_upper_fraction=upper,
                soc_lower_fraction=float(np.mean(frame.soc <= E_MIN + TOL)),
                storage_pass=upper < 0.99, soc_min=float(frame.soc.min()), soc_max=float(frame.soc.max()),
                soc_final=float(frame.soc.iloc[-1]), E_emergency=float(frame.emergency.sum()),
                grid=float(frame.grid.sum()), called=float(frame.called.sum()), unused=float(frame.unused.sum()),
                unused_ratio=float(frame.unused.sum() / max(1.0, frame.grid.sum())),
                charge=float(frame.charge.sum()), discharge=float(frame.discharge.sum()),
                storage_throughput=float(frame.charge.sum() + frame.discharge.sum()),
                spill=float(frame.spill.sum()))


def production_gates(data: Inputs, frame: pd.DataFrame, mode: str, config: Config, output: Path) -> dict:
    import hashlib
    import json
    from .rolling import validate_frame
    validate_frame(frame, mode, config, full=True)
    if config.allow_limited or abs(float(frame.initial_soc.iloc[0]) - 6000) > 1e-6:
        raise ValueError('正式解设置或初始SOC不符')
    state = json.loads((output / 'state.json').read_text(encoding='utf-8'))
    audits = []
    if [item['day'] for item in state['days']] != list(range(31, 365)):
        raise ValueError('正式334日receipt不完整')
    for receipt in state['days']:
        date = str((pd.Timestamp('2025-01-01') + pd.Timedelta(days=receipt['day'])).date())
        for key, path in [('dispatch', output / 'days' / f'{date}.csv'), ('audit', output / 'audit' / f'{date}.json')]:
            if hashlib.sha256(path.read_bytes()).hexdigest() != receipt['hashes'][key]:
                raise ValueError('日文件SHA不匹配')
        day_audit = json.loads((output / 'audit' / f'{date}.json').read_text(encoding='utf-8'))
        audits.extend([day_audit['solver']] if mode == '4-2' else [n['solver'] for n in day_audit['nodes']])
    expected = 334 if mode == '4-2' else 1336
    certified = sum(a['status'] == 'Optimal' and a['reliable'] and a['solution_source'] == 'optimal_solver'
                    and a['integer_variables'] == 0 for a in audits)
    baseline = baseline_metrics(data)
    metrics = sanity_metrics(frame, baseline['C_realized'])
    result = dict(mode=mode, baseline=baseline, metrics=metrics, solver_nodes=len(audits),
                  certified_nodes=certified, limited_nodes=sum(a['status'] != 'Optimal' for a in audits),
                  fallback_nodes=sum(a['solution_source'] != 'optimal_solver' for a in audits),
                  max_balance_error=float(abs(frame.called + frame.discharge + frame.emergency - frame.net_kwh - frame.charge - frame.spill).max()),
                  max_solver_seconds=max(a['wall_seconds'] for a in audits),
                  mean_solver_seconds=float(np.mean([a['wall_seconds'] for a in audits])),
                  variables_range=[min(a['variables'] for a in audits), max(a['variables'] for a in audits)],
                  constraints_range=[min(a['constraints'] for a in audits), max(a['constraints'] for a in audits)],
                  dispatch_sha256=hashlib.sha256((output / 'dispatch.csv').read_bytes()).hexdigest())
    result['passed'] = bool(certified == expected == len(audits) and metrics['economic_pass'] and metrics['storage_pass'])
    write_json(output / 'production_gates.json', result)
    if not result['passed']:
        write_json(output / 'active.json', {'status': 'publication_blocked', 'gates': result})
        raise ValueError('正式发布门禁失败，详见production_gates.json')
    return result
