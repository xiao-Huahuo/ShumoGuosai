"""7.6.2/7.7.5—7.7.6：结算量、物理调用量和因果储能反馈分离。"""
import numpy as np
from src.q3.physics import Policy, replay as _surplus_replay
from .config import TOL


def adjustment_quantity(grid: np.ndarray, reference: np.ndarray) -> np.ndarray:
    difference = np.asarray(grid) - np.asarray(reference)
    return 1.5 * np.maximum(difference, 0) - 0.5 * np.maximum(-difference, 0)


def replay(policy: Policy, net: np.ndarray, initial: float) -> dict[str, np.ndarray]:
    """Q3验证反馈给出同一c/r/h/SOC；再把总富余精确拆成未调用计划量u与物理弃电w。"""
    base = _surplus_replay(policy, np.asarray(net, dtype=float), initial, mode="aggregate")
    balance_need = np.asarray(net) + base["charge"] - base["discharge"]
    called = np.minimum(policy.grid, np.maximum(balance_need, 0))
    unused = policy.grid - called
    spill = np.maximum(-balance_need + called, 0)
    result = {
        "called": called,
        "unused": unused,
        "charge": base["charge"],
        "discharge": base["discharge"],
        "emergency": base["emergency"],
        "spill": spill,
        "soc": base["soc"],
        "total_surplus": base["spill"],
    }
    if min(called.min(), unused.min(), spill.min()) < -TOL:
        raise ValueError("物理调用量拆分出现负值")
    np.testing.assert_allclose(unused + spill, base["spill"], atol=TOL, rtol=0)
    np.testing.assert_allclose(called + base["discharge"] + base["emergency"],
                               np.asarray(net) + base["charge"] + spill, atol=TOL, rtol=0)
    return result


def scenario_costs(policy: Policy, responses: list[dict], prices: np.ndarray,
                   reference: np.ndarray | None = None, today: int | None = None) -> np.ndarray:
    prices = np.asarray(prices, dtype=float)
    today = prices.shape[1] if today is None else min(int(today), prices.shape[1])
    result = np.empty(len(prices))
    for j, (path_prices, response) in enumerate(zip(prices, responses)):
        if reference is None:
            scheduled = path_prices * policy.grid
        else:
            scheduled = path_prices * policy.grid
            scheduled[:today] = path_prices[:today] * (
                reference[:today] + adjustment_quantity(policy.grid[:today], reference[:today])
            )
        result[j] = float(np.sum(scheduled + 5 * path_prices * response["emergency"]))
    return result

