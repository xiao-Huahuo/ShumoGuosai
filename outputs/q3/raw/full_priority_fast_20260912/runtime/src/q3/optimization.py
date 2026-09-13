"""3.13—3.17：有限域精确反馈MILP；LP只提供下界和可行策略初值。"""
from dataclasses import dataclass
import time
import numpy as np
from pyscipopt import Model, quicksum, Eventhdlr, SCIP_EVENTTYPE, SCIP_STAGE
from pathlib import Path
from .config import Config, CAP, E_MIN, E_MAX, ETA, TOL
from .physics import Policy, replay, adjustment
from .scenarios import Scenarios


@dataclass
class Solution:
    policy: Policy | None
    responses: list[dict]
    audit: dict


class LimitedSolve(RuntimeError):
    def __init__(self, audit: dict):
        super().__init__('限时内未取得所要求的最优性证书；保留诊断，不发布正式结果')
        self.audit = audit

    def __reduce__(self) -> tuple:
        return (LimitedSolve, (self.audit,))


def objective(policy: Policy, responses: list[dict], weights: np.ndarray, prices: np.ndarray,
              reference: np.ndarray | None, today: int, terminal: float) -> float:
    schedule = np.dot(prices, policy.grid) if reference is None else (
        adjustment(policy.grid[:today], reference[:today], prices[:today]).sum()
        +np.dot(prices[today:], policy.grid[today:]))
    return float(schedule+sum(w*(5*np.dot(prices, r['emergency'])-terminal*r['soc'][-1])
                              for w, r in zip(weights, responses)))


def make_model(seconds: float, gap: float = 0., threads: int = 1) -> Model:
    model = Model('q3_exact_causal_policy')
    model.hideOutput()
    model.setRealParam('limits/time', seconds)
    model.setRealParam('limits/gap', gap)
    model.setIntParam('parallel/minnthreads', threads)
    model.setIntParam('parallel/maxnthreads', threads)
    model.setIntParam('randomization/randomseedshift', 0)
    return model


def optimize_model(model: Model, threads: int) -> None:
    if threads > 1:
        model.solveConcurrent()
    else:
        model.optimize()


def scheduled_cost(model: Model, grid: list, prices: np.ndarray, reference: list | np.ndarray | None,
                   today: int, seed: list | None = None, seed_grid: np.ndarray | None = None,
                   seed_reference: np.ndarray | None = None) -> object:
    terms = []
    for t, (g, price) in enumerate(zip(grid, prices)):
        if reference is None or t >= today:
            terms.append(price*g)
        else:
            # convex slopes 0.5p and 1.5p; negative value is cancellation net saving.
            value = model.addVar(lb=-model.infinity(), name=f'adjust_{model.getNVars()}')
            for slope in (.5, 1.5):
                model.addCons(value >= slope*price*(g-reference[t]))
            terms.append(value)
            if seed is not None:
                delta = seed_grid[t]-seed_reference[t]
                seed.append((value, price*(1.5*max(delta, 0)-.5*max(-delta, 0))))
    return quicksum(terms)


