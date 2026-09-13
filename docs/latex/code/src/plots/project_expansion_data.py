"""全项目补充图的只读统计，保留各问口径与来源。"""
from pathlib import Path
import json,hashlib,shutil
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'outputs/processed/figures/project_expansion_20260913';DATA=OUT/'data'
RUNS={'Q2':ROOT/'outputs/q2/dispatch_runs/20260912_tail_reserve_final/processed/main','Q3':ROOT/'outputs/q3/raw/full_priority_rescue_7h_20260912/main',
      'Q4-2':ROOT/'outputs/q4/raw/rescue_lp_q42_20260913_v2','Q4-3':ROOT/'outputs/q4/raw/rescue_lp_q43_20260913_v3'}


def write(name,f):f.to_csv(DATA/name,index=False,encoding='utf-8',float_format='%.17g')
def read(path):return pd.read_csv(path,float_precision='round_trip')


def prepare():
    DATA.mkdir(parents=True,exist_ok=True);sources=[];daily=[];dens=[];profiles=[];events=[];frames={};edges=np.linspace(1200,10800,25)
    for model,path in RUNS.items():
        src=path/'dispatch.csv';sources.append(src);f=read(src);assert len(f)==334*144
        f['slot0']=f.groupby('date').cumcount();f['hour']=(f.slot0+1)/6
        if 'total_cost' not in f:f['total_cost']=f.planned_cost+f.emergency_cost
        frames[model]=f
        columns=['date','slot0','hour','timestamp','grid','charge','discharge','emergency','soc','initial_soc','price','net_kwh','total_cost','emergency_cost']
        write(f'trajectory_{model}.csv',f[columns])
        act=np.where(f.charge.to_numpy()>1e-5,0,np.where(f.discharge.to_numpy()>1e-5,1,2)).reshape(334,144)
        assert not ((f.charge>1e-5)&(f.discharge>1e-5)).any()
        soc=np.clip(f.soc.to_numpy().reshape(334,144),1200,10800) # only tolerance-level excursions; raw trajectory remains unaltered
        assert f.soc.between(1200-1e-5,10800+1e-5).all()
        for slot in range(144):
            counts,_=np.histogram(soc[:,slot],edges)
            assert counts.sum()==334
            dens.extend({'model':model,'slot0':slot,'soc_low':edges[j],'soc_high':edges[j+1],'count':int(n),'probability':n/334} for j,n in enumerate(counts))
            profiles.append({'model':model,'slot0':slot,'hour':(slot+1)/6,'charge_fraction':np.mean(act[:,slot]==0),'discharge_fraction':np.mean(act[:,slot]==1),'idle_fraction':np.mean(act[:,slot]==2)})
        for date,g in f.groupby('date'):
            daily.append({'model':model,'date':date,'total_cost':g.total_cost.sum(),'emergency_cost':g.emergency_cost.sum(),'emergency_kwh':g.emergency.sum(),
                          'end_soc':g.soc.iloc[-1],'initial_soc':g.initial_soc.iloc[0],'mean_soc':g.soc.mean(),
                          'lower_bound_fraction':np.mean(g.soc<=1200+1e-5),'upper_bound_fraction':np.mean(g.soc>=10800-1e-5)})
        mask=f.emergency.to_numpy()>1e-5;starts=np.flatnonzero(mask&~np.r_[False,mask[:-1]]);ends=np.flatnonzero(mask&~np.r_[mask[1:],False])+1
        for start,end in zip(starts,ends):
            g=f.iloc[start:end];energy=g.emergency.sum()
            events.append({'model':model,'start':g.timestamp.iloc[0],'end':g.timestamp.iloc[-1],'slots':end-start,'duration_h':(end-start)/6,
                           'energy_kwh':energy,'cost_yuan':g.emergency_cost.sum(),'weighted_price':np.dot(g.emergency,g.price)/energy})
    daily=pd.DataFrame(daily);write('daily_states.csv',daily);write('soc_density.csv',pd.DataFrame(dens));write('action_profiles.csv',pd.DataFrame(profiles));write('emergency_events.csv',pd.DataFrame(events))
    tails=[];shares=[]
    for model,g in daily.groupby('model'):
        g=g.sort_values(['emergency_cost','date'],ascending=[False,True]);values=g.emergency_cost.to_numpy();total=values.sum()
        tails.extend({'model':model,'rank':i,'day_fraction':i/334,'cumulative_cost_fraction':v/total} for i,v in enumerate(np.r_[0,np.cumsum(values)]))
        for frac in [.05,.1,.2]:
            n=int(np.ceil(frac*334));shares.append({'model':model,'nominal_fraction':frac,'actual_days':n,'share':values[:n].sum()/total,'total_emergency_cost':total})
    write('risk_concentration.csv',pd.DataFrame(tails));write('risk_shares.csv',pd.DataFrame(shares))
    f=frames['Q2'];selected=f.groupby('date').emergency.sum().sort_values(ascending=False,kind='stable').index[0];day=f[f.date==selected].copy()
    day['previous_soc']=np.r_[day.initial_soc.iloc[0],day.soc.to_numpy()[:-1]];day['reserve_threshold']=1200+day.soc_reserve_kwh
    day['forecast_net_kwh']=(day.predicted_load_kw-day.predicted_pv_kw)/6
    day['deficit']=np.maximum(day.net_kwh-day.grid,0);day['available_discharge']=.9*np.maximum(day.previous_soc-day.reserve_threshold,0)
    np.testing.assert_allclose(day.discharge,np.minimum.reduce([day.discharge_cap.to_numpy(),day.deficit.to_numpy(),day.available_discharge.to_numpy()]),atol=1e-6,rtol=0)
    write('reserve_day.csv',day)
    node_rows=[];example=[]
    for model in ['Q4-2','Q4-3']:
        for path in sorted((RUNS[model]/'audit').glob('*.json')):
            sources.append(path);a=json.loads(path.read_text(encoding='utf-8'))
            for node in [a] if model=='Q4-2' else a['nodes']:
                s=node['solver'];sc=node['scenarios'];assert s['status']=='Optimal'
                c=np.array(s['scenario_costs']);p=np.array(s['empirical_weights']);w=np.array(s['worst_case_weights'])
                np.testing.assert_allclose([p.sum(),w.sum()],[1,1],atol=1e-8,rtol=0)
                empirical=p@c;worst=w@c;assert worst>=empirical-1e-6
                np.testing.assert_allclose(worst,s['objective'],atol=1e-5,rtol=0)
                node_rows.append({'model':model,'date':path.stem,'hour':node.get('hour',0),'empirical':empirical,'worst':worst,'premium_yuan':worst-empirical,
                                 'premium_pct':(worst/empirical-1)*100 if empirical else np.nan,'rho':sc['radius'],'ESS':sc['ESS'],'history_n':len(sc['history_days']),'S':len(c)})
                if model=='Q4-3' and path.stem=='2025-07-01' and node['hour']==0:
                    example.extend({'scenario':i+1,'cost':cost,'empirical_p':pp,'worst_p':ww,'delta_contribution':(ww-pp)*cost} for i,(cost,pp,ww) in enumerate(zip(c,p,w)))
    write('dro_nodes.csv',pd.DataFrame(node_rows));write('dro_example.csv',pd.DataFrame(example))
    # 原审计的场景origin与概率直接恢复分位区间，不重新构造或选择场景。
    q2=RUNS['Q2'].parents[1];actual_path=q2/'inputs/processed/timeseries.csv';sources.append(actual_path)
    a=read(actual_path)[['load_kw','pv_kw']].to_numpy().reshape(365,144,2);shadow=q2/'raw/shadows';shape=json.loads((shadow/'shape.json').read_text(encoding='utf-8'));sources.append(shadow/'shape.json');stores={}
    calibration=read(RUNS['Q2']/'calibration.csv');sources.append(RUNS['Q2']/'calibration.csv');write('original_calibration.csv',calibration)
    interval=[]
    for date in sorted(frames['Q2'].date.unique()):
        path=RUNS['Q2']/'daily_audit'/f'{date}.json';sources.append(path);audit=json.loads(path.read_text(encoding='utf-8'));K=audit['selected_K'];item=audit[str(K)]
        sc=item['candidates'][str(item['S'])]['scenarios'];ids=np.array(sc['selected_origin_indices']);weights=np.array(sc['weights']);pair=item['selection']['pipeline']
        for name in pair:
            if name not in stores:
                p=shadow/(name+'.dat');sources.append(p);stores[name]=np.memmap(p,mode='r',dtype=shape['dtype'],shape=tuple(shape['shape']))
        d=(pd.Timestamp(date)-pd.Timestamp('2025-01-01')).days
        point=np.stack([stores[name][d,:K] for name in pair],axis=-1)
        blocks=np.stack([a[j:j+K]-np.stack([stores[name][j,:K] for name in pair],axis=-1) for j in ids])
        value=np.maximum(point[None]+blocks,0);net=(value[...,0]-value[...,1])/6
        for h in range(min(K,365-d)):
            v=net[:,h,:];order=np.argsort(v,axis=0,kind='stable');sorted_v=np.take_along_axis(v,order,axis=0)
            sw=np.take_along_axis(np.broadcast_to(weights[:,None],v.shape),order,axis=0);cdf=np.cumsum(sw,axis=0)
            q=lambda level:sorted_v[np.argmax(cdf>=level-1e-12,axis=0),np.arange(144)]
            truth=(a[d+h,:,0]-a[d+h,:,1])/6
            for nominal,lo,hi in [(.8,.1,.9),(.9,.05,.95)]:
                lower,upper=q(lo),q(hi);covered=int(((truth>=lower)&(truth<=upper)).sum())
                orig=calibration[(calibration.origin==date)&(calibration.horizon==h)&(calibration.nominal==nominal)].iloc[0]
                assert covered==orig.covered_intervals,(date,h,nominal,covered,orig.covered_intervals)
                interval.append({'origin':date,'month':pd.Timestamp(date).month,'horizon':h,'nominal':nominal,'n':144,'covered':covered,'width_sum':float((upper-lower).sum())})
    interval=pd.DataFrame(interval);write('interval_origin_stats.csv',interval)
    monthly=interval.groupby(['month','horizon','nominal'],as_index=False)[['n','covered','width_sum']].sum();monthly['coverage']=monthly.covered/monthly.n;monthly['bias_pp']=(monthly.coverage-monthly.nominal)*100;monthly['mean_width_kwh']=monthly.width_sum/monthly.n
    write('interval_monthly.csv',monthly)
    for name in ['device_joint_grid.csv','device_one_dimensional.csv','fixed_mode_marginals.csv','milp_rhs_checks.csv']:
        src=ROOT/'outputs/processed/figures/q1'/name;sources.append(src);shutil.copy2(src,DATA/name)
    sens=ROOT/'outputs/sensitivity_q2_q3/raw/local_20260913/daily_results.csv';sources.append(sens);ss=read(sens);write('q3_terminal_cases.csv',ss[(ss.question=='q3')&(ss.parameter=='lambda_E')])
    model_table=pd.DataFrame({
        '维度':['评价范围','电价信息','优化前瞻','正式执行块','储能决策','风险表示','求解结构'],
        '问题一':['单个典型日','已知分时电价','24 h','24 h','完整日计划','确定性输入','MILP'],
        '问题二':['正式334日','已知分时电价','自适应48/72 h','24 h','冻结上限+实时反馈','联合误差+动态裕度','随机策略优化'],
        '问题三':['正式334日','已知分时电价','每节点24 h','6 h','节点策略+实时反馈','条件联合误差','四节点随机优化'],
        '问题4-2':['正式334日','0点48h预测','48 h','24 h','节点固定充放电','联合误差+DRO','连续LP'],
        '问题4-3':['正式334日','0点48h预测','每节点24 h','6 h','节点固定充放电','条件联合误差+DRO','四节点连续LP']})
    write('information_boundaries.csv',model_table)
    sources.extend([ROOT/'src/q2/policy.py',ROOT/'src/q4/rolling.py',ROOT/'docs/plots/project_expansion/补充图方案.md'])
    meta={'language':'中文标注，数学符号与单位英文；用户已确认','models':list(RUNS),'formal_days':334,'density_bin_edges':edges.tolist(),'emergency_event_threshold_kwh':1e-5,
          'reserve_date':selected,'reserve_role':'retained-discharge threshold, not an extra hard SOC constraint',
          'calibration_origin_rows':len(interval),'DRO_nodes':len(node_rows),'sources':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in set(sources)}}
    (DATA/'provenance.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf-8');print({'reserve_date':selected,'interval_rows':len(interval),'DRO_nodes':len(node_rows),'source_hashes':len(meta['sources'])},flush=True)


if __name__=='__main__':prepare()
