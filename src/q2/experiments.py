"""最终方案2.10的可复现检验；未运行/计算受限的实验显式留状态而不填零。"""

import json
import hashlib
from pathlib import Path
import time

import numpy as np
import pandas as pd

from comparators import oracle_pair
from data import sha256, write_csv, write_json
from checkpoint import atomic_json
from baseline_reuse import main_baselines, reuse_main_baseline
from dispatch import load_prepared
from export_dispatch import emergency_events, summary, validate_dispatch, write_tables
from forecast import economic_metrics
from optimization import certify_policy, solve_policy
from incumbent import refine
from relaxation import recourse_bound
from policy import DT, ETA_C, ETA_D, PHYSICAL_TOL, Policy, replay
from protocol import PROTOCOL
from rolling import ComputationalLimit, _solve, dispatch_frame, run_rollout, warm_start
from scenarios import construct, eligible_origins, weighted_quantile
from shadows import combined, choose_day


def forecast_audit(store, frozen, actual, dates, prices, output):
    metrics, distribution, dependencies = [], [], []
    for name, prediction in store.items():
        variable = 0 if name.startswith("load") else 1
        for h in range(3):
            origins = np.arange(31, len(dates)-h)
            origins = origins[np.isfinite(prediction[origins, h]).all(axis=1)]
            if not len(origins):
                continue
            errors = actual[origins+h, :, variable]-prediction[origins, h]
            flat = errors.ravel()
            metrics.append({"model": name, "horizon": h, "n": flat.size, "mae_kw": float(np.abs(flat).mean()),
                            "rmse_kw": float(np.sqrt(np.mean(flat**2))), "role": "posthoc_never_online_selection"})
            distribution.append({"model": name, "horizon": h, "origins": len(origins), "mean_kw": float(flat.mean()),
                                 "std_kw": float(flat.std(ddof=1)), **{f"q{q:g}_kw": float(np.quantile(flat, q)) for q in (.1, .5, .8, .9)}})
            for lag in (1, 6, 12):
                dependencies.append({"pipeline": name, "horizon": h, "kind": f"within_day_lag_{lag}",
                                     "correlation": _corr(errors[:, :-lag], errors[:, lag:])})
    for pair in (("load_week", "pv_mean7"), ("load_week", "pv_dhr"),
                 (f"load_lgb_{frozen}", "pv_mean7"), (f"load_lgb_{frozen}", "pv_dhr")):
        prediction = combined(store, pair)
        origins = eligible_origins(prediction, len(actual), 3, minimum=1)
        origins = origins[origins >= 31]
        if not len(origins):
            continue
        blocks = np.stack([actual[j:j+3]-prediction[j] for j in origins])
        for h in range(3):
            metrics.append({"model": "|".join(pair), "horizon": h, "n": len(origins)*144,
                            **economic_metrics(actual[origins+h], prediction[origins, h], prices)})
            dependencies.append({"pipeline": "|".join(pair), "horizon": h, "kind": "load_pv_joint",
                                 "correlation": _corr(blocks[:, h, :, 0], blocks[:, h, :, 1])})
            if h < 2:
                net_error = blocks[..., 0]-blocks[..., 1]
                dependencies.append({"pipeline": "|".join(pair), "horizon": h, "kind": "same_origin_cross_day",
                                     "correlation": _corr(net_error[:, h], net_error[:, h+1])})
    rows = []
    for d in range(31, len(actual)):
        direct = actual[d-7, :, 0]-actual[d-7, :, 1]
        separate = store["load_week"][d, 0]-store["pv_mean7"][d, 0]
        real = actual[d, :, 0]-actual[d, :, 1]
        for name, predicted in (("direct_net_week", direct), ("separate_strong_baselines", separate)):
            demand, forecast = np.maximum(real*DT, 0), np.maximum(predicted*DT, 0)
            loss = prices*(np.maximum(forecast-demand, 0)+4*np.maximum(demand-forecast, 0))
            rows.append({"date": str(dates[d].date()), "path": name, "n": 144,
                         "absolute_error_sum_kw": float(np.abs(predicted-real).sum()),
                         "squared_error_sum_kw2": float(np.sum((predicted-real)**2)), "econ_loss_sum": float(loss.sum())})
    write_csv(output/"forecast_metrics.csv", pd.DataFrame(metrics))
    write_csv(output/"horizon_error_statistics.csv", pd.DataFrame(distribution))
    write_csv(output/"error_dependencies.csv", pd.DataFrame(dependencies))
    write_csv(output/"direct_net_forecast_comparison.csv", pd.DataFrame(rows))


