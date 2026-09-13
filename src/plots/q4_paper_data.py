"""Q4科研六图的真实数据与来源；不调用模型求解器。"""
from pathlib import Path
import hashlib,json
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'outputs/processed/figures/q4_paper_final_20260913'
DATA=OUT/'data'
RUNS={'4-2':ROOT/'outputs/q4/raw/rescue_lp_q42_20260913_v2','4-3':ROOT/'outputs/q4/raw/rescue_lp_q43_20260913_v3'}


def write(name,frame):
    frame.to_csv(DATA/name,index=False,encoding='utf-8',float_format='%.17g')


def prepare():
    DATA.mkdir(parents=True,exist_ok=True);frames={};daily={};sources=[];quality=[];flow=[];summaries=[]
    for mode,path in RUNS.items():
        for name in ['dispatch.csv','daily.csv','state.json','metrics.json','launch.json','result'+mode+'.xlsx']:sources.append(path/name)
        f=pd.read_csv(path/'dispatch.csv',float_precision='round_trip');d=pd.read_csv(path/'daily.csv',float_precision='round_trip')
        assert len(f)==48096 and len(d)==334 and d.date.iloc[0]=='2025-02-01' and d.date.iloc[-1]=='2025-12-31'
        assert f.initial_soc.iloc[0]==6000 and f.groupby('date').size().eq(144).all()
        np.testing.assert_allclose(f.called+f.discharge+f.emergency,f.net_kwh+f.charge+f.spill,atol=1e-7,rtol=0)
        np.testing.assert_allclose(f.grid,f.called+f.unused,atol=1e-7,rtol=0)
        np.testing.assert_allclose(f.soc-np.r_[6000,f.soc.to_numpy()[:-1]],.9*f.charge-f.discharge/.9,atol=1e-7,rtol=0)
        delta=f.grid-f.g0;adjust=f.price*(1.5*np.maximum(delta,0)-.5*np.maximum(-delta,0))
        np.testing.assert_allclose(f.adjustment_cost,adjust,atol=1e-7,rtol=0)
        np.testing.assert_allclose(f.total_cost,f.price*f.g0+adjust+5*f.price*f.emergency,atol=1e-7,rtol=0)
        f['hour_right']=(f.slot+1)/6;f['delta_grid_kwh']=delta
        write(f'dispatch_{mode}.csv',f);write(f'daily_{mode}.csv',d)
        write(f'riskday_{mode}.csv',f[f.date=='2025-07-01'])
        day=f[f.date=='2025-07-01'];write(f'riskday_soc_{mode}.csv',pd.DataFrame({'hour':np.arange(145)/6,'soc_kwh':np.r_[day.initial_soc.iloc[0],day.soc]}))
        for date in d.date:
            audit_path=path/'audit'/f'{date}.json';sources.append(audit_path);a=json.loads(audit_path.read_text(encoding='utf-8'))
            for node in [a] if mode=='4-2' else a['nodes']:
                s=node['solver'];assert s['status']=='Optimal' and s['integer_variables']==0 and s['reliable']
                sc=node['scenarios'];quality.append({'mode':mode,'date':date,'hour':node.get('hour',0),'status':s['status'],
                    'seconds':s['seconds'],'gap':s['gap'],'S':sc['S'],'rho':sc['radius'],'ESS':sc.get('ESS'),
                    'initial_soc':node['initial_soc'],'committed_slots':node['committed_slots']})
        energy={'pv':float(f.pv_kw.sum()/6),'called':float(f.called.sum()),'emergency':float(f.emergency.sum()),
                'discharge':float(f.discharge.sum()),'load':float(f.load_kw.sum()/6),'charge':float(f.charge.sum()),'spill':float(f.spill.sum())}
        np.testing.assert_allclose(sum(energy[k] for k in ['pv','called','emergency','discharge']),sum(energy[k] for k in ['load','charge','spill']),atol=1e-6,rtol=0)
        flow.extend({'mode':mode,'side':'input' if key in ['pv','called','emergency','discharge'] else 'output','key':key,'kwh':v} for key,v in energy.items())
        summaries.append({'mode':mode,**{k:float(f[k].sum()) for k in ['grid','called','unused','charge','discharge','emergency','spill','planned_cost','adjustment_cost','emergency_cost','total_cost']},
                          'initial_soc':6000.,'final_soc':float(f.soc.iloc[-1]),'annual_days':len(d)})
        frames[mode]=f;daily[mode]=d
    first,second=frames['4-2'],frames['4-3']
    for key in ['date','slot','price','price_forecast','load_kw','pv_kw']:
        pd.testing.assert_series_equal(first[key],second[key],check_names=False)
    write('solver_quality.csv',pd.DataFrame(quality));write('energy_flow.csv',pd.DataFrame(flow));write('strategy_summary.csv',pd.DataFrame(summaries))
    hourly=first.assign(hour=first.slot//6).groupby(['date','hour'])[['price','price_forecast']].mean().reset_index()
    write('hourly_prices.csv',hourly)
    clock=[]
    for hour,g in hourly.groupby('hour'):
        clock.append({'hour':int(hour),'n_days':len(g),'actual_median':g.price.median(),'actual_p10':g.price.quantile(.1),
                      'actual_p90':g.price.quantile(.9),'forecast_median':g.price_forecast.median()})
    write('price_clock.csv',pd.DataFrame(clock))
    paired=daily['4-2'][['date','total_cost','soc_end']].merge(daily['4-3'][['date','total_cost','soc_end']],on='date',suffixes=('_q42','_q43'),validate='one_to_one')
    paired['saving_yuan']=paired.total_cost_q42-paired.total_cost_q43
    write('daily_cost_pairs.csv',paired)
    senspath=ROOT/'outputs/processed/sensitivity_q4/daily_results.csv';sens=pd.read_csv(senspath,float_precision='round_trip');sources.append(senspath)
    assert len(sens)==30 and sens.all_optimal.all();write('local_sensitivity.csv',sens)
    for mode in RUNS:
        cols=['total_cost','planned_cost','adjustment_cost','emergency_cost'];f=frames[mode];d=daily[mode]
        np.testing.assert_allclose(f.groupby('date')[cols].sum(),d[cols],atol=1e-6,rtol=0)
    err=first.price-first.price_forecast
    config=json.loads((RUNS['4-3']/'state.json').read_text(encoding='utf-8'))['config']
    source_theme=ROOT/'docs/plots/q4_paper_final/ThemeDisplayer.html';sources.append(source_theme)
    audit={'runs':{m:str(p.relative_to(ROOT)) for m,p in RUNS.items()},'days':334,'slots_per_strategy':48096,'optimal_nodes':len(quality),
           'source_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},'riskday':'2025-07-01',
           'riskday_rule':'Reuse the high joint-risk day selected by the prior Q4 sensitivity protocol',
           'price_MAE':float(abs(err).mean()),'price_RMSE':float(np.sqrt(np.mean(err*err))),
           'total_saving_yuan':float(paired.saving_yuan.sum()),'saving_day_fraction':float((paired.saving_yuan>0).mean()),
           'config':config,'fonts':'FandolSong-Regular + Latin Modern Roman + Computer Modern math; local TeX Live 2026',
           'palette':{'Blue Lotus':['#19309A','#4B69EF','#7E96FE','#B6D8F7','#FFB967'],'月白深蓝':['#FFFEF0','#CDBFE2','#002254']}}
    (DATA/'provenance.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
    print({k:v for k,v in audit.items() if k not in ['source_sha256','config','palette']})


if __name__=='__main__':prepare()
