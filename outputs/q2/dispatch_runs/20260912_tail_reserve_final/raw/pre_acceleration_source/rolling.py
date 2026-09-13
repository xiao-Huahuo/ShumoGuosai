"""最终方案2.9/2.10：先冻结首日策略，再逐步真实回放；求解受限显式记录。"""

import numpy as np
import pandas as pd
import json
import os
import time
from contextlib import contextmanager
from pathlib import Path

from comparators import deterministic_policy, rigid_schedule
from checkpoint import atomic_json, read_checkpoint, recover_checkpoint, save_checkpoint
from data import calendar_for_day, sha256, write_csv, write_json
from optimization import certify_policy, solve_policy
from relaxation import recourse_bound
from policy import DT, E_INITIAL, Policy, replay, validate_replay
from protocol import PROTOCOL
from scenarios import (construct, dynamic_reserve, eligible_origins, joint_blocks,
                       quantile_comparison, weighted_quantile)
from shadows import choose_day, combined


class ComputationalLimit(RuntimeError):
    def __init__(self, details):
        super().__init__("未获得满足预注册MIP gap及映射验收的策略；不得当正式解发布")
        self.details = details


def _solve(net, prices, weights, soc, *, reserve=None, solver_seconds=None,
           solver_gap=PROTOCOL["solver_gap"], **options):
    if not np.isfinite(solver_gap) or not 0 < solver_gap < 1:
        raise ValueError("求解精度门槛无效")
    if len(net) == 1:
        policy, responses, info = deterministic_policy(net[0], prices, soc, reserve=reserve)
        if policy is not None:
            return policy, responses, info
    mean = np.average(net, weights=weights, axis=0)
    seed, _, _ = deterministic_policy(mean, prices, soc, reserve=reserve)
    bound_policy, bound_responses, bound = recourse_bound(
        net, prices, weights, soc, target_gap=solver_gap, reserve=reserve)
    if bound["certified_gap"] <= solver_gap:
        return certify_policy(net, prices, weights, soc, bound_policy, bound_responses, bound, solver_gap)
    if seed is None or sum(p*(prices@(seed.grid+5*replay(seed, path, soc)["emergency"])) for p, path in zip(weights, net)) > bound["incumbent_cost"]:
        seed = bound_policy
    supplemental = solver_seconds is not None and solver_seconds > PROTOCOL["solver_seconds"]
    if not options and (supplemental or solver_gap > PROTOCOL["solver_gap"]):
        from linear_policy import solve_linear_policy
        policy, responses, info = solve_linear_policy(net, prices, weights, soc, gap=solver_gap,
                                                      time_limit=solver_seconds or PROTOCOL["solver_seconds"],
                                                      seed_policy=seed, reserve=reserve)
        info["execution_role"] = ("supplemental_equivalent_physical_bound_MILP_after_original_budget_failure" if supplemental
                                  else "original_budget_equivalent_MILP_under_authorized_precision_revision")
        return policy, responses, info
    return solve_policy(net, prices, weights, soc, gap=solver_gap,
                        time_limit=solver_seconds or PROTOCOL["solver_seconds"], seed_policy=seed,
                        known_lower_bound=bound["lower_bound"], reserve=reserve, **options)


def _pool_cost(policy, net, prices, soc):
    return float(np.mean([5*np.dot(prices[:144], replay(policy.first(), path[:144], soc)["emergency"]) for path in net]))


