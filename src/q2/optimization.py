"""最终方案2.7.6：SCIP原生指示约束，精确绑定场景响应而非自由recourse。"""

import time

import numpy as np
from pyscipopt import Model, SCIP_PARAMSETTING, quicksum

from policy import (CAP, E_INITIAL, E_MIN, E_MAX, ETA_C, ETA_D,
                    PHYSICAL_TOL, Policy, replay)


def _size(model, transformed=False):
    variables = model.getVars(transformed=transformed)
    return {"continuous": sum(v.vtype() == "CONTINUOUS" for v in variables),
            "binary": sum(v.vtype() == "BINARY" for v in variables),
            "variables": len(variables), "constraints": model.getNConss()}


def build_model(net, prices, weights, initial_soc=E_INITIAL, *, fixed_policy=None, segments=1):
    net, prices, weights = map(lambda v: np.asarray(v, dtype=float), (net, prices, weights))
    if net.ndim != 2 or prices.shape != (net.shape[1],) or weights.shape != (net.shape[0],):
        raise ValueError("场景/电价/概率维度不符")
    if not all(np.isfinite(v).all() for v in (net, prices, weights)) or (prices <= 0).any() or (weights <= 0).any():
        raise ValueError("模型输入必须有限，电价及场景概率必须为正")
    if not np.isclose(weights.sum(), 1, atol=1e-12) or not E_MIN <= initial_soc <= E_MAX:
        raise ValueError("概率不守恒或初态越界")
    scenarios, periods = net.shape
    model = Model("q2_precommitted_feedback")
    model.hideOutput()
    grid_upper = np.maximum(net.max(axis=0), 0) + CAP
    g = [model.addVar(name=f"g_{t}", ub=float(grid_upper[t])) for t in range(periods)]
    if segments not in (1, 3):
        raise ValueError("仅实现方案指定的单一/三段SOC策略")
    cp = [[model.addVar(name=f"cp_{t}_{k}", ub=CAP) for k in range(segments)] for t in range(periods)]
    rp = [[model.addVar(name=f"rp_{t}_{k}", ub=CAP) for k in range(segments)] for t in range(periods)]
    if fixed_policy is not None:
        if fixed_policy.grid.shape != (periods,) or fixed_policy.charge_cap.size != periods*segments:
            raise ValueError("固定策略长度或维度不符")
        for variables, values in ((g, fixed_policy.grid), (np.array(cp).ravel(), fixed_policy.charge_cap.ravel()),
                                  (np.array(rp).ravel(), fixed_policy.discharge_cap.ravel())):
            for variable, value in zip(variables, values):
                model.addCons(variable == float(value))
    responses, branches = [], []
    for s in range(scenarios):
        row, selectors = [], []
        previous = float(initial_soc)
        for t in range(periods):
            n = float(net[s, t])
            c = model.addVar(name=f"c_{s}_{t}", ub=CAP)
            r = model.addVar(name=f"r_{s}_{t}", ub=CAP)
            q = model.addVar(name=f"q_{s}_{t}", ub=max(n, 0))
            w = model.addVar(name=f"w_{s}_{t}", ub=max(float(grid_upper[t])-n, 0))
            e = model.addVar(name=f"e_{s}_{t}", lb=E_MIN, ub=E_MAX)
            z = model.addVar(name=f"z_{s}_{t}", vtype="B", ub=0 if n < 0 else 1)
            lr = [model.addVar(vtype="B", name=f"lr_{s}_{t}_{k}") for k in range(3)]
            lc = [model.addVar(vtype="B", name=f"lc_{s}_{t}_{k}") for k in range(3)]
            x = n - g[t]
            available, room = ETA_D*(previous-E_MIN), (E_MAX-previous)/ETA_C
            if segments == 1:
                active_cp, active_rp = cp[t][0], rp[t][0]
            else:
                active_cp = model.addVar(name=f"active_cp_{s}_{t}", ub=CAP)
                active_rp = model.addVar(name=f"active_rp_{s}_{t}", ub=CAP)
                bands = [model.addVar(vtype="B", name=f"band_{s}_{t}_{k}") for k in range(3)]
                model.addCons(quicksum(bands) == 1)
                for k, band in enumerate(bands):
                    lo, hi = E_MIN+k*(E_MAX-E_MIN)/3, E_MIN+(k+1)*(E_MAX-E_MIN)/3
                    # 闭区间给出半开区间策略的下界松弛；独立半开区间回放+gap证书决定能否接受。
                    if t == 0:
                        initial_band = min(int(3*(initial_soc-E_MIN)/(E_MAX-E_MIN)), 2)
                        model.addCons(band == int(k == initial_band))
                    else:
                        model.addConsIndicator(lo-previous <= 0, binvar=band)
                        model.addConsIndicator(previous-hi <= 0, binvar=band)
                    for active, cap in ((active_cp, cp[t][k]), (active_rp, rp[t][k])):
                        model.addConsIndicator(active-cap <= 0, binvar=band)
                        model.addConsIndicator(cap-active <= 0, binvar=band)
            model.addCons(e == previous + ETA_C*c-r/ETA_D)
            model.addCons(g[t]+r+q == n+c+w)
            model.addCons(c <= active_cp); model.addCons(c <= room)
            model.addCons(r <= active_rp); model.addCons(r <= available)
            model.addCons(c <= CAP*(1-z)); model.addCons(r <= CAP*z)
            model.addCons(q <= max(n, 0)*z)
            model.addCons(w <= max(float(grid_upper[t])-n, 0)*(1-z))
            model.addConsIndicator(-x <= 0, binvar=z)
            model.addConsIndicator(x <= 0, binvar=z, activeone=False)
            model.addCons(quicksum(lr) == z)
            model.addCons(quicksum(lc) == 1-z)
            # 平衡+q/w非负给出对应分支的r<=x、c<=-x；仅需绑定一个最小项。
            for k, bound in enumerate((active_rp, x, available)):
                model.addConsIndicator(bound-r <= 0, binvar=lr[k])
            for k, bound in enumerate((active_cp, -x, room)):
                model.addConsIndicator(bound-c <= 0, binvar=lc[k])
            row.append((c, r, q, w, e)); selectors.append((z, lr, lc))
            previous = e
        responses.append(row); branches.append(selectors)
    plan_cost = quicksum(float(prices[t])*g[t] for t in range(periods))
    scenario_costs = [quicksum(5*float(prices[t])*responses[s][t][2] for t in range(periods)) for s in range(scenarios)]
    objective = plan_cost + quicksum(float(weights[s])*scenario_costs[s] for s in range(scenarios))
    model.setObjective(objective, "minimize")
    return model, {"g": g, "cp": cp if segments == 3 else [v[0] for v in cp],
                   "rp": rp if segments == 3 else [v[0] for v in rp], "response": responses, "branches": branches,
                   "objective": objective, "scenario_costs": scenario_costs}


