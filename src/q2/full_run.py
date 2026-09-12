"""Mac全量队列：两个独立工作进程、持久收据、依赖调度和逐日断点恢复。"""

import argparse
import datetime as dt
import fcntl
import html
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import traceback
import uuid

from checkpoint import atomic_json, read_checkpoint
from data import ROOT
from protocol import PROTOCOL
from execution import execution_settings
from baseline_reuse import main_baselines

DEPENDENT = {"deterministic", "rigid", "minimum_14", "minimum_21", "minimum_28", "oracles", "richer_soc"}
RESCUE_SECONDS = 900
WORKERS = 2
MAX_WORKER_RSS_KIB = 10*1024*1024  # 16GiB Mac为系统和其他应用保留约6GiB。


def read(path, default=None):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else ({} if default is None else default)


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def job_names(initial):
    return ["main", "structure_separate", "structure_direct_net", "forecast",
            "horizon_1", "horizon_2", "horizon_3",
            *[f"predictor_{load}_{pv}" for load in ("week", "lgb") for pv in ("mean7", "dhr")],
            "window_28", "window_56", "window_84", "window_expanding",
            "scenario_10", "scenario_20", "scenario_40",
            *[f"initial_{soc:g}" for soc in sorted({1200., 6000., initial, 10800.})],
            "deterministic", "rigid", "minimum_14", "minimum_21", "minimum_28", "oracles", "richer_soc"]


def output_for(run, name):
    return run/"processed/main" if name == "main" else run/"processed/experiments"/name


def eligible(jobs):
    """主结果依赖不满足时，仍继续所有独立实验。"""
    return [name for name, job in jobs.items() if job["status"] == "pending"
            and ((name not in DEPENDENT and not job.get("requires_main")) or jobs["main"]["status"] == "complete")]


def owned_process(job):
    """PID可能复用，必须同时匹配本脚本及唯一尝试标识。"""
    pid = job.get("pid")
    if not pid:
        return False
    result = subprocess.run(["ps", "-p", str(pid), "-o", "command="], capture_output=True, text=True)
    return result.returncode == 0 and "full_run.py" in result.stdout and job["attempt"] in result.stdout


def reconcile(run, jobs):
    for name, job in jobs.items():
        if job["status"] != "running":
            continue
        receipt = read(run/job["receipt"])
        if receipt:
            if receipt.get("attempt") != job["attempt"] or receipt.get("job") != name:
                raise ValueError("工作进程收据与任务不符")
            job.update(status="complete" if receipt["complete"] else "failed", finished=receipt["finished"],
                       error=receipt.get("error"), exit_code=receipt["exit_code"])
        elif not owned_process(job):
            # 进程被外部中断时重做未提交日，不把中断当计算失败。
            job.setdefault("interruptions", []).append({"attempt": job["attempt"], "observed": now()})
            job["status"] = "pending" if len(job["interruptions"]) < 3 else "failed"
            if job["status"] == "failed":
                job["error"] = "连续三次进程退出且未形成收据，保留存档并等待自动排查"


def guard_memory(run, jobs):
    """仅当本队列工作进程合计超出10GiB时停止最大任务，避免整机内存耗尽。"""
    measured = []
    for name, job in jobs.items():
        if job["status"] != "running" or not owned_process(job):
            continue
        result = subprocess.run(["ps", "-p", str(job["pid"]), "-o", "rss="], capture_output=True, text=True)
        if result.returncode == 0 and result.stdout.strip():
            job["rss_kib"] = int(result.stdout.strip())
            measured.append((job["rss_kib"], name, job))
    if sum(row[0] for row in measured) <= MAX_WORKER_RSS_KIB:
        return
    rss, name, job = max(measured, key=lambda row: row[0])
    if not owned_process(job) or (run/job["receipt"]).exists():
        return
    try:
        os.killpg(job["pid"], signal.SIGTERM)
    except ProcessLookupError:
        return  # 正常结束恰好发生在身份核验之后，交给完成收据处理。
    atomic_json(run/job["receipt"], {"job": name, "attempt": job["attempt"], "complete": False,
                                     "finished": now(), "exit_code": -int(signal.SIGTERM),
                                     "error": "队列工作进程总内存超过10GiB；仅中止最大任务的未提交日，已存档日保留",
                                     "worker_rss_kib": rss, "queue_rss_kib": sum(row[0] for row in measured),
                                     "resource_limit_kib": MAX_WORKER_RSS_KIB})


