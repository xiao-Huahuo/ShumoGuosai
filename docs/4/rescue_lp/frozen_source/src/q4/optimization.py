"""节点共享储能计划的连续LP；有限支持Wasserstein直接对偶，无MIP或fallback。"""
from dataclasses import dataclass
import hashlib
import multiprocessing as mp
import time
import traceback
import numpy as np
from highspy import Highs, HighsLp, HighsModelStatus, HighsStatus, MatrixFormat
from scipy.optimize import Bounds, LinearConstraint, linprog
from scipy.sparse import coo_matrix
from .config import CAP, E_MIN, E_MAX, ETA_C, ETA_D, Config, TOL, THROUGHPUT_EPSILON
from .physics import DispatchPolicy, replay, scenario_costs
from .scenarios import Scenarios


class LimitedSolve(RuntimeError):
    def __init__(self, audit: dict):
        super().__init__(f"节点未取得可信LP最优解：{audit.get('status')}")
        self.audit = audit


@dataclass
class Solution:
    policy: DispatchPolicy
    responses: list[dict]
    audit: dict


def worst_case_distribution(costs: np.ndarray, weights: np.ndarray, distance: np.ndarray,
                            radius: float) -> tuple[np.ndarray, float]:
    count = len(weights)
    columns = np.arange(count * count)
    equalities = coo_matrix((np.ones(count * count), (np.repeat(np.arange(count), count), columns)),
                            shape=(count, count * count)).tocsr()
    result = linprog(-np.tile(costs, count), A_ub=distance.ravel()[None], b_ub=[radius],
                     A_eq=equalities, b_eq=weights, bounds=(0, None), method='highs')
    if not result.success:
        raise RuntimeError(f'最坏分布运输问题失败：{result.message}')
    distribution = result.x.reshape(count, count).sum(axis=0)
    return distribution, float(distribution @ costs)


def build_matrix(scenarios: Scenarios, initial: float, *, reference: np.ndarray | None = None,
                 today: int | None = None) -> tuple:
    net, prices, weights = scenarios.net, scenarios.prices, scenarios.weights
    if net.ndim != 2 or prices.shape != net.shape or weights.shape != (len(net),):
        raise ValueError('联合场景维度不符')
    count, length = net.shape
    if any(not np.isfinite(v).all() for v in (net, prices, weights, scenarios.distance)):
        raise ValueError('联合场景含非有限值')
    if (prices < 0).any() or (weights <= 0).any() or not np.isclose(weights.sum(), 1):
        raise ValueError('价格或概率非法')
    if not E_MIN <= initial <= E_MAX or scenarios.radius < 0 or not np.isfinite(scenarios.radius):
        raise ValueError('初始SOC或半径非法')
    if scenarios.distance.shape != (count, count) or (scenarios.distance < 0).any():
        raise ValueError('距离矩阵非法')
    today = length if today is None else min(int(today), length)
    if reference is not None and (len(reference) < today or not np.isfinite(reference).all() or (reference < 0).any()):
        raise ValueError('基准购电计划非法')
    indices, lower, upper = {}, [], []

    def block(name, shape, lo=0.0, hi=np.inf):
        size = int(np.prod(shape))
        indices[name] = np.arange(len(lower), len(lower) + size).reshape(shape)
        lower.extend(np.broadcast_to(lo, shape).ravel())
        upper.extend(np.broadcast_to(hi, shape).ravel())
        return indices[name]

    g = block('g', (length,), hi=np.maximum(net.max(axis=0), 0) + CAP)
    c = block('c', (length,), hi=CAP)
    r = block('r', (length,), hi=CAP)
    e = block('E', (length,), lo=E_MIN, hi=E_MAX)
    x = block('x', (count, length))
    h = block('h', (count, length))
    w = block('w', (count, length))
    adjustment = block('adjustment', (today if reference is not None else 0,),
                       lo=-0.5 * reference[:today] if reference is not None else 0)
    phi = block('phi', (count,), lo=-np.inf)
    lam = block('wasserstein_lambda', (1,))
    alpha = block('alpha', (count,), lo=-np.inf)
    objective = np.zeros(len(lower))
    objective[c] = objective[r] = THROUGHPUT_EPSILON
    objective[lam] = scenarios.radius
    objective[alpha] = weights
    rows, columns, values, row_lower, row_upper = [], [], [], [], []

    def add(terms, lo=-np.inf, hi=np.inf):
        row = len(row_lower)
        for column, value in terms:
            if value != 0:
                rows.append(row); columns.append(int(column)); values.append(float(value))
        row_lower.append(float(lo)); row_upper.append(float(hi))

    for t in range(length):
        add([(c[t], 1), (r[t], 1)], hi=CAP)
        terms = [(e[t], 1), (c[t], -ETA_C), (r[t], 1 / ETA_D)]
        if t:
            terms.append((e[t - 1], -1))
        rhs = initial if t == 0 else 0
        add(terms, lo=rhs, hi=rhs)
        for j in range(count):
            add([(x[j, t], 1), (g[t], -1)], hi=0)
            add([(x[j, t], 1), (r[t], 1), (h[j, t], 1), (c[t], -1), (w[j, t], -1)],
                lo=net[j, t], hi=net[j, t])
    if reference is not None:
        for t in range(today):
            for factor in (0.5, 1.5):
                add([(g[t], factor), (adjustment[t], -1)], hi=factor * reference[t])
    for j in range(count):
        terms = [(phi[j], -1)] + [(h[j, t], 5 * prices[j, t]) for t in range(length)]
        constant = 0.0
        for t in range(length):
            if reference is not None and t < today:
                terms.append((adjustment[t], prices[j, t]))
                constant += reference[t] * prices[j, t]
            else:
                terms.append((g[t], prices[j, t]))
        add(terms, hi=-constant)
    for i in range(count):
        for j in range(count):
            add([(phi[j], 1), (alpha[i], -1), (lam[0], -scenarios.distance[i, j])], hi=0)
    matrix = coo_matrix((values, (rows, columns)), shape=(len(row_lower), len(lower))).tocsc()
    return (objective, Bounds(np.asarray(lower), np.asarray(upper)), np.zeros(len(lower), dtype=int),
            LinearConstraint(matrix, np.asarray(row_lower), np.asarray(row_upper)), indices, 0.0)


