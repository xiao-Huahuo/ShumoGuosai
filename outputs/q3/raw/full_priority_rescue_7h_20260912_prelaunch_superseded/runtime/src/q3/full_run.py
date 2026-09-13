"""主轨迹优先的全量监督：分片续算、异常重启、主表先导出、再做少量实验。"""
import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import traceback
import threading
from .config import ROOT,CODE_ROOT,Config,write_json,validate_production_rescue
from .checkpoint import run_lock
from .parallel import limit_native_libraries, validate_parallelism


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def worker(root: Path, q2_run: Path, workers: int, config: Config, end: int, samples: bool) -> None:
    from .data import read_inputs
    from .rolling import run_period
    from .export import write_tables, export_workbook
    from .sampled import run_samples
    write_json(root/'phase.json', {'phase': 'main', 'started': now()})
    data = read_inputs(q2_run, ROOT/'inputs/q3/processed')
    frame = run_period(data, config, root/'main', end=end, with_fiv=False, workers=workers, max_slices=None)
    if end < 365:
        write_json(root/'phase.json', {'phase': 'bounded_test_complete', 'end_day': end, 'finished': now()})
        return
    write_tables(frame, root/'main')
    export_workbook(frame, root/'main', config)
    rescue=[]
    if config.production_rescue:
        for path in sorted((root/'main/audit').glob('*.json')):
            day=json.loads(path.read_text(encoding='utf-8'))
            for node in day.get('nodes',[]):
                audit=node['solver'];rescue.append({'date':day['date'],'hour':node['hour'],
                    'accepted_by':audit.get('accepted_by','certified_3pct' if audit.get('reliable') else 'unknown'),
                    'objective':audit.get('objective'),'upper_bound':audit.get('upper_bound',audit.get('objective')),
                    'lower_bound':audit.get('lower_bound'),'gap':audit.get('gap')})
        finite=[row for row in rescue if row['gap'] is not None]
        write_json(root/'main/rescue_summary.json',{'nodes':len(rescue),
            'certified_3pct':sum(row['accepted_by']=='certified_3pct' for row in rescue),
            'hard_limit_feasible':sum(row['accepted_by']=='hard_limit_feasible' for row in rescue),
            'max_recorded_gap':max((row['gap'] for row in finite),default=None),'records':rescue})
    write_json(root/'main_complete.json', {'rows': len(frame), 'gap_target': config.gap,
        'result': str(root/'main/result3.xlsx'), 'finished': now(), 'sample_experiments_not_needed_for_main_export': True,
        'production_rescue':config.production_rescue,'all_nodes_certified_3pct':not config.production_rescue or all(
            row['accepted_by']=='certified_3pct' for row in rescue)})
    if samples:
        write_json(root/'phase.json', {'phase': 'sampled_experiments', 'started': now()})
        run_samples(data, config, frame, root/'samples', root/'main', workers)
    write_json(root/'phase.json', {'phase': 'complete', 'finished': now()})


