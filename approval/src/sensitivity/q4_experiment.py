"""Q4-S1/S2与四节点迁移：只复用基准，只做20个代表日OFAT实验。"""
from pathlib import Path
from dataclasses import asdict, replace
import argparse
import hashlib
import json
import os
import sys
import time
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
RUN = ROOT / 'outputs/q4/raw/sensitivity_20260913'
DOC = ROOT / 'docs/sensitivity_q4'
BASE = {'4-2': ROOT/'outputs/q4/raw/rescue_lp_q42_20260913_v2',
        '4-3': ROOT/'outputs/q4/raw/rescue_lp_q43_20260913_v3'}


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def digest(*arrays):
    h = hashlib.sha256()
    for a in arrays:
        a = np.ascontiguousarray(a)
        h.update(str((a.shape, a.dtype)).encode())
        h.update(a.tobytes())
    return h.hexdigest()


def configure(mode):
    """从对应正式快照加载Q4；Q3/Q2只读依赖逐文件校验。"""
    os.environ['Q4_WORKSPACE_ROOT'] = str(ROOT)
    os.environ['Q3_WORKSPACE_ROOT'] = str(ROOT)
    sys.path.insert(0, str(ROOT))
    import src.q4
    frozen = ROOT / ('docs/4/rescue_lp/frozen_source_v2' if mode == '4-2'
                     else 'docs/4/rescue_lp/frozen_source_v3')
    src.q4.__path__ = [str(frozen/'src/q4')]
    state = read_json(BASE[mode]/'state.json')
    for relative, expected in state['source_hashes'].items():
        source = frozen/'src'/relative if relative.startswith('q4/') else ROOT/'src'/relative
        assert sha(source) == expected, ('source changed', source)
    for name, expected in state['input_hashes'].items():
        assert sha(name) == expected, ('input changed', name)
    from src.q4.config import Config
    from highspy import Highs
    assert Highs().version() == state['solver_version']
    values = dict(state['config']); values['nodes'] = tuple(values['nodes'])
    return Config(**values), state


def inputs(state):
    from src.q3.data import read_inputs
    from src.q4.data import Inputs, read_prices
    from src.q4.price import Forecasts
    from src.q4.config import ATTACHMENTS, Q2_RUN, write_json
    q3 = read_inputs(Q2_RUN, RUN/'inputs/q3')
    folder = ROOT/'inputs/q4/rescue_processed'
    provenance = read_json(folder/'source_manifest.json')
    values = pd.read_csv(folder/'price_forecasts.csv', float_precision='round_trip').to_numpy(float)
    residuals = pd.read_csv(folder/'price_residuals.csv', float_precision='round_trip').to_numpy(float)
    assert hashlib.sha256(values.tobytes()).hexdigest() == state['price_forecasts_array_sha256']
    for decision in q3.provenance['q2_decisions']:
        old = next(d for d in provenance['q3_provenance']['q2_decisions'] if d['date'] == decision['date'])
        assert decision['sha256'] == old['sha256']
    write_json(RUN/'inputs/frozen_forecasts.json', {
        'price_forecasts_sha256': state['price_forecasts_array_sha256'],
        'load_pv_inputs': q3.provenance, 'price_model_retrained': False})
    return Inputs(q3, read_prices(ATTACHMENTS/'附件4.xlsx'),
                  Forecasts(values, residuals, provenance['price_model']), provenance)


