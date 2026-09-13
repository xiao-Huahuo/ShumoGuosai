"""仅为原MILP寻找更好的共享参数初始解；不提供全局最优性声明。"""

import numpy as np
from scipy.optimize import minimize
import time

from policy import CAP, E_MIN, E_MAX, ETA_C, ETA_D, Policy


def value_gradient(vector, net, prices, weights, initial_soc, reserve=None):
    """对原文逐步min/max映射作分段导数；最终策略另由独立回放及LP下界验收。"""
    t = len(prices)
    segments = (len(vector)//t-1)//2
    grid = vector[:t]
    cp, rp = vector[t:].reshape(2, t, segments)
    reserve = np.zeros(t) if reserve is None else np.asarray(reserve, dtype=float)
    if reserve.shape != (t,):
        raise ValueError("动态SOC安全裕度长度不符")
    state = np.full(len(net), initial_soc, dtype=float)
    value = float(prices@grid)
    derivatives = []
    for i in range(t):
        x = net[:, i]-grid[i]
        band = np.minimum((segments*(state-E_MIN)/(E_MAX-E_MIN)).astype(int), segments-1)
        band = np.maximum(band, 0)
        c_terms = np.array([cp[i, band], np.maximum(-x, 0), np.maximum((E_MAX-state)/ETA_C, 0)])
        reserve_active = state > E_MIN+reserve[i]
        r_terms = np.array([rp[i, band], np.maximum(x, 0),
                            np.maximum(ETA_D*(state-E_MIN-reserve[i]), 0)])
        c_index, r_index = c_terms.argmin(0), r_terms.argmin(0)
        charge, discharge = c_terms.min(0), r_terms.min(0)
        shortage = x-discharge > 0
        value += float(5*prices[i]*(np.maximum(x-discharge, 0)@weights))
        cg = (x < 0)&(c_index == 1)
        cc = (x < 0)&(c_index == 0)
        ce = -((x < 0)&(c_index == 2)).astype(float)/ETA_C
        rg = -((x > 0)&(r_index == 1)).astype(float)
        rr = (x > 0)&(r_index == 0)
        re = ((x > 0)&(r_index == 2)&reserve_active).astype(float)*ETA_D
        derivatives.append((cg, cc, ce, rg, rr, re, shortage, band))
        state += ETA_C*charge-discharge/ETA_D
    gg = np.zeros(t); gc, gr = np.zeros((2, t, segments)); adjoint = np.zeros(len(net))
    for i in range(t-1, -1, -1):
        cg, cc, ce, rg, rr, re, shortage, band = derivatives[i]
        emergency_price = 5*prices[i]*weights*shortage
        gg[i] = prices[i]+np.sum(emergency_price*(-1-rg)+adjoint*(ETA_C*cg-rg/ETA_D))
        np.add.at(gc[i], band, adjoint*ETA_C*cc)
        np.add.at(gr[i], band, -emergency_price*rr-adjoint*rr/ETA_D)
        adjoint = -emergency_price*re+adjoint*(1+ETA_C*ce-re/ETA_D)
    return value, np.r_[gg, gc.ravel(), gr.ravel()]


def refine(policy, net, prices, weights, initial_soc, *, target_cost=None, seconds=90):
    initial = np.r_[policy.grid, policy.charge_cap.ravel(), policy.discharge_cap.ravel()]
    best = [value_gradient(initial, net, prices, weights, initial_soc, policy.reserve)[0], initial.copy()]
    started = time.perf_counter()
    evaluations = 0
    class Finished(Exception):
        pass
    def objective(vector):
        nonlocal evaluations
        evaluations += 1
        value, gradient = value_gradient(vector, net, prices, weights, initial_soc, policy.reserve)
        if value < best[0]:
            best[:] = [value, vector.copy()]
        if target_cost is not None and best[0] <= target_cost:
            raise Finished("feasible_upper_bound_reached_requested_gap")
        if time.perf_counter()-started >= seconds:
            raise Finished("incumbent_search_time_budget")
        return value, gradient
    bounds = [(0, float(v)) for v in np.maximum(net.max(0), 0)+CAP]+[(0, CAP)]*(2*policy.charge_cap.size)
    try:
        solved = minimize(objective, initial, jac=True, method="L-BFGS-B", bounds=bounds,
                          options={"maxiter": 1000, "maxls": 30, "ftol": 1e-10})
        iterations, termination = int(solved.nit), str(solved.message)
    except Finished as error:
        iterations, termination = None, str(error)
    grid = best[1][:len(prices)]
    caps = best[1][len(prices):].reshape((2,)+policy.charge_cap.shape)
    return Policy(grid, *caps, policy.reserve), {"method": "piecewise_gradient_incumbent_only", "iterations": iterations,
                              "evaluations": evaluations, "seconds": time.perf_counter()-started,
                              "termination": termination, "candidate_cost": best[0],
                              "global_optimality_claim": False}
