"""最终检验方案的独立队列：只读主结果，计算任务等待主表完成。"""
import argparse
from dataclasses import replace
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
import time
import numpy as np
import pandas as pd
from .config import ROOT, Config, CAP, DT, E_MIN, E_MAX, ETA, TOL, write_csv, write_json
from .data import Inputs, read_inputs
from .rolling import date_of, run_period, run_day, fiv
from .physics import adjustment, replay, Policy
from .scenarios import construct, pool_indices
from .terminal import TerminalValues
from .export import summaries
from .analysis import forecast_diagnostics, paired_summary, stress_dates
from .parallel import process_pool, limit_native_libraries
from .checkpoint import run_lock
from .sampled import DATES

SPEC = ROOT/'docs/3/validation/Q3_第三问_模型检验与实验方案_最终版.md'
NODE_SETS = {'K0': (0,), 'K06': (0, 6), 'K0612': (0, 6, 12), 'K061218': (0, 6, 12, 18)}


def load_config(main_run: Path) -> Config:
    values = json.loads((main_run/'execution.json').read_text(encoding='utf-8'))['config']
    values['nodes'] = tuple(values['nodes'])
    return Config(**values)


def variant_configs(base: Config) -> dict[str, Config]:
    return {'M1': base, 'S10': replace(base, scenarios=10), 'S30': replace(base, scenarios=30),
        'tail0': replace(base, tail=0), 'tail4': replace(base, tail=4),
        'terminal08': replace(base, terminal_scale=.8), 'terminal12': replace(base, terminal_scale=1.2),
        'pchip': replace(base, interpolation='pchip'), 'lag': replace(base, feedback='lag'),
        'sequential': replace(base, settlement='sequential')}