def add_path(model: Model, grid: list, cp: list, rp: list, net: np.ndarray,
             upper: np.ndarray, initial: object, *, exact: bool, feedback: str,
             previous_net: float, initial_lower: float = E_MIN, initial_upper: float = E_MAX,
             seed_policy: Policy | None = None, seed_initial: float | None = None,
             seed_entries: list | None = None) -> dict:
    """允许initial为树父状态；所有响应由共享节点参数和已观测状态决定。"""
    responses = {key: [] for key in ('charge', 'discharge', 'emergency', 'spill', 'soc')}
    previous = initial
    seeded = replay(seed_policy, net, seed_initial, mode=feedback, previous_net=previous_net) if seed_policy else None

    def minimum(bounds: list, maxima: list[float], label: str, seed_bounds: list | None) -> object:
        value = model.addVar(lb=0, ub=min(maxima), name=label)
        switches = [model.addVar(vtype='B') for _ in bounds]
        model.addCons(quicksum(switches) == 1)
        for bound, maximum, switch in zip(bounds, maxima, switches):
            model.addCons(value <= bound)
            model.addCons(value >= bound-maximum*(1-switch))
        if seed_bounds is not None:
            selected = int(np.argmin(seed_bounds))
            seed_entries.append((value, min(seed_bounds)))
            seed_entries.extend((v, float(i == selected)) for i, v in enumerate(switches))
        return value

    for t, demand in enumerate(net):
        low = max(E_MIN, initial_lower-t*CAP/ETA)
        high = min(E_MAX, initial_upper+t*ETA*CAP)
        observed = demand if feedback == 'aggregate' else (previous_net if t == 0 else net[t-1])
        previous_seed = seed_initial if t == 0 else (seeded['soc'][t-1] if seeded else None)
        if exact:
            plus_bound, minus_bound = max(observed, 0), max(upper[t]-observed, 0)
            zp = model.addVar(lb=0, ub=plus_bound)
            zm = model.addVar(lb=0, ub=minus_bound)
            sign = model.addVar(vtype='B')
            model.addCons(observed-grid[t] == zp-zm)
            model.addCons(zp <= plus_bound*sign)
            model.addCons(zm <= minus_bound*(1-sign))
            if seeded:
                delta = observed-seed_policy.grid[t]
                seed_entries.extend(((zp, max(delta, 0)), (zm, max(-delta, 0)), (sign, float(delta >= 0))))
            cb = ([seed_policy.charge_cap[t], max(-delta, 0), max((E_MAX-previous_seed)/ETA, 0)] if seeded else None)
            rb = ([seed_policy.discharge_cap[t], max(delta, 0), max(ETA*(previous_seed-E_MIN), 0)] if seeded else None)
            c = minimum([cp[t], zm, (E_MAX-previous)/ETA], [CAP, minus_bound, (E_MAX-low)/ETA], 'c', cb)
            r = minimum([rp[t], zp, ETA*(previous-E_MIN)], [CAP, plus_bound, ETA*(high-E_MIN)], 'r', rb)
        else:
            c, r = (model.addVar(lb=0, ub=CAP) for _ in range(2))
        q = model.addVar(lb=0, ub=max(demand, 0)+CAP)
        u = model.addVar(lb=0, ub=max(upper[t]-demand, 0)+CAP)
        e = model.addVar(lb=max(E_MIN, low-CAP/ETA), ub=min(E_MAX, high+ETA*CAP))
        model.addCons(e == previous+ETA*c-r/ETA)
        model.addCons(grid[t]+r+q == demand+c+u)
        if exact and feedback == 'aggregate':
            model.addCons(q == zp-r)
            model.addCons(u == zm-c)
        # lag: q/u positive part is exact at optimum since q cost strictly positive and u free.
        for key, variable in zip(responses, (c, r, q, u, e)):
            responses[key].append(variable)
            if seeded and key not in ('charge', 'discharge'):
                seed_entries.append((variable, seeded[key][t]))
        previous = e
    return responses


