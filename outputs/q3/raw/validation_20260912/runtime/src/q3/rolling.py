"""3.11—3.22、3.28：冻结节点、真实逐槽执行、SOC连续和成对FIV。"""
import hashlib
import json
from concurrent.futures import Executor
from pathlib import Path
import numpy as np
import pandas as pd
from .config import Config, DT, E_INITIAL, TOL, write_csv, write_json
from .data import Inputs
from .physics import Policy, replay, adjustment, validate
from .scenarios import construct
from .terminal import TerminalValues
from .optimization import solve, LimitedSolve
from .parallel import process_pool, solve_job


def date_of(day: int) -> pd.Timestamp:
    return pd.Timestamp('2025-01-01')+pd.Timedelta(days=day)


def previous_net(data: Inputs, day: int, hour: int) -> float:
    slot = day*144+hour*6
    if slot == 0:
        raise ValueError('没有上一时隙观测')
    return float(np.diff(data.actual.reshape(-1, 2)[slot-1][::-1])[0]*DT)


def frame_for(data: Inputs, day: int, hour: int, policy: Policy, initial: float, config: Config) -> pd.DataFrame:
    start, end = hour*6, hour*6+len(policy.grid)
    actual = data.actual[day, start:end]
    if len(actual) != len(policy.grid):
        raise ValueError('真实执行不得跨越尚未建立下一日正式计划的午夜')
    net = (actual[:, 0]-actual[:, 1])*DT
    response = replay(policy, net, initial, mode=config.feedback, previous_net=previous_net(data, day, hour))
    return pd.DataFrame({'date': str(date_of(day).date()), 'slot': np.arange(start, end),
        'timestamp': date_of(day)+pd.to_timedelta((np.arange(start, end)+1)*10, unit='min'),
        'node_hour': hour, 'net_kwh': net, 'load_kw': actual[:, 0], 'pv_kw': actual[:, 1],
        'grid': policy.grid, 'charge_cap': policy.charge_cap, 'discharge_cap': policy.discharge_cap,
        'lag_observation': np.r_[previous_net(data, day, hour), net[:-1]],
        'price': data.prices[start:end], **response})


def fiv(data: Inputs, terminal: TerminalValues, day: int, hour: int, soc: float,
        reference: np.ndarray, config: Config, *, checkpoint_root: Path | None = None,
        require: bool = True, max_slices: int | None = 1) -> tuple[dict, list[dict]]:
    length, today = 108, min(144-hour*6, 108)
    new = construct(data, day, hour, config, length=length)
    old = construct(data, day, hour, config, origin=hour-6, length=length,
                    paired_days=np.asarray(new.audit['history_days'], dtype=int) if not new.audit['M0'] else None,
                    paired_weights=new.weights)
    if new.audit['M0'] != old.audit['M0'] or new.audit['history_days'] != old.audit['history_days']:
        raise ValueError('stale/updated配对历史支持不一致')
    coefficient, calibration = terminal.value(day, hour+18)
    prices = data.prices[(hour*6+np.arange(length))%144]
    records, costs, audits = [], [], []
    requests = [dict(scenarios=scenes, prices=prices, initial=soc, config=config,
                    reference=reference, today=today, terminal=coefficient,
                    previous_net=previous_net(data, day, hour), require=require, max_slices=max_slices,
                    checkpoint=checkpoint_root/name if checkpoint_root else None)
                for name, scenes in (('stale', old), ('updated', new))]
    solutions = list(terminal.executor.map(solve_job, requests)) if terminal.executor is not None else [solve_job(job) for job in requests]
    for (name, scenes), solution in zip((('stale', old), ('updated', new)), solutions):
        if solution.policy is None:
            raise LimitedSolve(solution.audit)
        # 直接价值只执行当前6h；跨日继续价值在相同18h冻结反事实策略上回放，代理交易不计入主轨迹。
        start = day*144+hour*6
        realized = data.actual.reshape(-1, 2)[start:start+length]
        if len(realized) < length:
            # 年末共同支持集未来实际量缺失，仍报告可见当日直接价值，不补造次年真值。
            valid_length = len(realized)
        else:
            valid_length = length
        policy = solution.policy.part(0, valid_length)
        response = replay(policy, (realized[:, 0]-realized[:, 1])*DT, soc,
                          mode=config.feedback, previous_net=previous_net(data, day, hour))
        schedule = prices[:valid_length]*policy.grid
        boundary = min(today, valid_length)
        schedule[:boundary] = prices[:boundary]*reference[:boundary]+adjustment(policy.grid[:boundary], reference[:boundary], prices[:boundary])
        cost = schedule+5*prices[:valid_length]*response['emergency']
        costs.append(cost)
        audits.append({'branch': name, 'solver': solution.audit, 'scenarios': scenes.audit})
        records.append({'branch': name, 'grid': policy.grid.tolist(), 'charge_cap': policy.charge_cap.tolist(),
                        'discharge_cap': policy.discharge_cap.tolist(), 'real_cost': cost.tolist(),
                        'soc': response['soc'].tolist()})
    direct = float(costs[0][:36].sum()-costs[1][:36].sum())
    complete = all(len(cost) == length for cost in costs)
    total = float(costs[0].sum()-costs[1].sum()) if complete else None
    row = {'date': str(date_of(day).date()), 'hour': hour, 'initial_soc': soc,
           'FIV_block': direct, 'FIV_day': direct if hour == 18 else None,
           'FIV_cmp': total if hour == 18 else None,
           'FIV_cont': total-direct if hour == 18 and complete else None,
           'comparison_complete': complete, 'calibration': calibration,
           'interpretation': '18h matched-support frozen counterfactual; no state mutation to main', 'audits': audits}
    return row, records


