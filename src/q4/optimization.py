"""7.5—7.7：有限支持Wasserstein DRO与严格因果饱和反馈的等价MILP。"""
from dataclasses import dataclass
import time
import numpy as np
from highspy import Highs as HighsAPI
from highspy import _core as highs_core
from scipy.optimize import Bounds, LinearConstraint, linprog
from scipy.sparse import coo_matrix, hstack, vstack
from src.q3.fast_solver import build_base_v2_free, linear_seed_v2_free, matrix_digest, matrix_error
from src.q3.physics import Policy
from .config import CAP, E_MIN, E_MAX, Config, TOL
from .physics import adjustment_quantity, replay, scenario_costs
from .scenarios import Scenarios


class LimitedSolve(RuntimeError):
    def __init__(self, audit: dict):
        super().__init__("节点未在预算内取得要求的gap证书")
        self.audit = audit


@dataclass
class Solution:
    policy: Policy
    responses: list[dict]
    audit: dict


def worst_case_distribution(costs: np.ndarray, weights: np.ndarray, distance: np.ndarray,
                            radius: float) -> tuple[np.ndarray, float]:
    count = len(weights)
    objective = -np.tile(costs, count)
    rows, cols, values = [], [], []
    for i in range(count):
        for j in range(count):
            column = i * count + j
            rows.append(i)
            cols.append(column)
            values.append(1.0)
    equalities = coo_matrix((values, (rows, cols)), shape=(count, count * count)).tocsr()
    inequality = distance.ravel()[None, :]
    result = linprog(objective, A_ub=inequality, b_ub=[radius], A_eq=equalities,
                     b_eq=weights, bounds=(0, None), method="highs")
    if not result.success:
        raise RuntimeError(f"最坏分布运输问题失败：{result.message}")
    transport = result.x.reshape(count, count)
    distribution = transport.sum(axis=0)
    return distribution, float(np.dot(distribution, costs))