def audit_main(data: Inputs, main_run: Path, output: Path) -> pd.DataFrame:
    """读取一次已提交日收据，未完成的节点/日不纳入正式审计。"""
    main = main_run/'main'; state_path = main/'state.json'
    if not state_path.exists():
        return pd.DataFrame()
    state = json.loads(state_path.read_text(encoding='utf-8'))
    if [item['day'] for item in state['days']]!=list(range(len(state['days']))):
        raise ValueError('主轨迹提交日期不是从1月1日起的连续前缀')
    metrics = {name: 0. for name in ('能量平衡最大残差', 'SOC递推最大残差', 'SOC越界次数', '功率越界次数',
        '同时充放电次数', '跨日SOC最大残差', '费用重算最大残差', '场景权重异常次数',
        '未来历史轨迹次数', '负荷预测器不一致次数', '已执行购电与节点策略最大残差', '来源数据最大残差', '未达求解精度节点数')}
    n, previous = 0, None
    for receipt in state['days']:
        d = int(receipt['day']); date = str(date_of(d).date())
        paths = {'dispatch': main/f'days/{date}.csv', 'audit': main/f'audit/{date}.json', 'information': main/f'information/{date}.json'}
        if any(hashlib.sha256(path.read_bytes()).hexdigest() != receipt['hashes'][key] for key, path in paths.items()):
            raise ValueError(f'主结果已提交文件摘要不符：{date}')
        frame = pd.read_csv(paths['dispatch'], float_precision='round_trip')
        expected=date_of(d)+pd.to_timedelta((np.arange(144)+1)*10,unit='min')
        if len(frame)!=144 or not np.array_equal(pd.to_datetime(frame.timestamp).to_numpy(),expected.to_numpy()):
            raise ValueError('主轨迹日期或144时段不完整')
        if d < 31:
            previous = float(frame.soc.iloc[-1]); continue
        n += 1
        c, r, q, u, e = [frame[key].to_numpy() for key in ('charge', 'discharge', 'emergency', 'spill', 'soc')]
        initial = float(frame.initial_soc.iloc[0]); net = frame.net_kwh.to_numpy(); g = frame.grid.to_numpy(); price = frame.price.to_numpy()
        metrics['能量平衡最大残差'] = max(metrics['能量平衡最大残差'], float(np.max(abs(g+r+q-net-c-u))))
        metrics['SOC递推最大残差'] = max(metrics['SOC递推最大残差'], float(np.max(abs(e-np.r_[initial, e[:-1]]-ETA*c+r/ETA))))
        metrics['SOC越界次数'] += int(((e < E_MIN-TOL)|(e > E_MAX+TOL)).sum())
        metrics['功率越界次数'] += int(((c < -TOL)|(r < -TOL)|(c > CAP+TOL)|(r > CAP+TOL)).sum())
        metrics['同时充放电次数'] += int(((c > TOL)&(r > TOL)).sum())
        if previous is not None: metrics['跨日SOC最大残差'] = max(metrics['跨日SOC最大残差'], abs(initial-previous))
        previous = float(e[-1])
        expected = frame.g0.to_numpy()*price+adjustment(g, frame.g0.to_numpy(), price)+5*price*q
        metrics['费用重算最大残差'] = max(metrics['费用重算最大残差'], float(np.max(abs(expected-frame.total_cost.to_numpy()))))
        metrics['来源数据最大残差'] = max(metrics['来源数据最大残差'], float(np.max(abs(frame[['load_kw', 'pv_kw']].to_numpy()-data.actual[d]))))
        audit = json.loads(paths['audit'].read_text(encoding='utf-8'))
        if [node['hour'] for node in audit['nodes']]!=[0,6,12,18]:
            raise ValueError('主轨迹缺少四信息节点')
        np.testing.assert_allclose(frame.g0,np.array(audit['nodes'][0]['grid']),atol=TOL,rtol=0)
        for node in audit['nodes']:
            hour = node['hour']; scenes = node['scenarios']; weights = np.array(scenes.get('weights', [1.]))
            metrics['场景权重异常次数'] += int((weights < 0).any() or not np.isclose(weights.sum(), 1., atol=1e-12, rtol=0))
            metrics['未来历史轨迹次数'] += sum(j >= d or j*144+hour*6+144 > d*144+hour*6 for j in scenes['history_days'])
            metrics['负荷预测器不一致次数'] += int(scenes['predictor'] != data.selected[d])
            metrics['未达求解精度节点数'] += int(not node['solver']['reliable'])
            metrics['已执行购电与节点策略最大残差'] = max(metrics['已执行购电与节点策略最大残差'],
                float(np.max(abs(g[hour*6:hour*6+36]-np.array(node['grid'][:36])))))
    result = pd.DataFrame([{'check': key, 'value': value if n else None,
        'status': '待正式数据' if n == 0 else '通过' if value <= (0 if '次数' in key or '节点数' in key else TOL) else '未通过',
        'formal_days_checked': n, 'scope': 'full_334_days' if n == 334 else 'committed_prefix_only',
        'tolerance': 0 if '次数' in key or '节点数' in key else TOL} for key, value in metrics.items()])
    write_csv(output/'audit_table.csv', result)
    write_json(output/'audit_receipt.json', {'committed_days': len(state['days']), 'formal_days': n,
        'input_manifest': data.provenance['files'], 'model_parameters_not_retuned': True,
        'historical_load_errors': 'inherited_Q2_rolling_origin_library; source/code tests accompany numeric audit',
        'time_resolution': '10min aggregate causal feedback, not claimed as observed sub10min control'})
    return result