def _corr(a, b):
    a, b = np.asarray(a).ravel(), np.asarray(b).ravel()
    return float(np.corrcoef(a, b)[0, 1]) if a.std() > 0 and b.std() > 0 else None


def scenario_audit(store, actual, dates, prices, directory):
    """从冻结预测、原origin块及实际medoid索引复现分布；不重新选模或求解。"""
    if not (directory/"dispatch.csv").exists() or not (directory/"daily_audit").exists():
        return
    executed = pd.read_csv(directory/"dispatch.csv", parse_dates=["date"], float_precision="round_trip")
    rigid = json.loads((directory/"run_status.json").read_text(encoding="utf-8")).get("settings", {}).get("kind") == "rigid"
    rows, profiles, states = [], [], []
    observed_dates = pd.DatetimeIndex(executed.date.unique())
    representative = {observed_dates[0], observed_dates[-1]} | set(pd.Timestamp(d) for d in PROTOCOL["specified_dates"])
    for date in observed_dates:
        audit = json.loads((directory/f"daily_audit/{date.date()}.json").read_text(encoding="utf-8"))
        k = audit["selected_K"]; entry = audit[str(k)]; selection = entry["selection"]
        d = dates.get_loc(date); origins = selection["origin_indices"]
        if any(j+k > d for j in origins):
            raise ValueError("事后审计发现场景误差块使用了当时尚未实现的数据")
        forecasts = combined(store, selection["pipeline"])
        point = forecasts[d, :k]
        blocks = np.stack([actual[j:j+k]-forecasts[j, :k] for j in origins])
        all_origins = selection.get("all_origin_indices", origins)
        all_blocks = np.stack([actual[j:j+k]-forecasts[j, :k] for j in all_origins])
        full, full_weights, _ = construct(
            point, blocks, np.tile(prices, k), origins=origins,
            all_blocks=all_blocks, all_origins=all_origins,
            tail_fraction=PROTOCOL["tail_fraction"])
        scenario = entry.get("scenarios", entry.get("candidates", {}).get(str(entry["S"]), {}).get("scenarios", {}))
        weights = np.asarray(scenario.get("weights", full_weights))
        selected_origins = scenario.get("selected_origin_indices")
        if selected_origins is None:
            net = full[scenario.get("indices", list(range(len(full))))]
        else:
            selected_blocks = np.stack([actual[j:j+k]-forecasts[j, :k] for j in selected_origins])
            values = np.maximum(point[None]+selected_blocks, 0)
            net = DT*(values[..., 0]-values[..., 1]).reshape(len(selected_origins), -1)
        if entry["S"] == 1 and len(full) > 1:
            net = DT*(point[..., 0]-point[..., 1]).reshape(1, -1); weights = np.ones(1)
        mean = np.average(net, weights=weights, axis=0)
        std = np.sqrt(np.average((net-mean)**2, weights=weights, axis=0))
        full80, full90 = [weighted_quantile(full, full_weights, q) for q in (.8, .9)]
        q80, q90 = [weighted_quantile(net, weights, q) for q in (.8, .9)]
        for h in range(k):
            cut = slice(144*h, 144*(h+1))
            rows.append({"origin": str(date.date()), "horizon": h, "M": len(full), "S": len(net),
                         "mean_net_kwh": float(mean[cut].mean()), "mean_timewise_variance_kwh2": float((std[cut]**2).mean()),
                         "full_Q80_mean_kwh": float(full80[cut].mean()), "reduced_Q80_mean_kwh": float(q80[cut].mean()),
                         "full_Q90_mean_kwh": float(full90[cut].mean()), "reduced_Q90_mean_kwh": float(q90[cut].mean()),
                         "positive_Q90_tail_underestimate_kwh": float(np.maximum(full90[cut]-q90[cut], 0).mean()),
                         "expected_objective_yuan_all_horizons": entry["selected_solver"]["objective"]})
        profiles.append(pd.DataFrame({"origin": str(date.date()), "step": np.arange(144*k), "horizon": np.arange(144*k)//144,
                                      "mean_net_kwh": mean, "std_net_kwh": std, "full_Q80_kwh": full80,
                                      "reduced_Q80_kwh": q80, "full_Q90_kwh": full90, "reduced_Q90_kwh": q90}))
        if date in representative:
            frozen = pd.read_csv(directory/f"frozen_plans/{date.date()}.csv", float_precision="round_trip")
            reserve = frozen.soc_reserve_kwh if "soc_reserve_kwh" in frozen else None
            policy = Policy(frozen.grid, frozen.charge_cap, frozen.discharge_cap, reserve)
            initial = float(executed[executed.date == date].initial_soc.iloc[0])
            if rigid:
                fixed_soc = initial+np.cumsum(ETA_C*policy.charge_cap-policy.discharge_cap/ETA_D)
                scenario_soc = np.tile(fixed_soc, (len(net), 1))
            else:
                scenario_soc = np.array([replay(policy, path, initial)["soc"] for path in net])
            states.append(pd.DataFrame({"origin": str(date.date()), "step": np.arange(k*144),
                                        "mean_scenario_soc_kwh": np.average(scenario_soc, weights=weights, axis=0),
                                        "scenario_soc_Q10_kwh": weighted_quantile(scenario_soc, weights, .1),
                                        "scenario_soc_Q90_kwh": weighted_quantile(scenario_soc, weights, .9)}))
    write_csv(directory/"scenario_distribution.csv", pd.DataFrame(rows))
    write_csv(directory/"scenario_profiles.csv", pd.concat(profiles, ignore_index=True))
    write_csv(directory/"scenario_soc_representative.csv", pd.concat(states, ignore_index=True))