def build_matrix(scenarios: Scenarios, initial: float, *, reference: np.ndarray | None = None,
                 today: int | None = None) -> tuple:
    net, prices, weights = scenarios.net, scenarios.prices, scenarios.weights
    if net.ndim != 2 or prices.shape != net.shape or weights.shape != (len(net),):
        raise ValueError("联合场景维度不符")
    if not all(np.isfinite(value).all() for value in (net, prices, weights)):
        raise ValueError("联合场景含非有限值")
    if (prices < 0).any() or (weights <= 0).any() or not np.isclose(weights.sum(), 1):
        raise ValueError("价格或经验概率非法")
    if not E_MIN <= initial <= E_MAX:
        raise ValueError("初始SOC非法")
    count, length = net.shape
    today = length if today is None else min(int(today), length)
    if reference is not None and len(reference) < today:
        raise ValueError("基准计划短于当日未执行区间")
    grid_upper = np.maximum(net.max(axis=0), 0) + CAP
    objective, bounds, integer, constraints, indices = build_base_v2_free(
        net, np.ones(length), weights, initial, grid_upper=grid_upper
    )
    objective[:] = 0.0
    offset = 0.0
    added_count = today if reference is not None else 0
    base_size = len(objective)
    adjustment = np.arange(base_size, base_size + added_count, dtype=int)
    position = base_size + added_count
    empirical = scenarios.radius <= TOL
    wasserstein_lambda = None
    alpha = np.empty(0, dtype=int)
    if not empirical:
        wasserstein_lambda = position
        alpha = np.arange(position + 1, position + 1 + count, dtype=int)
        position += 1 + count
    extra = position - base_size
    lo = np.r_[bounds.lb, np.zeros(extra)]
    hi = np.r_[bounds.ub, np.full(extra, np.inf)]
    if added_count:
        lo[adjustment] = -0.5 * reference[:today]
        delta = grid_upper[:today] - reference[:today]
        hi[adjustment] = np.maximum(0.5 * delta, 1.5 * delta)
    bounds = Bounds(lo, hi)
    integer = np.r_[integer, np.zeros(extra)]
    objective = np.r_[objective, np.zeros(extra)]
    matrix = hstack([constraints.A, coo_matrix((constraints.A.shape[0], extra))]).tocsc()
    row_lower = list(constraints.lb)
    row_upper = list(constraints.ub)
    rows, cols, values = [], [], []

    def add(terms: list[tuple[int, float]], lower: float = -np.inf, upper: float = np.inf) -> None:
        row = len(row_upper)
        for column, value in terms:
            rows.append(row - constraints.A.shape[0])
            cols.append(int(column))
            values.append(float(value))
        row_lower.append(float(lower))
        row_upper.append(float(upper))

    if added_count:
        for t in range(today):
            add([(indices["g"][t], 0.5), (adjustment[t], -1)], upper=0.5 * reference[t])
            add([(indices["g"][t], 1.5), (adjustment[t], -1)], upper=1.5 * reference[t])
    emergency = indices["responses"][2]
    if empirical:
        mean_price = weights @ prices
        objective[emergency] = 5 * weights[:, None] * prices
        if reference is None:
            objective[indices["g"]] = mean_price
        else:
            objective[adjustment] = mean_price[:today]
            objective[indices["g"][today:]] = mean_price[today:]
            offset = float(np.dot(mean_price[:today], reference[:today]))
    else:
        objective[wasserstein_lambda] = scenarios.radius
        objective[alpha] = weights
        for i in range(count):
            for j in range(count):
                terms = [(int(emergency[j, t]), 5 * prices[j, t]) for t in range(length)]
                constant = 0.0
                if reference is None:
                    terms.extend((int(indices["g"][t]), prices[j, t]) for t in range(length))
                else:
                    terms.extend((int(adjustment[t]), prices[j, t]) for t in range(today))
                    terms.extend((int(indices["g"][t]), prices[j, t]) for t in range(today, length))
                    constant = float(np.dot(prices[j, :today], reference[:today]))
                terms.extend(((int(wasserstein_lambda), -scenarios.distance[i, j]), (int(alpha[i]), -1.0)))
                add(terms, upper=-constant)
    if row_upper[len(constraints.ub):]:
        addition = coo_matrix(
            (values, (rows, cols)), shape=(len(row_upper) - len(constraints.ub), len(objective))
        ).tocsc()
        matrix = vstack([matrix, addition]).tocsc()
    constraints = LinearConstraint(matrix, np.asarray(row_lower), np.asarray(row_upper))
    indices.update(adjustment=adjustment, wasserstein_lambda=wasserstein_lambda, alpha=alpha)
    return objective, bounds, integer, constraints, indices, offset