def select_resolution(point, blocks, prices, soc, *, origins=None, all_blocks=None,
                      all_origins=None, reserve=None, forced_count=None,
                      solver_seconds=None, solver_gap=PROTOCOL["solver_gap"]):
    construction = {"origins": origins, "all_blocks": all_blocks, "all_origins": all_origins,
                    "tail_fraction": PROTOCOL["tail_fraction"]}
    full_net, full_weights, _ = construct(point, blocks, prices, **construction)
    m = len(blocks)
    counts = [m] if m <= 40 else [10, 20, 40]
    if forced_count is not None and m > 40:
        counts = [min(m, forced_count)]
    results, audit = {}, {"M": m, "candidates": {}, "computational_limited": False}
    for count in counts:
        net, weights, scenario = construct(point, blocks, prices, count, **construction)
        policy, responses, info = _solve(net, prices, weights, soc, reserve=reserve,
                                         solver_seconds=solver_seconds, solver_gap=solver_gap)
        item = {"scenarios": scenario, "solver": info}
        if policy is not None:
            item["full_pool_first_day_emergency_cost"] = _pool_cost(policy, full_net, prices, soc)
            item["scenario_first_day_emergency_cost"] = float(sum(5*p*np.dot(prices[:144], r["emergency"][:144]) for p, r in zip(weights, responses)))
            item["tail_quantiles"] = quantile_comparison(full_net, net, weights)
        audit["candidates"][str(count)] = item
        if policy is not None and info["reliable"]:
            results[count] = (policy, responses, weights, net)
    if not results:
        raise ComputationalLimit(audit)
    selected = max(results)
    if m > 40 and forced_count is None:
        if 20 in results and 40 in results:
            j20, j40 = [audit["candidates"][str(s)]["solver"]["objective"] for s in (20, 40)]
            g20, g40 = results[20][0].grid[:144], results[40][0].grid[:144]
            dj = abs(j40-j20)/max(abs(j40), 1e-8)
            dg = float(np.abs(g40-g20).sum()/max(g40.sum(), 1e-8))
            audit.update(delta_J_20_40=dj, delta_g_20_40=dg)
            if dj <= PROTOCOL["stability_objective_relative"] and dg <= PROTOCOL["stability_grid_relative"]:
                selected = 20
        else:
            audit["computational_limited"] = True
        def tail_bad(count):
            entry = audit["candidates"][str(count)]
            quantile_bad = max(v["normalized_error"] for v in entry["tail_quantiles"].values()) > PROTOCOL["tail_quantile_relative"]
            reference = audit["candidates"].get("40", entry).get("full_pool_first_day_emergency_cost", 0)
            deterioration = (entry["full_pool_first_day_emergency_cost"]-reference)/max(reference, 1e-8)
            return quantile_bad or deterioration > PROTOCOL["full_pool_emergency_relative"]
        if selected == 20 and tail_bad(20) and 40 in results:
            selected = 40
        if selected == 40 and tail_bad(40):
            policy, responses, info = _solve(full_net, prices, full_weights, soc, reserve=reserve,
                                             solver_seconds=solver_seconds, solver_gap=solver_gap)
            audit["candidates"][str(m)] = {"solver": info, "scenarios": {"M": m, "S": m, "reduced": False}, "trigger": "tail_check_failed_at_40"}
            if policy is not None and info["reliable"]:
                results[m] = (policy, responses, full_weights, full_net)
                selected = m
            else:
                audit["computational_limited"] = True
                audit["tail_requirement_unresolved"] = True
    policy, responses, weights, net = results[selected]
    audit.update(S=selected, selected_solver=audit["candidates"][str(selected)]["solver"])
    return policy, responses, weights, net, audit


