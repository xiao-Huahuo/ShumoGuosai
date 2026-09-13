"""python -m src.q3.run：默认安全计时；全量仅通过显式full子命令。"""
import argparse
from dataclasses import asdict, replace
from datetime import datetime
import json
from pathlib import Path
import time
import numpy as np
import pandas as pd
from .config import Config, ROOT, E_INITIAL, write_csv, write_json
from .data import read_inputs
from .scenarios import construct
from .terminal import TerminalValues
from .optimization import solve
from .physics import replay
from .rolling import run_period, run_day, previous_net
from .analysis import forecast_diagnostics, run_experiments
from .export import export_workbook, write_tables


def benchmark(q2_run: Path, output: Path, seconds: float = 20., *, solver_threads: int = 1) -> dict:
    started = time.perf_counter()
    config = Config(seconds=seconds, solver_threads=solver_threads)
    data = read_inputs(q2_run, ROOT/'inputs/q3/processed')
    preparation_seconds = time.perf_counter()-started
    terminal = TerminalValues(data, config)
    rows, node_details = [], []
    # 日期在读取测试结果前固定；初态6000仅用于性能试验，不声称是真实1月预热后的状态。
    for day in (31, 171, 354):
        soc, reference = E_INITIAL, None
        for hour in (0, 6, 12, 18):
            node_initial = soc
            node_reference = None if hour == 0 else reference[hour*6:].copy()
            stage_start = time.perf_counter()
            scenes = construct(data, day, hour, config)
            construction_seconds = time.perf_counter()-stage_start
            fd_start = time.perf_counter()
            coefficient, calibration = terminal.value(day, hour)
            fd_seconds = time.perf_counter()-fd_start
            prices = data.prices[(hour*6+np.arange(144))%144]
            solution = solve(scenes, prices, soc, config, reference=None if hour == 0 else reference[hour*6:],
                today=144-hour*6, terminal=coefficient, previous_net=previous_net(data, day, hour), require=False)
            if solution.policy is not None:
                if hour == 0:
                    reference = solution.policy.grid.copy()
                actual = data.actual[day, hour*6:hour*6+36]
                response = replay(solution.policy.part(0, 36), (actual[:, 0]-actual[:, 1])/6, soc)
                soc = float(response['soc'][-1])
            rows.append({'date': str((pd.Timestamp('2025-01-01')+pd.Timedelta(days=day)).date()), 'hour': hour,
                'scenario_seconds': construction_seconds, 'terminal_seconds': fd_seconds, **solution.audit})
            node_details.append({'day': day, 'hour': hour, 'initial_soc': node_initial,
                'reference': None if node_reference is None else node_reference.tolist(),
                'policy': None if solution.policy is None else {key: getattr(solution.policy, key).tolist() for key in ('grid', 'charge_cap', 'discharge_cap')},
                'scenarios': scenes.audit, 'terminal': calibration})
            write_csv(output/'timing_samples.csv', pd.DataFrame(rows))
            write_json(output/'sample_details.json', node_details)
            print(f'小样本 day={day} hour={hour} S={len(scenes.weights)} {solution.audit["seconds"]:.2f}s gap={solution.audit.get("gap")} {solution.audit["status"]}', flush=True)
            if reference is None:
                break
    frame = pd.DataFrame(rows)
    write_csv(output/'terminal_calibration.csv', pd.DataFrame(terminal.cache.values()))
    write_csv(output/'terminal_delta_stability.csv', pd.DataFrame(terminal.stability(29, 0)))
    diag = forecast_diagnostics(data, output/'diagnostics')
    m0_frame, m0_audit, _ = run_day(data, terminal, 31, E_INITIAL, replace(config, deterministic=True))
    write_csv(output/'M0_timing_dispatch.csv', m0_frame)
    write_json(output/'M0_timing_audit.json', m0_audit)
    m0_durations = np.array([node['solver']['seconds'] for node in m0_audit['nodes']])
    durations = frame.seconds.to_numpy()
    # 主模型预热Jan8—31为96次；正式334×4=1336；首7天冷启动无MILP。
    jobs = {'main_warmup_and_formal': 24*4+334*4, 'FIV_18h_comparisons': 334*6,
            'OUV_extra_three_update_sets': (24+334)*(1+2+3), 'M0': (24+334)*4,
            'nine_sensitivities_with_FIV_and_OUV': 9*((24+334)*10+334*6)}
    projections = []
    for name, count in jobs.items():
        measured = m0_durations if name == 'M0' else durations
        projections.append({'scope': name, 'solve_count': count, 'median_hours': float(np.median(measured)*count/3600),
            'p90_hours': float(np.quantile(measured, .9)*count/3600), 'max_sample_hours': float(measured.max()*count/3600)})
    write_csv(output/'runtime_projection.csv', pd.DataFrame(projections))
    report = {'full_run_started': False, 'config': asdict(config), 'preparation_seconds': preparation_seconds,
        'elapsed_seconds': time.perf_counter()-started, 'samples': len(rows),
        'certified_samples': int(frame.reliable.sum()), 'limited_samples': int((~frame.reliable).sum()),
        'median_node_seconds': float(np.median(durations)), 'p90_node_seconds': float(np.quantile(durations, .9)),
        'projections': projections, 'diagnostics': diag,
        'initial_state': 'Each timing day starts at6000; intra-day SOC continuous; not formal warmup state',
        'caveat': 'Censored solves make exact-optimum completion time unknown. Projections are observed-budget CPU planning, not guaranteed completion; FD/preparation/M2/stress and IO are extra.',
        'hardware_contention': f'Sequential Q3 sample jobs, SCIP threads={solver_threads}; other machine workload may contend'}
    write_json(output/'timing_report.json', report)
    body = '<!doctype html><html lang="zh"><meta charset="utf-8"><title>第三问代码与计时验收</title><style>body{font:16px -apple-system,sans-serif;max-width:1180px;margin:40px auto;color:#263445;padding:0 20px}table{border-collapse:collapse;font-size:13px;width:100%;margin:20px 0}td,th{border-bottom:1px solid #d5dce3;padding:8px;text-align:right}th{background:#ecf3f7}img{max-width:100%}.status{padding:18px;background:#e7f0f4;border-left:4px solid #0072b2}</style><h1>第三问 · 小样本计时验收</h1>'
    body += '<p class="status">未启动全量。正式 S=20、尾部2。以下为真实附件的性能试验，不能作为正式 result3。</p>'
    body += f'<p>样本 {len(rows)} 个；获得所要求证书 {int(frame.reliable.sum())} 个；其余仅保存可行解与间隙。单节点中位数 {np.median(durations):.2f} 秒。</p>'
    body += frame[['date', 'hour', 'scenario_count', 'seconds', 'gap', 'reliable', 'status']].to_html(index=False)
    body += '<h2>按实测预算外推</h2><p>限时未达最优的样本被截断，不能据此承诺严格最优全年完成时间。下表未含辅助标定、M2和附加结算对照。</p>'
    body += pd.DataFrame(projections).to_html(index=False)
    body += '<h2>预报原始数据诊断</h2><img src="diagnostics/figures/forecast_error_heatmaps.png" alt="四发布时间与24小时提前量的MAE、RMSE和Bias热图">'
    body += '<p><a href="timing_samples.csv">计时CSV</a> · <a href="timing_report.json">完整计时记录</a> · <a href="terminal_delta_stability.csv">终端扰动核验</a></p></html>'
    body = body.replace('<meta charset="utf-8">', '<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">')
    body = body.replace('<style>', '<style>.table-scroll{overflow-x:auto;max-width:100%}table{min-width:700px}')
    body = body.replace('<table', '<div class="table-scroll"><table').replace('</table>', '</table></div>')
    (output/'report.html').write_text(body, encoding='utf-8')
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['benchmark', 'parallel-benchmark', 'prepare', 'full'], nargs='?', default='parallel-benchmark')
    parser.add_argument('--q2-run', type=Path, default=ROOT/'outputs/q2/dispatch_runs/20260911_224501')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--seconds', type=float, default=None)
    parser.add_argument('--gap', type=float, default=0., help='正式默认0，不继承Q2历史3%%授权')
    parser.add_argument('--workers', type=int, default=4, help='独立计算进程上限；子实验内不再建池')
    parser.add_argument('--solver-threads', type=int, default=1, help='每个MILP的SCIP线程数；>1显式调用solveConcurrent')
    parser.add_argument('--experiments', action='store_true', help='显式full后执行所有M0/M2/FIV/OUV和敏感性')
    args = parser.parse_args()
    from .parallel import limit_native_libraries, validate_parallelism
    validate_parallelism(args.workers, args.solver_threads)
    limit_native_libraries()
    output = args.output or ROOT/'outputs/q3/raw'/datetime.now().strftime('%Y%m%d_%H%M%S')
    if args.command == 'parallel-benchmark':
        from .parallel_benchmark import benchmark as parallel_benchmark
        report = parallel_benchmark(output, seconds=args.seconds or 8., workers=args.workers)
        print(json.dumps({key: report[key] for key in ('workers', 'throughput_speedup', 'full_run_started')}, ensure_ascii=False))
    elif args.command == 'benchmark':
        report = benchmark(args.q2_run.resolve(), output, args.seconds or 20., solver_threads=args.solver_threads)
        print(json.dumps({k: report[k] for k in ('samples', 'certified_samples', 'median_node_seconds', 'full_run_started')}, ensure_ascii=False))
    elif args.command == 'prepare':
        data = read_inputs(args.q2_run.resolve(), ROOT/'inputs/q3/processed')
        write_json(output/'diagnostics.json', forecast_diagnostics(data, output/'diagnostics'))
    else:
        config = Config(seconds=args.seconds or 120., gap=args.gap, solver_threads=args.solver_threads)
        data = read_inputs(args.q2_run.resolve(), ROOT/'inputs/q3/processed')
        write_json(output/'frozen_config.json', {'config': asdict(config), 'signature': config.signature(),
                   'assumption_authority': '2026-09-12 user confirmed FD historical24h E6000/6100 median last28'})
        frame = run_period(data, config, output/'main', with_fiv=True, workers=args.workers)
        write_tables(frame, output/'main')
        export_workbook(frame, output/'main', config)
        forecast_diagnostics(data, output/'diagnostics')
        if args.experiments:
            run_experiments(data, config, output, frame, workers=args.workers)


if __name__ == '__main__':
    main()