def solve_dual(scenarios: Scenarios, initial: float, config: Config, *, reference: np.ndarray | None = None,
               today: int | None = None) -> Solution:
    started = time.perf_counter()
    objective, bounds, integer, constraints, indices, offset = build_matrix(
        scenarios, initial, reference=reference, today=today
    )
    highs_core._Highs.resetGlobalScheduler(True)
    solver = HighsAPI()
    options = {
        "threads": config.solver_threads,
        "parallel": "on" if config.solver_threads > 1 else "off",
        "output_flag": True,
        "log_to_console": False,
        "mip_rel_gap": config.gap,
        "time_limit": config.seconds,
        "mip_feasibility_tolerance": 1e-8,
        "primal_feasibility_tolerance": 1e-8,
    }
    for key, value in options.items():
        if solver.setOptionValue(key, value) == highs_core.HighsStatus.kError:
            raise ValueError(f"HiGHS不接受参数{key}")
    matrix = constraints.A.tocsc()
    model = highs_core.HighsLp()
    model.num_col_, model.num_row_ = len(objective), matrix.shape[0]
    model.col_cost_, model.col_lower_, model.col_upper_ = objective, bounds.lb, bounds.ub
    model.row_lower_, model.row_upper_ = constraints.lb, constraints.ub
    model.offset_ = offset
    model.a_matrix_.num_col_, model.a_matrix_.num_row_ = model.num_col_, model.num_row_
    model.a_matrix_.format_ = highs_core.MatrixFormat.kColwise
    model.a_matrix_.start_, model.a_matrix_.index_, model.a_matrix_.value_ = matrix.indptr, matrix.indices, matrix.data
    model.integrality_ = [highs_core.HighsVarType(int(value)) for value in integer]
    if solver.passModel(model) == highs_core.HighsStatus.kError or solver.run() == highs_core.HighsStatus.kError:
        raise RuntimeError("HiGHS求解失败")
    info = solver.getInfo()
    if info.primal_solution_status != highs_core.kSolutionStatusFeasible:
        audit = {"status": solver.modelStatusToString(solver.getModelStatus()), "seconds": time.perf_counter() - started,
                 "reliable": False, "has_incumbent": False}
        raise LimitedSolve(audit)
    vector = np.asarray(solver.getSolution().col_value)
    feasibility, integrality = matrix_error(vector, bounds, integer, constraints)
    length = scenarios.net.shape[1]
    policy = Policy(np.maximum(vector[indices["g"]], 0), np.full(length, CAP),
                    np.maximum(vector[indices["rp"]], 0))
    responses = [replay(policy, path, initial) for path in scenarios.net]
    raw = np.stack([vector[block] for block in indices["responses"]], axis=-1)
    exact = np.asarray([
        np.column_stack([response[key] for key in ("charge", "discharge", "emergency", "total_surplus", "soc")])
        for response in responses
    ])
    projection = max(0.0, float(np.max(raw[..., 4] - exact[..., 4])),
                     float(np.max(exact[..., 2] - raw[..., 2])))
    costs = scenario_costs(policy, responses, scenarios.prices, reference, today)
    if scenarios.radius <= TOL:
        worst_weights = scenarios.weights.copy()
        value = float(np.dot(worst_weights, costs))
    else:
        worst_weights, value = worst_case_distribution(costs, scenarios.weights, scenarios.distance, scenarios.radius)
    raw_value = float(np.dot(objective, vector) + offset)
    lower = float(info.mip_dual_bound)
    gap = max(0.0, value - lower) / max(abs(value), 1e-10)
    valid = (feasibility <= TOL and integrality <= 1e-8 and projection <= TOL
             and value <= raw_value + 2e-4 and lower <= value + 2e-4)
    reliable = bool(valid and gap <= config.gap + 1e-8)
    audit = {
        "status": solver.modelStatusToString(solver.getModelStatus()),
        "solver": "HiGHS_1.15_Q4_finite_support_Wasserstein_MILP",
        "solver_version": solver.version(),
        "seconds": time.perf_counter() - started,
        "solver_seconds": float(solver.getRunTime()),
        "solver_threads": config.solver_threads,
        "requested_gap": config.gap,
        "gap": gap,
        "objective": value,
        "optimizer_objective": raw_value,
        "lower_bound": lower,
        "scenario_costs": costs.tolist(),
        "empirical_weights": scenarios.weights.tolist(),
        "worst_case_weights": worst_weights.tolist(),
        "radius": scenarios.radius,
        "variables": len(objective),
        "binaries": int(integer.sum()),
        "constraints": matrix.shape[0],
        "node_count": int(info.mip_node_count),
        "linear_feasibility_error": feasibility,
        "integrality_error": integrality,
        "monotone_projection_error": projection,
        "matrix_digest": matrix_digest(objective, bounds, integer, constraints),
        "has_incumbent": True,
        "valid": bool(valid),
        "reliable": reliable,
    }
    if not valid or (not reliable and not config.allow_limited):
        raise LimitedSolve(audit)
    return Solution(policy, responses, audit)


