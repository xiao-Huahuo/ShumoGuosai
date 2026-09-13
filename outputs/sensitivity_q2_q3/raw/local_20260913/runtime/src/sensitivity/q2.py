"""固定正式K/S/预测与历史块，仅扰动reserve倍率或tail比例。"""
import sys,json,time
from pathlib import Path
import numpy as np
import pandas as pd
from .common import ROOT,RUN,Q2,Q2_RUN,digest,file_hash,write_json,metrics,active
sys.path.insert(0,str(ROOT/'src/q2'))
from policy import Policy,DT,replay
from shadows import open_library,combined
from scenarios import joint_blocks,construct,dynamic_reserve
from rolling import _solve,dispatch_frame
from protocol import PROTOCOL


def prepare():
    store,_=open_library(Q2_RUN/'raw/shadows')
    actual_frame=pd.read_csv(Q2_RUN/'inputs/processed/timeseries.csv',float_precision='round_trip')
    actual=actual_frame[['load_kw','pv_kw']].to_numpy().reshape(365,144,2)
    prices=pd.read_csv(Q2_RUN/'inputs/processed/prices.csv',float_precision='round_trip').price_yuan_per_kwh.to_numpy()
    executed=pd.read_csv(Q2/'dispatch.csv',float_precision='round_trip')
    representatives=json.loads((RUN/'representatives.json').read_text())['q2']
    for row in representatives:
        date=row['date'];day=(pd.Timestamp(date)-pd.Timestamp('2025-01-01')).days
        audit_path=Q2/'daily_audit'/f'{date}.json';audit=json.loads(audit_path.read_text());k=audit['selected_K'];selected=audit[str(k)]
        selection=selected['selection'];forecasts=combined(store,selection['pipeline'])
        origins=np.asarray(selection['origin_indices']);all_origins=np.asarray(selection['all_origin_indices'])
        assert np.all(origins+k<=day) and np.all(all_origins+k<=day)
        point=np.asarray(forecasts[day,:k]);blocks=joint_blocks(actual[:day],forecasts,origins,k);all_blocks=joint_blocks(actual[:day],forecasts,all_origins,k)
        plan=pd.read_csv(Q2/'frozen_plans'/f'{date}.csv',float_precision='round_trip')
        policy=Policy(plan.grid,plan.charge_cap,plan.discharge_cap,plan.soc_reserve_kwh)
        calculated,_=dynamic_reserve(all_blocks,.8);np.testing.assert_allclose(policy.reserve[:144],calculated,atol=1e-8,rtol=0)
        p=np.tile(prices,k);net,w,scenes=construct(point,blocks,p,selected['S'],origins=origins,all_blocks=all_blocks,all_origins=all_origins,tail_fraction=.2)
        oldscenes=selected['candidates'][str(selected['S'])]['scenarios']
        assert scenes['selected_origin_indices']==oldscenes['selected_origin_indices']
        np.testing.assert_allclose(w,oldscenes['weights'],atol=1e-12,rtol=0)
        initial=row['initial_soc'];responses=[replay(policy,n,initial) for n in net]
        value=float(p@policy.grid+sum(weight*(5*p@resp['emergency']) for weight,resp in zip(w,responses)))
        np.testing.assert_allclose(value,selected['selected_solver']['objective'],atol=1e-5,rtol=0)
        base=executed[executed.date==date].copy()
        real=(actual[day,:,0]-actual[day,:,1])*DT
        for key,value in replay(policy.first(),real,initial).items():np.testing.assert_allclose(base[key],value,atol=1e-7,rtol=0)
        folder=RUN/'inputs/q2'/date;folder.mkdir(parents=True,exist_ok=True)
        np.savez(folder/'frozen.npz',point=point,blocks=blocks,all_blocks=all_blocks,origins=origins,all_origins=all_origins,
                 prices=p,net=net,weights=w,reserve=policy.reserve,real_net=real,initial=initial)
        base.to_csv(folder/'baseline_dispatch.csv',index=False,encoding='utf-8',float_format='%.17g')
        execution=audit['execution']
        metadata={'date':date,'role':row['role'],'K':k,'S':selected['S'],'initial_soc':initial,'baseline':metrics(base),
                  'baseline_solver':selected['selected_solver'],'gap':float(execution['gap']),'seconds':float(execution['base_solver_seconds']),
                  'rescue_seconds':float(execution['rescue_seconds']),'threads':int(execution.get('solver_threads',1)),'refine_seconds':float(execution.get('refine_seconds',5.)),
                  'fixed_history_sha256':digest(blocks,all_blocks,origins,all_origins),'point_sha256':digest(point),
                  'baseline_scenarios_sha256':digest(net,w),'baseline_reserve_sha256':digest(policy.reserve),
                  'baseline_audit_sha256':file_hash(audit_path),'baseline_plan_sha256':file_hash(Q2/'frozen_plans'/f'{date}.csv'),
                  'baseline_replay_verified':True,'scenario_reconstruction_verified':True}
        write_json(folder/'metadata.json',metadata)


