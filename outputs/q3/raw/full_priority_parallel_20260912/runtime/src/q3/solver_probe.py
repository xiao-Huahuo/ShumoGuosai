"""固定真实节点的求解器对比；只写隔离证据，不改活动运行。"""
import argparse
from dataclasses import replace
import json
from pathlib import Path
import time
from unittest.mock import patch
import numpy as np
import pandas as pd
from scipy.optimize._highspy import _core as highs
from scipy.optimize import LinearConstraint, Bounds
from scipy.sparse import vstack, csr_matrix, hstack, coo_matrix
from pyscipopt import Model, quicksum
from .config import ROOT, Config, CAP, TOL, ETA, E_MIN, E_MAX, write_json
from .data import read_inputs
from .scenarios import Scenarios, construct
from .physics import Policy, replay
from .optimization import objective
from .fast_solver import build_matrix, seed_vector, matrix_error
from .checkpoint import request_digest
from .rolling import previous_net


def discharge_hull(objective, bounds, integer, constraints, indices, scenes, initial):
    """四个反馈分支的透视凸包；整数时与原紧凑矩阵相同，连续时加强下界。"""
    net=scenes.net;s,t=net.shape;size=len(objective)
    split=np.arange(size,size+s*t*12).reshape(s,t,3,4)
    indices['hull_split']=split
    lower=np.r_[bounds.lb,np.zeros(s*t*12)];upper=np.r_[bounds.ub,np.full(s*t*12,np.inf)]
    rows=[];cols=[];vals=[];lbs=[];ubs=[]
    def add(terms,lo=-np.inf,hi=0.):
        row=len(ubs)
        for col,value in terms:
            rows.append(row);cols.append(int(col));vals.append(float(value))
        lbs.append(lo);ubs.append(hi)
    c,r,q,w,e=indices['responses'];lr=indices['lr'];z=indices['z']
    for j in range(s):
        emin=emax=initial
        for i in range(t):
            n=float(net[j,i]);gu=float(bounds.ub[indices['g'][i]])
            gb,pb,eb=split[j,i]
            # lambda_0=1-z；lambda_1..3为原有的三个最小值选择变量。
            selectors=[(int(z[j,i]),-1.,1.)]+[(int(a[j,i]),1.,0.) for a in lr]
            for block,total in ((gb,indices['g'][i]),(pb,indices['rp'][i])):
                add([(x,1) for x in block]+[(total,-1)],0.,0.)
            add([(x,1) for x in eb]+([] if i==0 else [(e[j,i-1],-1)]),initial if i==0 else 0.,initial if i==0 else 0.)
            for branch,(selector,sign,constant) in enumerate(selectors):
                for column,lo,hi in ((gb[branch],0.,gu),(pb[branch],0.,CAP),(eb[branch],emin,emax)):
                    add([(column,1),(selector,-hi*sign)],hi=hi*constant)
                    add([(column,-1),(selector,lo*sign)],hi=-lo*constant)
            # 充电分支g>=n，且只允许该分支充电。
            selector,sign,constant=selectors[0]
            add([(c[j,i],1),(selector,-CAP*sign)],hi=CAP*constant)
            add([(c[j,i],1),(gb[0],-1),(selector,n*sign)],hi=-n*constant)
            add([(c[j,i],ETA),(eb[0],1),(selector,-E_MAX*sign)],hi=E_MAX*constant)
            add([(w[j,i],1),(gb[0],-1),(c[j,i],1),(selector,n*sign)],-n*constant,-n*constant)
            # 放电上限分支：rp <= deficit, available。
            l1,l2,l3=[a[j,i] for a in lr]
            add([(pb[1],1),(gb[1],1),(l1,-n)])
            add([(pb[1],1),(eb[1],-ETA),(l1,ETA*E_MIN)])
            # 净缺口分支：0 <= deficit <= rp, available。
            add([(gb[2],1),(l2,-n)])
            add([(gb[2],-1),(l2,n),(pb[2],-1)])
            add([(gb[2],-1),(l2,n+ETA*E_MIN),(eb[2],-ETA)])
            # 剩余储能分支：available <= rp, deficit。
            add([(eb[3],ETA),(l3,-ETA*E_MIN),(pb[3],-1)])
            add([(eb[3],ETA),(l3,-ETA*E_MIN-n),(gb[3],1)])
            # 汇总三分支放电；q由能量平衡自动得到，避免重复分量。
            add([(r[j,i],1),(pb[1],-1),(l2,-n),(gb[2],1),(eb[3],-ETA),(l3,ETA*E_MIN)],0.,0.)
            # 可达储能界覆盖原cp=CAP反馈；不改变任何原策略。
            emin=max(E_MIN,emin-min(CAP,max(n,0))/ETA)
            emax=min(E_MAX,emax+ETA*min(CAP,max(gu-n,0)))
    extra=coo_matrix((vals,(rows,cols)),shape=(len(ubs),len(lower))).tocsc()
    matrix=vstack([hstack([constraints.A,coo_matrix((constraints.A.shape[0],len(lower)-size))]),extra]).tocsc()
    return np.r_[objective,np.zeros(len(lower)-size)],Bounds(lower,upper),np.r_[integer,np.zeros(len(lower)-size)],LinearConstraint(matrix,np.r_[constraints.lb,lbs],np.r_[constraints.ub,ubs]),indices


