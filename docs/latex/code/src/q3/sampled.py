"""用户授权的少量日期/取值辅助表；不再启动全年对照轨迹。"""
from dataclasses import replace
import json
import hashlib
from pathlib import Path
import numpy as np
import pandas as pd
from .config import Config, write_json, write_csv
from .data import Inputs
from .rolling import run_day, fiv, date_of
from .terminal import TerminalValues
from .parallel import process_pool
from .export import summaries

DATES = ('2025-03-20', '2025-06-21', '2025-09-23', '2025-12-21')


def sample_configs(base: Config) -> dict[str, Config]:
    return {'S10': replace(base, scenarios=10), 'S30': replace(base, scenarios=30),
            'terminal08': replace(base, terminal_scale=.8), 'terminal12': replace(base, terminal_scale=1.2),
            'M0': replace(base, deterministic=True), 'K0': replace(base, nodes=(0,)),
            'K06': replace(base, nodes=(0, 6)), 'K0612': replace(base, nodes=(0, 6, 12))}


def sample_job(request: tuple) -> dict:
    data, config, day, initial, label, output, main_directory = request
    signature = config.signature()
    receipt = output/'complete.json'
    if receipt.exists():
        saved = json.loads(receipt.read_text(encoding='utf-8'))
        if saved['signature'] != signature:
            raise ValueError('抽样任务已有收据与当前配置/源码不同')
        if any(hashlib.sha256((output/name).read_bytes()).hexdigest() != sha for name, sha in saved['hashes'].items()):
            raise ValueError('抽样任务结果文件损坏或缺失')
        return saved['result']
    terminal = TerminalValues(data, config, cache_path=output/'terminal_cache.json')
    if label == 'FIV':
        audit = json.loads((main_directory/f'audit/{date_of(day).date()}.json').read_text(encoding='utf-8'))
        original = np.array(audit['nodes'][0]['grid'])
        rows = []
        for node in audit['nodes'][1:]:
            hour = node['hour']
            part = output/f'FIV_{hour:02d}.json'
            if part.exists():
                saved = json.loads(part.read_text(encoding='utf-8'))
                if saved['signature'] != signature:
                    raise ValueError('已保存FIV分片配置不同')
                row = saved['row']
            else:
                row, branches = fiv(data, terminal, day, hour, node['initial_soc'], original[hour*6:], config,
                                   checkpoint_root=output/f'{hour:02d}', require=False)
                row['sample_scope'] = 'four_predeclared_dates_only'
                write_json(part, {'signature': signature, 'row': row, 'branches': branches})
            rows.append(row)
        result = {'date': str(date_of(day).date()), 'variant': label, 'FIV': rows}
    else:
        frame, audit, _ = run_day(data, terminal, day, initial, config, checkpoint_root=output/'nodes',
                                   max_slices=1, require=False)
        write_csv(output/'dispatch.csv', frame); write_json(output/'audit.json', audit)
        summary = summaries(frame)[0].iloc[0].to_dict()
        result = {**summary, 'variant': label, 'sample_scope': 'single_day_same_main_initial_SOC',
                  'certified_all_nodes': all(node['solver']['reliable'] for node in audit['nodes']),
                  'max_solver_gap': max(node['solver']['gap'] for node in audit['nodes']),
                  'nodes_count': len(audit['nodes'])}
    names = [f'FIV_{hour:02d}.json' for hour in (6, 12, 18)] if label == 'FIV' else ['dispatch.csv', 'audit.json']
    write_json(receipt, {'signature': signature, 'result': result,
                         'hashes': {name: hashlib.sha256((output/name).read_bytes()).hexdigest() for name in names}})
    return result


def run_samples(data: Inputs, base: Config, main: pd.DataFrame, output: Path, main_directory: Path,
                workers: int) -> None:
    output.mkdir(parents=True, exist_ok=True)
    rows, jobs = [], []
    for date in DATES:
        day = (pd.Timestamp(date)-pd.Timestamp('2025-01-01')).days
        frame = main[pd.to_datetime(main.date) == pd.Timestamp(date)]
        if len(frame) != 144:
            raise ValueError('主结果尚未完整，不能先抢算抽样对照')
        initial = float(frame.initial_soc.iloc[0])
        summary = summaries(frame)[0].iloc[0].to_dict()
        main_audit = json.loads((main_directory/f'audit/{date}.json').read_text(encoding='utf-8'))
        rows.append({**summary, 'variant': 'M1', 'sample_scope': 'single_day_same_main_initial_SOC',
                     'certified_all_nodes': all(node['solver']['reliable'] for node in main_audit['nodes']),
                     'max_solver_gap': max(node['solver']['gap'] for node in main_audit['nodes']), 'nodes_count': 4})
        for label, config in {**sample_configs(base), 'FIV': base}.items():
            jobs.append((data, config, day, initial, label, output/date/label, main_directory))
    write_json(output/'design.json', {'dates': list(DATES), 'variants': list(sample_configs(base)),
        'jobs': len(jobs), 'annual_comparators': False, 'selection_uses_observed_results': False,
        'authority': '用户2026-09-12要求辅助实验只取少量值做表，优先全年主计算',
        'each_auxiliary_solve_slices': 1, 'slice_seconds': base.seconds,
        'interpretation': '限时可行解可列真实费用及gap，不冒充已达标最优或全年稳健结论'})
    information = []
    with process_pool(workers, base.solver_threads) as executor:
        iterator = executor.map(sample_job, jobs) if executor else map(sample_job, jobs)
        for result in iterator:
            if result['variant'] == 'FIV':
                information.extend(result['FIV'])
            else:
                rows.append(result)
            write_csv(output/'sensitivity_table.csv', pd.DataFrame(rows))
            write_json(output/'FIV_samples.json', information)
    frame = pd.DataFrame(rows)
    differences = []
    for date in DATES:
        costs = frame[frame.date == date].set_index('variant').total_cost
        differences.extend({'date': date, 'hour': hour, 'sample_OUV': float(costs[old]-costs[new]),
             'scope': 'single_day_same_initial_state_not_annual_OUV'}
            for hour, old, new in ((6, 'K0', 'K06'), (12, 'K06', 'K0612'), (18, 'K0612', 'M1')))
    write_csv(output/'OUV_samples.csv', pd.DataFrame(differences))
    write_csv(output/'FIV_samples.csv', pd.DataFrame([{key: row[key] for key in
        ('date', 'hour', 'FIV_block', 'FIV_day', 'FIV_cmp', 'FIV_cont', 'comparison_complete')} for row in information]))
    write_json(output/'all_complete.json', {'dates': list(DATES), 'rows': len(rows), 'FIV_rows': len(information),
                                          'annual_conclusion_claimed': False})
