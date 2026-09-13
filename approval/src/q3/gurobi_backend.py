"""同一 SciPy 矩阵的可选 Gurobi 后端；许可证不足时明确失败，不静默改模型。"""
from __future__ import annotations
import time
from typing import Callable
import numpy as np
from .config import TOL


class GurobiUnavailable(RuntimeError):
    pass


def license_probe() -> dict:
    try:
        import gurobipy as gp
        from gurobipy import GRB
    except ImportError as error:
        return {'installed':False,'usable':False,'reason':'not_installed','error':str(error)}
    try:
        model=gp.Model('q3_license_probe');model.Params.OutputFlag=0
        value=model.addVar(vtype=GRB.BINARY);model.setObjective(value,GRB.MAXIMIZE);model.optimize()
        return {'installed':True,'usable':model.Status==GRB.OPTIMAL,'version':list(gp.gurobi.version()),
                'tiny_status':int(model.Status),'tiny_objective':float(model.ObjVal)}
    except gp.GurobiError as error:
        return {'installed':True,'usable':False,'version':list(gp.gurobi.version()),
                'reason':'license_error','error_code':int(error.errno),'error':str(error)}


def solve_gurobi_matrix(objective, bounds, integer, constraints, *, seed_vector: np.ndarray,
                        gap: float, seconds: float, threads: int, assess: Callable,
                        known_lower: float | None=None, progress: Callable | None=None,
                        mip_focus: int=0) -> tuple[np.ndarray,float,dict]:
    """解完全相同的稀疏矩阵；返回向量和 Gurobi 全局下界，语义验收由调用者的 assess 完成。"""
    try:
        import gurobipy as gp
        from gurobipy import GRB
    except ImportError as error:
        raise GurobiUnavailable('gurobipy未安装') from error
    objective=np.asarray(objective,dtype=float);seed_vector=np.asarray(seed_vector,dtype=float)
    matrix=constraints.A.tocsr();started=time.perf_counter()
    model=gp.Model('q3_same_matrix');model.Params.OutputFlag=0;model.Params.MIPGap=gap
    model.Params.TimeLimit=seconds;model.Params.Threads=threads;model.Params.FeasibilityTol=1e-8
    model.Params.IntFeasTol=1e-8;model.Params.MIPFocus=mip_focus
    vtypes=np.where(np.asarray(integer)==1,GRB.BINARY,GRB.CONTINUOUS)
    variables=model.addMVar(len(objective),lb=bounds.lb,ub=bounds.ub,obj=objective,vtype=vtypes)
    equal=constraints.lb==constraints.ub
    if equal.any():model.addMConstr(matrix[equal],variables,'=',constraints.ub[equal])
    lower=np.isfinite(constraints.lb)&~equal
    if lower.any():model.addMConstr(matrix[lower],variables,'>',constraints.lb[lower])
    upper=np.isfinite(constraints.ub)&~equal
    if upper.any():model.addMConstr(matrix[upper],variables,'<',constraints.ub[upper])
    variables.Start=seed_vector
    state={'vector':seed_vector.copy(),'raw':float(objective@seed_vector),
           'lower':float(known_lower) if known_lower is not None else -float('inf'),
           'last_save':0.,'last_archive':0,'assessed_value':None,'records':[]}
    def callback(active,where):
        if where==GRB.Callback.MIPSOL:
            candidate=np.asarray(active.cbGetSolution(variables),dtype=float)
            if np.isfinite(candidate).all() and float(objective@candidate)<state['raw']-TOL:
                state['vector']=candidate.copy();state['raw']=float(objective@candidate)
            state['lower']=max(state['lower'],float(active.cbGet(GRB.Callback.MIPSOL_OBJBND)))
        elif where==GRB.Callback.MIP:
            state['lower']=max(state['lower'],float(active.cbGet(GRB.Callback.MIP_OBJBND)))
        else:
            return
        elapsed=time.perf_counter()-started;archive=int(elapsed//120)
        certificate_due=(state['assessed_value'] is not None and
            state['assessed_value']-state['lower']<=max(TOL,gap*abs(state['assessed_value'])))
        if progress is not None and (certificate_due or elapsed-state['last_save']>=30 or archive>state['last_archive']):
            policy,responses,audit=assess(state['vector'],state['lower'])
            audit.update(seconds=elapsed,lower_bound=state['lower'],solver='Gurobi_same_matrix',
                         solver_version='.'.join(map(str,gp.gurobi.version())),solver_threads=threads,
                         mip_focus=mip_focus)
            progress(policy,responses,audit);state['last_save']=elapsed;state['last_archive']=archive
            state['assessed_value']=audit['objective']
            state['records'].append({'seconds':elapsed,'objective':audit['objective'],
                                     'lower_bound':state['lower'],'gap':audit['gap'],'reliable':audit['reliable']})
            if audit['reliable']:active.terminate()
    try:
        model.optimize(callback)
    except gp.GurobiError as error:
        reason='size_limited_license' if 'too large' in str(error).lower() else 'gurobi_error'
        raise GurobiUnavailable(f'{reason}: {error}') from error
    if model.SolCount:
        candidate=np.asarray(variables.X,dtype=float)
        if float(objective@candidate)<state['raw']-TOL:state['vector']=candidate;state['raw']=float(objective@candidate)
    final_lower=max(state['lower'],float(model.ObjBound))
    metadata={'status':int(model.Status),'solver':'Gurobi_same_matrix',
              'solver_version':'.'.join(map(str,gp.gurobi.version())),'solver_seconds':float(model.Runtime),
              'node_count':float(model.NodeCount),'simplex_iterations':float(model.IterCount),
              'barrier_iterations':float(model.BarIterCount),'solver_threads':threads,'mip_focus':mip_focus,
              'trajectory':state['records']}
    return state['vector'],final_lower,metadata
