"""固定正式历史条件池与lambda基准，节点内仍沿用原Q3求解与真实反馈。"""
from dataclasses import replace
import json,time
import numpy as np
import pandas as pd
from .common import ROOT,RUN,Q3,Q3_RUN,digest,file_hash,write_json,metrics,active
from src.q3.config import Config,DT
from src.q3.data import read_inputs
from src.q3.physics import Policy,replay,adjustment
from src.q3.scenarios import pool_indices,reduce_errors,Scenarios
from src.q3.optimization import solve,objective
from src.q3.rolling import frame_for,validate_frame,previous_net


def base_config():
    values=json.loads((Q3_RUN/'execution.json').read_text())['config'];values['nodes']=tuple(values['nodes'])
    return Config(**values)


def inputs():
    source=json.loads((Q3_RUN/'execution.json').read_text())['q2_run']
    return read_inputs(__import__('pathlib').Path(source))


def prepare():
    data=inputs();config=base_config();executed=pd.read_csv(Q3/'dispatch.csv',float_precision='round_trip')
    for row in json.loads((RUN/'representatives.json').read_text())['q3']:
        date=row['date'];day=(pd.Timestamp(date)-pd.Timestamp('2025-01-01')).days
        audit_path=Q3/'audit'/f'{date}.json';audit=json.loads(audit_path.read_text())
        folder=RUN/'inputs/q3'/date;folder.mkdir(parents=True,exist_ok=True)
        np.save(folder/'actual_day.npy',data.actual[day])
        base=executed[executed.date==date].copy();g0=base.g0.to_numpy();node_meta=[]
        for node in audit['nodes']:
            hour=node['hour'];ids,el,ep,scales=data.history(day,hour,data.selected[day]);pv=data.pv(day,hour)
            ix,pool=pool_indices(ids,scales,day,pv.sum()*DT,config);prices=data.prices[(hour*6+np.arange(144))%144]
            reps,w,reduction=reduce_errors(el[ix]-ep[ix],prices,config)
            assert ids[ix][reps].tolist()==node['scenarios']['history_days']
            np.testing.assert_allclose(w,node['scenarios']['weights'],atol=1e-12,rtol=0)
            point_load=data.load(day)[hour*6:hour*6+144];load=np.maximum(point_load+el[ix][reps],0);photovoltaic=np.maximum(pv+ep[ix][reps],0)
            net=(load-photovoltaic)*DT;policy=Policy(np.asarray(node['grid']),np.asarray(node['charge_cap']),np.asarray(node['discharge_cap']))
            responses=[replay(policy,path,node['initial_soc']) for path in net]
            coefficient=node['calibration']['median_unscaled']*node['calibration']['scale']
            reference=None if hour==0 else g0[hour*6:]
            val=objective(policy,responses,w,prices,reference,144-hour*6,coefficient)
            np.testing.assert_allclose(val,node['solver']['objective'],atol=1e-5,rtol=0)
            np.savez(folder/f'{hour:02d}.npz',point_load=point_load,point_pv=pv,load_errors=el[ix],pv_errors=ep[ix],history_days=ids[ix],
                     prices=prices,load=load,pv=photovoltaic,weights=w,terminal=coefficient,previous_net=previous_net(data,day,hour))
            node_meta.append({'hour':hour,'pool_size':len(ix),'history_sha256':digest(ids[ix],el[ix],ep[ix]),'point_sha256':digest(point_load,pv),
                              'baseline_scenarios_sha256':digest(load,photovoltaic,w),'terminal_baseline':coefficient,'calibration':node['calibration'],
                              'baseline_solver':node['solver']})
        reconstructed=replay(Policy(base.grid.to_numpy(),base.charge_cap.to_numpy(),base.discharge_cap.to_numpy()),base.net_kwh.to_numpy(),row['initial_soc'])
        for key,value in reconstructed.items():np.testing.assert_allclose(base[key],value,atol=1e-7,rtol=0)
        base.to_csv(folder/'baseline_dispatch.csv',index=False,encoding='utf-8',float_format='%.17g')
        write_json(folder/'metadata.json',{'date':date,'role':row['role'],'day_index':day,'initial_soc':row['initial_soc'],'baseline':metrics(base),
                                         'nodes':node_meta,'baseline_audit_sha256':file_hash(audit_path),'baseline_replay_verified':True,'scenario_reconstruction_verified':True})


