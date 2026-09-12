"""2.10：刚性场景计划、完全信息及fixed-g Oracle；均与主政策入口分离。"""

import time

import numpy as np
from scipy.optimize import linprog
from scipy.sparse import coo_matrix

from policy import CAP, E_MIN, E_MAX, ETA_C, ETA_D, PHYSICAL_TOL, Policy, replay, validate_replay


def rigid_schedule(net, prices, weights, initial_soc, *, fixed_grid=None):
    """共同c/r轨迹的精确LP。

    无回售、非负能价、可弃电且无终端等式时，LP同时充放电可消去：令
    a=min(c,r/(ηcηd))，c'=c-a，r'=r-ηcηd a。SOC不变，母线需求减少，
    仅减少q/增加w，故费用不增；投影后与LP下界一致才接受为精确解。
    """
    started = time.perf_counter()
    net, prices, weights = map(lambda x: np.asarray(x, dtype=float), (net, prices, weights))
    s, t = net.shape
    if prices.shape != (t,) or weights.shape != (s,) or not np.isclose(weights.sum(), 1) or min(weights) <= 0 or min(prices) <= 0:
        raise ValueError("对照输入维度/概率/电价不符")
    if not np.isfinite(net).all() or not E_MIN <= initial_soc <= E_MAX:
        raise ValueError("对照净负荷/初态无效")
    size = 4*t+2*s*t
    g, c, r, e = [np.arange(k*t, (k+1)*t) for k in range(4)]
    q = np.arange(4*t, 4*t+s*t).reshape(s, t)
    w = np.arange(4*t+s*t, size).reshape(s, t)
    objective = np.zeros(size)
    objective[g] = prices
    objective[q] = 5*weights[:, None]*prices
    bounds = [(0, None)]*size
    for indices, bound in ((c, (0, CAP)), (r, (0, CAP)), (e, (E_MIN, E_MAX))):
        for i in indices:
            bounds[i] = bound
    if fixed_grid is not None:
        fixed_grid = np.asarray(fixed_grid)
        if fixed_grid.shape != (t,) or not np.isfinite(fixed_grid).all() or (fixed_grid < 0).any():
            raise ValueError("Oracle固定购电输入不符")
        for i, value in zip(g, fixed_grid):
            bounds[i] = (float(value), float(value))
    rows, cols, coefficients, rhs = [], [], [], []
    def equation(terms, value):
        row = len(rhs)
        for col, coefficient in terms:
            rows.append(row); cols.append(int(col)); coefficients.append(coefficient)
        rhs.append(value)
    for i in range(t):
        terms = [(e[i], 1), (c[i], -ETA_C), (r[i], 1/ETA_D)]
        if i:
            terms.append((e[i-1], -1))
        equation(terms, initial_soc if i == 0 else 0)
    for j in range(s):
        for i in range(t):
            equation([(g[i], 1), (r[i], 1), (q[j, i], 1), (c[i], -1), (w[j, i], -1)], net[j, i])
    matrix = coo_matrix((coefficients, (rows, cols)), shape=(len(rhs), size)).tocsc()
    solved = linprog(objective, A_eq=matrix, b_eq=rhs, bounds=bounds, method="highs")
    if not solved.success:
        raise RuntimeError(f"对照/Oracle LP失败：{solved.message}")
    grid, charge, discharge = np.maximum(solved.x[g], 0), np.maximum(solved.x[c], 0), np.maximum(solved.x[r], 0)
    removed = np.minimum(charge, discharge/(ETA_C*ETA_D))
    charge, discharge = charge-removed, discharge-ETA_C*ETA_D*removed
    soc = initial_soc+np.cumsum(ETA_C*charge-discharge/ETA_D)
    responses = []
    for path in net:
        gap = path+charge-grid-discharge
        result = {"charge": charge, "discharge": discharge, "emergency": np.maximum(gap, 0),
                  "unused": np.maximum(-gap, 0), "soc": soc}
        validate_replay(grid, path, initial_soc, result, rigid=True)
        responses.append(result)
    exact_cost = float(prices@grid + sum(5*p*(prices@response["emergency"]) for p, response in zip(weights, responses)))
    if not np.isclose(exact_cost, solved.fun, rtol=1e-8, atol=1e-5):
        raise ValueError("去除充放电循环后费用未与LP下界一致")
    info = {"objective": exact_cost, "lower_bound": float(solved.fun), "reliable": True,
            "solve_seconds": time.perf_counter()-started, "status": "optimal",
            "continuous_variables": size, "binary_variables": 0, "constraints": len(rhs),
            "cycle_removed_kwh": float(removed.sum()), "solver": "scipy.linprog/HiGHS",
            "mip_gap": 0.0, "role": "rigid_shared_storage" if s > 1 else "perfect_information"}
    return grid, responses, info


def deterministic_policy(net, prices, initial_soc, reserve=None):
    """确定性退化：若LP下界被同一反馈映射达到，即取得可验证的全局最优证书。

    LP只是lower-bound计算器；只有原模型回放费用等于该下界才返回可靠策略。
    无法闭合时返回None，由调用方转入完整indicator模型，绝不松弛主模型。
    """
    net, prices = np.asarray(net), np.asarray(prices)
    grid, responses, info = rigid_schedule(net[None], prices, [1.], initial_soc)
    policy = Policy(grid, responses[0]["charge"], responses[0]["discharge"], reserve)
    actual = replay(policy, net, initial_soc)
    value = float(prices@(grid+5*actual["emergency"]))
    closed = bool(np.isclose(value, info["lower_bound"], rtol=1e-9, atol=PHYSICAL_TOL))
    return (policy if closed else None), [actual], {**info, "objective": value,
            "role": "deterministic_feedback_lower_bound_certificate", "reliable": closed,
            "certificate_gap_yuan": value-info["lower_bound"]}


def oracle_pair(real_net, prices, initial_soc, planned_grid, actual_cost):
    """两类Oracle仅接收已经完成的真实回放；调用方不得回流至预测/选模。"""
    _, _, perfect = rigid_schedule(np.asarray(real_net)[None], prices, [1.], initial_soc)
    _, _, response = rigid_schedule(np.asarray(real_net)[None], prices, [1.], initial_soc, fixed_grid=planned_grid)
    pi, fixed = perfect["objective"], response["objective"]
    if pi > fixed+PHYSICAL_TOL or fixed > actual_cost+PHYSICAL_TOL:
        raise ValueError("Oracle下界嵌套失败")
    return {"perfect_information": perfect, "fixed_grid_information": response,
            "actual_cost": actual_cost, "Gap_PI": (actual_cost-pi)/pi if pi else None,
            "Gap_resp": (actual_cost-fixed)/actual_cost if actual_cost else None,
            "interpretation": "information_value_and_policy_restriction_not_pure_parameterization_loss"}