def metrics(frame, audit):
    nodes = audit.get('nodes', [audit])
    solvers = [n['solver'] for n in nodes]
    difference = (frame.grid - frame.g0).to_numpy()
    return dict(total_cost=float(frame.total_cost.sum()), planned_cost=float(frame.planned_cost.sum()),
                emergency_kwh=float(frame.emergency.sum()), emergency_cost=float(frame.emergency_cost.sum()),
                min_soc=float(min(frame.initial_soc.iloc[0], frame.soc.min())),
                final_soc=float(frame.soc.iloc[-1]), initial_soc=float(frame.initial_soc.iloc[0]),
                adjustment_up_kwh=float(np.maximum(difference, 0).sum()),
                adjustment_down_kwh=float(np.maximum(-difference, 0).sum()),
                adjustment_abs_kwh=float(abs(difference).sum()), adjustment_net_kwh=float(difference.sum()),
                adjustment_cost=float(frame.adjustment_cost.sum()),
                solve_seconds=float(sum(s['seconds'] for s in solvers)),
                solver_native_seconds=float(sum(s['solver_seconds'] for s in solvers)),
                solve_wall_seconds=float(sum(s['wall_seconds'] for s in solvers)),
                scenario_seconds=float(sum(n['scenarios']['construction_seconds'] for n in nodes)),
                nodes=len(nodes), all_optimal=all(s['status'] == 'Optimal' and s['reliable'] for s in solvers),
                max_gap=float(max(s['gap'] for s in solvers)))


def baseline(mode, date):
    frame = pd.read_csv(BASE[mode]/f'days/{date}.csv', float_precision='round_trip')
    audit = read_json(BASE[mode]/f'audit/{date}.json')
    return frame, audit


def prepare(data, config):
    """先固定规则、候选指标和日期，完成后才能开始任何敏感性求解。"""
    from src.q4.config import write_csv, write_json, DT
    from src.q4.scenarios import _scale
    selection_path = RUN/'representatives.json'
    if selection_path.exists():
        return read_json(selection_path)
    rows = []
    for day in range(151, 365):
        date = str((pd.Timestamp('2025-01-01') + pd.Timedelta(days=day)).date())
        days, en, ep = data.joint_history(day, 0, 288)
        keep = days >= day-config.residual_window
        sn, sp = _scale(en[keep, :144]), _scale(ep[keep, :144])
        actual_net = (data.q3.actual[day, :, 0]-data.q3.actual[day, :, 1])*DT
        net_error = actual_net-data.point_net(day, 0, 288)[:144]
        price_error = data.actual_prices[day]-data.point_price(day, 0, 288)[:144]
        risk = float(np.mean(np.maximum(net_error/sn, 0)*np.maximum(price_error/sp, 0)))
        rows.append(dict(date=date, day=day, price_std=float(data.actual_prices[day].std()),
                         joint_risk=risk, peak_net_kwh=float(actual_net.max())))
    risks = pd.DataFrame(rows)
    selected = {}
    for mode in BASE:
        daily = pd.read_csv(BASE[mode]/'daily.csv', float_precision='round_trip')
        annual_median = float(daily.total_cost.median())
        table = risks.merge(daily[['date','total_cost','emergency','adjustment_cost']], on='date')
        table['median_distance'] = abs(table.total_cost-annual_median)
        rules = [('常规日','median_distance',True), ('高价格波动日','price_std',False),
                 ('高联合风险日','joint_risk',False), ('高运行压力日','emergency',False)]
        if mode == '4-3':
            rules = [rules[0], rules[2]]
        used, chosen = set(), []
        for role, key, ascending in rules:
            row = table[~table.date.isin(used)].sort_values([key,'date'], ascending=[ascending,True]).iloc[0]
            used.add(row.date)
            chosen.append(dict(role=role,date=row.date,day=int(row.day),metric=key,
                               metric_value=float(row[key]), annual_cost_median=annual_median))
        selected[mode] = chosen
        write_csv(RUN/f'selection_metrics_{mode}.csv',table)
    write_json(selection_path, {'rules': 'June-Dec; ordinary closest to full formal-year median; volatility population std; joint risk mean positive standardized OOS net residual times positive standardized OOS price residual (scales from available 56-day history); pressure maximum baseline emergency kWh; ties date ascending; duplicates advance rank',
                                'selected_before_variants': True, 'modes': selected})
    return read_json(selection_path)