def _master_matrix(scenarios: Scenarios, initial: float, cuts: list[np.ndarray], *,
                   reference: np.ndarray | None, today: int | None) -> tuple:
    """Wasserstein歧义集的精确行生成主问题；cuts为已分离的可行概率分布。"""
    net, prices = scenarios.net, scenarios.prices
    count, length = net.shape
    today = length if today is None else min(int(today), length)
    grid_upper = np.maximum(net.max(axis=0), 0) + CAP
    objective, bounds, integer, constraints, indices = build_base_v2_free(
        net, np.ones(length), scenarios.weights, initial, grid_upper=grid_upper
    )
    objective[:] = 0.0
    base_size = len(objective)
    adjustment = np.arange(base_size, base_size + (today if reference is not None else 0), dtype=int)
    theta = base_size + len(adjustment)
    size = theta + 1
    lo = np.r_[bounds.lb, np.zeros(size - base_size)]
    hi = np.r_[bounds.ub, np.full(size - base_size, np.inf)]
    if len(adjustment):
        lo[adjustment] = -0.5 * reference[:today]
        delta = grid_upper[:today] - reference[:today]
        hi[adjustment] = np.maximum(0.5 * delta, 1.5 * delta)
    objective = np.r_[objective, np.zeros(size - base_size)]
    objective[theta] = 1.0
    integer = np.r_[integer, np.zeros(size - base_size)]
    matrix = hstack([constraints.A, coo_matrix((constraints.A.shape[0], size - base_size))]).tocsc()
    lower, upper = list(constraints.lb), list(constraints.ub)
    rows, cols, values = [], [], []

    def add(terms: list[tuple[int, float]], rhs: float) -> None:
        row = len(upper) - len(constraints.ub)
        for column, value in terms:
            rows.append(row)
            cols.append(int(column))
            values.append(float(value))
        lower.append(-np.inf)
        upper.append(float(rhs))

    if len(adjustment):
        for t in range(today):
            add([(indices["g"][t], 0.5), (adjustment[t], -1)], 0.5 * reference[t])
            add([(indices["g"][t], 1.5), (adjustment[t], -1)], 1.5 * reference[t])
    emergency = indices["responses"][2]
    for distribution in cuts:
        mean_price = distribution @ prices
        terms = [(theta, -1.0)]
        terms.extend((int(emergency[j, t]), 5 * distribution[j] * prices[j, t])
                     for j in range(count) for t in range(length) if distribution[j] > 1e-14)
        constant = 0.0
        if reference is None:
            terms.extend((int(indices["g"][t]), mean_price[t]) for t in range(length))
        else:
            terms.extend((int(adjustment[t]), mean_price[t]) for t in range(today))
            terms.extend((int(indices["g"][t]), mean_price[t]) for t in range(today, length))
            constant = float(np.dot(mean_price[:today], reference[:today]))
        add(terms, -constant)
    addition = coo_matrix((values, (rows, cols)), shape=(len(upper) - len(constraints.ub), size)).tocsc()
    matrix = vstack([matrix, addition]).tocsc()
    indices.update(adjustment=adjustment, theta=theta)
    return objective, Bounds(lo, hi), integer, LinearConstraint(matrix, np.asarray(lower), np.asarray(upper)), indices