def make_day(store, frozen, history, d, prices, soc, *, horizon="auto", minimum=14,
             window="auto", forced_count=None, fixed_pair=None, kind="feedback",
             solver_seconds=None, progress_path=None, solver_gap=PROTOCOL["solver_gap"]):
    started = time.perf_counter()
    candidates = (2, 3, 1) if horizon == "auto" else (int(horizon),)
    results, audits = {}, {}
    for k in candidates:
        # K1只能在K2/K3全部失败时被选中；已有可靠长时域时不重复求K1。
        if horizon == "auto" and k == 1 and results:
            audits["skipped_K1"] = {"reason": "K2_or_K3_reliable_K1_cannot_change_selection"}
            continue
        if progress_path is not None:
            atomic_json(progress_path, {"day_index": d, "date": str((pd.Timestamp("2025-01-01")+pd.Timedelta(days=d)).date()),
                                       "K": k, "solver_gap": solver_gap, "solver_seconds": solver_seconds or PROTOCOL["solver_seconds"],
                                       "started_at": time.time(), "phase": "solving"})
        point, blocks, selection = choose_day(store, frozen, history, d, k, prices, minimum=minimum,
                                             window=window, fixed_pair=fixed_pair)
        selection["common_scored_origins"] = [int(j) for j in selection["common_scored_origins"]]
        price_horizon = np.tile(prices, k)
        if blocks is None:
            origins = all_origins = None
            all_blocks = None
            reserve_day = np.zeros(144)
            reserve_meta = {"quantile": PROTOCOL["reserve_quantile"], "historical_blocks": 0,
                            "max_reserve_kwh": 0., "mean_reserve_kwh": 0.}
        else:
            origins = np.asarray(selection["origin_indices"], dtype=int)
            forecasts = combined(store, selection["pipeline"])
            all_origins = eligible_origins(forecasts, d, k, minimum=minimum, window=None)
            all_blocks = joint_blocks(history, forecasts, all_origins, k)
            reserve_day, reserve_meta = dynamic_reserve(all_blocks, PROTOCOL["reserve_quantile"])
            selection["all_origin_indices"] = all_origins.tolist()
        reserve = np.r_[reserve_day, np.zeros(144*(k-1))]
        selection["dynamic_soc_reserve"] = reserve_meta
        try:
            if kind == "deterministic":
                net = DT*(point[..., 0]-point[..., 1]).reshape(1, -1)
                policy, responses, solver = _solve(net, price_horizon, np.array([1.]), soc,
                                                   reserve=reserve, solver_seconds=solver_seconds,
                                                   solver_gap=solver_gap)
                if policy is None or not solver["reliable"]:
                    raise ComputationalLimit(solver)
                weights = np.array([1.]); audit = {"M": len(blocks), "S": 1, "selected_solver": solver}
            elif kind == "rigid":
                if forced_count is None:
                    _, _, weights, net, audit = select_resolution(
                        point, blocks, price_horizon, soc, origins=origins, all_blocks=all_blocks,
                        all_origins=all_origins, reserve=reserve, solver_seconds=solver_seconds,
                        solver_gap=solver_gap)
                else:
                    net, weights, scenarios = construct(
                        point, blocks, price_horizon, forced_count, origins=origins,
                        all_blocks=all_blocks, all_origins=all_origins,
                        tail_fraction=PROTOCOL["tail_fraction"])
                    audit = {"M": len(blocks), "S": len(weights), "scenarios": scenarios}
                grid, responses, solver = rigid_schedule(net, price_horizon, weights, soc)
                policy = Policy(grid, responses[0]["charge"], responses[0]["discharge"])
                audit["selected_solver"] = solver
            else:
                policy, responses, weights, net, audit = select_resolution(point, blocks, price_horizon, soc,
                                                                          origins=origins, all_blocks=all_blocks,
                                                                          all_origins=all_origins, reserve=reserve,
                                                                          forced_count=forced_count,
                                                                          solver_seconds=solver_seconds,
                                                                          solver_gap=solver_gap)
        except ComputationalLimit as error:
            audits[str(k)] = {"selection": selection, "error": error.details}
            continue
        day_cost = float(prices@policy.grid[:144] + sum(5*p*(prices@r["emergency"][:144]) for p, r in zip(weights, responses)))
        audit.update(selection=selection, first_day_expected_cost=day_cost)
        audits[str(k)] = audit
        results[k] = (policy, weights, net, point)
    if not results:
        raise ComputationalLimit(audits)
    selected = max(results)
    if horizon == "auto" and 2 in results and 3 in results:
        g2, g3 = results[2][0].grid[:144], results[3][0].grid[:144]
        dg = float(np.abs(g2-g3).sum()/max(g3.sum(), 1e-8))
        c2, c3 = audits["2"]["first_day_expected_cost"], audits["3"]["first_day_expected_cost"]
        dc = abs(c2-c3)/max(abs(c3), 1e-8)
        audits["stability_48_72"] = {"grid_relative": dg, "first_day_expected_cost_relative": dc,
                                      "interpretation": "open_loop_first_day_stability_only"}
        if dg <= PROTOCOL["stability_grid_relative"] and dc <= PROTOCOL["stability_objective_relative"]:
            selected = 2
    audits["selected_K"] = selected
    audits["computational_limited"] = any(str(k) in audits and "error" in audits[str(k)] for k in candidates) or any(v.get("computational_limited", False) for v in audits.values() if isinstance(v, dict))
    audits["runtime_seconds"] = time.perf_counter()-started
    return *results[selected], audits