def no_storage_quantile(store, frozen, actual, dates, prices, output):
    records = []
    for d in range(31, len(dates)):
        point, blocks, _ = choose_day(store, frozen, actual[:d], d, 1, prices)
        net, weights, _ = construct(point, blocks, prices)
        demand = np.maximum(net, 0)
        policies = {"point_forecast": np.maximum(DT*(point[0, :, 0]-point[0, :, 1]), 0),
                    "conditional_empirical_mean": np.average(demand, weights=weights, axis=0),
                    "empirical_Q80": weighted_quantile(demand, weights, .8)}
        real = np.maximum(DT*(actual[d, :, 0]-actual[d, :, 1]), 0)
        for name, grid in policies.items():
            records.append({"date": str(dates[d].date()), "method": name,
                            "actual_cost_yuan": float(prices@(grid+5*np.maximum(real-grid, 0))),
                            "empirical_expected_cost_yuan": float(prices@grid+sum(5*p*(prices@np.maximum(path-grid, 0)) for p, path in zip(weights, demand))),
                            "emergency_kwh": float(np.maximum(real-grid, 0).sum())})
    write_csv(output/"no_storage_quantile.csv", pd.DataFrame(records))


def structural_rollout(actual, dates, prices, initial_soc, output, *, direct):
    """结构对照在相同K=2、同一确定性反馈调度器和初态下仅改变净负荷预测路径。"""
    from forecast import seasonal
    if (output/"summary.json").exists():
        saved = pd.read_csv(output/"dispatch.csv", parse_dates=["date", "timestamp"], float_precision="round_trip")
        design = json.loads((output/"design.json").read_text(encoding="utf-8"))
        validate_dispatch(saved, full_period=True)
        if design != {"direct_net": direct, "K": 2, "uncertainty": "held_deterministic_for_structure_isolation", "initial_soc": initial_soc}:
            raise ValueError("结构对照缓存条件不符")
        np.testing.assert_allclose(saved.net_kwh, DT*(actual[31:, :, 0]-actual[31:, :, 1]).ravel(), atol=1e-5, rtol=0)
        return saved
    soc, frames = initial_soc, []
    for d in range(31, len(dates)):
        if direct:
            point_net = np.concatenate([actual[d-7+h, :, 0]-actual[d-7+h, :, 1] for h in range(2)])*DT
        else:
            point = seasonal(actual[:d], 2)
            point_net = DT*(point[..., 0]-point[..., 1]).ravel()
        policy, _, info = _solve(point_net[None], np.tile(prices, 2), np.ones(1), soc)
        if policy is None or not info["reliable"]:
            raise ComputationalLimit({"date": str(dates[d]), "solver": info})
        frame = dispatch_frame(dates[d], policy, DT*(actual[d, :, 0]-actual[d, :, 1]), soc, prices)
        frames.append(frame); soc = float(frame.soc.iloc[-1])
    result = pd.concat(frames, ignore_index=True)
    write_csv(output/"dispatch.csv", result)
    write_tables(result, output)
    write_json(output/"design.json", {"direct_net": direct, "K": 2, "uncertainty": "held_deterministic_for_structure_isolation", "initial_soc": initial_soc})
    return result


