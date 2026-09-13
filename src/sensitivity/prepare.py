"""仅按预注册指标选择代表日，并检查正式条件池是否支持OFAT。"""
from pathlib import Path
import sys,json,hashlib
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from src.q3.data import read_inputs
from src.q3.config import Config,DT
from src.q3.scenarios import pool_indices
OUT=ROOT/'outputs/sensitivity_q2_q3/raw/local_20260913'
Q2=ROOT/'outputs/q2/dispatch_runs/20260912_tail_reserve_final/processed/main'
Q3=ROOT/'outputs/q3/raw/full_priority_rescue_7h_20260912/main'


def select(frame, rules):
    selected=[];used=set()
    for role,columns,ascending,mask in rules:
        ordered=frame.loc[mask].sort_values(columns+['date'],ascending=ascending+[True],kind='stable')
        chosen=ordered[~ordered.date.isin(used)].iloc[0]
        used.add(chosen.date);selected.append({'role':role,**chosen.to_dict()})
    return selected


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    f=pd.read_csv(Q2/'dispatch.csv',float_precision='round_trip')
    f['predicted_net_kwh']=(f.predicted_load_kw-f.predicted_pv_kw)*DT
    f['net_mae']=abs(f.net_kwh-f.predicted_net_kwh)
    f['total_cost']=f.planned_cost+f.emergency_cost
    metrics=f.groupby('date',sort=True).agg(total_cost=('total_cost','sum'),emergency=('emergency','sum'),net_mae=('net_mae','mean'),peak_net=('net_kwh','max'),initial_soc=('initial_soc','first')).reset_index()
    metrics['median_cost_distance']=abs(metrics.total_cost-metrics.total_cost.median())
    low=metrics.emergency<=metrics.emergency.median()
    q2=select(metrics,[('常规日',['median_cost_distance'],[True],low),('高预测误差日',['net_mae'],[False],np.ones(len(metrics),bool)),('高紧急购电日',['emergency'],[False],np.ones(len(metrics),bool)),('高系统压力日',['peak_net'],[False],np.ones(len(metrics),bool))])
    metrics.to_csv(OUT/'q2_selection_metrics.csv',index=False,encoding='utf-8')
    data=read_inputs(ROOT/'outputs/q2/dispatch_runs/20260911_224501')
    f=pd.read_csv(Q3/'dispatch.csv',float_precision='round_trip')
    metrics=f.groupby('date',sort=True).agg(total_cost=('total_cost','sum'),emergency=('emergency','sum'),adjustment_cost=('adjustment_cost','sum'),peak_net=('net_kwh','max'),initial_soc=('initial_soc','first')).reset_index()
    changes=[]
    for date in metrics.date:
        day=(pd.Timestamp(date)-pd.Timestamp('2025-01-01')).days
        old=data.pv(day,0)
        changes.append(float(np.mean(np.r_[abs(data.pv(day,6)[:36]-old[36:72]),abs(data.pv(day,12)[:36]-old[72:108])])))
    metrics['pv_update_mae_kw']=changes
    metrics['median_cost_distance']=abs(metrics.total_cost-metrics.total_cost.median())
    any_day=np.ones(len(metrics),bool)
    q3=select(metrics,[('常规日',['median_cost_distance'],[True],any_day),('高预测更新日',['pv_update_mae_kw'],[False],any_day),('高调整成本日',['adjustment_cost'],[False],any_day),('高风险日',['emergency'],[False],any_day)])
    metrics.to_csv(OUT/'q3_selection_metrics.csv',index=False,encoding='utf-8')
    capacity=[]
    for row in q3:
        date=row['date'];day=(pd.Timestamp(date)-pd.Timestamp('2025-01-01')).days
        baseline=json.loads((Q3/'audit'/f'{date}.json').read_text())
        for node in baseline['nodes']:
            h=node['hour'];ids,el,ep,scales=data.history(day,h,data.selected[day])
            pool,meta=pool_indices(ids,scales,day,data.pv(day,h).sum()*DT,Config())
            assert len(pool)==node['scenarios']['candidate_count']
            capacity.append({'date':date,'hour':h,'frozen_pool_size':len(pool),'supports_S30':len(pool)>=30,'history_days':ids[pool].tolist()})
    for row in q2:
        a=json.loads((Q2/'daily_audit'/f"{row['date']}.json").read_text());selected=a[str(a['selected_K'])]
        row.update(K=a['selected_K'],S=selected['S'],M=selected['M'],solver_gap=selected['selected_solver'].get('requested_gap'),reserve_max=selected['selection']['dynamic_soc_reserve']['max_reserve_kwh'])
    result={'q2':q2,'q3':q3,'q3_pool_capacity':capacity,'q2_low_emergency_threshold':float(pd.read_csv(OUT/'q2_selection_metrics.csv').emergency.median()),'rules_frozen_before_experiments':True,'tie_break':'next unused by ranking then ascending date'}
    (OUT/'representatives.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