def monitor(run, state):
    rows = []
    labels = {"pending": "排队", "running": "计算中", "complete": "完成", "failed": "待自动排查"}
    for name, job in state["jobs"].items():
        directory = output_for(run, name)
        checkpoint = read(directory/"checkpoint.json")
        active = read(directory/"active_solve.json")
        days = checkpoint.get("days", read(directory/"summary.json").get("days", "—"))
        job["completed_days"] = days
        activity = ""
        if job["status"] == "running" and active.get("phase") == "solving":
            activity = f"{active.get('date')} · K={active.get('K')} · 单次上限{active.get('solver_seconds')}秒"
        if (name in DEPENDENT or job.get("requires_main")) and job["status"] == "pending" and state["jobs"]["main"]["status"] != "complete":
            activity = "等待主回放完整结果"
        reuse = read(directory/"baseline_reuse.json")
        if job["status"] == "complete" and reuse.get("complete"):
            activity = "复用经核验的相同主基准；未重复求解"
        log = f'<a href="../{html.escape(job["log"])}">日志</a>' if job.get("log") else ""
        rows.append(f'<tr><td>{html.escape(name)}</td><td>{labels[job["status"]]}</td><td>{days}</td>'
                    f'<td>{html.escape(activity)}</td><td>{log}</td></tr>')
    finished = sum(v["status"] == "complete" for k, v in state["jobs"].items() if k not in ("main", "forecast"))
    main_days = state["jobs"]["main"]["completed_days"]
    gap = state.get("execution", {}).get("gap", PROTOCOL["solver_gap"])
    document = f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="15"><title>第二问全量计算进度</title><style>
