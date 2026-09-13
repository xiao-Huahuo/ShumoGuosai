"""强化版11.3–11.8：同一模型的诊断、局部边际量与MILP重求敏感性。"""

import numpy as np

from export import read_csv
from model import (DT, PHYS_TOL_KWH, COST_TOL_YUAN, BINARY_TOL, ECONOMIC_VALUE_TOL, MIP_GAP_TOL, SCENARIOS, arrays, build_problem,
                   check_solution, solve, solve_lp, solve_milp, summary, write_csv, write_json)

ANALYSIS_SETTINGS = {"active_tolerance_kwh": PHYS_TOL_KWH, "rhs_step_kwh": 0.01,
                     "main_capacity_steps_kwh": [1.0, 10.0, 100.0],
                     "main_power_steps_kw": [1.0, 10.0, 100.0],
                     "all_scenario_boundary_steps": [1.0, 10.0, 100.0],
                     "economic_significance_threshold": None,
                     "economic_significance_note": "题目未给设备投资成本或经济显著性门槛；仅报告数值稳定性和节约",
                     "load_deltas": [-0.05, 0.0, 0.05], "pv_deltas": [-0.05, 0.0, 0.05],
                     "numerical_setting_note": "实现中的数值诊断设置；不改变主模型设备参数和目标"}


def verify_lp(problem, result):
    """核查LP原始可行性和KKT；只服务LP诊断，不替代MILP最优性证明。"""
    if result.status != 0 or not result.success:
        raise ValueError(f"LP未最优：{result.message}")
    n = len(problem["index"]["G"])
    x, a, lo, hi = result.x, problem["a"], problem["lower"], problem["upper"]
    y, z = result.eqlin.marginals, result.ineqlin.marginals
    yl, yu = result.lower.marginals, result.upper.marginals
    if not all(np.all(np.isfinite(v)) for v in (x, y, z, yl, yu)):
        raise ValueError("LP原始或对偶变量非有限")
    ubfinite = np.isfinite(hi)
    slack = problem["ub"][2 * n:] - a[2 * n:] @ x
    dual = y @ problem["ub"][:2 * n] + z @ problem["ub"][2 * n:]
    dual += yl @ lo + yu[ubfinite] @ hi[ubfinite]
    metrics = {
        "equality_residual": float(np.max(np.abs(a[:2 * n] @ x - problem["ub"][:2 * n]))),
        "inequality_violation": float(max(0, -slack.min())),
        "bound_violation": float(max(0, np.max(lo - x), np.max(x - hi))),
        "stationarity_residual": float(np.max(np.abs(problem["objective"] - a[:2 * n].T @ y
                                                       - a[2 * n:].T @ z - yl - yu))),
        "complementarity_residual": float(max(np.max(np.abs(z * slack)),
                                                 np.max(np.abs(yl * (x - lo))),
                                                 np.max(np.abs(yu[ubfinite] * (hi[ubfinite] - x[ubfinite]))))),
        "dual_sign_violation": float(max(0, z.max(), -yl.min(), yu.max())),
        "objective_recalculation_error": float(abs(problem["objective"] @ x - result.fun)),
        "primal_dual_gap": float(abs(result.fun - dual))}
    tolerances = {k: (COST_TOL_YUAN if k in ("complementarity_residual", "objective_recalculation_error", "primal_dual_gap")
                      else ECONOMIC_VALUE_TOL if k in ("stationarity_residual", "dual_sign_violation")
                      else PHYS_TOL_KWH) for k in metrics}
    if any(not np.isfinite(v) or v > tolerances[k] for k, v in metrics.items()):
        raise ValueError(f"LP检查失败：{metrics}")
    return {"passed": True, "metrics": metrics, "metric_tolerances": tolerances}


def lp_record(problem, result):
    return {"variables": {k: result.x[v].tolist() for k, v in problem["index"].items()},
            "objective_yuan": float(result.fun), "status": int(result.status),
            "equality_rhs_marginals": result.eqlin.marginals.tolist(),
            "inequality_rhs_marginals": result.ineqlin.marginals.tolist(),
            "lower_marginals": result.lower.marginals.tolist(),
            "upper_marginals": result.upper.marginals.tolist()}


