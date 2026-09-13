"""7.4/7.5/7.7：联合残差、前缀条件化、尾部保持缩减和Wasserstein半径。"""
from dataclasses import dataclass
from functools import lru_cache
import time
import numpy as np
from scipy.optimize import linprog
from scipy.sparse import coo_matrix
from .config import Config
from .data import Inputs


def _scale(values: np.ndarray) -> np.ndarray:
    median = np.median(values, axis=0)
    scale = 1.4826 * np.median(abs(values - median), axis=0)
    positive = scale[scale > 1e-10]
    fallback = float(np.median(positive)) if len(positive) else 1.0
    return np.where(scale > 1e-10, scale, fallback)


def joint_distance(net: np.ndarray, price: np.ndarray, net_weight: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    sn, sp = _scale(net), _scale(price)
    dn = np.mean(abs(net[:, None] - net[None, :]) / sn, axis=2)
    dp = np.mean(abs(price[:, None] - price[None, :]) / sp, axis=2)
    return net_weight * dn + (1 - net_weight) * dp, sn, sp


def medoids(distance: np.ndarray, count: int) -> np.ndarray:
    n = len(distance)
    if not 1 <= count <= n or distance.shape != (n, n):
        raise ValueError("k-medoids距离或数量非法")
    chosen = [int(np.argmin(distance.sum(axis=0)))]
    while len(chosen) < count:
        candidates = [i for i in range(n) if i not in chosen]
        chosen.append(min(candidates, key=lambda i: (np.min(distance[:, chosen + [i]], axis=1).sum(), i)))
    while True:
        current = float(np.min(distance[:, chosen], axis=1).sum())
        best = (current, None)
        for position in range(count):
            for candidate in range(n):
                if candidate in chosen:
                    continue
                trial = chosen.copy()
                trial[position] = candidate
                value = float(np.min(distance[:, trial], axis=1).sum())
                if value < best[0] - 1e-10:
                    best = value, trial
        if best[1] is None:
            return np.asarray(chosen, dtype=int)
        chosen = best[1]


@lru_cache(maxsize=8)
def _transport_equalities(count: int):
    columns = np.arange(count * count)
    rows = np.r_[np.repeat(np.arange(count), count), np.tile(np.arange(count), count) + count]
    return coo_matrix((np.ones(2 * count * count), (rows, np.tile(columns, 2))),
                      shape=(2 * count, count * count)).tocsr()


def _transport_distance(first: np.ndarray, second: np.ndarray, distance: np.ndarray) -> float:
    equalities = _transport_equalities(len(first))
    result = linprog(distance.ravel(), A_eq=equalities, b_eq=np.r_[first, second],
                     bounds=(0, None), method="highs")
    if not result.success:
        raise RuntimeError(f"Wasserstein运输问题失败：{result.message}")
    return float(result.fun)


def _prefix_weights(data: Inputs, days: np.ndarray, day: int, hour: int, config: Config) -> tuple[np.ndarray, dict]:
    if hour == 0 or not config.conditional:
        weights = np.full(len(days), 1 / len(days))
        return weights, {"conditional": False, "bandwidth": None, "ESS": float(len(days))}
    history = np.vstack([data.prefix(int(j), hour) for j in days])
    observed = data.prefix(day, hour)
    scale = history.std(axis=0)
    scale[scale < 1e-10] = 1.0
    distances = np.mean(abs(history - observed) / scale, axis=1)
    positive = distances[distances > 1e-12]
    bandwidth = float(np.median(positive)) if len(positive) else 1.0
    target = min(config.min_ess, float(len(days)))
    while True:
        shifted = distances - distances.min()
        raw = np.exp(-shifted / max(bandwidth, 1e-12))
        weights = raw / raw.sum()
        ess = float(1 / np.dot(weights, weights))
        if ess >= target - 1e-9:
            break
        bandwidth *= 1.5
    return weights, {"conditional": True, "bandwidth": bandwidth, "ESS": ess,
                     "prefix_dimension": history.shape[1], "target_ESS": target}


def _reduce(net: np.ndarray, price: np.ndarray, prior: np.ndarray, config: Config) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, dict]:
    distance, sn, sp = joint_distance(net, price, config.net_weight)
    risk = np.mean(np.maximum(net / sn, 0) * np.maximum(price / sp, 0), axis=1)
    tail = np.flatnonzero(risk > np.quantile(risk, 0.9))
    count = min(config.scenarios, len(net))
    if len(tail) > count:
        raise ValueError("90%联合尾部轨迹多于场景上限，禁止删除强制尾部")
    if len(net) <= count:
        representatives = np.arange(len(net))
    else:
        rest = np.asarray([i for i in range(len(net)) if i not in set(tail)], dtype=int)
        ordinary_count = count - len(tail)
        ordinary = medoids(distance[np.ix_(rest, rest)], ordinary_count) if ordinary_count else np.empty(0, dtype=int)
        representatives = np.r_[tail, rest[ordinary]]
    # 尾部为singleton，普通质量只分配给普通medoids。
    tail_set = set(tail)
    ordinary_rows = np.asarray([i for i in range(len(net)) if i not in tail_set], dtype=int)
    ordinary_columns = np.asarray([k for k, i in enumerate(representatives) if i not in tail_set], dtype=int)
    if len(ordinary_rows) and not len(ordinary_columns):
        raise ValueError("强制尾部之外至少需要一个普通代表")
    labels = np.empty(len(net), dtype=int)
    if len(ordinary_rows):
        labels[ordinary_rows] = ordinary_columns[np.argmin(
            distance[np.ix_(ordinary_rows, representatives[ordinary_columns])], axis=1)]
    labels[representatives] = np.arange(len(representatives))
    weights = np.bincount(labels, weights=prior, minlength=len(representatives))
    np.testing.assert_allclose(weights.sum(), prior.sum(), atol=1e-12)
    weights /= weights.sum()
    tail_columns = [k for k, i in enumerate(representatives) if i in tail_set]
    np.testing.assert_allclose(weights[tail_columns], prior[representatives[tail_columns]] / prior.sum(), atol=1e-12)
    audit = {
        "tail_indices_in_pool": tail.tolist(),
        "tail_prior_mass": prior[tail].tolist(),
        "tail_weights": weights[tail_columns].tolist(),
        "tail_singletons_verified": True,
        "tail_risk_threshold": float(np.quantile(risk, 0.9)),
        "risk_scores": risk.tolist(),
        "represented_counts": np.bincount(labels, minlength=len(representatives)).tolist(),
        "representative_pool_indices": representatives.tolist(),
    }
    return representatives, labels, weights, distance[np.ix_(representatives, representatives)], audit