def richer_context(net, weights, prices, soc, audit_path, plan_path):
    digest = hashlib.sha256()
    for values in (net, weights, prices, [soc]):
        array = np.asarray(values, dtype="<f8")
        digest.update(str(array.shape).encode("utf-8")); digest.update(array.tobytes())
    return {"scenario_input_sha256": digest.hexdigest(), "main_audit_sha256": sha256(audit_path),
            "main_policy_sha256": sha256(plan_path),
            "solver_sources": {name: sha256(Path(__file__).parent/name)
                               for name in ("policy.py", "optimization.py", "incumbent.py", "relaxation.py")}}


def save_richer_policy(output, record, policy, context):
    """策略CSV先以唯一文件名写完，最后原子提交逐日期收据，旧收据不会指向半份文件。"""
    date = record["date"]
    path = output/f"richer_soc/{date}_{time.time_ns()}_policy.csv"
    columns = {"grid": policy.grid}
    for key, caps in (("charge_cap", policy.charge_cap), ("discharge_cap", policy.discharge_cap)):
        columns.update({f"{key}_{k}": caps[:, k] for k in range(3)})
    write_csv(path, pd.DataFrame(columns))
    saved = {**record, "context": context, "policy_file": str(path.relative_to(output)), "policy_sha256": sha256(path)}
    atomic_json(output/f"richer_soc/{date}.json", saved)
    return saved