def active_sets(solution):
    settings = solution["settings"]
    return {key: (np.flatnonzero(np.abs(np.array(solution[var]) - limit) <= PHYS_TOL_KWH) + 1).tolist()
            for key, var, limit in (("E_min", "E", settings["e_min"]), ("E_max", "E", settings["e_max"]),
                                    ("charge", "C", settings["charge_kw"] * DT),
                                    ("discharge", "D", settings["discharge_kw"] * DT))}


def scaled_data(data, dl, dpv):
    return [{**r, "load_kw": r["load_kw"] * (1 + dl), "load_kwh": r["load_kwh"] * (1 + dl),
             "pv_kw": r["pv_kw"] * (1 + dpv), "pv_kwh": r["pv_kwh"] * (1 + dpv)} for r in data]


def local_marginals(data, solution, scenario):
    mode = np.rint(solution["u"]).astype(int)
    problem = build_problem(data, solution["eta_c"], solution["eta_d"], **solution["settings"], fixed_mode=mode)
    result = solve_lp(problem)
    checks = verify_lp(problem, result)
    if abs(result.fun - solution["solver"]["objective_yuan"]) > COST_TOL_YUAN:
        raise ValueError("固定最优模式LP费用与主MILP不一致")
    n, ec, ed = len(data), solution["eta_c"], solution["eta_d"]
    active = active_sets(solution)
    # SciPy marginals=dJ/db。SOC RHS增加为内部注入，价值lambda=-dJ/dh。
    mu, lam = result.eqlin.marginals[:n], -result.eqlin.marginals[n:]
    rows = []
    for i, r in enumerate(data):
        low, high = ec * lam[i], lam[i] / ed
        gain_c, gain_d = low - mu[i], mu[i] - high
        c, d, e = (solution[k][i] for k in ("C", "D", "E"))
        if gain_c > ECONOMIC_VALUE_TOL:
            tendency = "charge"
        elif gain_d > ECONOMIC_VALUE_TOL:
            tendency = "discharge"
        elif min(abs(mu[i] - low), abs(mu[i] - high)) <= ECONOMIC_VALUE_TOL:
            tendency = "indifferent_boundary"
        else:
            tendency = "idle_band"
        action = "charge" if c > PHYS_TOL_KWH else "discharge" if d > PHYS_TOL_KWH else "idle"
        if (c > PHYS_TOL_KWH and gain_c < -ECONOMIC_VALUE_TOL) or (d > PHYS_TOL_KWH and gain_d < -ECONOMIC_VALUE_TOL):
            raise ValueError("实际非零动作与允许方向的局部边际条件矛盾")
        rows.append({"scenario": scenario, "t": i + 1, "interval": r["interval"],
                     "price_yuan_per_kwh": r["price_yuan_per_kwh"], "mu_yuan_per_kwh": float(mu[i]),
                     "lambda_yuan_per_kwh": float(lam[i]), "charge_threshold": float(low),
                     "discharge_threshold": float(high), "charge_gain": float(gain_c),
                     "discharge_gain": float(gain_d), "tendency": tendency, "actual_action": action,
                     "fixed_u": int(mode[i]), "mode_blocks_tendency": int(
                         (tendency == "charge" and mode[i] == 0) or (tendency == "discharge" and mode[i] == 1)),
                     "E_min_active": int(i + 1 in active["E_min"]), "E_max_active": int(i + 1 in active["E_max"]),
                     "charge_max_active": int(i + 1 in active["charge"]),
                     "discharge_max_active": int(i + 1 in active["discharge"])})
    return rows, problem, result, checks