def progress(root: Path, process_pid: int | None, status: str, attempt: int) -> dict:
    def read(path: Path) -> dict:
        return json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    state = read(root/'main/state.json'); active = read(root/'main/active.json')
    phase=read(root/'phase.json');execution=read(root/'execution.json')
    rescue=bool(execution.get('config',{}).get('production_rescue'))
    samples=bool(execution.get('sampled_experiments'))
    date = active.get('date')
    candidates = list((root/'main/nodes'/date).glob('*/latest.json')) if date else []
    latest = max(candidates, key=lambda p: p.stat().st_mtime) if candidates else None
    node = read(latest).get('content', {}).get('audit', {}) if latest else {}
    info = {'status': status, 'phase': phase.get('phase', 'starting'), 'worker_pid': process_pid,
        'attempt': attempt, 'completed_days_including_warmup': len(state.get('days', [])),
        'formal_days': max(0, len(state.get('days', []))-31), 'total_formal_days': 334,
        'active_date': date, 'active_hour': latest.parent.name if latest else None,
        'last_solver_gap': node.get('gap'), 'completed_slices': node.get('completed_slices'),
        'node_reliable': node.get('reliable'), 'node_accepted':node.get('accepted'),
        'accepted_by':node.get('accepted_by'),'hard_limit_seconds':node.get('hard_limit_seconds'),
        'checkpoint': str(latest) if latest else None,
        'soc': state.get('soc'), 'updated_at': now(), 'main_result_ready': (root/'main_complete.json').exists(),
        'production_rescue':rescue,'completed_sample_jobs':len(list((root/'samples').glob('*/*/complete.json'))),
        'sample_jobs_total':36 if samples else 0}
    write_json(root/'progress.json', info)
    gap = '-' if info['last_solver_gap'] is None else f'{info["last_solver_gap"]:.3%}'
    body = '<!doctype html><html lang="zh"><meta charset="utf-8"><meta http-equiv="refresh" content="10"><meta name="viewport" content="width=device-width,initial-scale=1"><title>第三问全量计算进度</title><style>body{max-width:1000px;margin:40px auto;padding:0 20px;font:17px/1.7 -apple-system,sans-serif;color:#263b50}strong{color:#0072b2}table{border-collapse:collapse}td{padding:8px 18px;border-bottom:1px solid #ccd6df}</style><h1>第三问全年主计算</h1>'
    body += f'<p>状态 <strong>{status}</strong>；阶段 {info["phase"]}；正式完成 <strong>{info["formal_days"]}/334 天</strong>，含预热完成 {info["completed_days_including_warmup"]} 天。</p>'
    body += f'<table><tr><td>当前日期/节点</td><td>{date or "-"} / {info["active_hour"] or "-"}</td></tr><tr><td>最新求解间隙</td><td>{gap}</td></tr><tr><td>已完成求解切片</td><td>{info["completed_slices"] or 0}</td></tr><tr><td>最近日末SOC</td><td>{info["soc"]}</td></tr><tr><td>监督启动次数</td><td>{attempt}</td></tr></table>'
    body += ('<p>比赛生产救援：3%证书优先；06:00最多35秒，其余节点最多8秒。到限后仅接受通过原物理和完整矩阵验证的可行策略，并如实保存UB、LB和gap。当前只运行主轨迹。</p>' if rescue else
             '<p>主计算按用户批准的3%最优性间隙推进。每节点/每6小时块/每日存档；求解有切片及事件快照。</p>')
    if info['main_result_ready']:
        body += '<p><a href="main/result3.xlsx">下载主结果 result3.xlsx</a></p>'
        if info['sample_jobs_total']:
            body += f'<p>抽样辅助任务 {info["completed_sample_jobs"]}/{info["sample_jobs_total"]}。</p>'
    body += '<p><a href="progress.json">进度记录</a> · <a href="supervisor.json">运行与重启记录</a> · <a href="worker.log">计算日志</a></p></html>'
    (root/'progress.html').write_text(body, encoding='utf-8')
    return info


def stop_group(child: subprocess.Popen, force: bool = False) -> None:
    try:
        os.killpg(child.pid, signal.SIGKILL if force else signal.SIGTERM)
    except ProcessLookupError:
        pass


def last_worker_activity(root: Path) -> float:
    paths = [root/'phase.json', root/'main/state.json']
    paths += list((root/'main').rglob('latest.json'))+list((root/'samples').rglob('latest.json'))
    paths += list(root.rglob('terminal_cache.json'))
    return max((path.stat().st_mtime for path in paths if path.exists()), default=0.)


