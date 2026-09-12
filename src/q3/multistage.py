"""3.23：阶段条件聚类四阶段树与实际求解，严格限于ex-post诊断。"""
from dataclasses import dataclass
import numpy as np
import pandas as pd
import time
from pyscipopt import quicksum
from .config import CAP, Config, DT, E_MIN, E_MAX, TOL
from .data import Inputs
from .scenarios import medoids, pool_indices
from .physics import Policy, replay, adjustment
from .optimization import make_model, add_path, scheduled_cost, LimitedSolve
from .rolling import date_of, previous_net, frame_for, validate_frame


def conditional_tree(revisions: np.ndarray) -> tuple[np.ndarray, list[dict]]:
    """每父节点至少4条且每子节点至少2条才能分支，避免叶节点揭示唯一未来轨迹。"""
    n = len(revisions)
    if revisions.ndim != 3 or revisions.shape[1] != 3 or n == 0:
        raise ValueError('需要history×三阶段×共同目标修正向量')
    labels = np.zeros((n, 4), dtype=int)
    nodes = [{'id': 0, 'stage': 0, 'parent': None, 'members': list(range(n)), 'probability': 1., 'conditional_probability': 1.}]
    for stage in range(1, 4):
        for parent in [node for node in nodes if node['stage'] == stage-1]:
            ids = np.asarray(parent['members'])
            values = revisions[ids, stage-1]
            center, scale = values.mean(0), values.std(0)+np.finfo(float).eps
            standardized = (values-center)/scale
            count = 2 if len(ids) >= 4 and np.unique(values, axis=0).shape[0] >= 2 else 1
            reps, assignment = medoids(standardized, count)
            if count == 2 and np.bincount(assignment, minlength=2).min() < 2:
                reps, assignment = medoids(standardized, 1)
            for cluster, representative in enumerate(reps):
                members = ids[assignment == cluster]
                node_id = len(nodes)
                labels[members, stage] = node_id
                nodes.append({'id': node_id, 'stage': stage, 'parent': parent['id'], 'members': members.tolist(),
                    'probability': len(members)/n, 'conditional_probability': len(members)/len(ids),
                    'medoid_revision': values[representative].tolist(), 'center': center.tolist(), 'scale': scale.tolist()})
    return labels, nodes


def tree_inputs(data: Inputs, day: int, config: Config) -> tuple[np.ndarray, np.ndarray, list[dict], dict]:
    name = data.selected[day]
    ids, el, ep, scales = data.history(day, 0, name, method=config.interpolation)
    # 三次修正的共同18h支持直到次日12；所有历史修正/最终24h轨迹均需已实现。
    valid = ids*144+216 <= day*144
    ids, el, ep, scales = ids[valid], el[valid], ep[valid], scales[valid]
    selected, pool = pool_indices(ids, scales, day, data.pv(day, 0, config.interpolation).sum()*DT, config)
    ids, el, ep = ids[selected], el[selected], ep[selected]
    if len(ids) < 2:
        raise ValueError('M2历史样本不足以保留最终实现不确定性')
    revisions = np.asarray([[data.pv(int(j), k, config.interpolation)[:108]-data.pv(int(j), k-6, config.interpolation)[36:]
                             for k in (6, 12, 18)] for j in ids])
    labels, nodes = conditional_tree(revisions)
    load = np.maximum(data.load(day)[:144]+el, 0)
    pv = np.maximum(data.pv(day, 0, config.interpolation)+ep, 0)
    return (load-pv)*DT, labels, nodes, {'history_days': ids.tolist(), 'load_upper': (load.max(0)*DT+CAP).tolist(),
                                       'pool': pool, 'role': 'ex_post_only_never_select_M1',
                                       'minimum_child_samples': 2, 'maximum_branches': [2, 2, 2]}


