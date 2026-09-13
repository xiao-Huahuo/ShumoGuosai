"""最终方案2.7.3/2.9.3：冻结策略、单步因果响应与独立物理验收。"""

from dataclasses import dataclass

import numpy as np

DT = 1 / 6
E_MIN, E_MAX, E_INITIAL = 1200.0, 10800.0, 6000.0
ETA_C = ETA_D = 0.9
CAP = 5000 * DT
PHYSICAL_TOL = 1e-5  # kWh，仅数值验收容差，不参与经济策略或紧急事件定义。


@dataclass(frozen=True)
class Policy:
    grid: np.ndarray
    charge_cap: np.ndarray
    discharge_cap: np.ndarray

    def __post_init__(self):
        for name in ("grid", "charge_cap", "discharge_cap"):
            value = np.array(getattr(self, name), dtype=float, copy=True)
            if not np.isfinite(value).all() or (value < 0).any():
                raise ValueError("策略必须有限、非负")
            value.setflags(write=False)
            object.__setattr__(self, name, value)
        if self.grid.ndim != 1 or not len(self.grid):
            raise ValueError("购电策略应为非空一维数组")
        shapes = ((len(self.grid),), (len(self.grid), 3))
        if self.charge_cap.shape not in shapes or self.discharge_cap.shape != self.charge_cap.shape:
            raise ValueError("响应上限应为每时段一组或三组SOC分段参数")
        if max(self.charge_cap.max(), self.discharge_cap.max()) > CAP + PHYSICAL_TOL:
            raise ValueError("响应上限超过物理功率")

    def first(self, periods=144):
        return Policy(self.grid[:periods], self.charge_cap[:periods], self.discharge_cap[:periods])


def respond(net, previous_soc, grid, charge_cap, discharge_cap):
    """只接收本时段观测；没有未来数组、场景库或优化器接口。单位全部kWh。"""
    if not np.isfinite([net, previous_soc, grid, charge_cap, discharge_cap]).all():
        raise ValueError("非有限单步输入")
    if not E_MIN - PHYSICAL_TOL <= previous_soc <= E_MAX + PHYSICAL_TOL:
        raise ValueError("上一时段SOC越界")
    if min(grid, charge_cap, discharge_cap) < 0 or max(charge_cap, discharge_cap) > CAP + PHYSICAL_TOL:
        raise ValueError("单步策略边界不合法")
    deficit = net - grid
    charge = min(charge_cap, max(-deficit, 0), max((E_MAX - previous_soc) / ETA_C, 0))
    discharge = min(discharge_cap, max(deficit, 0), max(ETA_D * (previous_soc - E_MIN), 0))
    emergency = max(deficit - discharge, 0)
    unused = max(-deficit - charge, 0)
    soc = previous_soc + ETA_C * charge - discharge / ETA_D
    return charge, discharge, emergency, unused, soc


def replay(policy, net, initial_soc):
    """顺序聚合回放；第t步只向respond传入net[t]及已实现状态。"""
    net = np.asarray(net, dtype=float)
    if net.shape != policy.grid.shape or not np.isfinite(net).all():
        raise ValueError("真实净负荷与冻结策略长度不一致")
    state = float(initial_soc)
    output = np.empty((len(net), 5))
    for t, current_net in enumerate(net):
        if policy.charge_cap.ndim == 2:
            segment = min(int(3 * max(state - E_MIN, 0) / (E_MAX - E_MIN)), 2)
            cp, rp = policy.charge_cap[t, segment], policy.discharge_cap[t, segment]
        else:
            cp, rp = policy.charge_cap[t], policy.discharge_cap[t]
        output[t] = respond(current_net, state, policy.grid[t], cp, rp)
        state = output[t, 4]
    result = dict(zip(("charge", "discharge", "emergency", "unused", "soc"), output.T))
    validate_replay(policy.grid, net, initial_soc, result)
    return result


def validate_replay(grid, net, initial_soc, result, *, rigid=False):
    c, r, q, w, e = [np.asarray(result[k]) for k in ("charge", "discharge", "emergency", "unused", "soc")]
    np.testing.assert_allclose(grid + r + q, net + c + w, atol=PHYSICAL_TOL, rtol=0)
    np.testing.assert_allclose(e, np.r_[initial_soc, e[:-1]] + ETA_C*c - r/ETA_D,
                               atol=PHYSICAL_TOL, rtol=0)
    if min(c.min(), r.min(), q.min(), w.min()) < -PHYSICAL_TOL or e.min() < E_MIN-PHYSICAL_TOL or e.max() > E_MAX+PHYSICAL_TOL:
        raise ValueError("回放能量/SOC边界失败")
    if max(c.max(), r.max()) > CAP + PHYSICAL_TOL or np.any((c > PHYSICAL_TOL) & (r > PHYSICAL_TOL)):
        raise ValueError("回放功率/充放电互斥失败")
    if not rigid and np.any((q > PHYSICAL_TOL) & (c > PHYSICAL_TOL)):
        raise ValueError("负荷优先失败：紧急购电同时充电")


def cost(policy, response, prices):
    return float(np.dot(prices, policy.grid + 5 * response["emergency"]))