def matrix_digest(scenarios, initial, reference=None, today=None):
    from src.q4.optimization import build_matrix
    objective, bounds, integer, constraints, indices, offset = build_matrix(scenarios, initial, reference=reference, today=today)
    matrix = constraints.A
    h = hashlib.sha256()
    for a in (objective,bounds.lb,bounds.ub,constraints.lb,constraints.ub,matrix.indptr,matrix.indices,matrix.data):
        h.update(np.asarray(a).tobytes())
    return h.hexdigest()


def freeze(data, day, mode, config, frame, audit):
    from src.q4.scenarios import construct
    from src.q4.config import write_json
    nodes = audit.get('nodes', [dict(audit, hour=0)])
    cache = {}
    for n in nodes:
        hour = n['hour']; length = 288 if mode == '4-2' else 144
        s = construct(data, day, hour, length, config)
        old = n['scenarios']
        for key in ['history_days','representative_pool_indices','tail_indices_in_pool','represented_counts']:
            assert s.audit[key] == old[key], key
        for key in ['weights','bootstrap_distances','radius']:
            np.testing.assert_allclose(s.audit[key], old[key], atol=1e-12,rtol=1e-12)
        reference = None if hour == 0 else np.asarray(nodes[0]['grid'])[hour*6:]
        today = None if mode == '4-2' else 144-hour*6
        assert matrix_digest(s,n['initial_soc'],reference,today) == n['solver']['matrix_digest'], (mode,day,hour,'baseline matrix mismatch')
        signature = digest(s.net,s.prices,s.weights,s.distance)
        s.audit.update(scenario_fingerprint=signature, baseline_matrix_verified=True)
        cache[hour] = s
        directory = RUN/'frozen'/mode/audit['date']; directory.mkdir(parents=True,exist_ok=True)
        if not (directory/f'{hour:02d}.json').exists():
            np.savez_compressed(directory/f'{hour:02d}.npz',net=s.net,prices=s.prices,weights=s.weights,
                                distance=s.distance,radius=s.radius)
            write_json(directory/f'{hour:02d}.json',s.audit)
        else:
            assert read_json(directory/f'{hour:02d}.json')['scenario_fingerprint'] == signature
    return cache