def load_richer_policy(output, date, context, net, prices, weights, soc, *, solver_gap=PROTOCOL["solver_gap"]):
    path = output/f"richer_soc/{date}.json"
    if not path.exists():
        return None
    saved = json.loads(path.read_text(encoding="utf-8"))
    if not saved["solver"]["reliable"]:
        return None
    if saved["context"] != context:
        raise ValueError("已完成的SOC分段对照与当前主策略/场景/源码不一致，禁止混用")
    policy_path = output/saved["policy_file"]
    if sha256(policy_path) != saved["policy_sha256"]:
        raise ValueError("SOC分段策略存档摘要不符，禁止复用损坏策略")
    frame = pd.read_csv(policy_path, float_precision="round_trip")
    if len(frame) != len(prices):
        raise ValueError("SOC分段策略的完整前瞻长度不符")
    policy = Policy(frame.grid, frame[[f"charge_cap_{k}" for k in range(3)]].to_numpy(),
                    frame[[f"discharge_cap_{k}" for k in range(3)]].to_numpy())
    responses = [replay(policy, row, soc) for row in net]
    cost = float(prices@policy.grid+sum(5*p*(prices@row["emergency"]) for p, row in zip(weights, responses)))
    np.testing.assert_allclose(cost, saved["solver"]["objective"], atol=PHYSICAL_TOL, rtol=0)
    lower = saved["solver"]["dual_bound"]
    if lower > cost+PHYSICAL_TOL or max(cost-lower, 0)/max(abs(lower), 1e-8) > solver_gap+1e-8:
        raise ValueError("SOC分段策略存档的费用与当前精度证书不一致")
    return policy, saved


def richer_real_metrics(policy, net, prices, soc, main_day):
    response = replay(policy.first(), net, soc)
    actual_frame = pd.DataFrame({"timestamp": main_day.timestamp.to_numpy(), "emergency": response["emergency"],
                                 "emergency_cost": 5*prices*response["emergency"]})
    return {"actual_cost": float(prices@(policy.grid[:144]+5*response["emergency"])),
            "emergency_kwh": float(response["emergency"].sum()), "final_soc": float(response["soc"][-1]),
            "emergency_events": len(emergency_events(actual_frame)),
            "main_actual_cost": float((main_day.planned_cost+main_day.emergency_cost).sum()),
            "main_emergency_kwh": float(main_day.emergency.sum()),
            "main_emergency_events": len(emergency_events(main_day)), "main_final_soc": float(main_day.soc.iloc[-1])}