def rhs_validation(problem, result, step=0.01):
    """对所有母线需求/内部注入做双侧微扰；退化时校验影子价落在差分区间。"""
    n = len(problem["index"]["G"])
    records = []
    for row, shadow in enumerate(result.eqlin.marginals):
        slopes, statuses = {}, {}
        for side, sign in (("minus", -1), ("plus", 1)):
            changed = solve_lp(problem, (row, sign * step))
            statuses[side] = int(changed.status)
            if changed.status == 0:
                shifted = {**problem, "ub": problem["ub"].copy()}
                shifted["ub"][row] += sign * step
                verify_lp(shifted, changed)
                slopes[side] = float((changed.fun - result.fun) / (sign * step))
            elif changed.status == 2:
                slopes[side] = None  # 边界处方向不可行；绝不填造差分值。
            else:
                raise ValueError(f"RHS扰动求解异常：{changed.message}")
        violation = max(0, (slopes["minus"] - shadow) if slopes["minus"] is not None else 0,
                        (shadow - slopes["plus"]) if slopes["plus"] is not None else 0)
        if violation > ECONOMIC_VALUE_TOL:
            raise ValueError(f"影子价格符号或差分区间错误：row={row}, {slopes}, shadow={shadow}")
        records.append({"kind": "bus_demand" if row < n else "internal_injection",
                        "t": row % n + 1, "step_kwh": step, "shadow_dJ_db": float(shadow),
                        "minus_slope": slopes["minus"], "plus_slope": slopes["plus"],
                        "minus_status": statuses["minus"], "plus_status": statuses["plus"],
                        "interval_violation": float(violation),
                        "two_sided_smooth": int(all(v is not None and abs(v - shadow) <= ECONOMIC_VALUE_TOL for v in slopes.values()))})
    return records


def milp_rhs_validation(data, solution, fixed_rows, step=0.01):
    """CR-02：全部模式可重新选择；不将非凸MILP值函数强作凸函数。"""
    problem = build_problem(data, solution["eta_c"], solution["eta_d"], **solution["settings"])
    base = solution["solver"]["objective_yuan"]
    records, raw = [], []
    n = len(data)
    for row, fixed in enumerate(fixed_rows):
        item = {"kind": fixed["kind"], "t": fixed["t"], "step_kwh": step,
                "fixed_shadow_dJ_db": fixed["shadow_dJ_db"],
                "base_action": "idle" if max(solution["C"][row % n], solution["D"][row % n]) <= PHYS_TOL_KWH else "active"}
        for side, sign in (("minus", -1), ("plus", 1)):
            changed = {**problem, "lb": problem["lb"].copy(), "ub": problem["ub"].copy()}
            changed["lb"][row] += sign * step
            changed["ub"][row] += sign * step
            result = solve_milp(changed)
            item[side + "_status"] = int(result.status)
            item[side + "_slope"] = None
            if result.status == 2:
                raw.append({"row": row, "side": side, "status": 2})
                continue
            if result.status != 0 or not result.success:
                raise ValueError(f"原MILP扰动失败：{result.message}")
            if not np.all(np.isfinite(result.x)) or not np.all(np.isfinite([result.fun, result.mip_dual_bound, result.mip_gap])):
                raise ValueError("原MILP扰动含非有限结果")
            x, lhs = result.x, changed["a"] @ result.x
            residual = float(max(0, np.max(changed["lb"] - lhs), np.max(lhs - changed["ub"]),
                                 np.max(changed["lower"] - x), np.max(x - changed["upper"])))
            binary_error = float(np.max(np.abs(x[problem["index"]["u"]] - np.rint(x[problem["index"]["u"]]))))
            cost_error = float(abs(problem["objective"] @ x - result.fun))
            bound_gap = float(abs(result.fun - result.mip_dual_bound))
            if (residual > PHYS_TOL_KWH or binary_error > BINARY_TOL or cost_error > COST_TOL_YUAN
                    or bound_gap > COST_TOL_YUAN or not np.isfinite(result.mip_gap) or result.mip_gap > MIP_GAP_TOL):
                raise ValueError("原MILP扰动的物理/整数/最优性复核失败")
            slope = float((result.fun - base) / (sign * step))
            item[side + "_slope"] = slope
            # 固定模式可行域是原MILP子集，只比较目标，不假设两侧导数次序。
            fixed_slope = fixed[side + "_slope"]
            if fixed_slope is not None and result.fun > base + fixed_slope * sign * step + COST_TOL_YUAN:
                raise ValueError("原MILP最优费用高于可行固定模式LP")
            raw.append({"row": row, "side": side, "status": 0,
                        "objective_yuan": float(result.fun), "dual_bound_yuan": float(result.mip_dual_bound),
                        "mip_gap": float(result.mip_gap), "residual_kwh": residual,
                        "variables": {k: x[v].tolist() for k, v in problem["index"].items()}})
        item["fixed_shadow_matches_milp_both_sides"] = int(all(
            item[side + "_slope"] is not None and
            abs(item[side + "_slope"] - fixed["shadow_dJ_db"]) <= ECONOMIC_VALUE_TOL
            for side in ("minus", "plus")))
        item["milp_two_sided_smooth"] = int(item["minus_slope"] is not None and item["plus_slope"] is not None
                                                 and abs(item["minus_slope"] - item["plus_slope"]) <= ECONOMIC_VALUE_TOL)
        # lambda = -dJ/dh；保留两侧来源，避免将非光滑点压成唯一价格。
        for side in ("minus", "plus"):
            slope = item[side + "_slope"]
            item[side + "_economic_value"] = None if slope is None else slope * (1 if row < n else -1)
        records.append(item)
    return records, raw