def run(mode):
    os.environ["Q4_SENS_MODE"] = mode
    config, state = configure(mode)
    from src.q4.config import write_csv, write_json
    from src.q4 import rolling
    from src.q4.scenarios import construct
    from src.q4.optimization import LimitedSolve
    data = inputs(state)
    representatives = prepare(data, config)['modes'][mode]
    # 每种模式首次读入时固定所有原始基准文件hash；恢复时校验，禁止混用。
    source_files = [BASE[mode]/'state.json']
    for r in representatives:
        source_files += [BASE[mode]/f"days/{r['date']}.csv",BASE[mode]/f"audit/{r['date']}.json"]
    manifest = {str(p):sha(p) for p in source_files}
    annual = BASE[mode]/'dispatch.csv'
    if annual.is_file():
        manifest[str(annual)] = sha(annual)
    else:
        reference = BASE[mode]/'annual_dispatch_reference.json'
        manifest[str(annual)] = read_json(reference)['sha256']
        manifest[str(reference)] = sha(reference)
    manifest_path = RUN/f'baseline_hashes_{mode}.json'
    if manifest_path.exists():
        assert read_json(manifest_path) == manifest
    else:
        write_json(manifest_path,manifest)
    cached, baseline_rows = {}, []
    for r in representatives:
        f,a = baseline(mode,r['date'])
        rolling.validate_frame(f,mode,config)
        cached[r['date']] = freeze(data,r['day'],mode,config,f,a)
        baseline_rows.append(dict(mode=mode,date=r['date'],role=r['role'],parameter='baseline',setting='1.00 / 0.5,0.5',
                                  baseline_reused=True,**metrics(f,a),delta_cost_pct=0.,delta_emergency_kwh=0.,
                                  delta_emergency_pct=0. if f.emergency.sum()>0 else None,delta_adjustment_cost=0.))
    write_json(RUN/f'baseline_metrics_{mode}.json',baseline_rows)
    stages = [('rho',0.75),('rho',1.25)]
    if mode == '4-2': stages += [('weight',0.7),('weight',0.3)]
    original = rolling.construct
    for parameter,value in stages:
        for r,base in zip(representatives,baseline_rows):
            date = r['date']; case = f'{mode}_{parameter}_{value}_{date}'
            directory = RUN/'cases'/case; directory.mkdir(parents=True,exist_ok=True)
            receipt = directory/'result.json'
            if receipt.exists():
                saved = read_json(receipt)
                assert saved['artifact_hashes'] == {name:sha(directory/name) for name in ['dispatch.csv','audit.json']}
                print('REUSED',case,flush=True); continue
            test = replace(config, **({'dro_scale':value} if parameter=='rho' else {'net_weight':value}))
            assert [k for k in asdict(config) if asdict(config)[k]!=asdict(test)[k]] == [('dro_scale' if parameter=='rho' else 'net_weight')]
            write_json(RUN/'active.json',dict(status='running',case=case,started_at=time.time()))
            print('START',case,flush=True)
            def selected_scenarios(data_arg,day,hour,length,config_arg):
                base_s = cached[date][hour]
                if parameter == 'rho':
                    s = replace(base_s,radius=base_s.radius*value,audit=dict(base_s.audit,
                                radius=base_s.radius*value,radius_scale=value,construction_reused=True))
                    assert digest(s.net,s.prices,s.weights,s.distance) == base_s.audit['scenario_fingerprint']
                else:
                    s = construct(data_arg,day,hour,length,config_arg)
                    assert s.audit['history_days'] == base_s.audit['history_days']
                    assert s.audit['tail_indices_in_pool'] == base_s.audit['tail_indices_in_pool']
                    assert not np.array_equal(s.distance,base_s.distance)
                    s.audit.update(full_weight_pipeline_rebuilt=True,construction_reused=False,
                                   scenario_fingerprint=digest(s.net,s.prices,s.weights,s.distance))
                s.audit['base_radius'] = base_s.radius
                return s
            rolling.construct = selected_scenarios
            started = time.perf_counter()
            try:
                runner = rolling.run_day_q42 if mode=='4-2' else rolling.run_day_q43
                frame,audit = runner(data,r['day'],base['initial_soc'],test)
            except LimitedSolve as error:
                write_json(directory/'failure.json',error.audit)
                raise
            finally:
                rolling.construct = original
            row = metrics(frame,audit)
            assert row['all_optimal']
            row.update(mode=mode,date=date,role=r['role'],parameter=parameter,setting=str(value),
                       baseline_reused=False,day_elapsed_seconds=time.perf_counter()-started,
                       delta_cost_pct=100*(row['total_cost']-base['total_cost'])/base['total_cost'],
                       delta_emergency_kwh=row['emergency_kwh']-base['emergency_kwh'],
                       delta_emergency_pct=100*(row['emergency_kwh']-base['emergency_kwh'])/base['emergency_kwh'] if base['emergency_kwh']>0 else None,
                       delta_adjustment_cost=row['adjustment_cost']-base['adjustment_cost'])
            audit['experiment'] = dict(parameter=parameter,value=value,base_config=asdict(config),test_config=asdict(test),
                                       formal_source_hashes=state['source_hashes'],baseline_reoptimized=False)
            write_csv(directory/'dispatch.csv',frame);write_json(directory/'audit.json',audit)
            write_json(receipt,dict(metrics=row,artifact_hashes={name:sha(directory/name) for name in ['dispatch.csv','audit.json']}))
            print('DONE',case,round(row['delta_cost_pct'],4),'%',round(row['solve_seconds'],2),'s',flush=True)
    assert manifest == {str(p):sha(p) for p in source_files}
    write_json(RUN/f'completed_{mode}.json',dict(status='complete',days=len(representatives)*len(stages),baseline_days_reused=len(representatives)))


if __name__ == '__mp_main__':
    configure(os.environ['Q4_SENS_MODE'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser();parser.add_argument('mode',choices=['4-2','4-3'])
    run(parser.parse_args().mode)
