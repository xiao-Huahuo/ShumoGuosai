"""主MILP的自由场景响应LP下界；只能加速/证明gap，不能冒充实际策略。"""

import time

import numpy as np
from scipy.optimize import linprog
from scipy.sparse import coo_matrix

from policy import CAP, E_MIN, E_MAX, ETA_C, ETA_D, Policy, replay
from scenarios import weighted_quantile
from incumbent import refine


def _candidate_costs(net, prices, weights, grid, charges, discharges, initial_soc, reserve):
    """同时评价多个合法参数候选；每一步仍仅依赖当前场景值和上一状态。"""
    count, scenarios = len(charges), len(net)
    state = np.full((count, scenarios), initial_soc, dtype=float)
    costs = np.full(count, float(prices@grid))
    for i in range(len(prices)):
        x = net[:, i]-grid[i]
        charge = np.minimum(np.minimum(charges[:, i, None], np.maximum(-x, 0)), np.maximum((E_MAX-state)/ETA_C, 0))
        discharge = np.minimum(np.minimum(discharges[:, i, None], np.maximum(x, 0)),
                               np.maximum(ETA_D*(state-E_MIN-reserve[i]), 0))
        state += ETA_C*charge-discharge/ETA_D
        costs += 5*prices[i]*(np.maximum(x-discharge, 0)@weights)
    return costs


def recourse_bound(net, prices, weights, initial_soc, *, target_gap=.01, reserve=None):
    started = time.perf_counter()
    s, t = net.shape
    reserve = np.zeros(t) if reserve is None else np.asarray(reserve, dtype=float)
    if reserve.shape != (t,):
        raise ValueError("动态SOC安全裕度长度不符")
    size = t+5*s*t
    grid = np.arange(t)
    charge, discharge, emergency, unused, soc = [np.arange(t+k*s*t, t+(k+1)*s*t).reshape(s, t) for k in range(5)]
    objective = np.zeros(size)
    objective[grid] = prices
    objective[emergency] = 5*weights[:, None]*prices
    bounds = np.zeros((size, 2)); bounds[:, 1] = np.inf
    bounds[grid, 1] = np.maximum(net.max(0), 0)+CAP
    bounds[charge, 1] = bounds[discharge, 1] = CAP
    bounds[soc, 0], bounds[soc, 1] = E_MIN, E_MAX
    rows, cols, coefficients, rhs = [], [], [], []
    def equation(terms, value):
        row = len(rhs)
        for column, coefficient in terms:
            rows.append(row); cols.append(int(column)); coefficients.append(coefficient)
        rhs.append(float(value))
    for j in range(s):
        for i in range(t):
            equation([(grid[i], 1), (discharge[j, i], 1), (emergency[j, i], 1),
                      (charge[j, i], -1), (unused[j, i], -1)], net[j, i])
            terms = [(soc[j, i], 1), (charge[j, i], -ETA_C), (discharge[j, i], 1/ETA_D)]
            if i:
                terms.append((soc[j, i-1], -1))
            equation(terms, initial_soc if i == 0 else 0)
    matrix = coo_matrix((coefficients, (rows, cols)), shape=(len(rhs), size)).tocsc()
    solved = linprog(objective, A_eq=matrix, b_eq=rhs, bounds=bounds, method="highs")
    if not solved.success:
        raise RuntimeError(f"主MILP的LP下界求解失败：{solved.message}")
    # 这些水平只是MILP可行初始解搜索网格，不是新的风险目标或预测超参数。
    caps = []
    for index in (charge, discharge):
        actions = np.maximum(solved.x[index], 0)
        caps.append([np.average(actions, weights=weights, axis=0),
                     *[weighted_quantile(actions, weights, q) for q in (0., .25, .5, .75, 1.)],
                     np.full(t, CAP)])
    pairs = [(c, r) for c in caps[0] for r in caps[1]]
    charges, discharges = np.asarray([c for c, _ in pairs]), np.asarray([r for _, r in pairs])
    planned = np.maximum(solved.x[grid], 0)
    costs = _candidate_costs(net, prices, weights, planned, charges, discharges, initial_soc, reserve)
    best = int(np.argmin(costs))
    policy = Policy(planned, charges[best], discharges[best], reserve)
    refinement = None
    if (costs[best]-solved.fun)/max(abs(solved.fun), 1e-8) > target_gap:
        policy, refinement = refine(policy, net, prices, weights, initial_soc,
                                    target_cost=solved.fun+target_gap*max(abs(solved.fun), 1e-8))
    responses = [replay(policy, path, initial_soc) for path in net]
    value = float(prices@policy.grid + sum(5*p*(prices@r["emergency"]) for p, r in zip(weights, responses)))
    if refinement is None:
        np.testing.assert_allclose(value, costs[best], atol=1e-5, rtol=1e-12)
    else:
        np.testing.assert_allclose(value, refinement["candidate_cost"], atol=1e-5, rtol=1e-12)
    # 由可行域包含关系：LP下界 <= 原参数化策略最优值 <= 经独立回放的可行策略费用。
    lower = float(solved.fun)
    gap = max(value-lower, 0)/max(abs(lower), 1e-8)
    return policy, responses, {"lower_bound": lower, "incumbent_cost": value, "certified_gap": gap,
                               "seconds": time.perf_counter()-started, "variables": size,
                               "constraints": len(rhs), "refinement": refinement,
                               "role": "lower_bound_only_never_free_recourse_execution"}