def _run_master(objective: np.ndarray, bounds: Bounds, integer: np.ndarray, constraints: LinearConstraint,
                config: Config, seconds: float, seed: np.ndarray | None) -> tuple[np.ndarray, object, object]:
    highs_core._Highs.resetGlobalScheduler(True)
    solver = HighsAPI()
    for key, value in {
        "threads": config.solver_threads,
        "parallel": "on" if config.solver_threads > 1 else "off",
        "output_flag": True,
        "log_to_console": False,
        "mip_rel_gap": config.gap,
        "time_limit": max(seconds, 0.05),
        "mip_feasibility_tolerance": 1e-8,
        "primal_feasibility_tolerance": 1e-8,
    }.items():
        if solver.setOptionValue(key, value) == highs_core.HighsStatus.kError:
            raise ValueError(f"HiGHS不接受参数{key}")
    matrix = constraints.A.tocsc()
    model = highs_core.HighsLp()
    model.num_col_, model.num_row_ = len(objective), matrix.shape[0]
    model.col_cost_, model.col_lower_, model.col_upper_ = objective, bounds.lb, bounds.ub
    model.row_lower_, model.row_upper_ = constraints.lb, constraints.ub
    model.a_matrix_.num_col_, model.a_matrix_.num_row_ = model.num_col_, model.num_row_
    model.a_matrix_.format_ = highs_core.MatrixFormat.kColwise
    model.a_matrix_.start_, model.a_matrix_.index_, model.a_matrix_.value_ = matrix.indptr, matrix.indices, matrix.data
    model.integrality_ = [highs_core.HighsVarType(int(value)) for value in integer]
    if solver.passModel(model) == highs_core.HighsStatus.kError:
        raise RuntimeError("HiGHS主问题加载失败")
    if seed is not None and len(seed) == len(objective):
        candidate = highs_core.HighsSolution()
        candidate.col_value = seed
        candidate.value_valid = True
        solver.setSolution(candidate)
    if solver.run() == highs_core.HighsStatus.kError:
        raise RuntimeError("HiGHS主问题求解失败")
    info = solver.getInfo()
    if info.primal_solution_status != highs_core.kSolutionStatusFeasible:
        if seed is None:
            raise LimitedSolve({"status": solver.modelStatusToString(solver.getModelStatus()),
                                "has_incumbent": False, "reliable": False})
        # 预求解耗尽节点预算时HiGHS可能尚未接纳MIP start；该向量已由完整矩阵验收，
        # 因而仍是合法限时incumbent。全局下界在调用方保守取不小于0的有效值。
        return seed.copy(), info, solver
    return np.asarray(solver.getSolution().col_value), info, solver


def _initial_master_seed(scenarios: Scenarios, initial: float, cuts: list[np.ndarray], objective: np.ndarray,
                         bounds: Bounds, integer: np.ndarray, constraints: LinearConstraint, indices: dict,
                         reference: np.ndarray | None, today: int | None) -> np.ndarray:
    """用逐时最大净需求构造必然可行的事前策略，避免困难根节点在限时内找不到incumbent。"""
    length = scenarios.net.shape[1]
    policy = Policy(np.maximum(scenarios.net.max(axis=0), 0), np.full(length, CAP), np.zeros(length))
    vector = linear_seed_v2_free(policy, scenarios.net, initial, indices, len(objective))
    if len(indices["adjustment"]):
        count = len(indices["adjustment"])
        vector[indices["adjustment"]] = adjustment_quantity(policy.grid[:count], reference[:count])
    responses = [replay(policy, path, initial) for path in scenarios.net]
    costs = scenario_costs(policy, responses, scenarios.prices, reference, today)
    vector[indices["theta"]] = max(float(np.dot(distribution, costs)) for distribution in cuts)
    feasibility, integrality = matrix_error(vector, bounds, integer, constraints)
    if feasibility > TOL or integrality > 1e-8:
        raise ValueError(f"确定性可行初值验收失败：{feasibility}/{integrality}")
    return vector