def solve_dual(scenarios: Scenarios, initial: float, config: Config, *, reference=None, today=None) -> Solution:
    """worker内求解；只返回Optimal且原矩阵、真实回放、DRO原对偶均通过的解。"""
    started = time.perf_counter()
    objective, bounds, integer, constraints, indices, offset = build_matrix(
        scenarios, initial, reference=reference, today=today)
    solver = Highs()
    for key, value in dict(threads=config.solver_threads, output_flag=False, time_limit=config.seconds,
                           primal_feasibility_tolerance=1e-8, dual_feasibility_tolerance=1e-8).items():
        if solver.setOptionValue(key, value) == HighsStatus.kError:
            raise ValueError(f'HiGHS不接受参数{key}')
    matrix = constraints.A
    model = HighsLp()
    model.num_col_, model.num_row_ = len(objective), matrix.shape[0]
    model.col_cost_, model.col_lower_, model.col_upper_ = objective, bounds.lb, bounds.ub
    model.row_lower_, model.row_upper_ = constraints.lb, constraints.ub
    model.a_matrix_.format_ = MatrixFormat.kColwise
    model.a_matrix_.num_col_, model.a_matrix_.num_row_ = model.num_col_, model.num_row_
    model.a_matrix_.start_, model.a_matrix_.index_, model.a_matrix_.value_ = matrix.indptr, matrix.indices, matrix.data
    if solver.passModel(model) == HighsStatus.kError or solver.run() == HighsStatus.kError:
        raise LimitedSolve(dict(status='solver_error', reliable=False, solution_source='none'))
    status = solver.getModelStatus()
    if status != HighsModelStatus.kOptimal:
        raise LimitedSolve(dict(status=solver.modelStatusToString(status), reliable=False,
                                solution_source='none', seconds=time.perf_counter() - started))
    vector = np.asarray(solver.getSolution().col_value)
    activity = matrix @ vector
    feasibility = max(0.0, float(np.max(bounds.lb - vector)), float(np.max(vector - bounds.ub)),
                      float(np.max(constraints.lb - activity)), float(np.max(activity - constraints.ub)))
    policy = DispatchPolicy(*(np.maximum(vector[indices[key]], 0) for key in ('g', 'c', 'r')))
    # 保持SOC完全相同，消除数值退化造成的同时充放电；需求只能减少。
    overlap = np.minimum(policy.charge, policy.discharge / (ETA_C * ETA_D))
    policy.charge -= overlap
    policy.discharge -= ETA_C * ETA_D * overlap
    responses = [replay(policy, path, initial) for path in scenarios.net]
    costs = scenario_costs(policy, responses, scenarios.prices, reference, today)
    worst_weights, robust_value = worst_case_distribution(costs, scenarios.weights, scenarios.distance, scenarios.radius)
    raw_value = float(objective @ vector + offset)
    value = robust_value + THROUGHPUT_EPSILON * float(np.sum(policy.charge + policy.discharge))
    duality_error = abs(value - raw_value)
    # 使用行、列对偶重构LP下界，而不是MILP专有字段。
    dual = solver.getSolution()
    row_dual, col_dual = np.asarray(dual.row_dual), np.asarray(dual.col_dual)
    def bound_value(multipliers, lo, hi):
        pos, neg = multipliers > 1e-10, multipliers < -1e-10
        return float(multipliers[pos] @ lo[pos] + multipliers[neg] @ hi[neg])
    lower_bound = bound_value(row_dual, constraints.lb, constraints.ub) + bound_value(col_dual, bounds.lb, bounds.ub)
    certificate_error = abs(raw_value - lower_bound)
    valid = bool(feasibility <= TOL and duality_error <= 2e-4 and certificate_error <= 2e-4)
    digest = hashlib.sha256()
    for array in (objective, bounds.lb, bounds.ub, constraints.lb, constraints.ub, matrix.indptr, matrix.indices, matrix.data):
        digest.update(np.asarray(array).tobytes())
    audit = dict(status='Optimal', solver='HiGHS_finite_support_Wasserstein_LP', solver_version=solver.version(),
                 seconds=time.perf_counter() - started, solver_seconds=solver.getRunTime(),
                 solver_threads=config.solver_threads, solution_source='optimal_solver',
                 gap=max(0.0, value - lower_bound) / max(1.0, abs(value)), objective=robust_value,
                 optimizer_objective=raw_value, lower_bound=lower_bound, variables=len(objective),
                 constraints=matrix.shape[0], integer_variables=int(integer.sum()), binaries=0,
                 linear_feasibility_error=feasibility, replay_duality_error=duality_error,
                 lp_certificate_error=certificate_error, simultaneous_charge_removed=float(overlap.sum()),
                 storage_schedule='node_shared_fixed_committed_block',
                 dro_formulation='finite_support_direct_dual', dro_coupling_constraints=len(costs)**2,
                 throughput_epsilon=THROUGHPUT_EPSILON, scenario_costs=costs.tolist(),
                 empirical_weights=scenarios.weights.tolist(), worst_case_weights=worst_weights.tolist(),
                 radius=scenarios.radius, matrix_digest=digest.hexdigest(), valid=valid, reliable=valid)
    if not valid:
        raise LimitedSolve(audit)
    return Solution(policy, responses, audit)