def rollout_job(request: tuple) -> dict:
    data, cfg, path, dates, initials, scope, with_fiv = request
    signature = cfg.signature(); complete = path/'validation_complete.json'
    if complete.exists():
        saved = json.loads(complete.read_text(encoding='utf-8'))
        if saved['signature'] != signature or saved['scope'] != scope:
            raise ValueError('检验分支的已有收据与配置/范围不同')
        for file, digest in saved['files'].items():
            if hashlib.sha256((path/file).read_bytes()).hexdigest() != digest: raise ValueError('检验结果摘要损坏')
        return {'path': str(path), 'status': 'complete', 'reused': True}
    if scope == 'full':
        frame = run_period(data, cfg, path, workers=1, with_fiv=with_fiv, max_slices=None)
    else:
        terminal = TerminalValues(data, cfg, cache_path=path/'terminal_cache.json'); pieces = []
        for date in dates:
            d = (pd.Timestamp(date)-pd.Timestamp('2025-01-01')).days
            daily, audit, info = run_day(data, terminal, d, initials[date], cfg, with_fiv=with_fiv,
                checkpoint_root=path/'nodes'/date, require=False, max_slices=1)
            write_csv(path/f'days/{date}.csv', daily); write_json(path/f'audit/{date}.json', audit)
            write_json(path/f'information/{date}.json', info); pieces.append(daily)
        frame = pd.concat(pieces, ignore_index=True); write_csv(path/'dispatch.csv', frame)
    write_csv(path/'daily.csv', summaries(frame)[0])
    names=['dispatch.csv','daily.csv']+[f'{kind}/{date}.json' for kind in ('audit','information') for date in dates]
    write_json(complete, {'signature': signature, 'scope': scope, 'dates': list(dates),
                         'files': {name: hashlib.sha256((path/name).read_bytes()).hexdigest() for name in names}})
    return {'path': str(path), 'status': 'complete', 'reused': False}


def base_fiv_job(request: tuple) -> dict:
    data, cfg, main, output, dates, scope = request
    for date in dates:
        terminal = TerminalValues(data, cfg, cache_path=output/'nodes'/date/'terminal_cache.json')
        done = output/f'information/{date}.json'
        receipt=output/f'receipts/{date}.json'
        if done.exists() and receipt.exists():
            saved=json.loads(receipt.read_text(encoding='utf-8'))
            if saved['signature']!=cfg.signature() or saved['sha256']!=hashlib.sha256(done.read_bytes()).hexdigest():
                raise ValueError('已有FIV日期收据与结果不匹配')
            rows=json.loads(done.read_text(encoding='utf-8'))
            if scope!='full' or all(branch['solver']['reliable'] for row in rows for branch in row['audits']): continue
        d = (pd.Timestamp(date)-pd.Timestamp('2025-01-01')).days
        audit = json.loads((main/f'audit/{date}.json').read_text(encoding='utf-8'))
        grid = np.array(audit['nodes'][0]['grid']); rows = []
        for node in audit['nodes'][1:]:
            hour = node['hour']
            row, branches = fiv(data, terminal, d, hour, node['initial_soc'], grid[hour*6:], cfg,
                checkpoint_root=output/'nodes'/date/str(hour), require=scope == 'full',
                max_slices=None if scope == 'full' else 1)
            write_json(output/f'branches/{date}_{hour}.json', branches); rows.append(row)
        write_json(done, rows)
        write_json(receipt,{'signature':cfg.signature(),'sha256':hashlib.sha256(done.read_bytes()).hexdigest()})
    return {'path': str(output), 'status': 'complete'}