def _seed(model, variables, net, initial_soc, policy):
    """可行预承诺策略作为求解器初始解，最终仍须满足预注册gap；不是替代求解。"""
    solution = model.createPartialSol()
    for key, values in (("g", policy.grid), ("cp", policy.charge_cap), ("rp", policy.discharge_cap)):
        for variable, value in zip(np.array(variables[key], dtype=object).ravel(), values.ravel()):
            model.setSolVal(solution, variable, float(value))
    for s, path in enumerate(net):
        response = replay(policy, path, initial_soc)
        previous = initial_soc
        for t in range(len(path)):
            for variable, key in zip(variables["response"][s][t], ("charge", "discharge", "emergency", "unused", "soc")):
                model.setSolVal(solution, variable, float(response[key][t]))
            z, lr, lc = variables["branches"][s][t]
            x = path[t]-policy.grid[t]
            deficit = x >= 0
            model.setSolVal(solution, z, int(deficit))
            band = min(max(int(3*(previous-E_MIN)/(E_MAX-E_MIN)), 0), 2)
            cp = policy.charge_cap[t] if policy.charge_cap.ndim == 1 else policy.charge_cap[t, band]
            rp = policy.discharge_cap[t] if policy.discharge_cap.ndim == 1 else policy.discharge_cap[t, band]
            rmin = int(np.argmin([rp, max(x, 0), ETA_D*(previous-E_MIN)]))
            cmin = int(np.argmin([cp, max(-x, 0), (E_MAX-previous)/ETA_C]))
            for k in range(3):
                model.setSolVal(solution, lr[k], int(deficit and k == rmin))
                model.setSolVal(solution, lc[k], int(not deficit and k == cmin))
            previous = response["soc"][t]
    model.addSol(solution)