def _worker(connection, scenarios, initial, config, reference, today):
    try:
        connection.send(('ok', solve_dual(scenarios, initial, config, reference=reference, today=today)))
    except LimitedSolve as error:
        connection.send(('failure', error.audit))
    except Exception:
        connection.send(('failure', dict(status='worker_exception', reliable=False, traceback=traceback.format_exc())))
    finally:
        connection.close()


def solve(scenarios: Scenarios, initial: float, config: Config, *, reference=None, today=None) -> Solution:
    """独立进程硬截止；任何失败都不能进入正式日文件。"""
    context = mp.get_context('spawn')
    parent, child = context.Pipe(duplex=False)
    process = context.Process(target=_worker, args=(child, scenarios, initial, config, reference, today))
    started = time.perf_counter()
    process.start()
    child.close()
    try:
        if not parent.poll(config.hard_timeout):
            raise LimitedSolve(dict(status='hard_timeout', reliable=False, solution_source='none',
                                    hard_timeout=config.hard_timeout))
        try:
            status, result = parent.recv()
        except EOFError as error:
            raise LimitedSolve(dict(status='worker_exit', reliable=False, solution_source='none')) from error
        if status != 'ok':
            raise LimitedSolve(result)
        result.audit['wall_seconds'] = time.perf_counter() - started
        result.audit['hard_timeout'] = config.hard_timeout
        return result
    finally:
        parent.close()
        process.join(timeout=0.2)
        if process.is_alive():
            process.kill()
            process.join()