def metric_tables(data: Inputs, main: Path, output: Path, variants: dict[str, Config], dates: list[str], scope: str) -> None:
    economics, sensitivity, model_comparison = [], [], []
    errors = pd.read_csv(output/'forecast/forecast_revision_pairs.csv')
    mae = errors[errors.date.isin(dates)&errors.block].groupby('hour')[['old_absolute_error','new_absolute_error']].mean()
    base_dispatch = pd.read_csv(main/'dispatch.csv')
    base_dispatch = base_dispatch[base_dispatch.date.isin(dates)]
    base_daily = summaries(base_dispatch)[0].set_index('date')
    for label, cfg in variants.items():
        paths = {key: output/'rollouts'/label/key for key in NODE_SETS}
        costs = {}
        for key, path in paths.items():
            frame = base_dispatch if label == 'M1' and key == 'K061218' else pd.read_csv(path/'dispatch.csv')
            costs[key] = frame.groupby('date').total_cost.sum().reindex(dates)
        info_dir = output/'base_fiv/information' if label == 'M1' else paths['K061218']/'information'
        info = [row for date in dates for row in json.loads((info_dir/f'{date}.json').read_text(encoding='utf-8'))]
        for hour, old, new in ((6, 'K0', 'K06'), (12, 'K06', 'K0612'), (18, 'K0612', 'K061218')):
            values = np.array([row['FIV_block'] for row in info if row['hour'] == hour])
            op = (costs[old]-costs[new]).to_numpy()
            if len(values) != len(dates) or not np.isfinite(op).all(): raise ValueError('FIV/OUV配对日期不完整')
            records = [row for row in info if row['hour'] == hour]
            reliable = all(branch['solver']['reliable'] for row in records for branch in row['audits'])
            ouv_reliable = True
            for key in (old, new):
                for date in dates:
                    audit_path = main/f'audit/{date}.json' if label=='M1' and key=='K061218' else paths[key]/f'audit/{date}.json'
                    node_audit = json.loads(audit_path.read_text(encoding='utf-8'))
                    ouv_reliable &= all(node['solver']['reliable'] for node in node_audit['nodes'])
            economics.append({'variant': label, 'hour': hour, 'scope': scope, 'days': len(dates),
                'old_MAE': mae.loc[hour, 'old_absolute_error'], 'new_MAE': mae.loc[hour, 'new_absolute_error'],
                'FIV_sum': float(values.sum()), 'FIV_median': float(np.median(values)), 'FIV_positive_fraction': float((values > 0).mean()),
                'OUV_sum': float(op.sum()), 'OUV_median': float(np.median(op)), 'OUV_positive_fraction': float((op > 0).mean()),
                'FIV18_day': sum(row['FIV_day'] for row in records) if hour == 18 else None,
                'FIV18_cont': sum(row['FIV_cont'] for row in records if row['FIV_cont'] is not None) if hour == 18 else None,
                'cross_day_valid_dates': sum(row['comparison_complete'] for row in records), 'all_FIV_solves_certified': reliable,
                'all_OUV_solves_certified': bool(ouv_reliable),
                'interpretation': '求解未全部达标，暂不作结论' if not (reliable and ouv_reliable) else '本范围内FIV与OUV均为正' if values.sum()>0 and op.sum()>0 else '本范围内收益有限或符号不一致'})
        full = base_dispatch if label == 'M1' else pd.read_csv(paths['K061218']/'dispatch.csv')
        day = summaries(full)[0].set_index('date').reindex(dates)
        terminal_socs, gaps, seconds, tail_retained = [], [], [], []
        for date in dates:
            d = (pd.Timestamp(date)-pd.Timestamp('2025-01-01')).days
            audit_path = main/f'audit/{date}.json' if label == 'M1' else paths['K061218']/f'audit/{date}.json'
            audit = json.loads(audit_path.read_text(encoding='utf-8'))
            for node in audit['nodes']:
                hour = node['hour']; scenes = construct(data, d, hour, cfg)
                if scenes.audit['history_days'] != node['scenarios']['history_days']: raise ValueError('回读场景与原节点不一致')
                policy = Policy(*(np.array(node[key]) for key in ('grid', 'charge_cap', 'discharge_cap')))
                previous = float((data.actual.reshape(-1, 2)[d*144+hour*6-1, 0]-data.actual.reshape(-1, 2)[d*144+hour*6-1, 1])*DT)
                e = [replay(policy, n, node['initial_soc'], mode=cfg.feedback, previous_net=previous)['soc'][-1] for n in scenes.net]
                terminal_socs.append(float(scenes.weights@e)); gaps.append(node['solver']['gap']); seconds.append(node['solver']['seconds'])
                ids, el, ep, scales = data.history(d, hour, data.selected[d], method=cfg.interpolation)
                indices, _ = pool_indices(ids, scales, d, data.pv(d, hour, cfg.interpolation).sum()*DT, cfg)
                risk = np.maximum(el[indices]-ep[indices], 0)@data.prices[(hour*6+np.arange(144))%144]*DT
                top = ids[indices[np.argsort(-risk, kind='stable')[:min(2, len(indices))]]]
                tail_retained.append(float(np.mean(np.isin(top, scenes.audit['history_days']))))
        aligned = full[full.slot<36].merge(base_dispatch[base_dispatch.slot<36], on=['date','slot'], suffixes=('_v','_base'))
        sensitivity.append({'variant': label, 'scope': scope, 'days': len(dates), 'total_cost': float(day.total_cost.sum()),
            'cost_change_pct': float((day.total_cost.sum()/base_daily.total_cost.sum()-1)*100),
            'emergency_kwh': float(day.emergency.sum()), 'emergency_cost': float(day.emergency_cost.sum()),
            'emergency_change_kwh': float(day.emergency.sum()-base_daily.emergency.sum()),
            'emergency_change_pct': float((day.emergency.sum()/base_daily.emergency.sum()-1)*100) if base_daily.emergency.sum() else None,
            'adjustment_cost': float(day.adjustment_cost.sum()), 'throughput': float(day.throughput.sum()),
            'first_block_grid_L1': float((aligned.grid_v-aligned.grid_base).abs().sum()),
            'mean_window_terminal_soc': float(np.mean(terminal_socs)), 'top2_risk_retained_fraction': float(np.mean(tail_retained)),
            'solver_seconds': float(sum(seconds)), 'max_solver_gap': float(max(gaps)),
            'all_nodes_certified': all(gap <= cfg.gap+1e-8 for gap in gaps)})
    eco = pd.DataFrame(economics)
    for metric in ('FIV_sum', 'OUV_sum'):
        eco[metric+'_rank'] = eco.groupby('variant')[metric].rank(ascending=False, method='min')
    write_csv(output/'information_value.csv', eco); write_csv(output/'sensitivity.csv', pd.DataFrame(sensitivity))
    m0 = pd.read_csv(output/'rollouts/M0/K061218/dispatch.csv'); m0 = m0[m0.date.isin(dates)]
    daily0 = summaries(m0)[0].set_index('date').reindex(dates)
    for label, day in (('M0', daily0), ('M1', base_daily)):
        model_comparison.append({'model': label, 'scope': scope, 'days': len(dates),
            **{key: float(day[key].sum()) for key in ('total_cost','planned_cost','adjustment_cost','emergency_cost','emergency','throughput')},
            'emergency_slot_rate': float(day.emergency_slots.sum()/(len(dates)*144)),
            'cost_improvement_pct_vs_M0': float((daily0.total_cost.sum()-day.total_cost.sum())/daily0.total_cost.sum()*100)})
    difference = (daily0.total_cost-base_daily.total_cost).to_numpy()
    write_csv(output/'M0_M1_comparison.csv', pd.DataFrame(model_comparison))
    write_csv(output/'M0_M1_daily_pairs.csv', pd.DataFrame({'date': dates,'saving_M1':difference}))
    write_json(output/'M0_M1_paired_statistics.json', paired_summary(difference))
    write_csv(output/'M0_M1_daily_SOC.csv',pd.DataFrame({'date':dates,
        'M0_initial_soc':daily0.soc_start.to_numpy(),'M1_initial_soc':base_daily.soc_start.to_numpy(),
        'M0_end_soc':daily0.soc_end.to_numpy(),'M1_end_soc':base_daily.soc_end.to_numpy()}))