def dispatch_frame(date, policy, net, soc, prices, *, rigid=False):
    first = policy.first()
    if rigid:
        charge, discharge = first.charge_cap, first.discharge_cap
        gap = net+charge-first.grid-discharge
        response = {"charge": charge, "discharge": discharge, "emergency": np.maximum(gap, 0),
                    "unused": np.maximum(-gap, 0), "soc": soc+np.cumsum(.9*charge-discharge/.9)}
        validate_replay(first.grid, net, soc, response, rigid=True)
    else:
        response = replay(first, net, soc)
    frame = calendar_for_day(date)
    frame["day_of_year"] = pd.Timestamp(date).dayofyear
    frame["grid"] = first.grid
    frame["charge_cap"] = first.charge_cap
    frame["discharge_cap"] = first.discharge_cap
    frame["soc_reserve_kwh"] = first.reserve
    frame["net_kwh"] = net
    frame["initial_soc"] = soc
    frame["price"] = prices
    for key, value in response.items():
        frame[key] = value
    frame["planned_cost"] = prices*first.grid
    frame["emergency_cost"] = 5*prices*response["emergency"]
    return frame


def warm_start(actual, dates, prices, output):
    """1月仅积累预测/误差历史，储能不主动调度，2月1日SOC固定为6000kWh。"""
    if np.asarray(actual).shape[:2] != (365, 144) or len(dates) != 365 or len(prices) != 144:
        raise ValueError("1月历史预热输入不完整")
    write_csv(output/"warm_dispatch.csv", pd.DataFrame(columns=[
        "date", "charge", "discharge", "soc"]))
    write_json(output/"warm_start.json", {"initial_soc_jan1": E_INITIAL,
                                         "january_charge_kwh": 0.,
                                         "january_discharge_kwh": 0.,
                                         "prediction_history_days": 31,
                                         "feb1_baseline_soc": E_INITIAL,
                                         "interpretation": "paper_final_fixed_initialization_january_storage_inactive"})
    return E_INITIAL


@contextmanager
def _exclusive_run_lock(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        import msvcrt
        with path.open("a+b") as lock:
            if lock.seek(0, os.SEEK_END) == 0:
                lock.write(b"0"); lock.flush()
            lock.seek(0)
            try:
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as error:
                raise RuntimeError("该实验已有写入进程，拒绝并发覆盖检查点") from error
            try:
                yield
            finally:
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl
        with path.open("a", encoding="utf-8") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise RuntimeError("该实验已有写入进程，拒绝并发覆盖检查点") from error
            try:
                yield
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)


def run_rollout(store, frozen, actual, dates, prices, initial_soc, output, **settings):
    """每个实验仅允许一个写入者；不同实验可在独立目录并行。"""
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    with _exclusive_run_lock(output/"run.lock"):
        return _run_rollout(store, frozen, actual, dates, prices, initial_soc, output, **settings)