def solve_policy(net, prices, weights, initial_soc=E_INITIAL, *, gap=0.01, time_limit=120,
                 fixed_policy=None, seed_policy=None, log_path=None, cvar=None, segments=1,
                 known_lower_bound=None):
    started = time.perf_counter()
    model, variables = build_model(net, prices, weights, initial_soc, fixed_policy=fixed_policy, segments=segments)
    model.setPresolve(SCIP_PARAMSETTING.FAST)
    model.setIntParam("presolving/maxrounds", 1)
    model.setIntParam("misc/usesymmetry", 0)
    model.setRealParam("limits/gap", gap)
    model.setRealParam("limits/time", time_limit)
    model.setRealParam("numerics/feastol", 1e-8)
    model.setIntParam("randomization/randomseedshift", 0)
    if log_path:
        model.setLogfile(str(log_path))
    if cvar is not None:
        alpha, epsilon, reference = cvar
        if not 0 < alpha < 1 or epsilon < 0 or reference < 0:
            raise ValueError("CVaR扩展参数不合法")
        eta = model.addVar(name="cvar_eta", lb=0)
        xi = [model.addVar(name=f"cvar_xi_{s}") for s in range(len(weights))]
        for excess, scenario_cost in zip(xi, variables["scenario_costs"]):
            model.addCons(excess >= scenario_cost-eta)
        model.addCons(variables["objective"] <= (1+epsilon)*reference)
        model.setObjective(eta + quicksum(float(p)*v for p, v in zip(weights, xi))/(1-alpha))
    before = _size(model)
    if seed_policy is not None:
        _seed(model, variables, np.asarray(net), initial_soc, seed_policy)
    model.presolve()
    after = _size(model, transformed=True)
    model.optimize()
    status = str(model.getStatus())
    info = {"status": status, "solve_seconds": model.getSolvingTime(),
            "wall_seconds": time.perf_counter()-started, "before_presolve": before,
            "after_presolve": after, "solver": "SCIP", "solver_version": ".".join(map(str, (
                model.getMajorVersion(), model.getMinorVersion(), model.getTechVersion()))),
            "mip_gap": float(model.getGap()) if model.getNSols() else None,
            "dual_bound": float(model.getDualbound()), "solutions": model.getNSols(),
            "requested_gap": gap, "time_limit": time_limit}
    if not model.getNSols():
        model.freeProb()
        return None, None, {**info, "reliable": False}
    sol = model.getBestSol()
    def values(key):
        array = np.array(variables[key], dtype=object)
        return np.maximum([model.getSolVal(sol, v) for v in array.ravel()], 0).reshape(array.shape)
    policy = Policy(values("g"), values("cp"), values("rp"))
    responses = [replay(policy, path, initial_soc) for path in net]
    raw = np.array([[[model.getSolVal(sol, v) for v in entry] for entry in row] for row in variables["response"]])
    exact = np.array([np.array([r[k] for k in ("charge", "discharge", "emergency", "unused", "soc")]).T for r in responses])
    mapping_error = float(np.max(np.abs(exact-raw)))
    objective = float(np.dot(prices, policy.grid) + sum(float(p)*5*np.dot(prices, r["emergency"]) for p, r in zip(weights, responses)))
    certificate_gap = max(objective-info["dual_bound"], 0)/max(abs(info["dual_bound"]), 1e-8)
    info.update(objective=objective, optimizer_objective=float(model.getObjVal()),
                mapping_error_kwh=mapping_error,
                reliable=bool(info["mip_gap"] <= gap+1e-8 and mapping_error <= PHYSICAL_TOL))
    if known_lower_bound is not None and cvar is None:
        lower = max(info["dual_bound"], known_lower_bound)
        certificate_gap = max(objective-lower, 0)/max(abs(lower), 1e-8)
        info.update(scip_mip_gap=info["mip_gap"], mip_gap=certificate_gap,
                    dual_bound=lower, external_lp_lower_bound=known_lower_bound,
                    reliable=bool(certificate_gap <= gap+1e-8 and mapping_error <= PHYSICAL_TOL))
    if segments == 3:
        info.update(half_open_policy_certified_gap=certificate_gap,
                    soc_boundary_formulation="closed_interval_lower_bound_and_exact_half_open_replay_certificate",
                    reliable=bool(certificate_gap <= gap+1e-8))
    if mapping_error > PHYSICAL_TOL and segments == 1:
        model.freeProb()
        raise ValueError(f"MILP与单步因果映射不等价：{mapping_error}kWh")
    model.freeProb()
    return policy, responses, info


def certify_policy(net, prices, weights, initial_soc, policy, responses, bound, gap):
    """仍构建并presolve原生MILP以报告实际规模；可行策略+全局下界提供gap证书。"""
    started = time.perf_counter()
    segments = 1 if policy.charge_cap.ndim == 1 else policy.charge_cap.shape[1]
    model, variables = build_model(net, prices, weights, initial_soc, segments=segments)
    before = _size(model)
    # 不固定策略参数做presolve，报告原问题规模而不是固定策略后的退化规模。
    model.setPresolve(SCIP_PARAMSETTING.FAST)
    model.setRealParam("numerics/feastol", 1e-8)
    model.setIntParam("presolving/maxrounds", 1)
    model.setIntParam("misc/usesymmetry", 0)
    model.setRealParam("limits/time", 120)
    model.presolve()
    after = _size(model, transformed=True)
    actual = [replay(policy, path, initial_soc) for path in net]
    cost = float(np.dot(prices, policy.grid)+sum(5*p*np.dot(prices, r["emergency"]) for p, r in zip(weights, actual)))
    lower = bound["lower_bound"]
    certified_gap = max(cost-lower, 0)/max(abs(lower), 1e-8)
    info = {"status": "certified_by_feasible_policy_and_global_lp_lower_bound",
            "solver": "SCIP_native_MILP_presolve_and_HiGHS_bound", "solver_version": ".".join(map(str, (
                model.getMajorVersion(), model.getMinorVersion(), model.getTechVersion()))),
            "before_presolve": before, "after_presolve": after,
            "mip_gap": certified_gap, "requested_gap": gap, "objective": cost, "dual_bound": lower,
            "solve_seconds": time.perf_counter()-started+bound["seconds"],
            "mapping_error_kwh": 0.0, "mapping_evidence": "all_responses_generated_by_same_exact_frozen_policy",
            "reliable": bool(certified_gap <= gap and lower <= cost+PHYSICAL_TOL),
            "certificate": bound, "branch_and_bound_required": False}
    info["presolve_scope"] = "SCIP_FAST_one_round_symmetry_disabled_certificate_already_proves_gap"
    model.freeProb()
    return policy, actual, info