def richer_policy_diagnostic(store, frozen, actual, dates, prices, main, output, *, rescue_seconds=None, solver_gap=PROTOCOL["solver_gap"], execution_revision=None):
    frame = pd.read_csv(main/"dispatch.csv", parse_dates=["date", "timestamp"], float_precision="round_trip")
    volatility = np.std(np.diff(actual[31:, :, 0]-actual[31:, :, 1], axis=1), axis=1)
    varied = dates[31:][np.argsort(-volatility, kind="stable")[:PROTOCOL["high_variation_dates_count"]]]
    targets = sorted(set(pd.Timestamp(d) for d in PROTOCOL["specified_dates"]) | set(varied))
    records = []
    for date in targets:
        d = dates.get_loc(date)
        audit_path = main/f"daily_audit/{date.date()}.json"
        plan_path = main/f"frozen_plans/{date.date()}.csv"
        reference = json.loads(audit_path.read_text(encoding="utf-8"))
        k = reference["selected_K"]; selected = reference[str(k)]
        soc = float(frame[frame.date == date].initial_soc.iloc[0])
        point, blocks, _ = choose_day(store, frozen, actual[:d], d, k, prices,
                                     fixed_pair=selected["selection"]["pipeline"])
        net, weights, _ = construct(point, blocks, np.tile(prices, k), selected["S"])
        context = richer_context(net, weights, np.tile(prices, k), soc, audit_path, plan_path)
        main_day = frame[frame.date == date]
        cached = load_richer_policy(output, str(date.date()), context, net, np.tile(prices, k), weights, soc, solver_gap=solver_gap)
        if cached is not None:
            policy, record = cached
            actual_metrics = richer_real_metrics(policy, DT*(actual[d, :, 0]-actual[d, :, 1]), prices, soc, main_day)
            for key, value in actual_metrics.items():
                np.testing.assert_allclose(value, record[key], atol=PHYSICAL_TOL, rtol=0)
            records.append(record)
            atomic_json(output/"richer_soc_policy.json", {"records": records, "complete": len(records) == len(targets),
                                                        "reliable_all": all(v["solver"]["reliable"] for v in records)})
            continue
        frozen_plan = pd.read_csv(plan_path, float_precision="round_trip")
        base = Policy(frozen_plan.grid, frozen_plan.charge_cap, frozen_plan.discharge_cap)
        rich_seed = Policy(base.grid, np.repeat(base.charge_cap[:, None], 3, axis=1),
                           np.repeat(base.discharge_cap[:, None], 3, axis=1))
        rich, refinement = refine(rich_seed, net, np.tile(prices, k), weights, soc)
        _, _, bound = recourse_bound(net, np.tile(prices, k), weights, soc, target_gap=solver_gap)
        responses = [replay(rich, path, soc) for path in net]
        cost = float(np.tile(prices, k)@rich.grid+sum(5*p*(np.tile(prices, k)@r["emergency"]) for p, r in zip(weights, responses)))
        bound.update(incumbent_cost=cost, certified_gap=max(cost-bound["lower_bound"], 0)/max(abs(bound["lower_bound"]), 1e-8),
                     rich_refinement=refinement, seconds=bound["seconds"]+refinement["seconds"])
        if bound["certified_gap"] <= solver_gap:
            policy, _, solver = certify_policy(net, np.tile(prices, k), weights, soc, rich, responses, bound, solver_gap)
        else:
            policy, _, solver = solve_policy(net, np.tile(prices, k), weights, soc, seed_policy=rich,
                                             known_lower_bound=bound["lower_bound"],
                                             gap=solver_gap, time_limit=PROTOCOL["solver_seconds"], segments=3)
            if not solver["reliable"] and rescue_seconds is not None:
                original = solver
                atomic_json(output/f"richer_soc_attempts/{date.date()}_base_{time.time_ns()}.json", original)
                policy, _, solver = solve_policy(net, np.tile(prices, k), weights, soc,
                                                 seed_policy=policy if policy is not None else rich,
                                                 known_lower_bound=bound["lower_bound"],
                                                 gap=solver_gap, time_limit=rescue_seconds, segments=3)
                solver["original_budget_failure"] = original
        record = {"date": str(date.date()), "K": k, "S": len(weights), "solver": solver,
                  "same_information": True, "used_to_change_main": False,
                  "execution": {"gap": solver_gap, "precision_revision_sha256": execution_revision}}
        if policy is not None:
            record.update(richer_real_metrics(policy, DT*(actual[d, :, 0]-actual[d, :, 1]), prices, soc, main_day))
            record = save_richer_policy(output, record, policy, context)
        records.append(record)
        atomic_json(output/"richer_soc_policy.json", {"records": records, "complete": len(records) == len(targets),
                                                    "reliable_all": all(v["solver"]["reliable"] for v in records)})
    if not all(v["solver"]["reliable"] for v in records):
        raise ComputationalLimit({"experiment": "richer_soc", "records": records})


