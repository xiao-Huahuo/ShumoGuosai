"""独立敏感性目录、原子状态与同日基准比较。"""
from pathlib import Path
import hashlib,json,os,time
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[2]
RUN=ROOT/'outputs/sensitivity_q2_q3/raw/local_20260913'
Q2_RUN=ROOT/'outputs/q2/dispatch_runs/20260912_tail_reserve_final'
Q2=Q2_RUN/'processed/main'
Q3_RUN=ROOT/'outputs/q3/raw/full_priority_rescue_7h_20260912'
Q3=Q3_RUN/'main'


def safe(value):
    if isinstance(value,dict):return {str(k):safe(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):return [safe(v) for v in value]
    if isinstance(value,np.ndarray):return safe(value.tolist())
    if isinstance(value,np.generic):return safe(value.item())
    if isinstance(value,float) and not np.isfinite(value):return None
    return value


def write_json(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix(path.suffix+f'.{os.getpid()}.pending')
    with temporary.open('w',encoding='utf-8') as stream:
        json.dump(safe(value),stream,ensure_ascii=False,indent=2,allow_nan=False);stream.flush();os.fsync(stream.fileno())
    temporary.replace(path)


def digest(*arrays):
    h=hashlib.sha256()
    for value in arrays:
        a=np.asarray(value);h.update(str(a.shape).encode());h.update(np.ascontiguousarray(a).tobytes())
    return h.hexdigest()


def file_hash(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def active(question,job,phase,**extra):
    write_json(RUN/f'{question}_active.json',{'phase':phase,'date':job['date'],'parameter':job['parameter'],'value':job['value'],'started_at':job.get('started_at',time.time()),**extra})


def metrics(frame):
    return dict(total_cost=float((frame.planned_cost+frame.emergency_cost+(frame.adjustment_cost if 'adjustment_cost' in frame else 0)).sum()),
                planned_cost=float(frame.planned_cost.sum()),adjustment_cost=float(frame.adjustment_cost.sum()) if 'adjustment_cost' in frame else 0.,
                emergency_kwh=float(frame.emergency.sum()),emergency_cost=float(frame.emergency_cost.sum()),
                min_soc=float(frame.soc.min()),final_soc=float(frame.soc.iloc[-1]),
                charge_kwh=float(frame.charge.sum()),discharge_kwh=float(frame.discharge.sum()),
                throughput_kwh=float(frame.charge.sum()+frame.discharge.sum()))


def comparison(variant,baseline):
    return dict(delta_cost_pct=100*(variant['total_cost']-baseline['total_cost'])/baseline['total_cost'],
                delta_emergency_kwh=variant['emergency_kwh']-baseline['emergency_kwh'],
                delta_emergency_pct=100*(variant['emergency_kwh']-baseline['emergency_kwh'])/baseline['emergency_kwh'] if baseline['emergency_kwh']>0 else None,
                emergency_pct_defined=baseline['emergency_kwh']>0)
