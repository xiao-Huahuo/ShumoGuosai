"""3.22—3.25：预测诊断、paired统计、事后实验及科研图。"""
from dataclasses import replace
from pathlib import Path
import json
import numpy as np
import pandas as pd
from .config import Config, DT, write_csv, write_json
from .data import Inputs
from .rolling import date_of
from .terminal import TerminalValues
from .multistage import tree_inputs, solve_tree, replay_tree
from .export import summaries, write_tables


def forecast_diagnostics(data: Inputs, output: Path) -> dict:
    errors, updates, corr = [], [], []
    actual = data.actual.reshape(-1, 2)
    for hour in (0, 6, 12, 18):
        trajectories = []
        for day in range(365):
            trajectory = []
            for h in range(1, 25):
                slot = day*144+(hour+h)*6-1
                if slot >= len(actual):
                    continue
                truth = actual[slot, 1]
                error = data.hourly[day, hour//6, h-1]-truth
                errors.append({'date': str(date_of(day).date()), 'issue_hour': hour, 'horizon': h,
                               'target': date_of(day)+pd.Timedelta(hours=hour+h), 'error_kw': error})
                trajectory.append(error)
                if hour and h <= 18:
                    old = data.hourly[day, hour//6-1, h+5]
                    updates.append({'date': str(date_of(day).date()), 'hour': hour, 'horizon': h,
                                    'block': h <= 6, 'old_absolute_error': abs(old-truth),
                                    'new_absolute_error': abs(error)})
            if len(trajectory) == 24:
                trajectories.append(trajectory)
        x = np.asarray(trajectories)
        for lag in range(1, 24):
            left, right = x[:, :-lag].ravel(), x[:, lag:].ravel()
            value = float(np.corrcoef(left, right)[0, 1]) if min(left.std(), right.std()) > 0 else None
            corr.append({'issue_hour': hour, 'lag_hours': lag, 'correlation': value, 'pairs': len(left)})
    frame = pd.DataFrame(errors); rows = []
    for (hour, horizon), group in frame.groupby(['issue_hour', 'horizon']):
        e = group.error_kw.to_numpy()
        rows.append({'issue_hour': hour, 'horizon': horizon, 'n': len(e), 'MAE': np.abs(e).mean(),
                     'RMSE': np.sqrt(np.mean(e**2)), 'Bias': e.mean()})
    metrics, comparison = pd.DataFrame(rows), pd.DataFrame(updates)
    write_csv(output/'forecast_errors.csv', frame)
    write_csv(output/'forecast_metrics.csv', metrics)
    write_csv(output/'forecast_revision_pairs.csv', comparison)
    write_csv(output/'forecast_error_autocorrelation.csv', pd.DataFrame(corr))
    block = comparison[comparison.block].groupby('hour')[['old_absolute_error', 'new_absolute_error']].mean()
    write_csv(output/'forecast_block_mae.csv', block.reset_index())
    # 已实现真值只在独立诊断模块读取，绝不写回主配置或选模。
    from src.plots.q3 import forecast_heatmaps
    font = forecast_heatmaps(metrics, output/'figures')
    return {'hourly_block_mae': block.reset_index().to_dict('records'), 'font': font,
            'year_end_missing_targets': 365*4*24-len(frame), 'future_targets_filled': False}


def paired_summary(values: np.ndarray) -> dict:
    values = np.asarray(values, dtype=float)
    if len(values) == 0:
        raise ValueError('配对统计没有共同日期')
    return {'days': len(values), 'total_saving': float(values.sum()), 'mean': float(values.mean()),
            'median': float(np.median(values)), 'IQR': float(np.quantile(values, .75)-np.quantile(values, .25)),
            'positive_day_fraction': float((values > 0).mean()), 'min': float(values.min()), 'max': float(values.max())}


def information_summary(paths: dict[str, Path], output: Path) -> pd.DataFrame:
    sets = ['K0', 'K06', 'K0612', 'K061218']
    costs = {}
    for key in sets:
        frame = pd.read_csv(paths[key]/'dispatch.csv')
        costs[key] = frame.groupby('date').total_cost.sum()
    rows, paired = [], []
    for old, new, hour in zip(sets[:-1], sets[1:], (6, 12, 18)):
        comparison = pd.concat([costs[old], costs[new]], axis=1, keys=['old', 'new'])
        if comparison.isna().any().any():
            raise ValueError('OUV分支评价日期不一致')
        difference = comparison.old-comparison.new
        rows.append({'metric': 'OUV', 'hour': hour, **paired_summary(difference.to_numpy())})
        paired.extend({'date': str(date), 'hour': hour, 'saving': float(value)} for date, value in difference.items())
    information = []
    for path in sorted((paths['K061218']/'information').glob('*.json')):
        information.extend(json.loads(path.read_text(encoding='utf-8')))
    for hour in (6, 12, 18):
        group = [r for r in information if r['hour'] == hour]
        if group:
            rows.append({'metric': 'FIV_block', 'hour': hour, **paired_summary(np.array([r['FIV_block'] for r in group]))})
        if hour == 18:
            for metric in ('FIV_day', 'FIV_cmp', 'FIV_cont'):
                valid = [r[metric] for r in group if r[metric] is not None]
                if valid:
                    rows.append({'metric': metric, 'hour': hour, **paired_summary(np.array(valid))})
    result = pd.DataFrame(rows)
    write_csv(output/'information_value_summary.csv', result)
    write_csv(output/'OUV_daily_pairs.csv', pd.DataFrame(paired))
    write_json(output/'FIV_detail.json', information)
    return result


def variants(base: Config) -> dict[str, Config]:
    """预先固定的单因素事后对照，不通过其结果改写base。"""
    return {'S10': replace(base, scenarios=10), 'S30': replace(base, scenarios=30),
            'tail0': replace(base, tail=0), 'tail4': replace(base, tail=4),
            'all_history': replace(base, unconditional=True),
            'terminal08': replace(base, terminal_scale=.8), 'terminal12': replace(base, terminal_scale=1.2),
            'pchip': replace(base, interpolation='pchip'), 'lag': replace(base, feedback='lag')}


def stress_dates(data: Inputs, main: pd.DataFrame) -> pd.DataFrame:
    daily, _ = summaries(main)
    rows = []
    features = []
    for row in daily.itertuples():
        d = (pd.Timestamp(row.date)-pd.Timestamp('2025-01-01')).days
        # 不选年末无法回放完整18h反事实的日期。
        if d >= 364:
            continue
        actual = data.actual[d]
        features.append({'day': d, 'pv_energy': float(actual[:, 1].sum()*DT),
            'pv_error': float(np.abs(data.pv(d, 0)-actual[:, 1]).mean()),
            'peak_net': float((actual[:, 0]-actual[:, 1]).max()), 'emergency': row.emergency})
    features = pd.DataFrame(features)
    for q, label in ((1/6, 'low_pv'), (.5, 'middle_pv'), (5/6, 'high_pv')):
        target = features.pv_energy.quantile(q)
        d = int(features.loc[(features.pv_energy-target).abs().idxmin(), 'day'])
        rows.append({'day': d, 'stratum': label})
    for feature in ('pv_error', 'peak_net', 'emergency'):
        rows.append({'day': int(features.loc[features[feature].idxmax(), 'day']), 'stratum': 'high_'+feature})
    return pd.DataFrame(rows).merge(features, on='day')


def run_experiments(data: Inputs, base: Config, root: Path, main: pd.DataFrame, *, workers: int = 1) -> None:
    """独立SOC链有界并行；每条链仍严格按日期推进。"""
    from .parallel import run_rollout_jobs
    configs = {'baseline': base, **variants(base)}
    jobs = []
    for name, config in configs.items():
        for label, nodes in zip(('K0', 'K06', 'K0612', 'K061218'), ((0,), (0, 6), (0, 6, 12), (0, 6, 12, 18))):
            if name == 'baseline' and len(nodes) == 4:
                continue
            jobs.append(dict(data=data, config=replace(config, nodes=nodes),
                output=root/'experiments'/name/label, with_fiv=len(nodes) == 4))
    jobs.append(dict(data=data, config=replace(base, deterministic=True), output=root/'experiments/M0', with_fiv=False))
    run_rollout_jobs(jobs, workers, root/'parallel_experiments.json')
    all_results, info_rows, differences = [], [], []
    for name, config in configs.items():
        paths = {}
        for label, nodes in zip(('K0', 'K06', 'K0612', 'K061218'), ((0,), (0, 6), (0, 6, 12), (0, 6, 12, 18))):
            path = root/'main' if name == 'baseline' and len(nodes) == 4 else root/'experiments'/name/label
            frame = main if name == 'baseline' and len(nodes) == 4 else pd.read_csv(path/'dispatch.csv')
            paths[label] = path
            daily, _ = summaries(frame)
            all_results.append({'variant': name, 'nodes': label, 'cost': float(daily.total_cost.sum()),
                                **{key: float(daily[key].sum()) for key in ('planned_cost', 'adjustment_cost', 'emergency_cost',
                                     'emergency', 'emergency_events', 'emergency_slots', 'throughput')},
                                'last_soc': float(daily.soc_end.iloc[-1])})
            if len(nodes) == 4:
                # 首块决策差和求解耗时按实际已提交审计计算。
                merged = main[['date', 'slot', 'grid']].merge(frame[['date', 'slot', 'grid']], on=['date', 'slot'], suffixes=('_base', '_variant'))
                first = merged[merged.slot < 36]
                seconds = sum(node['solver']['seconds'] for path_audit in (path/'audit').glob('*.json')
                              for node in json.loads(path_audit.read_text(encoding='utf-8')).get('nodes', []))
                differences.append({'variant': name, 'first_block_grid_L1': float((first.grid_base-first.grid_variant).abs().sum()),
                                    'solve_seconds': seconds})
        info = information_summary(paths, root/'experiments'/name)
        info['variant'] = name; info_rows.append(info)
    m0 = pd.read_csv(root/'experiments/M0/dispatch.csv')
    write_tables(m0, root/'experiments/M0')
    daily0, _ = summaries(m0)
    all_results.append({'variant': 'M0', 'nodes': 'K061218', 'cost': float(daily0.total_cost.sum()),
                        **{key: float(daily0[key].sum()) for key in ('planned_cost', 'adjustment_cost', 'emergency_cost',
                             'emergency', 'emergency_events', 'emergency_slots', 'throughput')},
                        'last_soc': float(daily0.soc_end.iloc[-1])})
    write_csv(root/'experiment_comparison.csv', pd.DataFrame(all_results))
    write_csv(root/'scenario_decision_timing.csv', pd.DataFrame(differences))
    combined = pd.concat(info_rows, ignore_index=True)
    combined['rank_by_saving'] = combined.groupby(['variant', 'metric']).total_saving.rank(ascending=False, method='min')
    write_csv(root/'information_robustness.csv', combined)
    selected = stress_dates(data, main); write_csv(root/'stress_dates.csv', selected)
    from .parallel import process_pool
    requests = []
    for day in sorted(selected.day.unique()):
        baseline_day = main[pd.to_datetime(main.date) == date_of(int(day))]
        requests.append((data, base, root, int(day), float(baseline_day.initial_soc.iloc[0]),
                         float(baseline_day.total_cost.sum())))
    with process_pool(workers, base.solver_threads) as executor:
        results = list(executor.map(m2_job, requests)) if executor is not None else list(map(m2_job, requests))
    write_csv(root/'M2_comparison.csv', pd.DataFrame(results))
    values = np.array([r['relative_loss'] for r in results])
    write_json(root/'M2_summary.json', {**paired_summary(values), 'q90': float(np.quantile(values, .9)),
              'max_absolute_gap': float(np.max(np.abs(values))), 'interpretation': 'stratified_stress_sample_not_annual_unbiased_estimate'})
    with process_pool(workers, base.solver_threads) as executor:
        groups = executor.map(settlement_job, requests) if executor is not None else map(settlement_job, requests)
        sequential_rows = [row for group in groups for row in group]
    write_csv(root/'settlement_stress_comparison.csv', pd.DataFrame(sequential_rows))


def m2_job(request: tuple) -> dict:
    data, base, root, day, initial, baseline_cost = request
    terminal = TerminalValues(data, base)
    net, labels, nodes, audit = tree_inputs(data, day, base)
    coefficient, calibration = terminal.value(day, 0)
    from .optimization import LimitedSolve
    try:
        solution = solve_tree(net, labels, nodes, np.array(audit['load_upper']), data.prices, initial, coefficient, base)
    except LimitedSolve as error:
        write_json(root/f'M2/{date_of(day).date()}_failure.json', error.audit)
        raise
    frame = replay_tree(data, day, initial, nodes, solution, base)
    write_csv(root/f'M2/{date_of(day).date()}.csv', frame)
    write_json(root/f'M2/{date_of(day).date()}.json', {'scenarios': audit, 'nodes': nodes, 'labels': labels.tolist(),
                'solver': solution['audit'], 'calibration': calibration})
    return {'date': str(date_of(day).date()), 'M1_cost': baseline_cost,
            'M2_cost': float(frame.total_cost.sum()),
            'relative_loss': float((baseline_cost-frame.total_cost.sum())/frame.total_cost.sum())}


def settlement_job(request: tuple) -> list[dict]:
    # 每个stress日独立；同日各更新时间集从相同主轨迹初态开始。
    from .rolling import run_day
    data, base, root, day, initial, _ = request
    terminal = TerminalValues(data, base)
    sequential_rows = []
    for settlement in ('final', 'sequential'):
        costs = []
        for nodes in ((0,), (0, 6), (0, 6, 12), (0, 6, 12, 18)):
            config = replace(base, settlement=settlement, nodes=nodes)
            frame, audit, info = run_day(data, terminal, int(day), initial, config, with_fiv=len(nodes) == 4)
            path = root/f'settlement_stress/{settlement}/{day}_K{len(nodes)}'
            write_csv(path/'dispatch.csv', frame); write_json(path/'audit.json', audit); write_json(path/'information.json', info)
            costs.append(float(frame.total_cost.sum()))
            sequential_rows.append({'day': int(day), 'settlement': settlement, 'nodes': len(nodes),
                'cost': costs[-1], 'adjustment_cost': float(frame.adjustment_cost.sum()),
                'emergency_cost': float(frame.emergency_cost.sum()), 'scope': 'paired_stress_day_same_initial_state',
                'FIV6': next((r['FIV_block'] for r in info if r['hour'] == 6), None),
                'FIV12': next((r['FIV_block'] for r in info if r['hour'] == 12), None),
                'FIV18': next((r['FIV_block'] for r in info if r['hour'] == 18), None)})
        for row in sequential_rows[-4:]:
            row.update(OUV6=costs[0]-costs[1], OUV12=costs[1]-costs[2], OUV18=costs[2]-costs[3])
    return sequential_rows
