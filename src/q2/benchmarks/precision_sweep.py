"""同一真实日、相同求解路线的1%—5%限时比较；不修改正式执行。"""

import datetime as dt
import hashlib
import io
import json
from pathlib import Path
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
    output = run / "raw/solver_diagnostics" / dt.datetime.now().strftime("precision_sweep_%Y%m%d_%H%M%S")
    output.mkdir()
    date = "2025-05-05"
    sources = {str(p.relative_to(ROOT)): sha256(p) for p in (ROOT / "src/q2").glob("*.py")}
    precision_hash = sha256(run / "raw/solver_precision_revision.json")
    store, frozen, actual, dates, prices = load_prepared(run)
    directory = run / "processed/main"
    for _ in range(10):
        checkpoint = (directory / "checkpoint.json").read_bytes()
        raw = (directory / "daily.csv").read_bytes()
        if (checkpoint == (directory / "checkpoint.json").read_bytes()
                and hashlib.sha256(raw).hexdigest() == json.loads(checkpoint)["sha256"]["daily.csv"]):
            break
    else:
        raise RuntimeError("未取得稳定的已提交逐日表")
    daily = pd.read_csv(io.BytesIO(raw), float_precision="round_trip")
    old = json.loads((directory / f"daily_audit/{date}.json").read_text(encoding="utf-8"))
    soc = float(daily.loc[daily.date == date, "initial_soc"].iloc[0])
    day = int(dates.get_loc(pd.Timestamp(date)))
    records, summary, candidate_rows, input_hashes = [], [], [], {}
    metadata = {
        "status": "running", "date": date, "initial_soc": soc,
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "candidate_time_limit_seconds": 120, "supplemental_retries": False,
        "gap_order_percent": [3, 4, 5, 2, 1], "official_gap_unchanged": .02,
        "source_sha256": sources, "benchmark_source_sha256": sha256(Path(__file__)),
        "official_precision_sha256": precision_hash,
        "timing_scope": "make_day_K1_K2_K3_including_selection_and_validation_excluding_shared_library_load_and_final_actual_replay",
        "same_algorithm": "original_LP_certificate_then_existing_equivalent_HiGHS_MILP_for_all_gaps",
        "one_percent_difference_from_legacy": "isolated_native_fallback_redirected_to_same_current_equivalent_MILP; production_1pct_route_not_changed",
        "limitations": "one_day_one_trial_per_gap_with_two_live_official_workers; censored_failures_are_not_time_to_success; not_an_annual_ETA",
        "records": records,
    }
    write_json(output / "benchmark.json", metadata)
    original_solve, original_native = rolling._solve, rolling.solve_policy
    calls = []

    def same_linear(net, price, weights, initial, *, gap, time_limit, seed_policy, known_lower_bound):
        # 原1%入口会调用native；仅在本隔离进程统一算法，避免把算法差异当精度效应。
        return solve_linear_policy(net, price, weights, initial, gap=gap,
                                   time_limit=time_limit, seed_policy=seed_policy)

    def timed_solve(net, price, weights, initial, **kwargs):
        k = len(price) // 144
        digest = hashlib.sha256()
        for value in (net, price, weights, np.array([initial])):
            array = np.ascontiguousarray(value, dtype=np.float64)
            digest.update(str(array.shape).encode("utf-8")); digest.update(array.tobytes())
        fingerprint = digest.hexdigest()
        assert fingerprint == input_hashes.setdefault(k, fingerprint), "不同精度输入不一致"
        started = time.perf_counter()
        policy, responses, info = original_solve(net, price, weights, initial, **kwargs)
        elapsed = time.perf_counter() - started
        if policy is not None:
            for path, response in zip(net, responses):
                validate_replay(policy.grid, path, initial, response)
        if info["reliable"]:
            assert policy is not None and info["mip_gap"] <= kwargs["solver_gap"] + 1e-8
        call = {"K": k, "input_sha256": fingerprint, "wall_seconds": elapsed, "solver": info}
        calls.append(call)
        print(json.dumps({"gap_percent": 100 * kwargs["solver_gap"], "K": k,
                          "seconds": elapsed, "reliable": info["reliable"], "gap": info.get("mip_gap")}), flush=True)
        return policy, responses, info

    rolling.solve_policy, rolling._solve = same_linear, timed_solve
    try:
        for percent in metadata["gap_order_percent"]:
            calls = []
            started = time.perf_counter()
            policy = None
            try:
                policy, _, _, _, audit = rolling.make_day(
                    store, frozen, actual[:day], day, prices, soc, solver_gap=percent / 100)
            except rolling.ComputationalLimit as error:
                audit = error.details
            wall = time.perf_counter() - started
            assert len(calls) == 3 and [c["K"] for c in calls] == [1, 2, 3]
            for k in ("1", "2", "3"):
                assert audit[k]["selection"] == old[k]["selection"]
                new_k, old_k = audit[k].get("error", audit[k]), old[k].get("error", old[k])
                assert new_k["M"] == old_k["M"]
                for count, entry in new_k["candidates"].items():
                    assert entry["scenarios"] == old_k["candidates"][count]["scenarios"]
            accepted = sum(c["solver"]["reliable"] for c in calls)
            row = {"gap_percent": percent, "day_wall_seconds": wall,
                   "accepted_candidates": accepted, "total_candidates": 3,
                   "all_candidates_passed": accepted == 3, "selected_K": audit.get("selected_K"),
                   "K1_seconds": calls[0]["wall_seconds"], "K2_seconds": calls[1]["wall_seconds"],
                   "K3_seconds": calls[2]["wall_seconds"]}
            for call in calls:
                info = call["solver"]
                candidate_rows.append({"gap_percent": percent, "K": call["K"],
                                       "wall_seconds": call["wall_seconds"], "solver_seconds": info["solve_seconds"],
                                       "achieved_gap": info.get("mip_gap"), "accepted": info["reliable"],
                                       "status": info["status"], "objective": info.get("objective"),
                                       "dual_bound": info.get("dual_bound")})
            if policy is not None:
                frame = rolling.dispatch_frame(dates[day], policy, DT * (actual[day, :, 0] - actual[day, :, 1]), soc, prices)
                row.update(actual_day_cost=float(frame.planned_cost.sum() + frame.emergency_cost.sum()),
                           final_soc=float(frame.soc.iloc[-1]))
                write_csv(output / f"policy_{percent}pct.csv", pd.DataFrame({
                    "grid": policy.grid, "charge_cap": policy.charge_cap, "discharge_cap": policy.discharge_cap}))
            summary.append(row); records.append({**row, "calls": calls, "audit": audit})
            write_json(output / "benchmark.json", metadata)
            write_csv(output / "summary.csv", pd.DataFrame(summary).sort_values("gap_percent"))
            write_csv(output / "candidates.csv", pd.DataFrame(candidate_rows).sort_values(["gap_percent", "K"]))
            print("COMPLETE", json.dumps(row), flush=True)
    finally:
        rolling._solve, rolling.solve_policy = original_solve, original_native
    assert all(sha256(ROOT / name) == digest for name, digest in sources.items())
    assert sha256(run / "raw/solver_precision_revision.json") == precision_hash
    metadata.update(status="completed", finished_at=dt.datetime.now(dt.timezone.utc).isoformat(),
                    input_sha256_by_K=input_hashes)
    write_json(output / "benchmark.json", metadata)
    print("RESULT_DIRECTORY", output, flush=True)


if __name__ == "__main__":
    main()
