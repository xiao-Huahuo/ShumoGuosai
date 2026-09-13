"""只改进MILP初始可行策略；分段梯度不提供任何全局最优性声明。"""
import time
import numpy as np
from scipy.optimize import minimize
from .config import CAP, E_MIN, E_MAX, ETA
from .physics import Policy, adjustment


def value_gradient(vector: np.ndarray, net: np.ndarray, prices: np.ndarray, weights: np.ndarray,
                   initial: float, reference: np.ndarray | None, today: int, terminal: float) -> tuple[float, np.ndarray]:
    t = len(prices); g, cp, rp = vector.reshape(3, t)
    state = np.full(len(net), initial)
    if reference is None:
        value, price_gradient = float(prices@g), prices.copy()
    else:
        value = float(adjustment(g[:today], reference[:today], prices[:today]).sum()+prices[today:]@g[today:])
        price_gradient = prices.copy(); price_gradient[:today] *= np.where(g[:today] >= reference[:today], 1.5, .5)
    derivatives = []
    for i in range(t):
        x = net[:, i]-g[i]
        cterms = np.array([np.full(len(net), cp[i]), np.maximum(-x, 0), np.maximum((E_MAX-state)/ETA, 0)])
        rterms = np.array([np.full(len(net), rp[i]), np.maximum(x, 0), np.maximum(ETA*(state-E_MIN), 0)])
        ci, ri = cterms.argmin(0), rterms.argmin(0)
        c, r = cterms.min(0), rterms.min(0)
        shortage = x-r > 0
        value += float(5*prices[i]*(np.maximum(x-r, 0)@weights))
        derivatives.append(((x < 0)&(ci == 1), (x < 0)&(ci == 0), -((x < 0)&(ci == 2)).astype(float)/ETA,
                            -((x > 0)&(ri == 1)).astype(float), (x > 0)&(ri == 0), ((x > 0)&(ri == 2)).astype(float)*ETA, shortage))
        state += ETA*c-r/ETA
    value -= float(terminal*(weights@state))
    gradient = np.zeros((3, t)); adjoint = -terminal*weights
    for i in range(t-1, -1, -1):
        cg, cc, ce, rg, rr, re, shortage = derivatives[i]
        emergency_price = 5*prices[i]*weights*shortage
        gradient[0, i] = price_gradient[i]+np.sum(emergency_price*(-1-rg)+adjoint*(ETA*cg-rg/ETA))
        gradient[1, i] = np.sum(adjoint*ETA*cc)
        gradient[2, i] = np.sum(-emergency_price*rr-adjoint*rr/ETA)
        adjoint = -emergency_price*re+adjoint*(1+ETA*ce-re/ETA)
    return value, gradient.ravel()


def refine(policy: Policy, net: np.ndarray, prices: np.ndarray, weights: np.ndarray, initial: float,
           reference: np.ndarray | None, today: int, terminal: float, upper: np.ndarray,
           seconds: float) -> Policy:
    started = time.perf_counter()
    vector = np.r_[policy.grid, policy.charge_cap, policy.discharge_cap]
    best = [value_gradient(vector, net, prices, weights, initial, reference, today, terminal)[0], vector.copy()]

    class BudgetReached(Exception):
        pass

    def evaluate(v: np.ndarray) -> tuple[float, np.ndarray]:
        value, gradient = value_gradient(v, net, prices, weights, initial, reference, today, terminal)
        if value < best[0]:
            best[:] = [value, v.copy()]
        if time.perf_counter()-started > seconds:
            raise BudgetReached
        return value, gradient

    try:
        minimize(evaluate, vector, jac=True, method='L-BFGS-B',
                 bounds=[(0., float(v)) for v in upper]+[(0., CAP)]*(2*len(prices)),
                 options={'maxiter': 100, 'maxls': 20, 'ftol': 1e-10})
    except BudgetReached:
        pass
    return Policy(*best[1].reshape(3, len(prices)))