def run_experiments(run_path, only=None, *, rescue_seconds=None, solver_gap=PROTOCOL["solver_gap"], execution_revision=None):
    run_path = Path(run_path)
    store, frozen, actual, dates, prices = load_prepared(run_path)
    root = run_path/"processed"
    output = root/"experiments"
    output.mkdir(parents=True, exist_ok=True)
    if only is None or only == "forecast":
        forecast_audit(store, frozen, actual, dates, prices, output)
        no_storage_quantile(store, frozen, actual, dates, prices, output)
        if only == "forecast":
            return {"forecast": {"complete": True}}
    warm_file = root/"warm_start.json"
    initial = json.loads(warm_file.read_text(encoding="utf-8"))["feb1_baseline_soc"] if warm_file.exists() else warm_start(actual, dates, prices, root)
    status = {}
    def record(name, function):
        if only is not None and name != only:
            return
        try:
            function()
            status[name] = {"complete": True}
        except (RuntimeError, ValueError, AssertionError) as error:
            status[name] = {"complete": False, "reason": str(error), "details": getattr(error, "details", None)}
        write_json(output/f"status/{name}.json", status[name])
    for direct in (False, True):
        name = "structure_direct_net" if direct else "structure_separate"
        record(name, lambda direct=direct, name=name: structural_rollout(actual, dates, prices, initial, output/name, direct=direct))
    main = root/"main"
    main_state = json.loads((main/"run_status.json").read_text(encoding="utf-8")) if (main/"run_status.json").exists() else {}
    frame = pd.read_csv(main/"dispatch.csv", parse_dates=["date", "timestamp"], float_precision="round_trip") if main_state.get("complete") else None
    specifications = {
        "deterministic": {"kind": "deterministic", "reference_audits": main/"daily_audit"},
        "rigid": {"kind": "rigid", "reference_audits": main/"daily_audit"},
        **{f"predictor_{load}_{pv}": {"fixed_pair": ["load_week" if load == "week" else f"load_lgb_{frozen}",
                                                     "pv_mean7" if pv == "mean7" else "pv_dhr"]}
           for load in ("week", "lgb") for pv in ("mean7", "dhr")},
        **{f"window_{w or 'expanding'}": {"window": w} for w in (28, 56, 84, None)},
        **{f"horizon_{k}": {"horizon": k} for k in (1, 2, 3)},
        **{f"scenario_{s}": {"window": None, "forced_count": s} for s in (10, 20, 40)},
        **{f"initial_{soc:g}": {"initial_override": soc} for soc in sorted({1200., 6000., initial, 10800.})},
    }
    if frame is not None:
        baseline = combined(store, ("load_week", "pv_mean7"))
        common_start = next(d for d in range(31, len(dates)) if len(eligible_origins(baseline, d, 3, 28)))
        common_soc = float(frame[frame.date == dates[common_start]].initial_soc.iloc[0])
        for threshold in (14, 21, 28):
            specifications[f"minimum_{threshold}"] = {"minimum": threshold, "start": common_start, "initial_override": common_soc}
    for name, settings in specifications.items():
        if (name in ("deterministic", "rigid") or name in main_baselines(initial)) and frame is None:
            if only is None or only == name:
                status[name] = {"complete": False, "reason": "主回放尚未完整通过，缺少共同预测与场景审计"}
                write_json(output/f"status/{name}.json", status[name])
            continue
        current = dict(settings); soc = current.pop("initial_override", initial)
        def execute(current=current, soc=soc, name=name):
            if reuse_main_baseline(run_path, name, store, frozen, actual, dates, prices, initial):
                return
            result, _ = run_rollout(store, frozen, actual, dates, prices, soc, output/name,
                                    rescue_seconds=rescue_seconds, solver_gap=solver_gap,
                                    execution_revision=execution_revision, **current)
            validate_dispatch(result, rigid=current.get("kind") == "rigid")
            write_tables(result, output/name)
        record(name, execute)
    if frame is not None:
        cost = float(frame.planned_cost.sum()+frame.emergency_cost.sum())
        record("oracles", lambda: write_json(output/"oracles.json", oracle_pair(frame.net_kwh.to_numpy(), np.tile(prices, 334),
                                                                              initial, frame.grid.to_numpy(), cost)))
        record("richer_soc", lambda: richer_policy_diagnostic(store, frozen, actual, dates, prices, main, output,
                                                            rescue_seconds=rescue_seconds, solver_gap=solver_gap,
                                                            execution_revision=execution_revision))
    else:
        for name in ("minimum_14", "minimum_21", "minimum_28", "oracles", "richer_soc"):
            if only is None or only == name:
                status[name] = {"complete": False, "reason": "主回放尚未完整通过，不能杜撰共同SOC或Oracle"}
                write_json(output/f"status/{name}.json", status[name])
    if only is not None and not status:
        raise ValueError(f"未知实验：{only}")
    return status