def run_day(data: Inputs, terminal: TerminalValues, day: int, initial: float, config: Config,
            *, with_fiv: bool = False, checkpoint_root: Path | None = None,
            max_slices: int | None = 1, require: bool = True) -> tuple[pd.DataFrame, dict, list[dict]]:
    if day < 7:
        # Q2既定预热协议：首7日不制定可用负荷计划、储能停机；真实缺口只记紧急购电。
        net = (data.actual[day, :, 0]-data.actual[day, :, 1])*DT
        zero = np.zeros(144)
        response = replay(Policy(zero, zero, zero), net, initial)
        frame = pd.DataFrame({'date': str(date_of(day).date()), 'slot': np.arange(144),
            'timestamp': date_of(day)+pd.to_timedelta((np.arange(144)+1)*10, unit='min'),
            'node_hour': 0, 'net_kwh': net, 'load_kw': data.actual[day, :, 0], 'pv_kw': data.actual[day, :, 1],
            'grid': zero, 'charge_cap': zero, 'discharge_cap': zero, 'price': data.prices, **response,
            'g0': zero, 'initial_soc': initial, 'adjustment_cost': zero,
            'lag_observation': np.r_[0. if day == 0 else previous_net(data, day, 0), net[:-1]]})
        frame['planned_cost'] = 0.
        frame['emergency_cost'] = 5*frame.price*frame.emergency
        frame['total_cost'] = frame.emergency_cost
        return frame, {'cold_start': True, 'reason': 'Q2 Jan1-Jan7 stationary storage, unavailable load forecast'}, []
    soc, g0, version = initial, None, None
    frames, nodes, information = [], [], []
    node_list = list(config.nodes)
    for index, hour in enumerate(node_list):
        next_hour = node_list[index+1] if index+1 < len(node_list) else 24
        length = (next_hour-hour)*6
        scenes = construct(data, day, hour, config)
        coefficient, calibration = terminal.value(day, hour)
        prices = data.prices[(hour*6+np.arange(144))%144]
        reference = None if hour == 0 else (version if config.settlement == 'sequential' else g0)[hour*6:]
        solution = solve(scenes, prices, soc, config, reference=reference, today=144-hour*6,
                         terminal=coefficient, previous_net=previous_net(data, day, hour), require=require,
                         checkpoint=checkpoint_root/f'{hour:02d}' if checkpoint_root else None, max_slices=max_slices)
        if solution.policy is None:
            raise LimitedSolve(solution.audit)
        policy = solution.policy
        if hour == 0:
            g0 = policy.grid.copy(); version = g0.copy()
            booked_adjustment = np.zeros(144)
        elif config.settlement == 'sequential':
            # sequential交易语义：当天所有剩余计划在每次节点成为新有效版并真实记账；跨日仍非交易。
            count = 144-hour*6
            booked_adjustment[hour*6:] += adjustment(policy.grid[:count], version[hour*6:], data.prices[hour*6:])
            version[hour*6:] = policy.grid[:count]
        if with_fiv and hour and day >= 31:
            paired_reference = (reference.copy() if config.settlement == 'sequential' else g0[hour*6:].copy())
            item, counterfactuals = fiv(data, terminal, day, hour, soc, paired_reference, config,
                checkpoint_root=checkpoint_root/f'FIV_{hour}' if checkpoint_root else None, require=require, max_slices=max_slices)
            information.append(item)
        else:
            counterfactuals = []
        executed = frame_for(data, day, hour, policy.part(0, length), soc, config)
        executed['g0'] = g0[hour*6:next_hour*6]
        executed['initial_soc'] = initial
        if checkpoint_root:
            write_csv(checkpoint_root/f'{hour:02d}'/'executed_block.csv', executed)
        nodes.append({'hour': hour, 'initial_soc': soc, 'committed_slots': length,
            'solver': solution.audit, 'scenarios': scenes.audit, 'calibration': calibration,
            'grid': policy.grid.tolist(), 'charge_cap': policy.charge_cap.tolist(),
            'discharge_cap': policy.discharge_cap.tolist(),
            'roles': ['committed' if t < length else 'today_proxy' if t < 144-hour*6 else 'continuation_proxy' for t in range(144)],
            'delta_from_g0': (policy.grid[:144-hour*6]-g0[hour*6:]).tolist(), 'fiv_branches': counterfactuals})
        frames.append(executed); soc = float(executed.soc.iloc[-1])
    frame = pd.concat(frames, ignore_index=True)
    frame['planned_cost'] = frame.price*frame.g0
    frame['adjustment_cost'] = (booked_adjustment if config.settlement == 'sequential' else
        adjustment(frame.grid.to_numpy(), frame.g0.to_numpy(), frame.price.to_numpy()))
    frame['emergency_cost'] = 5*frame.price*frame.emergency
    frame['total_cost'] = frame.planned_cost+frame.adjustment_cost+frame.emergency_cost
    validate_frame(frame, config)
    return frame, {'date': str(date_of(day).date()), 'nodes': nodes, 'settlement': config.settlement}, information


