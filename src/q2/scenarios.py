"""最终方案2.5：完整联合误差块、近期窗口、尾部保护medoids与概率守恒。"""

import numpy as np
from scipy.spatial.distance import cdist

from policy import DT


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


def construct(point, blocks, prices, count=None):
    size = len(blocks)
    if size <= 40:
        indices, weights, meta = np.arange(size), np.ones(size)/size, {"reduced": False}
    elif count is None or count == size:
        indices, weights, meta = np.arange(size), np.ones(size)/size, {"reduced": False}
    else:
        indices, weights, meta = medoids(blocks, prices, count)
        meta["reduced"] = True
    values = np.maximum(np.asarray(point)[None]+blocks[indices], 0)
    net = DT*(values[..., 0]-values[..., 1]).reshape(len(indices), -1)
    return net, weights, {**meta, "M": size, "S": len(indices), "indices": indices.tolist(), "weights": weights.tolist()}


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
