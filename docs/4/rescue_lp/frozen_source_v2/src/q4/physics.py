"""节点预提交储能计划；结算额度、实际调用和紧急购电分别核算。"""
from dataclasses import dataclass
import numpy as np
from .config import CAP, E_MIN, E_MAX, ETA_C, ETA_D, TOL


@dataclass
class DispatchPolicy:
    grid: np.ndarray
    charge: np.ndarray
    discharge: np.ndarray

    def part(self, start: int, end: int) -> 'DispatchPolicy':
        return DispatchPolicy(*(value[start:end].copy() for value in
                                (self.grid, self.charge, self.discharge)))


def adjustment_quantity(grid: np.ndarray, reference: np.ndarray) -> np.ndarray:
    difference = np.asarray(grid) - np.asarray(reference)
    return 1.5 * np.maximum(difference, 0) - 0.5 * np.maximum(-difference, 0)


def replay(policy: DispatchPolicy, net: np.ndarray, initial: float) -> dict[str, np.ndarray]:
    net = np.asarray(net, dtype=float)
    grid, charge, discharge = (np.asarray(v, dtype=float) for v in
                               (policy.grid, policy.charge, policy.discharge))
    if any(v.shape != net.shape or not np.isfinite(v).all() for v in (grid, charge, discharge, net)):
        raise ValueError('储能计划与净负荷维度或数值非法')
    if min(grid.min(), charge.min(), discharge.min()) < -TOL or np.max(charge + discharge) > CAP + TOL:
        raise ValueError('购电非负约束或储能功率约束违反')
    soc = initial + np.cumsum(ETA_C * charge - discharge / ETA_D)
    if min(initial, soc.min()) < E_MIN - TOL or max(initial, soc.max()) > E_MAX + TOL:
        raise ValueError('SOC越界')
    balance_need = net + charge - discharge
    called = np.minimum(grid, np.maximum(balance_need, 0))
    unused = grid - called
    emergency = np.maximum(balance_need - called, 0)
    spill = np.maximum(called - balance_need, 0)
    np.testing.assert_allclose(called + discharge + emergency, net + charge + spill, atol=TOL, rtol=0)
    return dict(called=called, unused=unused, charge=charge.copy(), discharge=discharge.copy(),
                emergency=emergency, spill=spill, soc=soc, total_surplus=unused + spill)


def scenario_costs(policy: DispatchPolicy, responses: list[dict], prices: np.ndarray,
                   reference: np.ndarray | None = None, today: int | None = None) -> np.ndarray:
    prices = np.asarray(prices, dtype=float)
    today = prices.shape[1] if today is None else min(int(today), prices.shape[1])
    quantity = policy.grid.copy()
    if reference is not None:
        quantity[:today] = reference[:today] + adjustment_quantity(policy.grid[:today], reference[:today])
    return np.asarray([np.sum(p * (quantity + 5 * response['emergency']))
                       for p, response in zip(prices, responses)])