def benchmark_job(request: tuple) -> dict:
    from .multistage import tree_inputs, solve_tree, replay_tree
    data, cfg, main, output, day, regime = request
    date = str(date_of(day).date()); path = output/date
    receipt = path/'complete.json'
    if receipt.exists():
        saved = json.loads(receipt.read_text(encoding='utf-8'))
        if saved['signature'] != cfg.signature(): raise ValueError('M2已有结果配置不同')
        if any(hashlib.sha256((path/name).read_bytes()).hexdigest()!=sha for name,sha in saved['files'].items()):
            raise ValueError('M2切片输出损坏或缺失')
        return saved['result']
    original = pd.read_csv(main/f'days/{date}.csv'); initial = float(original.initial_soc.iloc[0])
    net, labels, nodes, audit = tree_inputs(data, day, cfg)
    terminal = TerminalValues(data, cfg, cache_path=path/'terminal_cache.json')
    coefficient, calibration = terminal.value(day, 0)
    # 每个M2日期为一个有界求解切片；开始前保留实际输入和可行初始策略，结束后保存完整节点策略。
    write_csv(path/'scenario_input.csv', pd.DataFrame({'scenario':np.repeat(np.arange(len(net)),144),
        'slot':np.tile(np.arange(144),len(net)), 'net_kwh':net.ravel()}))
    seed = np.maximum(net.max(0), 0)
    write_json(path/'initial_checkpoint.json', {'signature':cfg.signature(), 'initial_soc':initial,
        'grid':seed.tolist(), 'charge_cap':0., 'discharge_cap':0., 'slice_seconds':cfg.seconds,
        'objective':float(data.prices@seed-coefficient*initial), 'lower_bound':-coefficient*E_MAX,
        'tree':nodes,'labels':labels.tolist(),'calibration':calibration,'source':audit})
    solved = solve_tree(net, labels, nodes, np.array(audit['load_upper']), data.prices, initial, coefficient, cfg, require=False)
    write_json(path/'solver.json', solved['audit'])
    if 'policies' not in solved:
        result = {'date':date,'regime':regime,'status':'no_feasible_solution','M1_cost':float(original.total_cost.sum()),
                  'M2_cost':None,'relative_loss':None,'gap':None,'certified':False}
    else:
        frame = replay_tree(data, day, initial, nodes, solved, cfg)
        write_csv(path/'dispatch.csv', frame)
        write_json(path/'policies.json', {'g0':solved['g0'].tolist(), 'policies':{str(k):{field:getattr(policy,field).tolist()
            for field in ('grid','charge_cap','discharge_cap')} for k,policy in solved['policies'].items()}})
        cost = float(frame.total_cost.sum())
        result = {'date':date,'regime':regime,'status':solved['audit']['status'],'M1_cost':float(original.total_cost.sum()),
                  'M2_cost':cost,'relative_loss':float((original.total_cost.sum()-cost)/cost),
                  'gap':solved['audit']['gap'],'certified':solved['audit']['reliable']}
    files=['initial_checkpoint.json','scenario_input.csv','solver.json']
    if 'policies' in solved: files += ['dispatch.csv','policies.json']
    write_json(receipt, {'signature':cfg.signature(), 'result':result,
        'files':{name:hashlib.sha256((path/name).read_bytes()).hexdigest() for name in files}})
    return result