def hull_seed(vector, indices, initial):
    """把经原反馈验证的完整初值投影到分支拆分变量。"""
    split=indices['hull_split'];s,t=split.shape[:2]
    e=indices['responses'][4]
    for j in range(s):
        for i in range(t):
            branch=0 if vector[indices['z'][j,i]]<.5 else 1+int(np.argmax([vector[a[j,i]] for a in indices['lr']]))
            vector[split[j,i,0,branch]]=vector[indices['g'][i]]
            vector[split[j,i,1,branch]]=vector[indices['rp'][i]]
            vector[split[j,i,2,branch]]=initial if i==0 else vector[e[j,i-1]]
    return vector



def distance_cuts(f,b,integer,c,idx,scenes):
    """同一因果反馈对输入路径的非扩张界，包含全部场景对。"""
    from scipy.sparse import coo_matrix
    from .config import ETA,E_MAX,E_MIN
    rows=[];cols=[];values=[];rhs=[]
    e=idx['responses'][4];q=idx['responses'][2]
    for a in range(len(scenes.weights)):
        for d in range(a+1,len(scenes.weights)):
            lo=hi=0.
            for t,delta in enumerate(scenes.net[a]-scenes.net[d]):
                qhi=max(delta,0)+ETA*max(-lo,0);qlo=-max(-delta,0)-ETA*max(hi,0)
                lo=max(-(E_MAX-E_MIN),min(lo,0)-max(delta,0)/ETA)
                hi=min(E_MAX-E_MIN,max(hi,0)+max(-delta,0)/ETA)
                for block,l,u in ((e,lo,hi),(q,qlo,qhi)):
                    for sign,bound in ((1,u),(-1,-l)):
                        if bound>=b.ub[block[a,t]]-b.lb[block[d,t]] and sign==1:continue
                        if bound>=b.ub[block[d,t]]-b.lb[block[a,t]] and sign==-1:continue
                        k=len(rhs);rows.extend([k,k]);cols.extend([block[a,t],block[d,t]]);values.extend([sign,-sign]);rhs.append(bound)
    matrix=coo_matrix((values,(rows,cols)),shape=(len(rhs),len(f))).tocsc()
    return f,b,integer,LinearConstraint(vstack([c.A,matrix]).tocsc(),np.r_[c.lb,np.full(len(rhs),-np.inf)],np.r_[c.ub,rhs]),idx