def bottlenecks(data, solution, scenario, steps):
    rows, records = [], {}
    active = active_sets(solution)
    base_cost = solution["solver"]["objective_yuan"]
    for resource, parameter, direction, unit, active_key in (
            ("storage_upper", "e_max", 1, "yuan/(kWh day)", "E_max"),
            ("storage_lower", "e_min", -1, "yuan/(kWh day)", "E_min"),
            ("charge_power", "charge_kw", 1, "yuan/(kW day)", "charge"),
            ("discharge_power", "discharge_kw", 1, "yuan/(kW day)", "discharge")):
        group = []
        base = solution["settings"][parameter]
        for step in steps:
            settings = {**solution["settings"], parameter: base + direction * step}
            changed = solve(data, solution["eta_c"], solution["eta_d"], **settings)
            check = check_solution(data, changed)
            saving = base_cost - changed["solver"]["objective_yuan"]
            if saving < -COST_TOL_YUAN:
                raise ValueError("放宽约束后最优费用增加，违反嵌套可行域")
            group.append({"scenario": scenario, "resource": resource, "base_limit": base,
                          "increment": step, "parameter_change": direction * step,
                          "increment_period_kwh": step if parameter in ("e_min", "e_max") else step * DT,
                          "base_cost_yuan": base_cost, "relaxed_cost_yuan": changed["solver"]["objective_yuan"],
                          "saving_yuan": saving, "value_per_unit_day": saving / step, "unit": unit,
                          "active_count": len(active[active_key]),
                          "active_periods": ";".join(map(str, active[active_key])),
                          "global_gap": changed["solver"]["mip_gap"]})
            records[f"{resource}_{step:g}"] = {"solution": changed, "validation": check}
        values = [r["value_per_unit_day"] for r in group]
        stable = len(values) >= 3 and max(values) - min(values) <= ECONOMIC_VALUE_TOL
        for r in group:
            r.update({"multistep_value_spread": max(values) - min(values), "multistep_stable": int(stable),
                      "stable_positive_value": int(stable and min(values) > ECONOMIC_VALUE_TOL),
                      "numerical_bottleneck": int(bool(active[active_key]) and stable and min(values) > ECONOMIC_VALUE_TOL),
                      "economic_bottleneck": None,
                      "economic_significance": "not_assessed_no_economic_threshold"})
        rows.extend(group)
    return rows, records


def checked_analysis_csv(path, rows):
    if any(isinstance(v, (float, np.floating)) and not np.isfinite(v) for r in rows for v in r.values()):
        raise ValueError(f"分析CSV含非有限数值：{path}")
    write_csv(path, rows)
    actual = read_csv(path)
    expected = [{k: "" if v is None else str(v) for k, v in r.items()} for r in rows]
    if actual != expected:
        raise ValueError(f"分析CSV关闭回读不一致：{path}")
    return {"passed": True, "rows": len(rows), "columns": list(rows[0])}