def validate_frame(frame: pd.DataFrame, config: Config, *, full: bool = False) -> None:
    dates, times = pd.to_datetime(frame.date), pd.to_datetime(frame.timestamp)
    if frame.empty or times.duplicated().any() or not times.diff().dropna().eq(pd.Timedelta(minutes=10)).all():
        raise ValueError('回放不连续')
    if not dates.eq((times-pd.Timedelta(minutes=10)).dt.normalize()).all():
        raise ValueError('右端点归属日期错误')
    np.testing.assert_allclose(frame.net_kwh, (frame.load_kw-frame.pv_kw)*DT, atol=TOL, rtol=0)
    last = None
    for _, day in frame.groupby('date', sort=False):
        if len(day) != 144 or not np.array_equal(day.slot, np.arange(144)):
            raise ValueError('每日必须144个完整时段')
        initial = float(day.initial_soc.iloc[0])
        if last is not None and abs(initial-last) > TOL:
            raise ValueError('跨日SOC断裂')
        validate(day.grid.to_numpy(), day.net_kwh.to_numpy(), initial,
                 {k: day[k].to_numpy() for k in ('charge', 'discharge', 'emergency', 'spill', 'soc')})
        recovered = replay(Policy(day.grid.to_numpy(), day.charge_cap.to_numpy(), day.discharge_cap.to_numpy()),
            day.net_kwh.to_numpy(), initial, mode=config.feedback, previous_net=float(day.lag_observation.iloc[0]))
        for key in recovered:
            np.testing.assert_allclose(day[key], recovered[key], atol=TOL, rtol=0)
        np.testing.assert_allclose(day.lag_observation.iloc[1:], day.net_kwh.iloc[:-1], atol=TOL, rtol=0)
        if config.settlement == 'final':
            np.testing.assert_allclose(day.adjustment_cost, adjustment(day.grid.to_numpy(), day.g0.to_numpy(), day.price.to_numpy()), atol=TOL)
        np.testing.assert_allclose(day.planned_cost, day.price*day.g0, atol=TOL)
        np.testing.assert_allclose(day.emergency_cost, 5*day.price*day.emergency, atol=TOL)
        np.testing.assert_allclose(day.total_cost, day.planned_cost+day.adjustment_cost+day.emergency_cost, atol=TOL)
        last = float(day.soc.iloc[-1])
    if full and (len(frame) != 334*144 or dates.min() != pd.Timestamp('2025-02-01') or dates.max() != pd.Timestamp('2025-12-31')):
        raise ValueError('拒绝把部分日期发布为完整result3.xlsx')