body{{font:16px/1.7 system-ui;background:#f3f5f7;color:#173747;margin:0}}main{{max-width:1100px;margin:32px auto;padding:0 20px}}
.cards{{display:flex;gap:20px;flex-wrap:wrap}}.card{{background:white;border-radius:12px;padding:20px;flex:1;min-width:190px}}
strong{{display:block;font-size:28px;color:#126587}}.table{{overflow:auto;background:white;padding:16px;margin-top:24px;border-radius:12px}}
table{{border-collapse:collapse;width:100%;white-space:nowrap}}td,th{{padding:9px;text-align:left;border-bottom:1px solid #dce6e9}}
a{{color:#126587}}small{{color:#526b78}}</style><main><h1>第二问全量计算进度</h1>
<div class="cards"><div class="card">主回放<strong>{main_days} / 334 日</strong></div><div class="card">论文验证<strong>{finished} / 27</strong></div></div>
<p>自动前瞻先比较48与72小时，只有两者都未获可靠解才求24小时兜底。27项验证含可复用基准和代表日诊断，并非27次独立全年重算；相同基准须核验后复用。</p>
<p>每个完整日独立存档，两个实验同时计算。任务中断后从最后完整日续算。原120秒预算整日无可靠候选时，追加每次900秒计算，当前gap门槛为{gap:.0%}，已完成的更严格结果保留；历史预算失败保留，不算作原预算通过。</p>
<p>精度指单次优化费用证书，不是全年费用或预测误差。<a href="../raw/solver_precision_revision.json">精度修订记录（如已启用）</a></p>
<p><a href="report.html">验收报告（生成时的快照）</a> · <a href="../raw/full_run_state.json">完整运行状态</a></p>
<div class="table"><table><thead><tr><th>任务</th><th>状态</th><th>已存档日数</th><th>当前计算</th><th>记录</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div>
<p><small>自动刷新15秒。更新时间：{state['updated']}；队列状态：{html.escape(state['status'])}。完成主回放后才发布result2.xlsx，全部实验验收另行记录。</small></p></main></html>'''
    pending = run/"processed/progress.html.pending"
    pending.write_text(document, encoding="utf-8")
    pending.replace(run/"processed/progress.html")


def worker(run, name, attempt, receipt):
    result = {"job": name, "attempt": attempt, "started": now(), "pid": os.getpid()}
    code = 0
    try:
        precision = execution_settings(run)
        result["precision_execution"] = precision
        if name == "main":
            from dispatch import run_main
            run_main(run, rescue_seconds=RESCUE_SECONDS, **precision)
        else:
            from experiments import run_experiments
            statuses = run_experiments(run, only=name, rescue_seconds=RESCUE_SECONDS, **precision)
            if not statuses.get(name, {}).get("complete"):
                raise RuntimeError(f"实验尚未完成：{statuses}")
        result["complete"] = True
    except Exception as error:
        result.update(complete=False, error=str(error))
        traceback.print_exc()
        code = 2
    finally:
        result.update(finished=now(), exit_code=code)
        atomic_json(run/receipt, result)
    return code


def preflight(run):
    from dispatch import load_prepared
    from final_report import verify_code
    _, _, actual, dates, prices = load_prepared(run)
    verify_code(run)
    initial = read(run/"processed/warm_start.json")["feb1_baseline_soc"]
    checked = []
    for directory in [run/"processed/main", *sorted((run/"processed/experiments").glob("*"))]:
        if not (directory/"checkpoint.json").exists():
            continue
        status = read(directory/"run_status.json")
        import pandas as pd
        first = pd.read_csv(directory/"dispatch.csv", nrows=1, float_precision="round_trip")
        frame, _, _ = read_checkpoint(directory, actual, dates, prices, float(first.initial_soc.iloc[0]),
                                       status["start_index"], status["end_index"], status["settings"])
        checked.append({"directory": str(directory.relative_to(run)), "days": frame.date.nunique()})
    atomic_json(run/"raw/full_run_preflight.json", {"complete": True, "at": now(), "checkpoints": checked})
    return initial


def supervise(run):
    state_path = run/"raw/full_run_state.json"
    state = read(state_path)
    # 若监督进程重启但工作进程仍在，不在写入期间读取或恢复它的检查点。
    if state:
        reconcile(run, state["jobs"])
        guard_memory(run, state["jobs"])
        reconcile(run, state["jobs"])
    if not state or not any(v["status"] == "running" for v in state["jobs"].values()):
        initial = preflight(run)
    else:
        initial = read(run/"processed/warm_start.json")["feb1_baseline_soc"]
    precision = execution_settings(run)
    protocol = {"workers": WORKERS, "base_solver_seconds": PROTOCOL["solver_seconds"], "rescue_seconds": RESCUE_SECONDS,
                "gap": precision.get("solver_gap", PROTOCOL["solver_gap"]), "trigger": "all_day_candidates_failed", "model_changed": False,
                "interpretation": "supplementary_compute_not_retroactive_original_budget_success"}
    protocol_path = run/"raw/full_run_execution.json"
    if precision:
        protocol["precision_revision_sha256"] = precision["execution_revision"]
        protocol_path = run/f"raw/full_run_execution_{precision['execution_revision'][:12]}.json"
    if protocol_path.exists():
        if read(protocol_path)["execution"] != protocol:
            raise ValueError("队列执行设置改变，须显式记录新执行版本，禁止静默混用")
    else:
        atomic_json(protocol_path, {"execution": protocol, "frozen_at": now(), "authorization": "用户明确授权Mac自主全量计算与验收"})
    if not state:
        state = {"started": now(), "jobs": {name: {"status": "pending"} for name in job_names(initial)}}
    for name in main_baselines(initial):
        state["jobs"][name]["requires_main"] = True
    state.update(status="running", supervisor_pid=os.getpid(), execution=protocol)
    state["resource_policy"] = {"queue_worker_rss_limit_kib": MAX_WORKER_RSS_KIB,
                                "memory_action": "stop_largest_owned_worker_preserve_committed_days",
                                "unreported_process_exit_attempts": 3}
    children = {}
    while True:
        for pid, child in list(children.items()):
            if child.poll() is not None:
                del children[pid]
        reconcile(run, state["jobs"])
        guard_memory(run, state["jobs"])
        reconcile(run, state["jobs"])
        active = sum(v["status"] == "running" for v in state["jobs"].values())
        for name in eligible(state["jobs"])[:max(0, WORKERS-active)]:
            attempt = uuid.uuid4().hex
            log = f"raw/full_run_logs/{name}_{attempt}.log"
            receipt = f"raw/full_run_receipts/{name}_{attempt}.json"
            (run/log).parent.mkdir(parents=True, exist_ok=True)
            job = state["jobs"][name]
            job.update(status="running", attempt=attempt, log=log, receipt=receipt, started=now())
            command = [sys.executable, str(Path(__file__).resolve()), "--run-dir", str(run),
                       "--job", name, "--attempt", attempt, "--receipt", receipt]
            with (run/log).open("w", encoding="utf-8") as stream:
                child = subprocess.Popen(command, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT,
                                         env={**os.environ, "OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1", "MPLBACKEND": "Agg"},
                                         start_new_session=True)
            job["pid"] = child.pid
            children[child.pid] = child
            # 每个启动立刻提交PID，重启时可识别尚在运行的工作进程。
            atomic_json(state_path, state)
            print(f"{now()} 启动 {name} PID={child.pid}", flush=True)
        active = any(v["status"] == "running" for v in state["jobs"].values())
        state["updated"] = now()
        if not active and not eligible(state["jobs"]):
            state["status"] = "complete" if all(v["status"] == "complete" for v in state["jobs"].values()) else "needs_repair"
        monitor(run, state)
        atomic_json(state_path, state)
        if not active and not eligible(state["jobs"]):
            break
        time.sleep(10)
    from final_report import generate, verify_code
    verify_code(run)
    generate(run)
    return 0 if state["status"] == "complete" else 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--job")
    parser.add_argument("--attempt")
    parser.add_argument("--receipt")
    args = parser.parse_args()
    run = args.run_dir.resolve()
    if args.job:
        if not args.attempt or not args.receipt:
            parser.error("worker必须提供唯一attempt和receipt")
        return worker(run, args.job, args.attempt, args.receipt)
    with (run/"raw/full_run.lock").open("a", encoding="utf-8") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return supervise(run)


if __name__ == "__main__":
    raise SystemExit(main())