def plan_jobs(data: Inputs, base: Config, main: Path, output: Path, dates: list[str], scope: str) -> list[tuple]:
    initial = {date:float(pd.read_csv(main/f'days/{date}.csv').initial_soc.iloc[0]) for date in dates}
    jobs = []
    for label, cfg in variant_configs(base).items():
        for key, nodes in NODE_SETS.items():
            if label == 'M1' and key == 'K061218': continue
            jobs.append((data, replace(cfg,nodes=nodes), output/'rollouts'/label/key, dates, initial, scope, key=='K061218'))
    jobs.insert(3, (data, replace(base,deterministic=True), output/'rollouts/M0/K061218', dates, initial, scope, False))
    return jobs


def render_status(output: Path, status: dict) -> None:
    write_json(output/'status.json', status)
    body='<!doctype html><html lang="zh"><meta charset="utf-8"><meta http-equiv="refresh" content="30"><meta name="viewport" content="width=device-width,initial-scale=1"><title>第三问独立检验</title><style>body{font:17px/1.7 -apple-system,sans-serif;max-width:980px;margin:40px auto;padding:0 20px;color:#263b50}table{border-collapse:collapse}td,th{padding:7px;border-bottom:1px solid #ccd6df}.table{overflow:auto}</style><h1>第三问独立检验</h1>'
    body+=f'<p>阶段：{status["phase"]}；检验范围：{status.get("scope","待确认")}；主计算独立运行，检验不作为主表导出的前置条件。</p>'
    if (output/'audit_table.csv').exists():
        body+='<h2>已提交主结果审计</h2><div class="table">'+pd.read_csv(output/'audit_table.csv').to_html(index=False)+'</div>'
    body+='<p>优先顺序：正确性审计 → 预测误差/FIV/OUV → M0/M1 → 六组核心敏感性 → 4—8日M2 → 紧凑假设对照。所有统计按实际范围标注，不预设M1或M2一定更优。</p>'
    body+='<p><a href="forecast/figures/forecast_error_heatmaps.png">预报误差图</a> · <a href="audit_table.csv">审计表</a> · <a href="plan.json">检验计划</a> · <a href="status.json">状态</a></p></html>'
    (output/'report.html').write_text(body, encoding='utf-8')