def solve(scenarios: Scenarios, initial: float, config: Config, *, reference: np.ndarray | None = None,
          today: int | None = None) -> Solution:
    """精确约束生成：最坏分布LP负责分离，MILP主问题仅保留实际活跃概率切面。"""
    started = time.perf_counter()
    cuts = [scenarios.weights.copy()]
    seed = None
    best = None
    best_value = float("inf")
    global_lower = 0.0  # 全部购电、调整后结算和紧急购电成本均非负。
    iterations = []
    final_matrix = None
    while time.perf_counter() - started < config.seconds:
        remaining = config.seconds - (time.perf_counter() - started)
        objective, bounds, integer, constraints, indices = _master_matrix(
            scenarios, initial, cuts, reference=reference, today=today
        )
        if seed is None:
            seed = _initial_master_seed(scenarios, initial, cuts, objective, bounds, integer,
                                        constraints, indices, reference, today)
        vector, info, solver = _run_master(objective, bounds, integer, constraints, config, remaining, seed)
        seed = vector.copy()
        feasibility, integrality = matrix_error(vector, bounds, integer, constraints)
        length = scenarios.net.shape[1]
        policy = Policy(np.maximum(vector[indices["g"]], 0), np.full(length, CAP),
                        np.maximum(vector[indices["rp"]], 0))
        responses = [replay(policy, path, initial) for path in scenarios.net]
        raw = np.stack([vector[block] for block in indices["responses"]], axis=-1)
        exact = np.asarray([
            np.column_stack([response[key] for key in ("charge", "discharge", "emergency", "total_surplus", "soc")])
            for response in responses
        ])
        projection = max(0.0, float(np.max(raw[..., 4] - exact[..., 4])),
                         float(np.max(exact[..., 2] - raw[..., 2])))
        costs = scenario_costs(policy, responses, scenarios.prices, reference, today)
        worst_weights, value = worst_case_distribution(costs, scenarios.weights, scenarios.distance, scenarios.radius)
        lower = float(info.mip_dual_bound)
        if np.isfinite(lower):
            global_lower = max(global_lower, lower)
        if value < best_value:
            best_value = value
            best = (policy, responses, costs, worst_weights, feasibility, integrality, projection,
                    float(np.dot(objective, vector)), solver, info, constraints, objective, bounds, integer)
        master_value = float(vector[indices["theta"]])
        violation = value - master_value
        overall_gap = max(0.0, best_value - global_lower) / max(abs(best_value), 1e-10)
        iterations.append({"iteration": len(iterations) + 1, "cuts": len(cuts), "master_value": master_value,
                           "robust_value": value, "separation_violation": violation,
                           "restricted_lower_bound": lower if np.isfinite(lower) else None, "global_gap": overall_gap,
                           "solver_status": solver.modelStatusToString(solver.getModelStatus()),
                           "solver_seconds": float(solver.getRunTime())})
        final_matrix = (constraints, objective, bounds, integer)
        duplicate = any(np.max(abs(worst_weights - item)) <= 1e-10 for item in cuts)
        if overall_gap <= config.gap + 1e-8 and (violation <= TOL or duplicate):
            break
        if duplicate or remaining <= 0.1:
            break
        cuts.append(worst_weights)
    if best is None:
        raise LimitedSolve({"status": "time_limit_without_master", "has_incumbent": False, "reliable": False})
    (policy, responses, costs, worst_weights, feasibility, integrality, projection,
     raw_value, solver, info, constraints, objective, bounds, integer) = best
    gap = max(0.0, best_value - global_lower) / max(abs(best_value), 1e-10)
    valid = (feasibility <= TOL and integrality <= 1e-8 and projection <= TOL
             and global_lower <= best_value + 2e-4)
    reliable = bool(valid and gap <= config.gap + 1e-8)
    audit = {
        "status": "certificate" if reliable else "limited",
        "solver": "HiGHS_1.15_Q4_Wasserstein_constraint_generation_MILP",
        "solver_version": solver.version(),
        "seconds": time.perf_counter() - started,
        "solver_threads": config.solver_threads,
        "requested_gap": config.gap,
        "gap": gap,
        "objective": best_value,
        "optimizer_objective": raw_value,
        "lower_bound": global_lower,
        "scenario_costs": costs.tolist(),
        "empirical_weights": scenarios.weights.tolist(),
        "worst_case_weights": worst_weights.tolist(),
        "radius": scenarios.radius,
        "variables": len(objective),
        "binaries": int(integer.sum()),
        "constraints": constraints.A.shape[0],
        "active_distribution_cuts": iterations[-1]["cuts"],
        "iterations": iterations,
        "linear_feasibility_error": feasibility,
        "integrality_error": integrality,
        "monotone_projection_error": projection,
        "matrix_digest": matrix_digest(objective, bounds, integer, constraints),
        "has_incumbent": True,
        "valid": bool(valid),
        "reliable": reliable,
    }
    if not valid or (not reliable and not config.allow_limited):
        raise LimitedSolve(audit)
    return Solution(policy, responses, audit)
