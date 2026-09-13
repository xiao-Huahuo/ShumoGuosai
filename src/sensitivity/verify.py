"""独立核查40个局部实验：原件、OFAT输入、实际物理/费用、基准不变与聚合。"""
import json
import numpy as np
import pandas as pd
from .common import ROOT,RUN,file_hash,digest,write_json
from .run import design,optional_jobs,signature
from . import q2,q3


def main():
    expected=design()+(optional_jobs() if json.loads((RUN/'optional_decision.json').read_text())['q3_S3_run'] else [])
    baseline=json.loads((RUN/'baseline_files_manifest.json').read_text())
    assert all(file_hash(ROOT/path)==value for path,value in baseline.items())
    assert file_hash(ROOT/'docs/sensitivity_q2_q3/问题2与问题3敏感性分析实验方案_时间受限版.md')=='866563d9481f002ba4feba69b1b7e113027d92f3f8d94b4df9ccac3838a3696f'
    rows=[];balance_errors=[];state_errors=[]
    for job in expected:
        folder=RUN/'jobs'/job['id'];r=json.loads((folder/'result.json').read_text())
        assert r['status'] in ('complete','limited') and r['physical_verified']
        assert r['signature']==signature(job)
        assert file_hash(folder/'dispatch.csv')==r['dispatch_sha256'] and file_hash(folder/'audit.json')==r['audit_sha256']
        f=pd.read_csv(folder/'dispatch.csv',float_precision='round_trip');meta=json.loads((RUN/'inputs'/job['question']/job['date']/'metadata.json').read_text())
        assert len(f)==144 and set(f.date)=={job['date']}
        assert abs(float(f.initial_soc.iloc[0])-meta['initial_soc'])<1e-7
        soc=meta['initial_soc']+np.cumsum(.9*f.charge-f.discharge/.9)
        state_error=float(abs(f.soc-soc).max());assert state_error<1e-5;state_errors.append(state_error)
        assert f.soc.min()>=1200-1e-5 and f.soc.max()<=10800+1e-5
        assert max(f.charge.max(),f.discharge.max())<=5000/6+1e-5
        assert min(f.charge.min(),f.discharge.min(),f.emergency.min())>=-1e-5
        if job['question']=='q2':
            a=np.load(RUN/'inputs/q2'/job['date']/'frozen.npz');v=np.load(folder/'variant_inputs.npz')
            if job['parameter']=='beta_R':
                np.testing.assert_array_equal(v['reserve'],a['reserve']*job['value']);np.testing.assert_array_equal(v['net'],a['net']);np.testing.assert_array_equal(v['weights'],a['weights'])
            else:
                np.testing.assert_array_equal(v['reserve'],a['reserve'])
                assert len(v['weights'])==meta['S']==26
            policy_frame=pd.read_csv(folder/'policy.csv',float_precision='round_trip')
            policy=q2.Policy(policy_frame.grid,policy_frame.charge_cap,policy_frame.discharge_cap,policy_frame.reserve)
            response=q2.replay(policy.first(),a['real_net'],meta['initial_soc'])
            for key,values in response.items():np.testing.assert_allclose(f[key],values,atol=1e-7,rtol=0)
            np.testing.assert_allclose(f.net_kwh,a['real_net'],atol=1e-9,rtol=0)
            cost=float(np.sum(a['prices'][:144]*(f.grid+5*f.emergency)))
            error=float(abs(f.grid+f.discharge+f.emergency-f.net_kwh-f.charge-f.unused).max())
        else:
            a=json.loads((folder/'audit.json').read_text());assert len(a['nodes'])==4
            np.testing.assert_array_equal(f.node_hour,np.repeat([0,6,12,18],36))
            for n in a['nodes']:
                h=n['hour'];frozen=np.load(RUN/'inputs/q3'/job['date']/f'{h:02d}.npz');b=meta['nodes'][h//6]
                assert n['history_sha256']==b['history_sha256']==digest(frozen['history_days'],frozen['load_errors'],frozen['pv_errors'])
                expected_S=int(job['value']) if job['parameter']=='S' else 20
                assert n['scenarios']['S']==expected_S and n['scenarios']['pool_size']==28
                assert len(set(n['scenarios']['history_days']))==expected_S
                assert set(n['scenarios']['history_days']).issubset(set(frozen['history_days']))
                scale=job['value'] if job['parameter']=='lambda_E' else 1
                assert abs(n['terminal']-float(frozen['terminal'])*scale)<1e-12
                initial=meta['initial_soc'] if h==0 else float(f.soc.iloc[h*6-1]);assert abs(n['initial_soc']-initial)<1e-7
                block=f.iloc[h*6:(h+6)*6]
                for key in ['grid','charge_cap','discharge_cap']:np.testing.assert_allclose(block[key],n[key][:36],atol=1e-7,rtol=0)
            delta=f.grid-f.g0
            adjustment=f.price*(1.5*np.maximum(delta,0)-.5*np.maximum(-delta,0))
            np.testing.assert_allclose(f.adjustment_cost,adjustment,atol=1e-7,rtol=0)
            cost=float(np.sum(f.price*f.g0+adjustment+5*f.price*f.emergency))
            error=float(abs(f.grid+f.discharge+f.emergency-f.net_kwh-f.charge-f.spill).max())
        assert error<1e-5;balance_errors.append(error)
        assert abs(cost-r['total_cost'])<1e-6
        b=meta['baseline'];assert abs(r['delta_cost_pct']-100*(cost-b['total_cost'])/b['total_cost'])<1e-8
        assert abs(r['delta_emergency_kwh']-(f.emergency.sum()-b['emergency_kwh']))<1e-7
        if b['emergency_kwh']==0:assert r['delta_emergency_pct'] is None
        rows.append(r)
    detail=pd.read_csv(RUN/'daily_results.csv');aggregate=pd.read_csv(RUN/'aggregate_results.csv')
    assert len(detail)==len(expected)+20
    assert len(aggregate)==15
    for _,row in aggregate.iterrows():
        g=detail[(detail.question==row.question)&(detail.parameter==row.parameter)&(detail.value==row.value)]
        assert len(g)==4 and row.days==4
        for key in ['total_cost','delta_cost_pct','emergency_kwh','emergency_cost','adjustment_cost','min_soc','final_soc','seconds']:
            for suffix,fn in [('median',np.median),('min',np.min),('max',np.max)]:
                np.testing.assert_allclose(row[key+'_'+suffix],fn(g[key]),atol=1e-7,rtol=0)
    result={'jobs_verified':len(rows),'core_jobs':32,'optional_jobs':len(rows)-32,'original_plan_bytes_verified':True,'q3_S28_user_approved':True,
            'baseline_files_unchanged':len(baseline),'all_same_initial_soc':True,'OFAT_frozen_inputs_verified':True,
            'max_balance_error_kwh':max(balance_errors),'max_soc_transition_error_kwh':max(state_errors),
            'all_delta_and_aggregate_statistics_verified':True,'baseline_not_resolved':True,
            'certified_jobs':sum(r['status']=='complete' for r in rows),'limited_feasible_jobs':sum(r['status']=='limited' for r in rows),'failed_jobs':0}
    write_json(RUN/'independent_acceptance.json',result);print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