def scenarios_for(a,config):
    reps,weights,reduction=reduce_errors(a['load_errors']-a['pv_errors'],a['prices'],config)
    load=np.maximum(a['point_load']+a['load_errors'][reps],0);pv=np.maximum(a['point_pv']+a['pv_errors'][reps],0)
    assert len(weights)==config.scenarios
    return Scenarios(load,pv,weights,{'S':len(weights),'history_pool_frozen':True,'pool_size':len(a['history_days']),
                                    'history_days':a['history_days'][reps].tolist(),'weights':weights.tolist(),**reduction})


def run(job,folder,data=None):
    data=inputs() if data is None else data
    frozen=RUN/'inputs/q3'/job['date'];meta=json.loads((frozen/'metadata.json').read_text());base=base_config()
    if job['parameter']=='S':config=replace(base,scenarios=int(job['value']))
    elif job['parameter']=='lambda_E':config=replace(base,terminal_scale=float(job['value']))
    elif job['parameter']=='S_tail':config=replace(base,tail=int(job['value']))
    else:raise ValueError('未授权的Q3参数')
    np.testing.assert_array_equal(data.actual[meta['day_index']],np.load(frozen/'actual_day.npy'))
    soc=meta['initial_soc'];frames=[];audits=[];g0=None;started=time.perf_counter()
    for h,node_meta in zip((0,6,12,18),meta['nodes']):
        a=np.load(frozen/f'{h:02d}.npz');assert digest(a['history_days'],a['load_errors'],a['pv_errors'])==node_meta['history_sha256']
        scenes=scenarios_for(a,config)
        if job['parameter']=='lambda_E':assert digest(scenes.load,scenes.pv,scenes.weights)==node_meta['baseline_scenarios_sha256']
        coefficient=float(a['terminal'])*config.terminal_scale
        reference=None if h==0 else g0[h*6:]
        active('q3',job,'求解节点',hour=h,detail=f'S={config.scenarios}，tail={config.tail}，lambda倍率={config.terminal_scale:g}，gap=3%')
        hard=config.hard_06_seconds if h==6 else config.hard_other_seconds
        solution=solve(scenes,a['prices'],soc,config,reference=reference,today=144-h*6,terminal=coefficient,
                       previous_net=float(a['previous_net']),checkpoint=folder/'nodes'/f'{h:02d}',max_slices=1,require=True,hard_seconds=hard)
        if solution.policy is None:raise RuntimeError('Q3节点未得到可执行策略')
        if h==0:g0=solution.policy.grid.copy()
        frame=frame_for(data,meta['day_index'],h,solution.policy.part(0,36),soc,config)
        frame['g0']=g0[h*6:(h+6)*6];frame['initial_soc']=meta['initial_soc'];frames.append(frame)
        audits.append({'hour':h,'initial_soc':soc,'solver':solution.audit,'scenarios':scenes.audit,'terminal':coefficient,'terminal_baseline':float(a['terminal']),
                       'history_sha256':node_meta['history_sha256'],'grid':solution.policy.grid.tolist(),'charge_cap':solution.policy.charge_cap.tolist(),'discharge_cap':solution.policy.discharge_cap.tolist()})
        soc=float(frame.soc.iloc[-1]);write_json(folder/'partial_audit.json',{'nodes':audits})
    frame=pd.concat(frames,ignore_index=True);frame['planned_cost']=frame.price*frame.g0
    frame['adjustment_cost']=adjustment(frame.grid.to_numpy(),frame.g0.to_numpy(),frame.price.to_numpy())
    frame['emergency_cost']=5*frame.price*frame.emergency;frame['total_cost']=frame.planned_cost+frame.adjustment_cost+frame.emergency_cost
    validate_frame(frame,config)
    frame.to_csv(folder/'dispatch.csv',index=False,encoding='utf-8',float_format='%.17g')
    write_json(folder/'audit.json',{'nodes':audits,'baseline':meta,'frozen_pool':True,'only_first_soc_anchored_later_soc_from_variant':True})
    certified=sum(n['solver']['reliable'] for n in audits)
    gaps=[n['solver'].get('gap') for n in audits if n['solver'].get('gap') is not None]
    return {**metrics(frame),'seconds':time.perf_counter()-started,'reliable':certified==4,'max_gap':max(gaps) if gaps else None,
            'nodes':4,'certified_nodes':certified,'physical_verified':True},meta['baseline']