def _run_rollout(store, frozen, actual, dates, prices, initial_soc, output, *, start=31, end=None,
                 reference_audits=None, rescue_seconds=None, solver_gap=PROTOCOL["solver_gap"],
                 execution_revision=None, **settings):
    if not np.isfinite(solver_gap) or not 0 < solver_gap < 1:
        raise ValueError("求解精度门槛无效")
    output.mkdir(parents=True, exist_ok=True)
    recover_checkpoint(output)
    if rescue_seconds is not None and rescue_seconds <= PROTOCOL["solver_seconds"]:
        raise ValueError("追加计算预算必须大于原120秒，精度门槛保持不变")
    end = len(dates) if end is None else end
    source_hashes = {p.name: sha256(p) for p in Path(__file__).parent.glob("*.py")}
    soc, frames, daily, calibration = initial_soc, [], [], []
    resume_at = start
    if (output/"dispatch.csv").exists():
        previous, daily, calibration = read_checkpoint(output, actual, dates, prices, initial_soc, start, end, settings)
        completed = previous.date.nunique()
        frames = [previous]
        soc = float(previous.soc.iloc[-1]); resume_at += completed
        print(f"从已验收的{completed}日连续回放检查点续算", flush=True)
    previous_status = {}
    if (output/"run_status.json").exists():
        previous_status = json.loads((output/"run_status.json").read_text(encoding="utf-8"))
        if previous_status.get("failed_date"):
            atomic_json(output/f"failed_attempts/previous_status_{time.time_ns()}.json", previous_status)
    execution = {"base_solver_seconds": PROTOCOL["solver_seconds"], "rescue_seconds": rescue_seconds,
                 "rescue_trigger": "all_day_candidates_failed", "gap": solver_gap,
                 "interpretation": "supplementary_compute_not_retroactive_original_budget_success",
                 "tail_stratification": PROTOCOL["tail_stratification"],
                 "tail_fraction": PROTOCOL["tail_fraction"],
                 "dynamic_soc_reserve": PROTOCOL["dynamic_soc_reserve"],
                 "reserve_quantile": PROTOCOL["reserve_quantile"],
                 "evaluation_initial_soc_kwh": initial_soc}
    if solver_gap != PROTOCOL["solver_gap"] and not execution_revision:
        raise ValueError("非原精度续算必须携带显式执行修订摘要")
    if execution_revision:
        execution["precision_revision_sha256"] = execution_revision
    if solver_gap > PROTOCOL["solver_gap"]:
        execution["base_policy_solver"] = "equivalent_MILP_after_global_LP_certificate_attempt"
    if settings.get("horizon", "auto") == "auto" and reference_audits is None:
        execution["horizon_evaluation"] = "K2_K3_then_K1_only_if_both_fail"
    old_execution = previous_status.get("execution", {})
    if daily and old_execution.get("gap", PROTOCOL["solver_gap"]) > solver_gap:
        raise ValueError("更严格精度不能直接沿用较宽门槛的历史，需独立复核")
    history = previous_status.get("execution_history", [])
    if old_execution and old_execution != execution:
        history = [*history, {"execution": old_execution, "completed_days": len(daily),
                             "next_date": str(dates[resume_at].date()) if resume_at < end else None}]
    status_base = {"settings": settings, "start_index": start, "end_index": end,
                   "execution": execution, "execution_history": history}
    atomic_json(output/"run_status.json", {"complete": False, **status_base})
    for d in range(resume_at, end):
        daily_settings = dict(settings)
        if reference_audits is not None:
            reference = json.loads((reference_audits/f"{pd.Timestamp(dates[d]).date()}.json").read_text(encoding="utf-8"))
            chosen = reference[str(reference["selected_K"])]
            daily_settings.update(horizon=reference["selected_K"], forced_count=chosen["S"],
                                  fixed_pair=chosen["selection"]["pipeline"])
        try:
            try:
                policy, weights, net_scenarios, point, audit = make_day(
                    store, frozen, actual[:d], d, prices, soc, progress_path=output/"active_solve.json", solver_gap=solver_gap, **daily_settings)
            except ComputationalLimit as original:
                atomic_json(output/f"failed_attempts/{dates[d].date()}_base_{time.time_ns()}.json",
                            {"date": str(dates[d]), "solver_seconds": PROTOCOL["solver_seconds"], "details": original.details})
                if rescue_seconds is None:
                    raise
                print(f"{dates[d].date()} 原预算全候选受限，追加{rescue_seconds:g}秒预算，gap为{solver_gap:.0%}", flush=True)
                policy, weights, net_scenarios, point, audit = make_day(
                    store, frozen, actual[:d], d, prices, soc, solver_seconds=rescue_seconds,
                    progress_path=output/"active_solve.json", solver_gap=solver_gap, **daily_settings)
                audit.update(original_budget_failure=original.details, supplemental_solver_seconds=rescue_seconds,
                             computational_limited=True)
        except ComputationalLimit as error:
            atomic_json(output/"run_status.json", {"complete": False, **status_base,
                                                  "failed_date": str(dates[d]), "reason": str(error), "solver_details": error.details})
            atomic_json(output/"active_solve.json", {"date": str(dates[d].date()), "phase": "failed"})
            raise
        audit["execution"] = execution
        audit["source_sha256_at_rollout_start"] = source_hashes
        atomic_json(output/f"daily_audit/{pd.Timestamp(dates[d]).date()}.json", audit)
        write_csv(output/f"frozen_plans/{pd.Timestamp(dates[d]).date()}.csv", pd.DataFrame({
            "step": np.arange(len(policy.grid)), "grid": policy.grid,
            "charge_cap": policy.charge_cap, "discharge_cap": policy.discharge_cap,
            "soc_reserve_kwh": policy.reserve,
            "role": np.where(np.arange(len(policy.grid)) < 144, "first_day_frozen", "open_loop_proxy_only")}))
        # 到此之前当日actual[d]未进入任何选模、场景或求解调用。
        net = DT*(actual[d, :, 0]-actual[d, :, 1])
        frame = dispatch_frame(dates[d], policy, net, soc, prices, rigid=settings.get("kind") == "rigid")
        frame["predicted_load_kw"] = point[0, :, 0]
        frame["predicted_pv_kw"] = point[0, :, 1]
        frames.append(frame)
        selected_k = audit["selected_K"]
        selected = audit[str(selected_k)]
        selected_count = selected.get("S", len(weights))
        scenario_meta = selected.get("candidates", {}).get(
            str(selected_count), {}).get("scenarios", {})
        selected_solver = selected["selected_solver"]
        daily.append({"date": str(pd.Timestamp(dates[d]).date()), "K": selected_k,
                      "M": selected["M"], "S": len(weights),
                      "initial_soc": soc, "final_soc": float(frame.soc.iloc[-1]),
                      "min_soc": float(frame.soc.min()),
                      "planned_grid_kwh": float(frame.grid.sum()),
                      "planned_cost": float(frame.planned_cost.sum()),
                      "emergency_cost": float(frame.emergency_cost.sum()),
                      "cost": float(frame.planned_cost.sum()+frame.emergency_cost.sum()),
                      "emergency_kwh": float(frame.emergency.sum()),
                      "unused_kwh": float(frame.unused.sum()),
                      "charge_kwh": float(frame.charge.sum()),
                      "discharge_kwh": float(frame.discharge.sum()),
                      "tail_scenario_count": scenario_meta.get("S_tail", 0),
                      "body_scenario_count": scenario_meta.get("S_body", len(weights)),
                      "max_reserve_kwh": float(policy.reserve[:144].max()),
                      "mean_reserve_kwh": float(policy.reserve[:144].mean()),
                      "requested_mip_gap": selected_solver.get("requested_gap", solver_gap),
                      "achieved_mip_gap": selected_solver.get("mip_gap", 0.),
                      "runtime_seconds": audit.get("runtime_seconds", 0.),
                      "solver_status": selected_solver.get("status", "test_double"),
                      "computational_limited": audit["computational_limited"]})
        for h in range(min(selected_k, len(dates)-d)):
            realized = DT*(actual[d+h, :, 0]-actual[d+h, :, 1])
            scenario = net_scenarios[:, h*144:(h+1)*144]
            for nominal, low, high in ((.8, .1, .9), (.9, .05, .95)):
                lower, upper = weighted_quantile(scenario, weights, low), weighted_quantile(scenario, weights, high)
                calibration.append({"origin": str(pd.Timestamp(dates[d]).date()), "horizon": h, "nominal": nominal,
                                    "covered_intervals": int(((realized >= lower)&(realized <= upper)).sum()),
                                    "n": 144, "picp": float(((realized >= lower)&(realized <= upper)).mean())})
        soc = float(frame.soc.iloc[-1])
        save_checkpoint(output, pd.concat(frames, ignore_index=True), daily, calibration)
        print(f"真实回放 {pd.Timestamp(dates[d]).date()} K={selected_k} S={len(weights)} SOC={soc:.3f}", flush=True)
    atomic_json(output/"run_status.json", {"complete": True, **status_base, "days": len(daily),
                                         "initial_soc": initial_soc, "final_soc": soc,
                                         "full_evaluation_period": start == 31 and end == 365})
    atomic_json(output/"active_solve.json", {"phase": "complete", "days": len(daily)})
    return pd.concat(frames, ignore_index=True), pd.DataFrame(daily)
