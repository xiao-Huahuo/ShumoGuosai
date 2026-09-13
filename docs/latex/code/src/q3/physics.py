"""3.9、3.14—3.21：同一冻结反馈用于场景和真实回放。"""
from dataclasses import dataclass
import numpy as np
from .config import CAP, E_MIN, E_MAX, ETA, TOL


@dataclass
class Policy:
    grid: np.ndarray
    charge_cap: np.ndarray
    discharge_cap: np.ndarray

    def part(self, start: int, end: int) -> 'Policy':
        return Policy(*(v[start:end].copy() for v in (self.grid, self.charge_cap, self.discharge_cap)))


def adjustment(grid: np.ndarray, reference: np.ndarray, prices: np.ndarray) -> np.ndarray:
    difference = grid-reference
    return prices*(1.5*np.maximum(difference, 0)-.5*np.maximum(-difference, 0))


def replay(policy: Policy, net: np.ndarray, initial: float, *, mode: str = 'aggregate',
           previous_net: float | None = None) -> dict[str, np.ndarray]:
    net = np.asarray(net, dtype=float)
    if not E_MIN-TOL <= initial <= E_MAX+TOL or mode not in ('aggregate', 'lag'):
        raise ValueError('SOC或反馈口径非法')
    if any(v.shape != net.shape or not np.isfinite(v).all() for v in (policy.grid, policy.charge_cap, policy.discharge_cap)):
        raise ValueError('冻结策略维度或数值非法')
    if not np.isfinite(net).all() or min(policy.grid.min(), policy.charge_cap.min(), policy.discharge_cap.min()) < -TOL:
        raise ValueError('策略/净负荷非法')
    if max(policy.charge_cap.max(), policy.discharge_cap.max()) > CAP+TOL:
        raise ValueError('响应上限超过物理限值')
    if mode == 'lag' and previous_net is None:
        raise ValueError('lag反馈需要已实现上一时隙净负荷，不得读取当前值填补')
    result = {key: np.zeros(len(net)) for key in ('charge', 'discharge', 'emergency', 'spill', 'soc')}
    soc = float(initial)
    for t, demand in enumerate(net):
        observed = demand if mode == 'aggregate' else (previous_net if t == 0 else net[t-1])
        x = observed-policy.grid[t]
        c = min(policy.charge_cap[t], max(-x, 0), max((E_MAX-soc)/ETA, 0))
        r = min(policy.discharge_cap[t], max(x, 0), max(ETA*(soc-E_MIN), 0))
        remaining = demand-policy.grid[t]+c-r
        q, u = max(remaining, 0), max(-remaining, 0)
        soc += ETA*c-r/ETA
        for key, value in zip(result, (c, r, q, u, soc)):
            result[key][t] = value
    validate(policy.grid, net, initial, result)
    return result


def validate(grid: np.ndarray, net: np.ndarray, initial: float, result: dict) -> None:
    c, r, q, u, e = (result[key] for key in ('charge', 'discharge', 'emergency', 'spill', 'soc'))
    if not all(np.isfinite(v).all() for v in (grid, net, c, r, q, u, e)):
        raise ValueError('回放出现非有限数值')
    if min(c.min(), r.min(), q.min(), u.min(), grid.min()) < -TOL:
        raise ValueError('负电量')
    if max(c.max(), r.max()) > CAP+TOL or np.minimum(c, r).max() > TOL:
        raise ValueError('功率/互斥违规')
    if e.min() < E_MIN-TOL or e.max() > E_MAX+TOL:
        raise ValueError('SOC越界')
    np.testing.assert_allclose(grid+r+q-net-c-u, 0, atol=TOL, rtol=0)
    np.testing.assert_allclose(e-np.r_[initial, e[:-1]]-ETA*c+r/ETA, 0, atol=TOL, rtol=0)


def no_storage_decision(demand: np.ndarray, reference: float, weights: np.ndarray) -> float:
    """3.10离散经验分布退化模型；只供机制核验，不约束完整储能优化。"""
    choices = np.unique(np.r_[0., reference, demand[demand >= 0]])
    costs = [reference+float(adjustment(np.array([q]), np.array([reference]), np.ones(1))[0])
             +5*np.dot(weights, np.maximum(demand-q, 0)) for q in choices]
    return float(choices[np.argmin(costs)])