@dataclass
class Scenarios:
    net: np.ndarray
    prices: np.ndarray
    weights: np.ndarray
    distance: np.ndarray
    radius: float
    audit: dict


def construct(data: Inputs, day: int, hour: int, length: int, config: Config) -> Scenarios:
    started = time.perf_counter()
    point_net = data.point_net(day, hour, length)
    point_price = data.point_price(day, hour, length)
    days, net_errors, price_errors = data.joint_history(day, hour, length)
    recent = days >= day - config.residual_window
    days, net_errors, price_errors = days[recent], net_errors[recent], price_errors[recent]
    if len(days) == 0:
        return Scenarios(point_net[None], point_price[None], np.ones(1), np.zeros((1, 1)), 0.0,
                         {"day": day, "hour": hour, "length": length, "S": 1, "deterministic": True})
    prior, conditioning = _prefix_weights(data, days, day, hour, config)
    if not config.joint and len(days) > 1:
        permutation = np.random.default_rng(config.seed + day * 10 + hour).permutation(len(days))
        price_errors = price_errors[permutation]
    representatives, labels, weights, distance, reduction = _reduce(net_errors, price_errors, prior, config)
    reduced_net = net_errors[representatives]
    reduced_price = price_errors[representatives]
    radius = 0.0
    bootstrap = []
    if config.dro_scale > 0 and len(representatives) > 1:
        generator = np.random.default_rng(config.seed + day * 100 + hour)
        for _ in range(config.bootstrap_repetitions):
            counts = generator.multinomial(len(days), prior)
            sampled = np.bincount(labels, weights=counts, minlength=len(representatives)) / len(days)
            bootstrap.append(_transport_distance(sampled, weights, distance))
        radius = float(np.quantile(bootstrap, config.bootstrap_quantile)) * config.dro_scale
    audit = {
        "construction_seconds": time.perf_counter() - started,
        "day": day,
        "hour": hour,
        "length": length,
        "history_days": days.tolist(),
        "window": config.residual_window,
        "joint": config.joint,
        "S": len(representatives),
        "weights": weights.tolist(),
        "distance_weight_net": config.net_weight,
        "radius": radius,
        "radius_scale": config.dro_scale,
        "bootstrap_repetitions": config.bootstrap_repetitions,
        "bootstrap_quantile": config.bootstrap_quantile,
        "bootstrap_distances": bootstrap,
        **conditioning,
        **reduction,
    }
    return Scenarios(
        point_net + reduced_net,
        np.maximum(point_price + reduced_price, 0.0),
        weights,
        distance,
        radius,
        audit,
    )