def capture(run: Path, date: str, output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    execution=json.loads((run/'execution.json').read_text(encoding='utf-8'))
    values=execution['config'];values['nodes']=tuple(values['nodes']);config=Config(**values)
    day=(pd.Timestamp(date)-pd.Timestamp('2025-01-01')).days
    data=read_inputs(Path(execution['q2_run']),output/'prepared')
    scenes=construct(data,day,6,config)
    folder=run/'main/nodes'/date
    saved=json.loads((folder/'06/latest.json').read_text(encoding='utf-8'))['content']
    midnight=json.loads((folder/'00/latest.json').read_text(encoding='utf-8'))['content']
    initial=float(pd.read_csv(folder/'00/executed_block.csv',float_precision='round_trip').soc.iloc[-1])
    reference=np.asarray(midnight['policy']['grid'])[36:]
    prices=data.prices[(36+np.arange(144))%144];terminal=saved['audit']['terminal']
    with patch.object(Config,'signature',return_value=execution['signature']):
        signature=request_digest(config,scenes.load,scenes.pv,scenes.weights,prices,initial,
            reference,108,terminal,previous_net(data,day,6),None,None,None)
    if signature!=saved['signature']:raise ValueError('固定节点输入签名重建不符')
    with (output/'input.dat').open('wb') as stream:
        np.savez_compressed(stream,load=scenes.load,pv=scenes.pv,weights=scenes.weights,prices=prices,
            initial=initial,reference=reference,terminal=terminal,
            grid=saved['policy']['grid'],charge_cap=saved['policy']['charge_cap'],discharge_cap=saved['policy']['discharge_cap'])
    write_json(output/'input.json',{'run':str(run),'date':date,'signature':signature,'source_audit':saved['audit']})


def probe(folder: Path, method: str, seconds: float) -> dict:
    started=time.perf_counter()
    data=np.load(folder/'input.dat');scenes=Scenarios(data['load'],data['pv'],data['weights'],{})
    initial=float(data['initial']);terminal=float(data['terminal']);prices=data['prices'];ref=data['reference']
    f,b,integer,c,idx=build_matrix(scenes,prices,initial,reference=ref,today=108,terminal=terminal)
    if method.startswith('distance'):f,b,integer,c,idx=distance_cuts(f,b,integer,c,idx,scenes)
    if method.startswith('hull'):
        f,b,integer,c,idx=discharge_hull(f,b,integer,c,idx,scenes,initial)
    p=Policy(np.minimum(data['grid'],np.maximum(scenes.net.max(0),0)+CAP),np.full(len(prices),CAP),data['discharge_cap'])
    x=seed_vector(p,scenes,prices,initial,idx,len(f),ref)
    if 'hull_split' in idx:x=hull_seed(x,idx,initial)
    if max(matrix_error(x,b,integer,c))>TOL:raise ValueError('对比初值不可行')
    original_constraints=c;cutoff=None
    if method.startswith('cut'):
        cutoff=float(f@x-.03*abs(f@x))
        c=LinearConstraint(vstack([c.A,csr_matrix(f.reshape(1,-1))]).tocsc(),np.r_[c.lb,-np.inf],np.r_[c.ub,cutoff])
    threads=int(method[-1]);kind=method[:-1]
    if kind in ('highs','hull','cut','bound','seed','new','distance'):
        api=highs
        if kind=='new':
            from highspy import _core as api
        api._Highs.resetGlobalScheduler(True);m=api._Highs()
        options={'threads':threads,'parallel':'on' if threads>1 else 'off','output_flag':False,
            'mip_rel_gap':.03,'time_limit':seconds,'mip_feasibility_tolerance':1e-8,'primal_feasibility_tolerance':1e-8}
        if kind=='bound':options['mip_heuristic_effort']=0.
        if kind=='seed':options['random_seed']=17
        for key,value in options.items():
            if m.setOptionValue(key,value)==api.HighsStatus.kError:raise ValueError(key)
        lp=api.HighsLp();a=c.A
        lp.num_col_,lp.num_row_=len(f),a.shape[0];lp.col_cost_,lp.col_lower_,lp.col_upper_=f,b.lb,b.ub
        lp.row_lower_,lp.row_upper_=c.lb,c.ub;lp.a_matrix_.num_col_,lp.a_matrix_.num_row_=len(f),a.shape[0]
        lp.a_matrix_.format_=api.MatrixFormat.kColwise
        lp.a_matrix_.start_,lp.a_matrix_.index_,lp.a_matrix_.value_=a.indptr,a.indices,a.data
        lp.integrality_=[api.HighsVarType(int(v)) for v in integer];m.passModel(lp)
        if cutoff is None:
            seed=api.HighsSolution();seed.col_value=x;seed.value_valid=True;m.setSolution(seed)
        m.run();info=m.getInfo();lower=float(info.mip_dual_bound)
        if info.primal_solution_status==api.kSolutionStatusFeasible:x=np.array(m.getSolution().col_value)
        status=m.modelStatusToString(m.getModelStatus())
        if cutoff is not None:
            lower=cutoff if status=='Infeasible' else min(lower,cutoff)
    else:
        m=Model('q3_compact_probe');m.hideOutput();m.setRealParam('limits/time',seconds)
        m.setRealParam('limits/gap',.03/(1+.03));m.setRealParam('numerics/feastol',1e-8)
        m.setIntParam('parallel/minnthreads',threads);m.setIntParam('parallel/maxnthreads',threads)
        variables=[m.addVar(lb=float(lo),ub=None if np.isposinf(hi) else float(hi),vtype='B' if i else 'C',obj=float(cost))
            for lo,hi,i,cost in zip(b.lb,b.ub,integer,f)]
        a=c.A.tocsr()
        for row in range(a.shape[0]):
            start,end=a.indptr[row:row+2];expr=quicksum(float(value)*variables[col] for col,value in zip(a.indices[start:end],a.data[start:end]))
            if c.lb[row]==c.ub[row]:m.addCons(expr==float(c.ub[row]))
            else:
                if np.isfinite(c.lb[row]):m.addCons(expr>=float(c.lb[row]))
                if np.isfinite(c.ub[row]):m.addCons(expr<=float(c.ub[row]))
        seed=m.createSol()
        for var,value in zip(variables,x):m.setSolVal(seed,var,float(value))
        m.addSol(seed)
        if threads>1:m.solveConcurrent()
        else:m.optimize()
        lower=float(m.getDualbound());status=str(m.getStatus())
        if m.getNSols():x=np.array([m.getVal(v) for v in variables])
    policy=Policy(*[np.maximum(x[idx[k]],0) for k in ('g','cp','rp')])
    responses=[replay(policy,n,initial) for n in scenes.net]
    value=objective(policy,responses,scenes.weights,prices,ref,108,terminal)
    feasibility,integrality=matrix_error(x,b,integer,original_constraints)
    raw_soc=x[idx['responses'][4]];raw_q=x[idx['responses'][2]]
    projection=max(0.,float(np.max(raw_soc-np.array([r['soc'] for r in responses]))),float(np.max(np.array([r['emergency'] for r in responses])-raw_q)))
    if max(feasibility,projection)>TOL or integrality>1e-8 or value>f@x+TOL or lower>value+TOL:raise ValueError('独立物理/费用/界核验不通过')
    audit={'method':method,'seconds':time.perf_counter()-started,'status':status,'objective':value,'lower_bound':lower,
        'gap':max(0.,value-lower)/max(abs(value),1e-10),'reliable':bool(value-lower<=max(TOL,.03*abs(value))),
        'feasibility':feasibility,'integrality':integrality,'projection':projection,'binaries':int(integer.sum()),'threads':threads}
    write_json(folder/f'{method}.json',audit)
    write_json(folder/f'{method}_policy.json',{k:getattr(policy,k).tolist() for k in ('grid','charge_cap','discharge_cap')})
    return audit


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--capture',type=Path);parser.add_argument('--date')
    parser.add_argument('--folder',type=Path,required=True);parser.add_argument('--method',choices=['highs1','highs4','scip1','scip4','hull1','cut1','bound1','seed1','new1','new4','distance1'])
    parser.add_argument('--seconds',type=float,default=60.);args=parser.parse_args()
    if args.capture:capture(args.capture,args.date,args.folder)
    else:print(json.dumps(probe(args.folder,args.method,args.seconds)))
