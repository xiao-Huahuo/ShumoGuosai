"""同一冻结输入的串行/进程并行及SCIP线程对照，不触发全年运行。"""
from dataclasses import replace
import json
import os
from pathlib import Path
import resource
import sys
import time
import numpy as np
import pandas as pd
from .config import Config, ROOT, write_csv, write_json
from .scenarios import Scenarios
from .optimization import solve
from .parallel import process_pool, limit_native_libraries
from .data import read_inputs
from .terminal import TerminalValues


def measured_solve(request: dict) -> dict:
    started, cpu_start = time.perf_counter(), time.process_time()
    solution = solve(**request)
    cpu = time.process_time()-cpu_start
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/(1024**2 if sys.platform == 'darwin' else 1024)
    return {**solution.audit, 'wall_seconds': time.perf_counter()-started, 'cpu_seconds': cpu,
            'peak_rss_mib': rss, 'pid': os.getpid(),
            'grid': solution.policy.grid.tolist() if solution.policy else None}


def frozen_requests(seconds: float) -> list[dict]:
    folder = ROOT/'outputs/q3/raw/extended_timing_20260912'
    requests = []
    for name in ('node_171_12', 'node_354_6'):
        audit = json.loads((folder/(name+'.json')).read_text(encoding='utf-8'))
        frame = pd.read_csv(folder/(name+'.csv'), float_precision='round_trip')
        load = frame.pivot(index='scenario', columns='slot', values='load_kw').to_numpy()
        net = frame.pivot(index='scenario', columns='slot', values='net_kwh').to_numpy()
        scenes = Scenarios(load, np.maximum(load-6*net, 0), np.asarray(audit['weights']), audit['scenarios'])
        requests.append(dict(scenarios=scenes, prices=np.asarray(audit['prices']), initial=6000.,
            config=Config(seconds=seconds), reference=np.asarray(audit['reference']),
            today=144-audit['audit']['hour']*6, terminal=audit['terminal'], require=False))
    return requests


