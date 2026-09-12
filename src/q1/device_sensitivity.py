"""论文设备敏感性：每个参数点重求原MILP，保存CSV与压缩原始解。"""
import hashlib
import json
from pathlib import Path
import shutil
import tempfile

import numpy as np

from src.q1.model import ROOT, COST_TOL_YUAN, check_solution, solve, write_csv, write_json

# 明示的数值实验范围；仅改变指定边界，不推断实际扩容或投资回报。
ENERGY_GRID = list(range(6000, 30001, 2400))
POWER_GRID = list(range(1000, 10001, 1000))
POWER_SWEEP = list(range(0, 10001, 1000))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare(data, generation):
    sources = {str(p.relative_to(ROOT)): digest(p) for p in
               [Path(__file__), ROOT / 'src/q1/model.py', generation / 'inputs/processed/timeseries.csv']}
    key = hashlib.sha256(json.dumps(sources, sort_keys=True).encode('utf-8')).hexdigest()[:12]
    parent = ROOT / 'outputs/q1/figure_analysis'
    parent.mkdir(parents=True, exist_ok=True)
    target = parent / key
    if target.exists():
        manifest = json.loads((target / 'manifest.json').read_text(encoding='utf-8'))
        if not manifest['passed'] or any(digest(target / p) != h for p, h in manifest['output_sha256'].items()):
            raise ValueError('设备敏感性缓存校验失败')
        verify(data, target)
        return target
    staging = Path(tempfile.mkdtemp(prefix='.pending-', dir=parent))
    try:
        solutions, metadata, sweeps, grid = {}, [], [], []

        def point(emax, charge, discharge):
            name = f'E{emax}_C{charge}_D{discharge}'
            if name not in solutions:
                solution = solve(data, .9, e_max=emax, charge_kw=charge, discharge_kw=discharge)
                checked = check_solution(data, solution)
                solutions[name] = solution
                metadata.append({'point': name, 'e_max_kwh': emax, 'charge_kw': charge,
                                 'discharge_kw': discharge, 'cost_yuan': solution['solver']['objective_yuan'],
                                 'dual_bound_yuan': solution['solver']['dual_bound_yuan'],
                                 'mip_gap': solution['solver']['mip_gap'], 'status': solution['solver']['status'],
                                 'max_physical_residual_kwh': max(v for k, v in checked['metrics'].items() if k.endswith('_kwh'))})
                if len(solutions) % 20 == 0:
                    print(f'设备敏感性：已求解并验收 {len(solutions)} 个不同参数点', flush=True)
            return {'point': name, 'cost_yuan': solutions[name]['solver']['objective_yuan']}

        for power in POWER_GRID:
            for energy in ENERGY_GRID:
                grid.append({'e_max_kwh': energy, 'common_power_kw': power, **point(energy, power, power)})
        for resource, values in [('e_max', sorted([*ENERGY_GRID, 10900])),
                                  ('charge_kw', sorted([*POWER_SWEEP, 5100])),
                                  ('discharge_kw', sorted([*POWER_SWEEP, 5100]))]:
            for value in values:
                settings = {'e_max': 10800, 'charge_kw': 5000, 'discharge_kw': 5000, resource: value}
                sweeps.append({'resource': resource, 'limit': value,
                               **point(settings['e_max'], settings['charge_kw'], settings['discharge_kw'])})
        base = solutions['E10800_C5000_D5000']['solver']['objective_yuan']
        original = json.loads((generation / 'raw/solution_main.json').read_text(encoding='utf-8'))
        if abs(base - original['solver']['objective_yuan']) > COST_TOL_YUAN:
            raise ValueError('敏感性基准与已验收主目标不一致')
        for row in [*grid, *sweeps]:
            row['saving_from_base_yuan'] = base - row['cost_yuan']
        write_csv(staging / 'joint_grid.csv', grid)
        write_csv(staging / 'one_dimensional.csv', sweeps)
        write_csv(staging / 'solver_checks.csv', metadata)
        np.savez_compressed(staging / 'solutions.npz', **{
            key: np.asarray([s[k] for k in ('G', 'C', 'D', 'E', 'W', 'u')]) for key, s in solutions.items()})
        verification = verify(data, staging)
        write_json(staging / 'manifest.json', {
            'passed': True, 'source_sha256': sources, 'generation': generation.name,
            'assumptions': ['双单程效率0.9；Emin=1200；E0=E144=6000；其余模型与输入不变',
                            'Emax是储电上限；超过原额定容量的点仅为数学约束放宽实验，不能直接作为设备设计',
                            '二维纵轴同时改变充放电功率；一维功率曲线只改变一种功率',
                            '等值线在实际求解网格间作线性绘图插值，插值点不声称已求解',
                            '网格范围为绘图实验选择，不代表题目给定设备候选集；没有投资成本或经济显著性门槛'],
            'energy_grid_kwh': ENERGY_GRID, 'common_power_grid_kw': POWER_GRID,
            **verification, 'output_sha256': {p.name: digest(p) for p in staging.iterdir() if p.is_file()}})
        staging.rename(target)
    except BaseException:
        shutil.rmtree(staging)
        raise
    return target


def verify(data, folder):
    """从磁盘原始数组独立复核每个解，以及可行域嵌套的费用单调性。"""
    import csv
    def rows(name):
        with (folder / name).open(encoding='utf-8', newline='') as stream:
            return list(csv.DictReader(stream))
    checks, grid, curves = rows('solver_checks.csv'), rows('joint_grid.csv'), rows('one_dimensional.csv')
    with np.load(folder / 'solutions.npz', allow_pickle=False) as saved:
        if set(saved.files) != {r['point'] for r in checks}:
            raise ValueError('参数点与原始解不一一对应')
        for row in checks:
            solution = {k: a.tolist() for k, a in zip(('G', 'C', 'D', 'E', 'W', 'u'), saved[row['point']])}
            solution.update(E0=6000, eta_c=.9, eta_d=.9,
                            settings={'e_min': 1200, 'e_max': float(row['e_max_kwh']),
                                      'charge_kw': float(row['charge_kw']), 'discharge_kw': float(row['discharge_kw'])},
                            solver={'status': int(row['status']), 'objective_yuan': float(row['cost_yuan']),
                                    'dual_bound_yuan': float(row['dual_bound_yuan']), 'mip_gap': float(row['mip_gap'])})
            check_solution(data, solution)
    lookup = {r['point']: float(r['cost_yuan']) for r in checks}
    for row in [*grid, *curves]:
        if abs(float(row['cost_yuan']) - lookup[row['point']]) > COST_TOL_YUAN:
            raise ValueError('绘图CSV费用与原始解不一致')
    matrix = np.array([float(r['cost_yuan']) for r in grid]).reshape(len(POWER_GRID), len(ENERGY_GRID))
    differences = [np.diff(matrix, axis=0).max(), np.diff(matrix, axis=1).max()]
    for resource in ('e_max', 'charge_kw', 'discharge_kw'):
        differences.append(np.diff([float(r['cost_yuan']) for r in curves if r['resource'] == resource]).max())
    if max(differences) > COST_TOL_YUAN:
        raise ValueError('可行域放宽后费用反而升高')
    return {'unique_solves': len(checks), 'joint_points': len(grid), 'one_dimensional_points': len(curves),
            'all_saved_solutions_rechecked': True, 'monotonicity_passed': True,
            'max_mip_gap': max(float(r['mip_gap']) for r in checks)}
