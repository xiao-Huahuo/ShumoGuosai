"""图5-5经用户确认的局部K比较：共同72h场景前缀，同机同预算，非全年。"""
from pathlib import Path
import sys,json,time,hashlib
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'src/q2'))
from rolling import _solve,dispatch_frame
from checkpoint import atomic_json

OUT=ROOT/'outputs/q2/benchmarks/horizon_figure_20260913'
INPUT=ROOT/'outputs/sensitivity_q2_q3/raw/local_20260913/inputs/q2'
DATES=['2025-09-17','2025-06-01','2025-06-02','2025-09-28']


def main():
    OUT.mkdir(parents=True,exist_ok=True);rows=[]
    for date in DATES:
        data=np.load(INPUT/date/'frozen.npz');meta=json.loads((INPUT/date/'metadata.json').read_text())
        for k in (1,2,3):
            directory=OUT/f'{date}_K{k}';directory.mkdir(exist_ok=True)
            if (directory/'result.json').exists():rows.append(json.loads((directory/'result.json').read_text()));continue
            count=k*144;net=data['net'][:,:count].copy();weights=data['weights'].copy();prices=data['prices'][:count].copy();reserve=data['reserve'][:count].copy()
            atomic_json(OUT/'status.json',{'phase':'solving','date':date,'K':k,'completed':len(rows),'total':12})
            start=time.perf_counter();cache={};opts=dict(reserve=reserve,solver_gap=meta['gap'],solver_threads=meta['threads'],refine_seconds=meta['refine_seconds'],solve_cache=cache,cache_key='local_K')
            policy,_,info=_solve(net,prices,weights,float(data['initial']),solver_seconds=meta['seconds'],**opts)
            if policy is None or not info['reliable']:
                atomic_json(directory/'first_attempt.json',info)
                policy,_,info=_solve(net,prices,weights,float(data['initial']),solver_seconds=meta['rescue_seconds'],**opts)
            elapsed=time.perf_counter()-start
            if policy is None:raise RuntimeError(f'{date} K{k}没有可执行策略')
            frame=dispatch_frame(pd.Timestamp(date),policy,data['real_net'],float(data['initial']),prices[:144])
            frame.to_csv(directory/'dispatch.csv',index=False,encoding='utf-8',float_format='%.17g')
            atomic_json(directory/'audit.json',info)
            row={'date':date,'K':k,'horizon_hours':k*24,'S':len(weights),'initial_soc':float(data['initial']),
                 'realized_day_cost':float((frame.planned_cost+frame.emergency_cost).sum()),'emergency_kwh':float(frame.emergency.sum()),
                 'end_soc':float(frame.soc.iloc[-1]),'solve_seconds':elapsed,'gap':info.get('mip_gap',info.get('gap')),'reliable':bool(info['reliable']),
                 'requested_gap':meta['gap'],'threads':meta['threads'],'shared_72h_input_sha256':hashlib.sha256((INPUT/date/'frozen.npz').read_bytes()).hexdigest()}
            atomic_json(directory/'result.json',row);rows.append(row);print(date,k,row['reliable'],round(elapsed,2),flush=True)
            pd.DataFrame(rows).to_csv(OUT/'cases.csv',index=False,encoding='utf-8',float_format='%.17g')
    frame=pd.DataFrame(rows);assert len(frame)==12
    frame.groupby('K',as_index=False).agg(horizon_hours=('horizon_hours','first'),mean_day_cost=('realized_day_cost','mean'),
        mean_solve_seconds=('solve_seconds','mean'),mean_end_soc=('end_soc','mean'),mean_emergency_kwh=('emergency_kwh','mean'),
        certified_cases=('reliable','sum'),cases=('date','count')).to_csv(OUT/'summary.csv',index=False,encoding='utf-8',float_format='%.17g')
    atomic_json(OUT/'status.json',{'phase':'complete','completed':12,'total':12,'all_certified':bool(frame.reliable.all()),'scope':'four matched days, shared scenario prefixes, same machine, not annual'})


if __name__=='__main__':main()