def benchmark(output: Path, *, seconds: float = 8., workers: int = 4) -> dict:
    limit_native_libraries()
    output.mkdir(parents=True, exist_ok=True)
    requests = frozen_requests(seconds)
    # 不因结果选模型；以下只比较相同精度/相同输入的执行资源分配。
    native = []
    for threads in (1, 2, 4):
        for index, job in enumerate(requests):
            result = measured_solve({**job, 'config': replace(job['config'], solver_threads=threads)})
            native.append({'case': index, 'threads': threads, **{key: value for key, value in result.items() if key != 'grid'}})
            print(f'SCIP线程={threads} case={index} wall={result["wall_seconds"]:.2f}s gap={result["gap"]:.4%}', flush=True)
            write_csv(output/'native_threads.csv', pd.DataFrame(native))
    jobs = requests*2
    started = time.perf_counter()
    serial = [measured_solve(job) for job in jobs]
    serial_seconds = time.perf_counter()-started
    started = time.perf_counter()
    with process_pool(workers) as executor:
        parallel = list(executor.map(measured_solve, jobs)) if executor else [measured_solve(job) for job in jobs]
        parallel_seconds = time.perf_counter()-started
        # 将已热启动进程池复用于许多短辅助问题，避免每个FD单独建池。
        data = read_inputs(ROOT/'outputs/q2/dispatch_runs/20260911_224501')
        config = Config(seconds=15.)
        serial_fd = TerminalValues(data, config)
        fd_start = time.perf_counter()
        first = [serial_fd.value(31, hour)[0] for hour in (0, 6, 12, 18)]
        serial_fd_seconds = time.perf_counter()-fd_start
        parallel_fd = TerminalValues(data, config, executor)
        fd_start = time.perf_counter()
        second = [parallel_fd.value(31, hour)[0] for hour in (0, 6, 12, 18)]
        parallel_fd_seconds = time.perf_counter()-fd_start
        np.testing.assert_allclose(first, second, rtol=0, atol=1e-10)
    rows = []
    for mode, group in (('serial', serial), ('parallel', parallel)):
        for index, result in enumerate(group):
            rows.append({'mode': mode, 'case': index%2, 'replicate': index//2,
                         **{key: value for key, value in result.items() if key != 'grid'}})
    write_csv(output/'process_comparison.csv', pd.DataFrame(rows))
    write_json(output/'policies.json', {'serial': serial, 'parallel': parallel})
    equal = all(all(np.isclose(left[key], right[key], atol=1e-8, rtol=0) for key in ('objective', 'lower_bound', 'gap'))
                and np.allclose(left['grid'], right['grid'], atol=1e-8, rtol=0) for left, right in zip(serial, parallel))
    report = {'full_run_started': False, 'workers': workers, 'solver_threads_per_process': 1,
        'jobs': len(jobs), 'serial_wall_seconds': serial_seconds, 'parallel_wall_seconds_including_startup': parallel_seconds,
        'throughput_speedup': serial_seconds/parallel_seconds, 'worker_pids': sorted({row['pid'] for row in parallel}),
        'serial_FD_seconds': serial_fd_seconds, 'parallel_FD_seconds_warm_pool': parallel_fd_seconds,
        'FD_speedup': serial_fd_seconds/parallel_fd_seconds, 'FD_coefficients_equal': True,
        'max_worker_peak_rss_mib': max(row['peak_rss_mib'] for row in parallel),
        'all_replay_mapping_valid': all(row['mapping_error'] <= 1e-5 for row in serial+parallel),
        'observed_objective_bound_gap_grid_equal': equal,
        'memory_note': 'ru_maxrss is process lifetime high-water mark; serial parent previously ran native4-thread trials, not per-job memory',
        'precision': 'gap=0 remains unchanged; timed-out policies are diagnostic only',
        'interpretation': 'throughput of four identical bounded jobs; not proof of equal final policies or annual optimal completion time'}
    write_json(output/'report.json', report)
    body = '<!doctype html><html lang="zh"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>第三问并行计算验收</title><style>body{font:16px/1.6 -apple-system,sans-serif;max-width:1100px;margin:32px auto;padding:0 18px;color:#263b50}.table{overflow-x:auto}table{border-collapse:collapse;white-space:nowrap}td,th{padding:7px;border-bottom:1px solid #ccd6df}th{background:#eaf1f5}strong{color:#0072b2}</style><h1>第三问并行计算验收</h1>'
    body += f'<p>4个冻结输入实例：串行 <strong>{serial_seconds:.2f}s</strong> → {workers}进程 <strong>{parallel_seconds:.2f}s</strong>，吞吐加速 <strong>{report["throughput_speedup"]:.2f}×</strong>（含启动）。</p>'
    body += '<p>仍未启动全量。场景、模型、结算与gap=0不变；限时可行解不代表严格最优。跨日SOC链保持顺序。</p><h2>SCIP内部多线程</h2><div class="table">'
    body += pd.DataFrame(native)[['case', 'threads', 'wall_seconds', 'cpu_seconds', 'gap', 'mapping_error']].to_html(index=False)+'</div>'
    body += '<h2>独立任务进程并行</h2><div class="table">'+pd.DataFrame(rows)[['mode', 'case', 'replicate', 'wall_seconds', 'gap', 'peak_rss_mib']].to_html(index=False)+'</div>'
    body += f'<p>历史FD：串行{serial_fd_seconds:.3f}s、复用进程池{parallel_fd_seconds:.3f}s；四节点系数逐值一致。实测单worker峰值{report["max_worker_peak_rss_mib"]:.1f}MiB。</p>'
    body += '<p>内存列是进程生命期高水位；串行父进程此前已做4线程试验，不能用串并行两列断言单次内存节省。</p>'
    body += '<p><a href="native_threads.csv">线程对照CSV</a> · <a href="process_comparison.csv">进程对照CSV</a> · <a href="report.json">完整记录</a></p></html>'
    (output/'report.html').write_text(body, encoding='utf-8')
    return report
