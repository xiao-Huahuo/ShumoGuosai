"""3.8.1：近期量级条件池、尾部保持PAM k-medoids与配对场景。"""
from dataclasses import dataclass
import numpy as np
from scipy.spatial.distance import cdist
from .config import Config, DT
from .data import Inputs


def medoids(values: np.ndarray, count: int) -> tuple[np.ndarray, np.ndarray]:
    """确定性PAM BUILD+SWAP，稳定并列按索引；重复轨迹不复制伪样本。"""
    n = len(values)
    if not 1 <= count <= n:
        raise ValueError('medoid数无效')
    distance = cdist(values, values)
    chosen = [int(np.argmin(distance.sum(axis=0)))]
    while len(chosen) < count:
        candidates = [j for j in range(n) if j not in chosen]
        chosen.append(min(candidates, key=lambda j: (np.min(distance[:, chosen+[j]], axis=1).sum(), j)))
    while True:
        cost = np.min(distance[:, chosen], axis=1).sum()
        best = (cost, None)
        for position in range(count):
            for candidate in range(n):
                if candidate in chosen:
                    continue
                trial = chosen.copy(); trial[position] = candidate
                objective = np.min(distance[:, trial], axis=1).sum()
                if objective < best[0]-1e-10:
                    best = objective, trial
        if best[1] is None:
            break
        chosen = best[1]
    chosen = np.asarray(chosen, dtype=int)
    labels = np.argmin(distance[:, chosen], axis=1)
    labels[chosen] = np.arange(count)  # 每个真实代表至少代表其自身，零距离并列可任意分配。
    return chosen, labels


def pool_indices(days: np.ndarray, scales: np.ndarray, day: int, current_scale: float,
                 config: Config) -> tuple[np.ndarray, dict]:
    if len(days) == 0:
        return np.array([], dtype=int), {'window': None, 'candidate_count': 0}
    indices = np.arange(len(days)); window = None
    if not config.unconditional:
        for window in (28, 56, 84, None):
            indices = np.flatnonzero(day-days <= window) if window is not None else np.arange(len(days))
            if len(indices) >= config.scenarios or window is None:
                break
        cuts = np.quantile(scales[indices], [1/3, 2/3])
        bins = np.searchsorted(cuts, scales[indices], side='right')
        current_bin = int(np.searchsorted(cuts, current_scale, side='right'))
        selected = []
        for b in sorted(range(3), key=lambda b: (abs(b-current_bin), b)):
            selected.extend(indices[bins == b].tolist())
            if len(selected) >= config.scenarios:
                break
        indices = np.asarray(sorted(selected), dtype=int)
    return indices, {'window': window, 'candidate_count': len(indices), 'unconditional': config.unconditional}


def reduce_errors(errors: np.ndarray, prices: np.ndarray, config: Config) -> tuple[np.ndarray, np.ndarray, dict]:
    n = len(errors)
    count = min(config.scenarios, n)
    if n <= count:
        return np.arange(n), np.full(n, 1/n), {'tail_indices': [], 'reduced': False}
    standardized = (errors-errors.mean(0))/(errors.std(0)+np.finfo(float).eps)
    risk = np.maximum(errors, 0)@prices*DT
    tail = np.argsort(-risk, kind='stable')[:config.tail]
    rest = np.array([j for j in range(n) if j not in tail])
    ordinary, _ = medoids(standardized[rest], count-len(tail)) if count > len(tail) else (np.array([], dtype=int), None)
    representatives = np.r_[tail, rest[ordinary]]
    labels = np.argmin(cdist(standardized, standardized[representatives]), axis=1)
    labels[representatives] = np.arange(count)
    weights = np.bincount(labels, minlength=count)/n
    return representatives, weights, {'tail_indices': tail.tolist(), 'risk_scores': risk.tolist(), 'reduced': True,
                                     'represented_counts': np.bincount(labels, minlength=count).tolist()}


@dataclass
class Scenarios:
    load: np.ndarray
    pv: np.ndarray
    weights: np.ndarray
    audit: dict

    @property
    def net(self) -> np.ndarray:
        return (self.load-self.pv)*DT


def construct(data: Inputs, day: int, hour: int, config: Config, *, origin: int | None = None,
              length: int = 144, paired_days: np.ndarray | None = None,
              paired_weights: np.ndarray | None = None) -> Scenarios:
    origin = hour if origin is None else origin
    offset = (hour-origin)*6
    name = data.selected[day]
    point_load = data.load(day)[hour*6:hour*6+length]
    full_pv = data.pv(day, origin, config.interpolation)
    point_pv = full_pv[offset:offset+length]
    if len(point_pv) != length or len(point_load) != length:
        raise ValueError('预测支持不足，禁止填未来真值')
    days, el, ep, scales = data.history(day, hour, name, method=config.interpolation,
                                       forecast_hour=origin, length=length)
    audit = {'day': day, 'hour': hour, 'forecast_origin': origin, 'length': length, 'predictor': name,
             'history_boundary_slot': day*144+hour*6}
    if config.deterministic or len(days) == 0:
        return Scenarios(point_load[None], point_pv[None], np.ones(1), {**audit, 'history_days': [], 'S': 1, 'M0': True})
    if paired_days is None:
        indices, pool = pool_indices(days, scales, day, full_pv.sum()*DT, config)
        reps, weights, reduction = reduce_errors(el[indices]-ep[indices],
                                                data.prices[(hour*6+np.arange(length))%144], config)
        selected = indices[reps]
        audit.update(pool, **reduction)
    else:
        lookup = {int(j): i for i, j in enumerate(days)}
        if any(int(j) not in lookup for j in paired_days):
            raise ValueError('配对场景包含当前尚未完整实现或predictor不匹配轨迹')
        selected = np.array([lookup[int(j)] for j in paired_days])
        weights = np.asarray(paired_weights, dtype=float)
    audit.update(history_days=days[selected].tolist(), S=len(selected), weights=weights.tolist(), M0=False)
    return Scenarios(np.maximum(point_load+el[selected], 0), np.maximum(point_pv+ep[selected], 0), weights, audit)