def execute(data: Inputs, main_run: Path, output: Path, scope: str, workers: int) -> None:
    base = load_config(main_run); main = main_run/'main'
    state=json.loads((main/'state.json').read_text(encoding='utf-8'))
    if state['sources']!=hashlib.sha256(json.dumps(data.provenance,sort_keys=True).encode('utf-8')).hexdigest():
        raise ValueError('检验与正式主轨迹的原始输入/预测来源不一致')
    checks=audit_main(data,main_run,output)
    if (checks.status=='未通过').any() or not (checks.formal_days_checked==334).all():
        raise ValueError('正式主结果审计未全部通过，暂停生成经济结论；不改写主计算')
    frame = pd.read_csv(main/'dispatch.csv')
    dates = sorted(frame.date.unique().tolist()) if scope=='full' else list(DATES)
    variants = variant_configs(base)
    jobs = plan_jobs(data, base, main, output, dates, scope)
    write_json(output/'plan.json', {'scope':scope,'dates':dates,'model':'frozen_M1_not_retuned','gap':base.gap,
        'variants':list(variants),'rollout_jobs':len(jobs),'reuse_M1':True,'M2_days_range':[4,8],
        'spec_sha256':hashlib.sha256(SPEC.read_bytes()).hexdigest(),'original_main_sources':str(main_run/'runtime_sources.json')})
    # 最高优先的信息价值先做；基准M1不重求，仅用已提交节点状态构造反事实。
    render_status(output, {'phase':'base_FIV','scope':scope})
    with process_pool(workers, base.solver_threads) as pool:
        requests = [(data,base,main,output/'base_fiv',[date],scope) for date in dates]
        completed = list(pool.map(base_fiv_job,requests)) if pool else list(map(base_fiv_job,requests))
        write_json(output/'base_FIV_jobs.json',completed)
    # 三条更新时间链和M0先于敏感性；所有任务与主进程分组/输出隔离。
    with process_pool(workers, base.solver_threads) as pool:
        render_status(output, {'phase':'OUV_and_M0','scope':scope})
        leading = list(pool.map(rollout_job,jobs[:4])) if pool else list(map(rollout_job,jobs[:4]))
        write_json(output/'leading_jobs.json',leading)
        metric_tables(data, main, output, {'M1':base}, dates, scope)
        render_status(output, {'phase':'core_sensitivity','scope':scope})
        results = list(pool.map(rollout_job,jobs[4:28])) if pool else list(map(rollout_job,jobs[4:28]))
        write_json(output/'core_jobs.json',results)
    selection = stress_dates(data, frame)
    chosen = selection.groupby('day',sort=True).stratum.apply(lambda s:';'.join(s)).to_dict()
    for date in DATES:
        if len(chosen)>=4: break
        chosen[(pd.Timestamp(date)-pd.Timestamp('2025-01-01')).days]='fixed_calendar_supplement'
    chosen = dict(list(chosen.items())[:8]); write_json(output/'M2_selection.json', {str(k):v for k,v in chosen.items()})
    render_status(output, {'phase':'M2_benchmark','scope':scope})
    requests=[(data,base,main,output/'M2',int(day),regime) for day,regime in chosen.items()]
    with process_pool(workers,base.solver_threads) as pool:
        records=list(pool.map(benchmark_job,requests)) if pool else list(map(benchmark_job,requests))
    write_csv(output/'M2_comparison.csv',pd.DataFrame(records))
    values=np.array([row['relative_loss'] for row in records if row['relative_loss'] is not None])
    write_json(output/'M2_summary.json',{'days':len(records),'median_relative_loss':float(np.median(values)) if len(values) else None,
        'max_absolute_relative_loss':float(np.max(abs(values))) if len(values) else None,
        'all_certified':all(row['certified'] for row in records),'scope':'stratified_stress_sample_not_unbiased_annual_estimate'})
    render_status(output, {'phase':'assumption_robustness','scope':scope})
    with process_pool(workers, base.solver_threads) as pool:
        records = list(pool.map(rollout_job,jobs[28:])) if pool else list(map(rollout_job,jobs[28:]))
        write_json(output/'assumption_jobs.json',records)
    metric_tables(data, main, output, variants, dates, scope)
    audit_main(data,main_run,output)
    render_status(output, {'phase':'complete','scope':scope,'main_not_modified':True})