def supervise(root: Path, q2_run: Path, workers: int, config: Config, end: int, samples: bool) -> None:
    root.mkdir(parents=True, exist_ok=True)
    with run_lock(root/'supervisor.lock'):
        frozen = {'config': asdict(config), 'signature': config.signature(), 'q2_run': str(q2_run),
                  'end_day': end, 'sampled_experiments': samples, 'workers': workers,
                  'authorization': ('用户授权七小时production rescue：3%优先，hard limit后仅接受原物理验证可行解'
                                    if config.production_rescue else '用户允许主计算gap≤3%，少量辅助实验，准备完成后自主启动全年')}
        path = root/'execution.json'
        if path.exists() and json.loads(path.read_text(encoding='utf-8')) != json.loads(json.dumps(frozen)):
            raise ValueError('已存在运行的代码/配置不同，禁止混入旧检查点')
        write_json(path, frozen)
        commands = [sys.executable, '-m', 'src.q3.full_run', '--worker', '--run-dir', str(root),
            '--q2-run', str(q2_run), '--workers', str(workers), '--seconds', str(config.seconds),
            '--gap', str(config.gap), '--solver-threads', str(config.solver_threads),
            '--solver-backend', config.solver_backend, '--formulation', config.formulation,
            '--solver-focus', config.solver_focus,
            '--hard-06-seconds',str(config.hard_06_seconds),'--hard-other-seconds',str(config.hard_other_seconds),
            '--end-day', str(end), '--supervisor-pid', str(os.getpid())]
        if not samples:
            commands.append('--main-only')
        if config.production_rescue:
            commands.append('--production-rescue')
        existing = root/'supervisor.json'
        history = json.loads(existing.read_text(encoding='utf-8')).get('history', []) if existing.exists() else []
        caffeinate = subprocess.Popen(['caffeinate', '-i', '-w', str(os.getpid())]) if sys.platform == 'darwin' else None
        child = None
        def stop(signum, frame) -> None:
            if child is not None and child.poll() is None:
                stop_group(child)
            raise SystemExit(128+signum)
        previous_handlers = {s: signal.signal(s, stop) for s in (signal.SIGTERM, signal.SIGINT)}
        try:
            for retry in range(1, 4):
                attempt = len(history)+1
                with (root/'worker.log').open('ab') as log:
                    child = subprocess.Popen(commands, cwd=CODE_ROOT.parent.parent, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
                    launched = time.time()
                    history.append({'attempt': attempt, 'pid': child.pid, 'started_at': now()})
                    write_json(root/'supervisor.json', {'status': 'running', 'supervisor_pid': os.getpid(), 'history': history})
                    while child.poll() is None:
                        progress(root, child.pid, 'running', attempt)
                        if time.time()-max(launched, last_worker_activity(root)) > max(600., 5*config.seconds):
                            history[-1]['watchdog_timeout'] = True
                            stop_group(child, force=True)
                        time.sleep(5)
                history[-1].update(return_code=child.returncode, ended_at=now())
                stop_group(child, force=True)  # 回收异常退出worker遗留的池进程，不影响别的运行组。
                if child.returncode == 0:
                    write_json(root/'supervisor.json', {'status': 'complete', 'history': history})
                    progress(root, None, 'complete', attempt)
                    return
                write_json(root/'supervisor.json', {'status': 'retrying' if retry < 3 else 'failed', 'history': history})
            progress(root, None, 'failed', attempt)
            raise RuntimeError('连续三次异常退出；已有检查点保留，停止重复失败')
        finally:
            if child is not None and child.poll() is None:
                stop_group(child)
                try:
                    child.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    stop_group(child, force=True); child.wait()
            for signum, handler in previous_handlers.items():
                signal.signal(signum, handler)
            if caffeinate is not None:
                caffeinate.terminate(); caffeinate.wait()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', type=Path, required=True)
    parser.add_argument('--q2-run', type=Path, default=ROOT/'outputs/q2/dispatch_runs/20260911_224501')
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--solver-threads', type=int, default=1)
    parser.add_argument('--solver-backend', choices=('auto','highs','gurobi'), default='highs')
    parser.add_argument('--formulation', choices=('legacy','v2_free'), default='v2_free')
    parser.add_argument('--solver-focus', choices=('default','bound'), default='default')
    parser.add_argument('--production-rescue',action='store_true')
    parser.add_argument('--hard-06-seconds',type=float,default=35.)
    parser.add_argument('--hard-other-seconds',type=float,default=8.)
    parser.add_argument('--seconds', type=float, default=120.)
    parser.add_argument('--gap', type=float, default=.03)
    parser.add_argument('--end-day', type=int, default=365, help='仅用于有界验收，正式365')
    parser.add_argument('--main-only', action='store_true')
    parser.add_argument('--worker', action='store_true')
    parser.add_argument('--supervisor-pid', type=int)
    args = parser.parse_args(); limit_native_libraries(); validate_parallelism(args.workers, args.solver_threads)
    if not 1 <= args.end_day <= 365:
        parser.error('end-day必须在1—365')
    if args.production_rescue and not args.main_only:
        parser.error('production rescue只允许--main-only，禁止辅助实验')
    config = Config(seconds=args.seconds, gap=args.gap, solver_threads=args.solver_threads,
                    solver_backend=args.solver_backend, formulation=args.formulation,
                    solver_focus=args.solver_focus,production_rescue=args.production_rescue,
                    hard_06_seconds=args.hard_06_seconds,hard_other_seconds=args.hard_other_seconds)
    if config.production_rescue:validate_production_rescue(config)
    function = worker if args.worker else supervise
    finished = threading.Event()
    if args.worker and args.supervisor_pid:
        def watch_owner() -> None:
            while not finished.wait(2):
                if os.getppid() != args.supervisor_pid:
                    if os.getpgrp() == os.getpid():
                        os.killpg(os.getpgrp(), signal.SIGTERM)
                    else:
                        os.kill(os.getpid(), signal.SIGTERM)
        threading.Thread(target=watch_owner, daemon=True).start()
    try:
        function(args.run_dir.resolve(), args.q2_run.resolve(), args.workers, config, args.end_day, not args.main_only)
    except Exception as error:
        write_json(args.run_dir.resolve()/('worker_error.json' if args.worker else 'supervisor_error.json'),
                   {'type': type(error).__name__, 'error': str(error), 'traceback': traceback.format_exc(), 'time': now()})
        raise
    finally:
        finished.set()


if __name__ == '__main__':
    main()