def run(job,folder):
    frozen=RUN/'inputs/q2'/job['date'];a=np.load(frozen/'frozen.npz');meta=json.loads((frozen/'metadata.json').read_text())
    reserve=a['reserve'].copy();net=a['net'];weights=a['weights'];scenes={}
    if job['parameter']=='beta_R':reserve*=job['value']
    elif job['parameter']=='rho_tail':
        net,weights,scenes=construct(a['point'],a['blocks'],a['prices'],meta['S'],origins=a['origins'],all_blocks=a['all_blocks'],all_origins=a['all_origins'],tail_fraction=job['value'])
    else:raise ValueError('未授权的Q2实验参数')
    assert len(net)==meta['S']
    assert digest(a['blocks'],a['all_blocks'],a['origins'],a['all_origins'])==meta['fixed_history_sha256']
    if job['parameter']=='rho_tail':assert digest(reserve)==meta['baseline_reserve_sha256']
    else:assert digest(net,weights)==meta['baseline_scenarios_sha256']
    np.savez(folder/'variant_inputs.npz',net=net,weights=weights,reserve=reserve)
    active('q2',job,'求解正式策略扰动',hour=0,detail=f"K={meta['K']}，S={meta['S']}，gap={meta['gap']:.0%}，线程={meta['threads']}")
    started=time.perf_counter();cache={}
    settings=dict(reserve=reserve,solver_gap=meta['gap'],solver_threads=meta['threads'],refine_seconds=meta['refine_seconds'],solve_cache=cache,cache_key='variant')
    policy,_,info=_solve(net,a['prices'],weights,float(a['initial']),solver_seconds=meta['seconds'],**settings)
    attempts=[info]
    if policy is None or not info['reliable']:
        active('q2',job,'原120秒预算未认证，沿用正式900秒追加预算',hour=0,detail='精度与模型不变；保存首次尝试')
        write_json(folder/'base_attempt.json',info)
        policy,_,info=_solve(net,a['prices'],weights,float(a['initial']),solver_seconds=meta['rescue_seconds'],**settings)
        attempts.append(info)
    if policy is None:raise RuntimeError('求解预算内无可行策略')
    frame=dispatch_frame(pd.Timestamp(job['date']),policy,a['real_net'],float(a['initial']),a['prices'][:144])
    frame.to_csv(folder/'dispatch.csv',index=False,encoding='utf-8',float_format='%.17g')
    pd.DataFrame({'grid':policy.grid,'charge_cap':policy.charge_cap,'discharge_cap':policy.discharge_cap,'reserve':policy.reserve}).to_csv(folder/'policy.csv',index=False,encoding='utf-8',float_format='%.17g')
    write_json(folder/'audit.json',{'solver':info,'attempts':attempts,'scenarios':scenes,'baseline':meta,'history_frozen':True})
    return {**metrics(frame),'seconds':time.perf_counter()-started,'reliable':bool(info['reliable']),'max_gap':info.get('mip_gap',info.get('gap',0)),
            'nodes':1,'certified_nodes':int(info['reliable']),'history_sha256':meta['fixed_history_sha256'],'physical_verified':True},meta['baseline']
