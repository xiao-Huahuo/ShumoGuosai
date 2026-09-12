"""最终方案2.5：完整联合误差块、近期窗口、尾部保护medoids与概率守恒。"""

import numpy as np
from scipy.spatial.distance import cdist

from policy import DT, E_MIN, E_MAX, ETA_D


def eligible_origins(shadows, current, horizon, minimum=14, window=None):
    """shadow的索引是forecast origin；只有整个horizon都已实现才有误差块。"""
    origins = np.arange(len(shadows))
    ready = (origins+horizon <= current) & np.isfinite(shadows[:, :horizon]).all(axis=(1, 2, 3))
    if window is not None:
        ready &= origins >= current-window
    result = origins[ready]
    return result if len(result) >= minimum else np.empty(0, dtype=int)


def history_window(shadows, current, horizon, minimum=14, forced_window="auto"):
    windows = [28, 56, 84, None] if forced_window == "auto" else [forced_window]
    for window in windows:
        origins = eligible_origins(shadows, current, horizon, minimum, window)
        if len(origins):
            return origins, window
    raise ValueError("该联合预测流程没有足够完整误差块；不得重采样制造样本")


def joint_blocks(history, shadows, origins, horizon):
    """在同一个origin下相减；保持L/PV、日内以及跨日前瞻次序。"""
    blocks = np.stack([history[j:j+horizon]-shadows[j, :horizon] for j in origins])
    if blocks.shape[1:] != (horizon, 144, 2) or not np.isfinite(blocks).all():
        raise ValueError("联合误差块不完整")
    return blocks


def net_error_energy(blocks):
    """负荷/PV联合误差块转换为母线侧净负荷误差，单位kWh。"""
    blocks = np.asarray(blocks, dtype=float)
    if blocks.ndim != 4 or blocks.shape[2:] != (144, 2) or not np.isfinite(blocks).all():
        raise ValueError("联合误差块维度或数值不合法")
    return (DT*(blocks[..., 0]-blocks[..., 1])).reshape(len(blocks), -1)


def cumulative_pressure(blocks):
    """S_j=max_k[cumsum(e_net)]_+，保留完整预测窗口的时序压力。"""
    errors = net_error_energy(blocks)
    return np.maximum(np.cumsum(errors, axis=1).max(axis=1), 0)


def dynamic_reserve(blocks, quantile=.8):
    """由已完整实现的历史首日误差计算并冻结144段SOC安全裕度。"""
    if not 0 <= quantile <= 1:
        raise ValueError("动态SOC安全裕度分位数不合法")
    errors = net_error_energy(blocks)[:, :144]
    future_pressure = np.empty_like(errors)
    running = np.zeros(len(errors))
    for t in range(143, -1, -1):
        running = np.maximum(errors[:, t]+running, 0)
        future_pressure[:, t] = running
    weights = np.ones(len(errors))/len(errors)
    bus_reserve = weighted_quantile(future_pressure, weights, quantile)
    reserve = np.minimum((E_MAX-E_MIN), bus_reserve/ETA_D)
    return reserve, {"quantile": quantile, "historical_blocks": len(blocks),
                     "max_reserve_kwh": float(reserve.max()),
                     "mean_reserve_kwh": float(reserve.mean())}


def weighted_quantile(values, weights, quantile):
    """离散经验分布左分位，满足F(g-)<=alpha<=F(g)；不作线性插值。"""
    values, weights = np.asarray(values), np.asarray(weights)
    if not 0 <= quantile <= 1 or values.shape[0] != len(weights) or (weights <= 0).any() or not np.isclose(weights.sum(), 1):
        raise ValueError("无效分位概率")
    order = np.argsort(values, axis=0, kind="stable")
    sorted_values = np.take_along_axis(values, order, axis=0)
    sorted_weights = np.broadcast_to(weights.reshape((-1,)+(1,)*(values.ndim-1)), values.shape)
    cumulative = np.cumsum(np.take_along_axis(sorted_weights, order, axis=0), axis=0)
    index = np.argmax(cumulative >= quantile-1e-12, axis=0)
    return np.take_along_axis(sorted_values, index[None], axis=0)[0]


def medoids(blocks, prices, count):
    """确定性PAM交换，强制最严重价格加权正净误差块，真实块代表且簇质量赋权。"""
    size = len(blocks)
    if not 1 <= count <= size:
        raise ValueError("medoid数量必须介于1和真实块数之间")
    scales = np.std(blocks, axis=(0, 1, 2), ddof=1)
    normalized = blocks/np.where(scales > 0, scales, 1)
    points = normalized.reshape(size, -1)
    distances = cdist(points, points)
    positive = np.maximum(DT*(blocks[..., 0]-blocks[..., 1]), 0)
    protected = int(np.argmax(np.sum(positive*np.asarray(prices).reshape(blocks.shape[1:3]), axis=(1, 2))))
    selected = [protected]
    while len(selected) < count:
        nearest = distances[:, selected].min(axis=1)
        remaining = [j for j in range(size) if j not in selected]
        costs = [np.minimum(nearest, distances[:, j]).sum() for j in remaining]
        selected.append(remaining[int(np.argmin(costs))])
    # PAM以严格下降为终止条件，不引入随机样本或任意迭代次数。
    while True:
        current = float(distances[:, selected].min(axis=1).sum())
        best, replacement = current, None
        for position in range(1, count):
            others = selected[:position]+selected[position+1:]
            nearest = distances[:, others].min(axis=1)
            for candidate in range(size):
                if candidate in selected:
                    continue
                score = float(np.minimum(nearest, distances[:, candidate]).sum())
                if score < best-1e-10:
                    best, replacement = score, (position, candidate)
        if replacement is None:
            break
        selected[replacement[0]] = replacement[1]
    selected = np.asarray(selected)
    assignment = np.argmin(distances[:, selected], axis=1)
    # 重复误差块也按实际origin保留概率；每个medoid自身归入自己的簇。
    assignment[selected] = np.arange(count)
    weights = np.bincount(assignment, minlength=count)/size
    return selected, weights, {"protected_index": protected, "cluster_assignment": assignment.tolist(),
                                "scales_kw": scales.tolist(), "distance_objective": float(distances[np.arange(size), selected[assignment]].sum())}