def solve_tree(net: np.ndarray, labels: np.ndarray, nodes: list[dict], upper: np.ndarray,
               prices: np.ndarray, initial: float, terminal: float, config: Config,
               *, require: bool = True) -> dict:
    started = time.perf_counter()
    n, slots = net.shape
    if slots%4:
        raise ValueError('四阶段树时域需可均分为四块')
    block = slots//4
    model = make_model(config.seconds, config.gap)
    seed_grid = np.maximum(net.max(0), 0)
    g0 = [model.addVar(lb=0, ub=float(v)) for v in upper]
    entries = list(zip(g0, seed_grid))
    policies = {}
    obj = quicksum(float(p)*v for p, v in zip(prices, g0))
    for node in nodes:
        stage = node['stage']; start, end = stage*block, (stage+1)*block
        g = g0[:block] if stage == 0 else [model.addVar(lb=0, ub=float(v)) for v in upper[start:end]]
        cp, rp = [[model.addVar(lb=0, ub=CAP) for _ in range(block)] for _ in range(2)]
        if stage:
            entries.extend(zip(g, seed_grid[start:end]))
            obj += node['probability']*scheduled_cost(model, g, prices[start:end], g0[start:end], block,
                entries, seed_grid[start:end], seed_grid[start:end])
        entries.extend((v, 0.) for v in cp+rp)
        policies[node['id']] = (g, cp, rp)
    paths = []
    for s, demand in enumerate(net):
        g, cp, rp = ([v for stage in range(4) for v in policies[int(labels[s, stage])][kind]] for kind in range(3))
        path = add_path(model, g, cp, rp, demand, upper, initial, exact=True, feedback='aggregate',
            previous_net=0., initial_lower=initial, initial_upper=initial,
            seed_policy=Policy(seed_grid, np.zeros(slots), np.zeros(slots)), seed_initial=initial, seed_entries=entries)
        paths.append(path)
        obj += (quicksum(5*float(p)*q for p, q in zip(prices, path['emergency']))-terminal*path['soc'][-1])/n
    model.setObjective(obj)
    seed = model.createSol()
    for variable, value in entries:
        model.setSolVal(seed, variable, float(value))
    seed_accepted = bool(model.addSol(seed))
    size = {'variables': model.getNVars(), 'constraints': model.getNConss(), 'binaries': model.getNBinVars()}
    model.optimize()
    audit = {'status': str(model.getStatus()), 'seconds': time.perf_counter()-started, 'seed_accepted': seed_accepted,
             'scenario_count': n, 'nodes': len(nodes), 'role': 'ex_post_only', **size}
    if not model.getNSols():
        audit.update(reliable=False, gap=None)
        if require:
            raise LimitedSolve(audit)
        return {'audit': audit}
    solved = {node_id: Policy(*(np.maximum(np.array([model.getVal(v) for v in a]), 0) for a in arrays)) for node_id, arrays in policies.items()}
    mapping = 0.
    for s, demand in enumerate(net):
        policy = Policy(*(np.concatenate([getattr(solved[int(labels[s, stage])], key) for stage in range(4)])
                          for key in ('grid', 'charge_cap', 'discharge_cap')))
        response = replay(policy, demand, initial)
        mapping = max(mapping, max(abs(float(model.getVal(v))-response[key][t]) for key in paths[s] for t, v in enumerate(paths[s][key])))
    value, bound = float(model.getObjVal()), float(model.getDualbound())
    gap = max(0., value-bound)/max(abs(value), 1e-10)
    audit.update(objective=value, lower_bound=bound, gap=gap, mapping_error=mapping,
                 reliable=mapping <= TOL and value-bound <= max(TOL, config.gap*abs(value)))
    if require and not audit['reliable']:
        raise LimitedSolve(audit)
    return {'audit': audit, 'g0': np.maximum(np.array([model.getVal(v) for v in g0]), 0), 'policies': solved}


def replay_tree(data: Inputs, day: int, initial: float, nodes: list[dict], solution: dict, config: Config) -> pd.DataFrame:
    current, soc, frames = 0, initial, []
    for stage in range(4):
        hour = stage*6
        if stage:
            revision = data.pv(day, hour, config.interpolation)[:108]-data.pv(day, hour-6, config.interpolation)[36:]
            children = [node for node in nodes if node['parent'] == current]
            selected = min(children, key=lambda node: (np.linalg.norm((revision-np.array(node['medoid_revision']))/np.array(node['scale'])), node['id']))
            current = selected['id']
        policy = solution['policies'][current]
        frame = frame_for(data, day, hour, policy, soc, config)
        frame['g0'] = solution['g0'][hour*6:hour*6+36]
        frame['initial_soc'] = initial
        frame['tree_node'] = current
        frames.append(frame); soc = float(frame.soc.iloc[-1])
    frame = pd.concat(frames, ignore_index=True)
    frame['planned_cost'] = frame.price*frame.g0
    frame['adjustment_cost'] = adjustment(frame.grid.to_numpy(), frame.g0.to_numpy(), frame.price.to_numpy())
    frame['emergency_cost'] = 5*frame.price*frame.emergency
    frame['total_cost'] = frame.planned_cost+frame.adjustment_cost+frame.emergency_cost
    validate_frame(frame, config)
    return frame