def run_period(data: Inputs, config: Config, output: Path, *, end: int = 365, with_fiv: bool = True,
               workers: int = 1, max_slices: int | None = 1) -> pd.DataFrame:
    from .checkpoint import run_lock
    with run_lock(output/'run.lock'), process_pool(workers, config.solver_threads) as executor:
        return _run_period(data, config, output, end=end, with_fiv=with_fiv, executor=executor, max_slices=max_slices)


def _run_period(data: Inputs, config: Config, output: Path, *, end: int, with_fiv: bool,
                executor: Executor | None, max_slices: int | None) -> pd.DataFrame:
    """只由显式full命令调用全年；每日CSV+审计先落盘，再原子提交receipt，可安全续算。"""
    output.mkdir(parents=True, exist_ok=True)
    signature = config.signature()
    sources = hashlib.sha256(json.dumps(data.provenance, sort_keys=True).encode('utf-8')).hexdigest()
    state_path = output/'state.json'
    state = json.loads(state_path.read_text(encoding='utf-8')) if state_path.exists() else {
        'signature': signature, 'sources': sources, 'days': [], 'soc': E_INITIAL, 'with_fiv': with_fiv}
    if state['signature'] != signature or state['sources'] != sources or state['with_fiv'] != with_fiv:
        raise ValueError('续算配置/模型/来源/FIV设置变化，禁止混用前缀')
    terminal = TerminalValues(data, config, executor, output/'terminal_cache.json')
    calibration_path = output/'terminal_calibration.csv'
    if calibration_path.exists():
        for row in pd.read_csv(calibration_path).to_dict('records'):
            terminal.cache[(int(row['history_day']), int(row['hour']), float(row['delta']))] = row
    all_frames = []
    for day in range(end):
        date = str(date_of(day).date()); path = output/f'days/{date}.csv'
        if day < len(state['days']):
            receipt = state['days'][day]
            files = {'dispatch': path, 'audit': output/f'audit/{date}.json', 'information': output/f'information/{date}.json'}
            if receipt['day'] != day or any(hashlib.sha256(p.read_bytes()).hexdigest() != receipt['hashes'][key] for key, p in files.items()):
                raise ValueError('已提交日期或数据摘要不一致')
            frame = pd.read_csv(path)
        else:
            write_json(output/'active.json', {'date': date, 'status': 'solving', 'completed_days': len(state['days'])})
            try:
                frame, audit, information = run_day(data, terminal, day, state['soc'], config, with_fiv=with_fiv,
                    checkpoint_root=output/'nodes'/date, max_slices=max_slices)
            except LimitedSolve as error:
                write_json(output/f'failures/{date}.json', error.audit)
                raise
            write_csv(path, frame)
            write_json(output/f'audit/{date}.json', audit)
            write_json(output/f'information/{date}.json', information)
            state['soc'] = float(frame.soc.iloc[-1])
            files = {'dispatch': path, 'audit': output/f'audit/{date}.json', 'information': output/f'information/{date}.json'}
            state['days'].append({'day': day, 'hashes': {key: hashlib.sha256(p.read_bytes()).hexdigest() for key, p in files.items()}})
            write_json(state_path, state)
            if terminal.cache:
                write_csv(calibration_path, pd.DataFrame(terminal.cache.values()))
            print(f'{output.name} {date} SOC={state["soc"]:.3f} 已提交', flush=True)
        all_frames.append(frame)
    result = pd.concat(all_frames, ignore_index=True)
    validate_frame(result, config)
    formal = result[pd.to_datetime(result.date) >= pd.Timestamp('2025-02-01')].copy()
    write_csv(output/'warmup.csv', result[pd.to_datetime(result.date) < pd.Timestamp('2025-02-01')])
    write_csv(output/'dispatch.csv', formal)
    write_json(output/'active.json', {'status': 'complete', 'completed_days': end})
    return formal