def main() -> None:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--main-run',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--scope',choices=['sampled','full','pending'],default='pending')
    parser.add_argument('--workers',type=int,default=2)
    args=parser.parse_args();limit_native_libraries();os.nice(10)
    output=args.output.resolve();main_run=args.main_run.resolve();output.mkdir(parents=True,exist_ok=True)
    with run_lock(output/'validation.lock'):
        request=output/'request.json'
        if not request.exists():write_json(request,{'scope':args.scope,'workers':args.workers})
        data=read_inputs(ROOT/'outputs/q2/dispatch_runs/20260911_224501',output/'prepared')
        forecast_diagnostics(data,output/'forecast')
        last_days=-1
        while True:
            settings=json.loads(request.read_text(encoding='utf-8'));scope=settings['scope']
            state_path=main_run/'main/state.json'
            days=len(json.loads(state_path.read_text(encoding='utf-8')).get('days',[])) if state_path.exists() else 0
            if days!=last_days:
                audit_main(data,main_run,output);last_days=days
            ready=(main_run/'main_complete.json').exists()
            render_status(output,{'phase':'waiting_scope' if scope=='pending' else 'waiting_main' if not ready else 'preparing',
                                  'scope':scope,'committed_main_days':days})
            if ready and scope in ('sampled','full'):break
            time.sleep(30)
        caffeine=subprocess.Popen(['caffeinate','-i','-w',str(os.getpid())]) if sys.platform=='darwin' else None
        try:
            execute(data,main_run,output,scope,int(settings['workers']))
        except Exception as error:
            render_status(output,{'phase':'failed_resume_available','scope':scope,'error':str(error)})
            raise
        finally:
            if caffeine is not None:
                caffeine.terminate();caffeine.wait()


if __name__=='__main__':
    main()