def run_analysis(data, solutions, output_raw, output):
    """覆盖三档单程效率和往返口径×负荷三档×光伏三档，共36情景。"""
    main = solutions["main"]
    raw, checks, csv_checks = {}, {}, {}
    baseline_rows = []
    for name in ("no_ess", "pv_only", "full"):
        s = main if name == "full" else solve(data, 0.9, baseline=name)
        checks[name] = check_solution(data, s)
        raw[name] = s
        baseline_rows.append({"baseline": name, **summary(data, s)})
    j0, jpv, jm = (r["cost_yuan"] for r in baseline_rows)
    if not jm <= jpv + COST_TOL_YUAN <= j0 + 2 * COST_TOL_YUAN:
        raise ValueError("嵌套基准成本次序错误")
    p, load, pv = arrays(data)
    if abs(j0 - p @ np.maximum(load - pv, 0)) > COST_TOL_YUAN:
        raise ValueError("No-ESS与解析基准费用不符")
    benefits = {"pv_increment_yuan": j0 - jpv, "flex_increment_yuan": jpv - jm,
                "total_saving_yuan": j0 - jm,
                "interpretation": "嵌套可行域增量节约；不是唯一光伏/套利因果分解"}
    problem = build_problem(data, 0.9)
    relaxed = solve_lp(problem)
    checks["lp_relaxation"] = verify_lp(problem, relaxed)
    raw["lp_relaxation"] = lp_record(problem, relaxed)
    u = relaxed.x[problem["index"]["u"]]
    c, d = (relaxed.x[problem["index"][v]] for v in ("C", "D"))
    diagnosis = {"milp_cost_yuan": jm, "lp_cost_yuan": float(relaxed.fun),
                 "integer_gap": float((jm - relaxed.fun) / max(1, abs(jm))),
                 "fractional_modes": int(np.sum((u > BINARY_TOL) & (u < 1 - BINARY_TOL))),
                 "simultaneous_periods": int(np.sum((c > PHYS_TOL_KWH) & (d > PHYS_TOL_KWH)))}
    if relaxed.fun > jm + COST_TOL_YUAN:
        raise ValueError("连续松弛下界大于MILP费用")
    scenario_rows, marginal_rows, capacity_rows, all_schedules, active_rows = [], [], [], [], []
    raw["scenarios"] = {}
    rhs_rows, milp_rhs_rows = [], []
    for efficiency_name, efficiency in SCENARIOS.items():
        for dl in ANALYSIS_SETTINGS["load_deltas"]:
            for dpv in ANALYSIS_SETTINGS["pv_deltas"]:
                key = f"{efficiency_name}_l{round(100 * (1 + dl))}_pv{round(100 * (1 + dpv))}"
                current = scaled_data(data, dl, dpv)
                s = solutions[efficiency_name] if dl == dpv == 0 else solve(current, efficiency)
                checks[key] = check_solution(current, s)
                local, fixed_problem, fixed_result, lp_check = local_marginals(current, s, key)
                checks[key + "_fixed_lp"] = lp_check
                marginal_rows.extend(local)
                active = active_sets(s)
                is_main = efficiency_name == "main" and dl == dpv == 0
                values, perturbed = bottlenecks(current, s, key, ANALYSIS_SETTINGS["all_scenario_boundary_steps"])
                capacity_rows.extend(values)
                if is_main:
                    rhs_rows = rhs_validation(fixed_problem, fixed_result, ANALYSIS_SETTINGS["rhs_step_kwh"])
                    milp_rhs_rows, raw["milp_rhs_solutions"] = milp_rhs_validation(current, s, rhs_rows, ANALYSIS_SETTINGS["rhs_step_kwh"])
                values_one = {r["resource"]: r["value_per_unit_day"] for r in values if r["increment"] == 1}
                aggregates = summary(current, s)
                scenario_rows.append({"scenario": key, "efficiency_name": efficiency_name,
                                      "load_delta": dl, "pv_delta": dpv, **aggregates,
                                      "arbitrage_price_multiplier": 1 / efficiency ** 2,
                                      **{k + "_active_count": len(v) for k, v in active.items()},
                                      **{k + "_value": v for k, v in values_one.items()},
                                      "mode_blocks_tendency_count": sum(r["mode_blocks_tendency"] for r in local),
                                      "action_changed_periods": sum(
                                          r["actual_action"] != ("charge" if main["C"][i] > PHYS_TOL_KWH else "discharge" if main["D"][i] > PHYS_TOL_KWH else "idle")
                                          for i, r in enumerate(local)),
                                      "max_soc_change_from_main_kwh": float(np.max(np.abs(np.array(s["E"]) - main["E"])))})
                for i, r in enumerate(current):
                    all_schedules.append({"scenario": key, **r,
                                          **{v: s[v][i] for v in ("G", "C", "D", "E", "W", "u")}})
                    active_rows.append({"scenario": key, "t": i + 1, "interval": r["interval"],
                                        **{k + "_active": int(i + 1 in v) for k, v in active.items()}})
                raw["scenarios"][key] = {"solution": s, "active_sets": active,
                                         "fixed_lp": lp_record(fixed_problem, fixed_result), "perturbations": perturbed}
                print(f"分析 {len(scenario_rows)}/36 {key}: {aggregates['cost_yuan']:.6f} 元；原MILP与固定模式LP检查通过", flush=True)
    sensitivity = []
    for ename in SCENARIOS:
        subset = [r for r in scenario_rows if r["efficiency_name"] == ename]
        base = next(r for r in subset if r["load_delta"] == r["pv_delta"] == 0)
        for factor, held in (("load_delta", "pv_delta"), ("pv_delta", "load_delta")):
            minus = next(r for r in subset if r[factor] == -0.05 and r[held] == 0)
            plus = next(r for r in subset if r[factor] == 0.05 and r[held] == 0)
            sensitivity.append({"efficiency_name": ename, "factor": factor, "delta": 0.05,
                                "minus_cost_yuan": minus["cost_yuan"], "base_cost_yuan": base["cost_yuan"],
                                "plus_cost_yuan": plus["cost_yuan"],
                                "normalized_sensitivity": (plus["cost_yuan"] - minus["cost_yuan"]) / (0.1 * base["cost_yuan"])})
    # 11.6：只考虑当天未来时段，理论价差条件不代替带边界的可执行计划。
    threshold_rows = []
    for ename, efficiency in SCENARIOS.items():
        for i, r in enumerate(data):
            future = p[i + 1:]
            threshold_rows.append({"efficiency_name": ename, "t": i + 1, "interval": r["interval"],
                                   "current_price": float(p[i]), "future_price_threshold": float(p[i] / efficiency ** 2),
                                   "future_max_price": float(future.max()) if len(future) else None,
                                   "future_profitable_periods": int(np.sum(future * efficiency ** 2 > p[i] + ECONOMIC_VALUE_TOL)),
                                   "pv_surplus_kwh": float(max(pv[i] - load[i], 0))})
    tables = {"baseline_comparison.csv": baseline_rows, "lp_diagnosis.csv": [diagnosis],
              "incremental_benefits.csv": [benefits], "marginal_values.csv": marginal_rows,
              "marginal_rhs_validation.csv": rhs_rows, "milp_rhs_validation.csv": milp_rhs_rows, "bottleneck_values.csv": capacity_rows,
              "sensitivity_scenarios.csv": scenario_rows, "normalized_sensitivity.csv": sensitivity,
              "active_constraints.csv": active_rows, "arbitrage_thresholds.csv": threshold_rows}
    for name, rows in tables.items():
        csv_checks[name] = checked_analysis_csv(output / name, rows)
    csv_checks["analysis_schedules.csv"] = checked_analysis_csv(output_raw / "analysis_schedules.csv", all_schedules)
    result = {"settings": ANALYSIS_SETTINGS, "lp_diagnosis": diagnosis, "benefits": benefits,
              "baseline_rows": baseline_rows, "scenarios": scenario_rows, "bottlenecks": capacity_rows,
              "normalized_sensitivity": sensitivity,
              "rhs_nonsmooth_or_one_sided_count": sum(not r["two_sided_smooth"] for r in rhs_rows),
              "milp_rhs_mismatch_count": sum(not r["fixed_shadow_matches_milp_both_sides"] for r in milp_rhs_rows),
              "milp_rhs_nonsmooth_count": sum(not r["milp_two_sided_smooth"] for r in milp_rhs_rows),
              "all_checks_passed": True}
    # 主情景在遍历中的位置由标签定位，不依赖列表顺序。
    result["main_marginals"] = [r for r in marginal_rows if r["scenario"] == "main_l100_pv100"]
    write_json(output_raw / "analysis_solutions.json", raw)
    write_json(output_raw / "analysis_validation.json", {"passed": True, "checks": checks,
                                                       "csv_readback": csv_checks, "rhs_checks": rhs_rows, "milp_rhs_checks": milp_rhs_rows})
    write_json(output / "analysis_summary.json", result)
    return result
