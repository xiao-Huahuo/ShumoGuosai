"""两真实日各重复两次的1%/3%配对实验；完整日模型、统一算法、正式执行只读。"""

import datetime as dt
import hashlib
import importlib.metadata
import io
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import rolling
from data import ROOT, sha256, write_csv, write_json
from dispatch import load_prepared
from linear_policy import solve_linear_policy
from policy import DT, validate_replay


def main():
    run = ROOT / "outputs/q2/dispatch_runs/20260911_224501"
    output = ROOT / "outputs/q2/precision_comparison" / dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    raw_dir, processed = output / "raw", output / "processed"
    raw_dir.mkdir(parents=True); processed.mkdir()
    print("RESULT_DIRECTORY", output, flush=True)
    protected = list((ROOT / "src/q2").glob("*.py")) + [run / "raw/solver_precision_revision.json", run / "raw/prepared_manifest.json"]
    hashes = {str(p.relative_to(ROOT)): sha256(p) for p in protected}
    load_started = time.perf_counter()
    store, frozen, actual, dates, prices = load_prepared(run)
    load_seconds = time.perf_counter() - load_started
    directory = run / "processed/main"
    for _ in range(10):
        checkpoint = (directory / "checkpoint.json").read_bytes()
        daily_bytes = (directory / "daily.csv").read_bytes()
        if (checkpoint == (directory / "checkpoint.json").read_bytes()
                and hashlib.sha256(daily_bytes).hexdigest() == json.loads(checkpoint)["sha256"]["daily.csv"]):
            break
    else:
        raise RuntimeError("未取得完整已提交日表")
    daily = pd.read_csv(io.BytesIO(daily_bytes), float_precision="round_trip")
    selected_dates = ["2025-02-01", "2025-03-20"]
    write_csv(raw_dir / "initial_states.csv", daily[daily.date.isin(selected_dates)])
    metadata = {
        "status": "running", "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "dates": selected_dates, "date_rule": "evaluation_first_day_and_first_protocol_specified_date",
        "repeats": 2, "requested_gaps": [.01, .03], "candidate_time_limit_seconds": 120,
        "supplemental_retries": False, "run_directory": str(run),
        "same_algorithm": "rolling_LP_certificate_then_existing_equivalent_HiGHS_MILP",
        "one_percent_route": "isolated_native_fallback_redirected_to_current_equivalent_HiGHS; production_unchanged",
        "timing_scope": "make_day_including_all_K_selection_solve_validation; excludes_common_library_load_and_actual_replay",
        "shared_load_seconds": load_seconds, "source_sha256": hashes,
        "benchmark_sha256": sha256(Path(__file__)), "daily_snapshot_sha256": hashlib.sha256(daily_bytes).hexdigest(),
        "machine": platform.platform(), "processor": platform.processor(), "logical_cpus": os.cpu_count(),
        "versions": {name: importlib.metadata.version(name) for name in ("numpy", "scipy", "pandas", "pyscipopt")},
        "thread_environment": {key: os.environ.get(key) for key in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS")},
        "background_processes_start": subprocess.check_output(["ps", "-axo", "pid,etime,%cpu,command"], text=True).splitlines(),
        "records": [], "input_hashes": {},
    }
    metadata["background_processes_start"] = [line for line in metadata["background_processes_start"] if "src/q2/full_run.py" in line]
    original_solve, original_native = rolling._solve, rolling.solve_policy
    calls, summaries, candidates = [], [], []
    context = {}

    def same_linear(net, price, weights, initial, *, gap, time_limit, seed_policy, known_lower_bound):
        return solve_linear_policy(net, price, weights, initial, gap=gap, time_limit=time_limit, seed_policy=seed_policy)

    def timed_solve(net, price, weights, initial, **kwargs):
        k = len(price) // 144
        key = f"{context['date']}_K{k}"
        digest = hashlib.sha256()
        for value in (net, price, weights, np.array([initial])):
            value = np.ascontiguousarray(value, dtype=np.float64)
            digest.update(str(value.shape).encode("utf-8")); digest.update(value.tobytes())
        fingerprint = digest.hexdigest()
        assert metadata["input_hashes"].setdefault(key, fingerprint) == fingerprint
        if not (raw_dir / f"input_{key}.npz").exists():
            np.savez_compressed(raw_dir / f"input_{key}.npz", net=net, prices=price, weights=weights, initial_soc=initial)
        started = time.perf_counter()
        policy, responses, info = original_solve(net, price, weights, initial, **kwargs)
        elapsed = time.perf_counter() - started
        item = {**context, "K": k, "scenarios": len(net), "input_sha256": fingerprint,
                "wall_seconds": elapsed, "solver": info}
        if policy is not None:
            for path, response in zip(net, responses):
                validate_replay(policy.grid, path, initial, response)
            policy_file = f"policy_{context['trial']}_K{k}.npz"
            np.savez_compressed(raw_dir / policy_file, grid=policy.grid, charge_cap=policy.charge_cap, discharge_cap=policy.discharge_cap)
            item["policy_file"] = policy_file
        if info["reliable"]:
            assert policy is not None and info["mip_gap"] <= kwargs["solver_gap"] + 1e-8
        calls.append(item)
        print(json.dumps({**context, "K": k, "seconds": elapsed, "gap": info.get("mip_gap"), "accepted": info["reliable"]}), flush=True)
        return policy, responses, info

    rolling._solve, rolling.solve_policy = timed_solve, same_linear
    try:
        for date_index, date in enumerate(selected_dates):
            day = int(dates.get_loc(pd.Timestamp(date)))
            soc = float(daily.loc[daily.date == date, "initial_soc"].iloc[0])
            for repeat in (1, 2):
                order = (1, 3) if (date_index + repeat) % 2 else (3, 1)
                for percent in order:
                    trial = f"{date}_r{repeat}_{percent}pct"
                    context = {"date": date, "repeat": repeat, "gap_percent": percent, "trial": trial}
                    calls = []
                    write_json(raw_dir / "active.json", context)
                    started = time.perf_counter()
                    policy = None
                    try:
                        policy, _, _, _, audit = rolling.make_day(store, frozen, actual[:day], day, prices, soc, solver_gap=percent / 100)
                    except rolling.ComputationalLimit as error:
                        audit = error.details
                    elapsed = time.perf_counter() - started
                    assert [item["K"] for item in calls] == [1, 2, 3]
                    row = {**context, "initial_soc": soc, "day_wall_seconds": elapsed,
                           "accepted_candidates": sum(item["solver"]["reliable"] for item in calls),
                           "total_candidates": len(calls), "selected_K": audit.get("selected_K")}
                    if policy is not None:
                        frame = rolling.dispatch_frame(dates[day], policy, DT * (actual[day, :, 0] - actual[day, :, 1]), soc, prices)
                        write_csv(raw_dir / f"dispatch_{trial}.csv", frame)
                        row.update(planned_cost=float(frame.planned_cost.sum()), emergency_cost=float(frame.emergency_cost.sum()),
                                   actual_cost=float(frame.planned_cost.sum() + frame.emergency_cost.sum()),
                                   grid_kwh=float(frame.grid.sum()), emergency_kwh=float(frame.emergency.sum()),
                                   final_soc=float(frame.soc.iloc[-1]),
                                   first_day_expected_cost=audit[str(audit["selected_K"])]["first_day_expected_cost"])
                    summaries.append(row)
                    for item in calls:
                        info = item["solver"]
                        candidates.append({**context, "K": item["K"], "scenarios": item["scenarios"],
                                           "wall_seconds": item["wall_seconds"], "achieved_gap": info.get("mip_gap"),
                                           "accepted": info["reliable"], "status": info["status"],
                                           "objective": info.get("objective"), "dual_bound": info.get("dual_bound"),
                                           "input_sha256": item["input_sha256"]})
                    metadata["records"].append({**row, "calls": calls, "audit": audit})
                    write_json(raw_dir / "benchmark.json", metadata)
                    write_csv(processed / "summary.csv", pd.DataFrame(summaries))
                    write_csv(processed / "candidates.csv", pd.DataFrame(candidates))
                    print("COMPLETE", json.dumps(row), flush=True)
    finally:
        rolling._solve, rolling.solve_policy = original_solve, original_native
    assert all(sha256(ROOT / name) == digest for name, digest in hashes.items()), "正式源码或冻结配置在实验中改变"
    metadata.update(status="completed", finished_at=dt.datetime.now(dt.timezone.utc).isoformat(), protected_files_unchanged=True)
    write_json(raw_dir / "benchmark.json", metadata)
    (raw_dir / "active.json").unlink()


if __name__ == "__main__":
    main()