def solve(scenarios: Scenarios, prices: np.ndarray, initial: float, config: Config, *,
          reference: np.ndarray | None = None, today: int = 144, terminal: float = 0.,
          previous_net: float = 0., require: bool = True, fixed: Policy | None = None,
          checkpoint: Path | None = None, max_slices: int | None = 1) -> Solution:
    started = time.perf_counter()
    net, weights = scenarios.net, scenarios.weights
    prices = np.asarray(prices, dtype=float)
    s, count = net.shape
    if len(prices) != count or scenarios.load.shape != net.shape or (prices <= 0).any():
        raise ValueError('场景/价格维度非法')
    if not all(np.isfinite(v).all() for v in (net, scenarios.load, weights, prices)) or (weights <= 0).any() or not np.isclose(weights.sum(), 1):
        raise ValueError('场景/概率非法')
    if not E_MIN <= initial <= E_MAX or terminal < 0 or not np.isfinite(terminal):
        raise ValueError('初態或终端残值非法')
    upper = scenarios.load.max(0)/6+CAP  # 3.13的负荷上界，不能以净负荷替换。
    today = min(today, count)
    if reference is not None and (len(reference) < today or not np.isfinite(reference[:today]).all()):
        raise ValueError('当天原计划不完整')

    if max_slices is not None and max_slices < 1:
        raise ValueError('切片次数必须为正或None')
    from .checkpoint import request_digest, load_snapshot, save_snapshot
    signature = request_digest(config, scenarios.load, scenarios.pv, weights, prices, initial,
        reference, today, terminal, previous_net,
        *(getattr(fixed, key) if fixed else None for key in ('grid', 'charge_cap', 'discharge_cap'))) if checkpoint else ''
    restored = load_snapshot(checkpoint/'latest.json', signature) if checkpoint else None
    restored_lower = -float('inf')
    if restored:
        restored_policy, restored_audit = restored
        restored_responses = [replay(restored_policy, n, initial, mode=config.feedback, previous_net=previous_net) for n in net]
        restored_value = objective(restored_policy, restored_responses, weights, prices, reference, today, terminal)
        if (restored_policy.grid > upper+TOL).any() or not np.isclose(restored_value, restored_audit['objective'], rtol=0, atol=TOL):
            raise ValueError('节点快照策略物理上界或重算目标不符')
        restored_lower = restored_audit.get('lower_bound')
        restored_lower = -float('inf') if restored_lower is None else float(restored_lower)
        if restored_lower > restored_value+TOL:
            raise ValueError('节点快照下界超过可行上界')
        if restored_audit.get('reliable'):
            if restored_value-restored_lower > max(TOL, config.gap*abs(restored_value)):
                raise ValueError('已完成节点快照的最优性证书不符')
            return Solution(restored_policy, restored_responses, {**restored_audit, 'restored_complete_node': True})
        if not require and max_slices == 1 and restored_audit.get('completed_slices', 0) >= 1:
            return Solution(restored_policy, restored_responses, {**restored_audit, 'restored_budgeted_sample': True})

    # 自由场景recourse仅为可证明下界，不作为实际策略。
    relaxed = make_model(max(.01, config.seconds/4))
    rg = [relaxed.addVar(lb=0, ub=float(v)) for v in upper]
    paths = [add_path(relaxed, rg, [], [], n, upper, initial, exact=False, feedback=config.feedback,
                      previous_net=previous_net, initial_lower=initial, initial_upper=initial) for n in net]
    expression = scheduled_cost(relaxed, rg, prices, reference, today)
    expression += quicksum(float(w)*(quicksum(5*float(p)*q for p, q in zip(prices, path['emergency']))
                                     -terminal*path['soc'][-1]) for w, path in zip(weights, paths))
    relaxed.setObjective(expression); relaxed.optimize()
    lower = max(restored_lower, float(relaxed.getDualbound()))
    candidates = []
    if fixed is not None:
        candidates.append(fixed)
    elif relaxed.getNSols():
        g = np.clip(np.array([relaxed.getVal(v) for v in rg]), 0, upper)
        candidates.append(Policy(g, np.full(count, CAP), np.full(count, CAP)))
        rc = np.array([[relaxed.getVal(v) for v in p['charge']] for p in paths])
        rr = np.array([[relaxed.getVal(v) for v in p['discharge']] for p in paths])
        candidates.append(Policy(g, np.clip(rc.max(0), 0, CAP), np.clip(rr.max(0), 0, CAP)))
    else:
        candidates.append(Policy(np.maximum(net.max(0), 0), np.zeros(count), np.zeros(count)))
    if restored and fixed is None:
        candidates.append(restored_policy)
    evaluated = []
    for candidate in candidates:
        responses = [replay(candidate, n, initial, mode=config.feedback, previous_net=previous_net) for n in net]
        value = objective(candidate, responses, weights, prices, reference, today, terminal)
        evaluated.append((value, candidate, responses))
    value, seed, responses = min(evaluated, key=lambda item: item[0])
    certified = max(0., value-lower)/max(abs(value), 1e-10) if np.isfinite(lower) else None
    if fixed is None and config.feedback == 'aggregate' and value-lower > max(TOL, config.gap*abs(value)):
        from .incumbent import refine
        candidate = refine(seed, net, prices, weights, initial, reference, today, terminal, upper,
                           min(1., config.seconds/10))
        candidate_responses = [replay(candidate, n, initial) for n in net]
        candidate_value = objective(candidate, candidate_responses, weights, prices, reference, today, terminal)
        if candidate_value < value:
            value, seed, responses = candidate_value, candidate, candidate_responses
            certified = max(0., value-lower)/max(abs(value), 1e-10)
    if fixed is None and certified is not None and value-lower <= max(TOL, config.gap*abs(value)):
        audit = {'status': 'certified_policy_from_LP_bound', 'objective': value,
            'lower_bound': lower, 'gap': certified, 'reliable': True, 'seconds': time.perf_counter()-started,
            'scenario_count': s, 'slots': count, 'variables': relaxed.getNVars(), 'binaries': 0,
            'mapping_error': 0., 'terminal': terminal, 'relaxation_is_not_execution': True,
            'solver_threads': 1, 'requested_solver_threads': config.solver_threads, 'solve_method': 'LP_certificate'}
        if checkpoint:
            save_snapshot(checkpoint/'latest.json', signature, seed, audit)
        return Solution(seed, responses, audit)
    if fixed is None and config.feedback=='aggregate' and config.gap>0 and config.solver_threads==1:
        from .fast_solver import solve_fast
        attempt=time.time_ns();last_slice=[0]
        if checkpoint:
            save_snapshot(checkpoint/'latest.json',signature,seed,{
                'status':'initial_incumbent_saved','objective':value,'lower_bound':lower,
                'gap':certified,'reliable':False,'completed_slices':0,'seconds':time.perf_counter()-started})
        def persist_fast(policy: Policy, responses: list, audit: dict) -> None:
            elapsed=time.perf_counter()-started
            completed=int(elapsed//config.seconds)
            if audit['status']!='searching':completed=max(1,int(np.ceil(elapsed/config.seconds)))
            audit.update(completed_slices=completed,slice_seconds=config.seconds,seconds=elapsed,
                         restored_incumbent=restored is not None,
                         certificate='original_feedback_cost_with_valid_monotone_MILP_lower_bound')
            if checkpoint:
                save_snapshot(checkpoint/'latest.json',signature,policy,audit)
                if completed>last_slice[0]:
                    save_snapshot(checkpoint/f'slice_{attempt}_{completed:05d}.json',signature,policy,audit)
                    last_slice[0]=completed
        policy,responses,audit=solve_fast(scenarios,prices,initial,config,reference=reference,today=today,
            terminal=terminal,seed=seed,known_lower=lower,
            seconds=1e20 if max_slices is None else config.seconds*max_slices,
            progress=persist_fast if checkpoint else None)
        if policy is not None:persist_fast(policy,responses,audit)
        if require and not audit['reliable']:raise LimitedSolve(audit)
        return Solution(policy,responses,audit)
    model = make_model(max(.01, config.seconds-(time.perf_counter()-started)), config.gap, config.solver_threads)
    entries = []
    arrays = []
    for bounds, values in ((upper, seed.grid), (np.full(count, CAP), seed.charge_cap), (np.full(count, CAP), seed.discharge_cap)):
        variables = [model.addVar(lb=float(values[t]) if fixed else 0., ub=float(values[t]) if fixed else float(b))
                     for t, b in enumerate(bounds)]
        entries.extend(zip(variables, values)); arrays.append(variables)
    g, cp, rp = arrays
    paths = [add_path(model, g, cp, rp, n, upper, initial, exact=True, feedback=config.feedback,
                      previous_net=previous_net, initial_lower=initial, initial_upper=initial,
                      seed_policy=seed, seed_initial=initial, seed_entries=entries) for n in net]
    expression = scheduled_cost(model, g, prices, reference, today, entries, seed.grid, reference)
    expression += quicksum(float(w)*(quicksum(5*float(p)*q for p, q in zip(prices, path['emergency']))
                                     -terminal*path['soc'][-1]) for w, path in zip(weights, paths))
    model.setObjective(expression)
    seed_solution = model.createSol()
    for variable, seed_value in entries:
        model.setSolVal(seed_solution, variable, float(seed_value))
    seed_accepted = bool(model.addSol(seed_solution))
    dimensions = {'variables': model.getNVars(), 'constraints': model.getNConss(), 'binaries': model.getNBinVars()}
    completed_slices = 0
    attempt_id = time.time_ns()
    def extract() -> Solution:
        nonlocal lower
        audit = {'status': str(model.getStatus()), 'seconds': time.perf_counter()-started,
                 'solver_seconds': float(model.getSolvingTime()), 'scenario_count': s, 'slots': count,
                 'requested_gap': config.gap, 'seed_accepted': seed_accepted, 'terminal': terminal,
                 'solver_threads': config.solver_threads,
                 'solve_method': 'SCIP_solveConcurrent' if config.solver_threads > 1 else 'SCIP_optimize', **dimensions}
        if model.getNSols():
            policy = Policy(*(np.clip(np.array([model.getVal(v) for v in a]), 0, b) for a, b in zip(arrays, (upper, CAP, CAP))))
            responses = [replay(policy, n, initial, mode=config.feedback, previous_net=previous_net) for n in net]
            value = objective(policy, responses, weights, prices, reference, today, terminal)
            mapping = max(abs(float(model.getVal(v))-float(response[key][t])) for path, response in zip(paths, responses)
                          for key in path for t, v in enumerate(path[key]))
            lower = max(lower, float(model.getDualbound()))
            gap = max(0., value-lower)/max(abs(value), 1e-10)
            reliable = mapping <= TOL and value-lower <= max(TOL, config.gap*abs(value))
            audit.update(objective=value, lower_bound=lower, gap=gap, mapping_error=mapping, reliable=reliable)
        else:
            policy, responses = None, []
            audit.update(objective=None, lower_bound=lower if abs(lower) < 1e19 else None, gap=None, reliable=False)
        audit['completed_slices'] = completed_slices
        audit['slice_seconds'] = config.seconds
        audit['restored_incumbent'] = restored is not None
        return Solution(policy, responses, audit)

    if checkpoint:
        seed_audit = {'status': 'initial_incumbent_saved', 'objective': value,
            'lower_bound': lower if abs(lower) < 1e19 else None, 'gap': certified,
            'reliable': False, 'seconds': time.perf_counter()-started, 'completed_slices': 0,
            'mapping_error': 0., 'source': 'original_feedback_feasible_seed'}
        save_snapshot(checkpoint/'latest.json', signature, seed, seed_audit)
        event = ProgressEvent(lambda: extract(), checkpoint, signature, Solution(seed, responses, seed_audit))
        model.includeEventhdlr(event, 'q3_durable_incumbent', 'periodic feasible policy and valid bound checkpoint')
    else:
        event = None
    while True:
        if completed_slices:
            model.setRealParam('limits/time', float(model.getSolvingTime())+config.seconds)
        optimize_model(model, config.solver_threads)
        completed_slices += 1
        if event is not None and event.failure is not None:
            raise event.failure
        result = extract()
        policy, responses, audit = result.policy, result.responses, result.audit
        if checkpoint and policy is not None:
            save_snapshot(checkpoint/'latest.json', signature, policy, audit)
            save_snapshot(checkpoint/f'slice_{attempt_id}_{completed_slices:05d}.json', signature, policy, audit)
        if audit['reliable'] or (max_slices is not None and completed_slices >= max_slices):
            break
        if str(model.getStatus()) not in ('timelimit', 'gaplimit') or policy is None:
            break
        print(f'节点继续切片{completed_slices+1}，gap={audit["gap"]:.6%}', flush=True)
    if event is not None:
        event.extract = None  # 断开事件闭包对SCIP模型的引用，避免跨日累计保留模型。
    if require and not audit['reliable']:
        raise LimitedSolve(audit)
    return Solution(policy, responses, audit)


class ProgressEvent(Eventhdlr):
    """约10秒保存一次；仅原模型可行策略及有效全局下界，不宣称序列化搜索树。"""
    def __init__(self, extract, directory: Path, signature: str, fallback: Solution):
        self.extract, self.directory, self.signature = extract, directory, signature
        self.fallback = fallback
        self.last = time.monotonic()
        self.failure: Exception | None = None

    def eventinit(self) -> None:
        self.model.catchEvent(SCIP_EVENTTYPE.BESTSOLFOUND | SCIP_EVENTTYPE.NODESOLVED | SCIP_EVENTTYPE.LPSOLVED | SCIP_EVENTTYPE.PRESOLVEROUND, self)

    def eventexit(self) -> None:
        self.model.dropEvent(SCIP_EVENTTYPE.BESTSOLFOUND | SCIP_EVENTTYPE.NODESOLVED | SCIP_EVENTTYPE.LPSOLVED | SCIP_EVENTTYPE.PRESOLVEROUND, self)

    def eventexec(self, event) -> None:
        if time.monotonic()-self.last < 10 or self.model.getNSols() == 0:
            return
        self.last = time.monotonic()
        try:
            from .checkpoint import save_snapshot
            result = self.extract() if self.model.getStage() >= SCIP_STAGE.SOLVING else self.fallback
            if result.policy is not None and result.audit['mapping_error'] <= TOL:
                save_snapshot(self.directory/'latest.json', self.signature, result.policy,
                              {**result.audit, 'checkpoint_event': True, 'checkpoint_stage': int(self.model.getStage())})
        except Exception as error:
            self.failure = error
            self.model.interruptSolve()