def _representatives(blocks, prices, count):
    if count == 0:
        return np.empty(0, dtype=int), {}
    if count >= len(blocks):
        return np.arange(len(blocks)), {"reduced": False}
    indices, _, meta = medoids(blocks, prices, count)
    return indices, {**meta, "reduced": True}


def construct(point, blocks, prices, count=None, *, origins=None, all_blocks=None,
              all_origins=None, tail_fraction=.2):
    """总场景数不变的body/tail分层；长期尾部与近期主体分别保留经验概率质量。"""
    blocks = np.asarray(blocks, dtype=float)
    all_blocks = blocks if all_blocks is None else np.asarray(all_blocks, dtype=float)
    size = len(blocks)
    if not size or not len(all_blocks) or not 0 < tail_fraction < 1:
        raise ValueError("场景池或尾部分层比例不合法")
    origins = np.arange(size) if origins is None else np.asarray(origins, dtype=int)
    all_origins = origins if all_origins is None else np.asarray(all_origins, dtype=int)
    if len(origins) != size or len(all_origins) != len(all_blocks):
        raise ValueError("场景误差块与forecast-origin索引不一致")
    scenario_count = size if size <= 40 or count is None or count == size else min(size, int(count))
    tail_pool_count = max(1, int(np.floor(tail_fraction*len(all_blocks)+.5)))
    pressure = cumulative_pressure(all_blocks)
    tail_pool_positions = np.argsort(pressure, kind="stable")[-tail_pool_count:]
    tail_origin_set = set(int(v) for v in all_origins[tail_pool_positions])
    body_pool_positions = np.array([i for i, origin in enumerate(origins)
                                    if int(origin) not in tail_origin_set], dtype=int)
    tail_count = max(1, int(np.floor(tail_fraction*scenario_count+.5)))
    body_count = scenario_count-tail_count
    if len(body_pool_positions) < body_count:
        fallback = [i for i in range(size) if i not in set(body_pool_positions.tolist())]
        body_pool_positions = np.r_[body_pool_positions, fallback]
    body_choice, body_meta = _representatives(blocks[body_pool_positions], prices, body_count)
    tail_choice, tail_meta = _representatives(all_blocks[tail_pool_positions], prices, tail_count)
    selected_body_positions = body_pool_positions[body_choice]
    selected_tail_positions = tail_pool_positions[tail_choice]
    selected_blocks = np.concatenate((blocks[selected_body_positions],
                                      all_blocks[selected_tail_positions]), axis=0)
    tail_mass = tail_pool_count/len(all_blocks)
    weights = np.r_[np.full(body_count, (1-tail_mass)/body_count) if body_count else np.empty(0),
                    np.full(tail_count, tail_mass/tail_count)]
    weights /= weights.sum()
    values = np.maximum(np.asarray(point)[None]+selected_blocks, 0)
    net = DT*(values[..., 0]-values[..., 1]).reshape(scenario_count, -1)
    selected_origins = np.r_[origins[selected_body_positions], all_origins[selected_tail_positions]]
    meta = {"reduced": bool(scenario_count < size), "tail_stratification": True,
            "M": size, "M_all": len(all_blocks), "S": scenario_count,
            "S_body": body_count, "S_tail": tail_count,
            "tail_fraction": tail_fraction, "tail_probability_mass": tail_mass,
            "body_probability_mass": 1-tail_mass,
            "tail_pool_count": tail_pool_count,
            "body_origin_indices": origins[selected_body_positions].tolist(),
            "tail_origin_indices": all_origins[selected_tail_positions].tolist(),
            "selected_origin_indices": selected_origins.tolist(),
            "indices": list(range(scenario_count)), "weights": weights.tolist(),
            "body_selection": body_meta, "tail_selection": tail_meta,
            "tail_pressure_min_kwh": float(pressure[tail_pool_positions].min()),
            "tail_pressure_max_kwh": float(pressure[tail_pool_positions].max())}
    return net, weights, meta


def quantile_comparison(full_net, reduced_net, weights):
    rows = {}
    scale = max(float(np.mean(np.abs(full_net))), 1e-8)
    for q in (.8, .9):
        full = weighted_quantile(full_net, np.ones(len(full_net))/len(full_net), q)
        reduced = weighted_quantile(reduced_net, weights, q)
        rows[str(q)] = {"mean_absolute_error_kwh": float(np.abs(full-reduced).mean()),
                       "normalized_error": float(np.abs(full-reduced).mean()/scale),
                       "positive_tail_underestimate_kwh": float(np.maximum(full-reduced, 0).mean())}
    return rows
