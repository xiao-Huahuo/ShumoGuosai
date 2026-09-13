"""等价求解器升级时逐节点核验并迁移；仅对已停止的旧运行执行。"""
import argparse
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import shutil
from unittest.mock import patch
import numpy as np
import pandas as pd
from .config import ROOT, CODE_ROOT, Config, E_INITIAL, TOL, write_json
from .checkpoint import request_digest, load_snapshot, save_snapshot
from .data import read_inputs
from .scenarios import construct
from .physics import replay
from .optimization import objective
from .rolling import previous_net, validate_frame
from .status_server import worker_alive


def migrate(old: Path, new: Path, threads: int) -> dict:
    old=old.resolve();new=new.resolve()
    progress=json.loads((old/'progress.json').read_text(encoding='utf-8'))
    if worker_alive(progress.get('worker_pid'),old):raise RuntimeError('必须先停止旧运行，避免复制活动提交')
    if new.exists():raise FileExistsError(new)
    original=json.loads((old/'execution.json').read_text(encoding='utf-8'))
    values=original['config'];values['nodes']=tuple(values['nodes']);before=Config(**values)
    after=replace(before,solver_threads=threads)
    for name,digest in json.loads((old/'runtime_sources.json').read_text(encoding='utf-8'))['files'].items():
        if hashlib.sha256((old/'runtime/src/q3'/name).read_bytes()).hexdigest()!=digest:raise ValueError('旧冻结源码摘要不符')
    runtime=new/'runtime/src/q3';runtime.mkdir(parents=True)
    for p in CODE_ROOT.glob('*.py'):
        if not p.name.startswith('test_'):shutil.copy2(p,runtime/p.name)
    (new/'runtime/src/__init__.py').write_text('',encoding='utf-8')
    requirements=(ROOT/'src/q2/requirements.txt').read_text(encoding='utf-8')+'\nhighspy==1.15.1\n'
    (new/'runtime/requirements.txt').write_text(requirements,encoding='utf-8')
    manifest={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in runtime.glob('*.py')}
    write_json(new/'runtime_sources.json',{'files':manifest,'requirements_sha256':hashlib.sha256(requirements.encode()).hexdigest(),
        'previous_run':str(old),'workspace':str(ROOT),'solver':'highspy==1.15.1','basis':'unchanged build_matrix, physics and model; solver implementation upgrade'})
    shutil.copytree(old/'main',new/'main')
    data=read_inputs(Path(original['q2_run']),new/'migration_prepared')
    state=json.loads((new/'main/state.json').read_text(encoding='utf-8'))
    sources=hashlib.sha256(json.dumps(data.provenance,sort_keys=True).encode('utf-8')).hexdigest()
    if sources!=state['sources']:raise ValueError('原始输入/Q2来源改变，拒绝迁移')
    frames=[]
    for row in state['days']:
        date=str((pd.Timestamp('2025-01-01')+pd.Timedelta(days=row['day'])).date())
        for key,path in {'dispatch':f'days/{date}.csv','audit':f'audit/{date}.json','information':f'information/{date}.json'}.items():
            p=new/'main'/path
            if p.read_bytes()!=(old/'main'/path).read_bytes() or hashlib.sha256(p.read_bytes()).hexdigest()!=row['hashes'][key]:raise ValueError('原日收据/字节不符')
        frames.append(pd.read_csv(new/f'main/days/{date}.csv',float_precision='round_trip'))
    validate_frame(pd.concat(frames,ignore_index=True),before)
    records=[]
    for p in sorted((old/'main/nodes').glob('*/*/latest.json')):
        date=p.parent.parent.name;hour=int(p.parent.name);day=(pd.Timestamp(date)-pd.Timestamp('2025-01-01')).days
        folder=old/'main/nodes'/date;scenes=construct(data,day,hour,before)
        saved=json.loads(p.read_text(encoding='utf-8'))['content'];terminal=saved['audit']['terminal']
        if hour:
            initial=float(pd.read_csv(folder/f'{hour-6:02d}/executed_block.csv',float_precision='round_trip').soc.iloc[-1])
            midnight=json.loads((folder/'00/latest.json').read_text(encoding='utf-8'))['content']['policy']['grid']
            reference=np.asarray(midnight)[hour*6:]
        else:
            prior=str((pd.Timestamp(date)-pd.Timedelta(days=1)).date())
            initial=float(pd.read_csv(old/f'main/days/{prior}.csv',float_precision='round_trip').soc.iloc[-1]) if day else E_INITIAL
            reference=None
        prices=data.prices[(hour*6+np.arange(144))%144];today=144-hour*6
        inputs=(scenes.load,scenes.pv,scenes.weights,prices,initial,reference,today,terminal,previous_net(data,day,hour),None,None,None)
        with patch.object(Config,'signature',return_value=original['signature']):old_request=request_digest(before,*inputs)
        policy,audit=load_snapshot(p,old_request)
        response=[replay(policy,n,initial) for n in scenes.net]
        cost=objective(policy,response,scenes.weights,prices,reference,today,terminal)
        if abs(cost-audit['objective'])>TOL or audit['lower_bound']>cost+TOL:raise ValueError('原节点政策/下界重算不符')
        if audit['reliable'] and cost-audit['lower_bound']>max(TOL,after.gap*abs(cost)):raise ValueError('原节点精度不符')
        request=request_digest(after,*inputs)
        save_snapshot(new/p.relative_to(old),request,policy,{**audit,'migrated_from_request_signature':old_request})
        records.append({'date':date,'hour':hour,'old_request':old_request,'new_request':request,'reliable':audit['reliable']})
    state['signature']=after.signature()
    state.setdefault('execution_history',[]).append({'source':str(old),'signature':original['signature'],'days':len(state['days'])})
    write_json(new/'main/state.json',state)
    cache_path=new/'main/terminal_cache.json';cache=json.loads(cache_path.read_text(encoding='utf-8'));content=cache['content']
    if cache['sha256']!=hashlib.sha256(json.dumps(content,sort_keys=True,allow_nan=False).encode()).hexdigest():raise ValueError('FD快照校验失败')
    content['signature']=hashlib.sha256((after.signature()+json.dumps(data.provenance,sort_keys=True)).encode()).hexdigest()
    write_json(cache_path,{'sha256':hashlib.sha256(json.dumps(content,sort_keys=True,allow_nan=False).encode()).hexdigest(),'content':content})
    report={'old_run':str(old),'old_signature':original['signature'],'new_signature':after.signature(),
        'days_byte_identical':len(state['days']),'node_records':records,'all_old_request_signatures_verified':True,'precision':after.gap,
        'solver_threads':threads,'all_committed_days_physics_verified':True,'FD_values_unchanged':True}
    write_json(new/'migration.json',report)
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--old',type=Path,required=True);parser.add_argument('--new',type=Path,required=True)
    parser.add_argument('--threads',type=int,default=4);args=parser.parse_args()
    result=migrate(args.old,args.new,args.threads)
    print(json.dumps({'days':result['days_byte_identical'],'nodes':len(result['node_records']),'signature':result['new_signature']}))
