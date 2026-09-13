"""把已停止的严格运行迁移为限时可行 production rescue；旧目录始终保留。"""
import argparse
from dataclasses import asdict,replace
import hashlib
import json
from pathlib import Path
import shutil
import shlex
from unittest.mock import patch
import numpy as np
import pandas as pd
from .config import ROOT,CODE_ROOT,Config,E_INITIAL,TOL,write_json,validate_production_rescue
from .checkpoint import request_digest,load_snapshot,save_snapshot
from .data import read_inputs
from .scenarios import construct
from .physics import replay
from .optimization import objective,accept_feasible_incumbent
from .rolling import previous_net,validate_frame
from .status_server import worker_alive


def migrate(old: Path,new: Path,hard_06: float,hard_other: float) -> dict:
    old=old.resolve();new=new.resolve();progress=json.loads((old/'progress.json').read_text(encoding='utf-8'))
    if worker_alive(progress.get('worker_pid'),old):raise RuntimeError('旧主仍在运行，拒绝复制活动现场')
    if new.exists():raise FileExistsError(new)
    original=json.loads((old/'execution.json').read_text(encoding='utf-8'));values=dict(original['config'])
    values['nodes']=tuple(values['nodes']);values.setdefault('solver_backend','highs');values.setdefault('formulation','legacy')
    values.setdefault('solver_focus','default');values.setdefault('production_rescue',False)
    values.setdefault('hard_06_seconds',hard_06);values.setdefault('hard_other_seconds',hard_other)
    before=Config(**values);after=replace(before,solver_threads=4,solver_backend='highs',formulation='legacy',
        solver_focus='default',production_rescue=True,hard_06_seconds=hard_06,hard_other_seconds=hard_other)
    validate_production_rescue(after)
    frozen=json.loads((old/'runtime_sources.json').read_text(encoding='utf-8'))
    for name,digest in frozen['files'].items():
        if hashlib.sha256((old/'runtime/src/q3'/name).read_bytes()).hexdigest()!=digest:
            raise ValueError(f'旧冻结源码摘要不符：{name}')
    requirements=(old/'runtime/requirements.txt').read_bytes()
    if hashlib.sha256(requirements).hexdigest()!=frozen['requirements_sha256'] or b'highspy==1.15.1' not in requirements:
        raise ValueError('旧冻结依赖摘要或HiGHS版本不符')
    runtime=new/'runtime/src/q3';runtime.mkdir(parents=True)
    for source in CODE_ROOT.glob('*.py'):
        if not source.name.startswith('test_'):shutil.copy2(source,runtime/source.name)
    (new/'runtime/src/__init__.py').write_text('',encoding='utf-8')
    (new/'runtime/requirements.txt').write_bytes(requirements)
    manifest={path.name:hashlib.sha256(path.read_bytes()).hexdigest() for path in runtime.glob('*.py')}
    signature_payload=(ROOT/'docs/3/Q3_第三问_最终建模_严格修订终稿_v4.md').read_bytes()
    signature_payload+=json.dumps(asdict(after),sort_keys=True).encode()
    for path in sorted(runtime.glob('*.py')):
        signature_payload+=path.name.encode()+path.read_bytes()
    frozen_signature=hashlib.sha256(signature_payload).hexdigest()
    if frozen_signature!=after.signature():raise ValueError('复制期间源码变化，冻结runtime签名不一致')
    write_json(new/'runtime_sources.json',{'files':manifest,
        'requirements_sha256':hashlib.sha256(requirements).hexdigest(),'previous_run':str(old),
        'workspace':str(ROOT),'solver':'HiGHS 1.15.1','formulation':'legacy fast exact-equivalent',
        'production_rescue':True,'config_signature':frozen_signature})
    shutil.copytree(old/'main',new/'main')
    for legacy_slice in (new/'main/nodes').glob('*/*/slice_*.json'):legacy_slice.unlink()
    data=read_inputs(Path(original['q2_run']),new/'migration_prepared')
    state=json.loads((new/'main/state.json').read_text(encoding='utf-8'))
    sources=hashlib.sha256(json.dumps(data.provenance,sort_keys=True).encode()).hexdigest()
    if sources!=state['sources']:raise ValueError('原始数据或Q2来源变化')
    if len(state.get('days',[]))!=25 or state.get('with_fiv') is not False:
        raise ValueError('只接受已核实的25日main-only前缀')
    frames=[]
    for receipt in state['days']:
        date=str((pd.Timestamp('2025-01-01')+pd.Timedelta(days=receipt['day'])).date())
        files={'dispatch':f'days/{date}.csv','audit':f'audit/{date}.json','information':f'information/{date}.json'}
        for key,relative in files.items():
            copied=new/'main'/relative;source=old/'main'/relative
            if copied.read_bytes()!=source.read_bytes() or hashlib.sha256(copied.read_bytes()).hexdigest()!=receipt['hashes'][key]:
                raise ValueError(f'已提交日期字节或收据不符：{date}/{key}')
        frames.append(pd.read_csv(new/f'main/days/{date}.csv',float_precision='round_trip'))
    validate_frame(pd.concat(frames,ignore_index=True),before)
    if abs(float(frames[-1].soc.iloc[-1])-float(state['soc']))>TOL:raise ValueError('state SOC与Jan25日末不符')
    records=[];rescued=[]
    for source_path in sorted((old/'main/nodes').glob('*/*/latest.json')):
        date=source_path.parent.parent.name;hour=int(source_path.parent.name)
        day=(pd.Timestamp(date)-pd.Timestamp('2025-01-01')).days;folder=old/'main/nodes'/date
        scenes=construct(data,day,hour,before);saved=json.loads(source_path.read_text(encoding='utf-8'))['content']
        terminal=float(saved['audit']['terminal'])
        if hour:
            initial=float(pd.read_csv(folder/f'{hour-6:02d}/executed_block.csv',float_precision='round_trip').soc.iloc[-1])
            midnight=json.loads((folder/'00/latest.json').read_text(encoding='utf-8'))['content']['policy']['grid']
            reference=np.asarray(midnight,dtype=float)[hour*6:]
        else:
            prior=str((pd.Timestamp(date)-pd.Timedelta(days=1)).date())
            initial=float(pd.read_csv(old/f'main/days/{prior}.csv',float_precision='round_trip').soc.iloc[-1]) if day else E_INITIAL
            reference=None
        prices=data.prices[(hour*6+np.arange(144))%144];today=144-hour*6
        inputs=(scenes.load,scenes.pv,scenes.weights,prices,initial,reference,today,terminal,
                previous_net(data,day,hour),None,None,None)
        with patch.object(Config,'signature',return_value=original['signature']):old_request=request_digest(before,*inputs)
        policy,audit=load_snapshot(source_path,old_request)
        responses=[replay(policy,path,initial) for path in scenes.net]
        value=objective(policy,responses,scenes.weights,prices,reference,today,terminal)
        lower=audit.get('lower_bound')
        if abs(value-audit['objective'])>TOL or (lower is not None and lower>value+TOL):
            raise ValueError(f'旧节点重算失败：{date}/{hour:02d}')
        if audit.get('reliable'):
            if value-float(lower)>max(TOL,before.gap*abs(value)):raise ValueError('旧3%证书不符')
            migrated={**audit,'upper_bound':value,'accepted':True,'certificate_met':True,'accepted_by':'certified_3pct',
                'migrated_from_request_signature':old_request,'migration_replay_validated':True}
        else:
            hard=hard_06 if hour==6 else hard_other
            accepted=accept_feasible_incumbent(policy,scenes,prices,initial,after,reference=reference,
                today=today,terminal=terminal,previous_net=previous_net(data,day,hour),audit=audit,
                hard_seconds=hard,source='saved_incumbent_migrated_at_rescue_start')
            migrated={**accepted.audit,'migrated_from_request_signature':old_request,
                      'legacy_elapsed_before_rescue':audit.get('seconds'),'hard_limit_reached':False,
                      'accepted_from_preexisting_checkpoint':True,
                      'lower_bound_origin':'preexisting_HiGHS_1.15.1_same_legacy_matrix'}
            rescued.append({'date':date,'hour':hour,'upper_bound':migrated['upper_bound'],
                'lower_bound':migrated['lower_bound'],'gap':migrated['gap'],'objective':migrated['objective']})
        new_request=request_digest(after,*inputs);save_snapshot(new/source_path.relative_to(old),new_request,policy,migrated)
        records.append({'date':date,'hour':hour,'old_request':old_request,'new_request':new_request,
                        'accepted_by':migrated['accepted_by']})
    if [(row['date'],row['hour']) for row in rescued]!=[('2025-01-26',6)]:
        raise ValueError(f'未可靠节点集合不是唯一Jan26/06：{rescued}')
    state['signature']=after.signature();state.setdefault('execution_history',[]).append(
        {'source':str(old),'signature':original['signature'],'days':len(state['days']),'mode':'production_rescue'})
    write_json(new/'main/state.json',state)
    cache_path=new/'main/terminal_cache.json';wrapper=json.loads(cache_path.read_text(encoding='utf-8'));content=wrapper['content']
    payload=json.dumps(content,sort_keys=True,allow_nan=False).encode()
    if wrapper['sha256']!=hashlib.sha256(payload).hexdigest():raise ValueError('FD缓存摘要不符')
    expected_old=hashlib.sha256((original['signature']+json.dumps(data.provenance,sort_keys=True)).encode()).hexdigest()
    if content.get('signature')!=expected_old:raise ValueError('FD缓存与旧运行签名不符')
    rows_digest=hashlib.sha256(json.dumps(content['rows'],sort_keys=True,allow_nan=False).encode()).hexdigest()
    calibration_path=new/'main/terminal_calibration.csv';calibration_sha=hashlib.sha256(calibration_path.read_bytes()).hexdigest()
    calibration=pd.read_csv(calibration_path,float_precision='round_trip')
    cache_keys={(int(row['history_day']),int(row['hour']),float(row['delta'])):row for row in content['rows']}
    for row in calibration.to_dict('records'):
        key=(int(row['history_day']),int(row['hour']),float(row['delta']))
        if key not in cache_keys or abs(float(row['value'])-float(cache_keys[key]['value']))>TOL:
            raise ValueError('CSV终端标定不是durable JSON缓存子集')
    content['signature']=hashlib.sha256((after.signature()+json.dumps(data.provenance,sort_keys=True)).encode()).hexdigest()
    payload=json.dumps(content,sort_keys=True,allow_nan=False).encode();write_json(cache_path,{'sha256':hashlib.sha256(payload).hexdigest(),'content':content})
    uv=shutil.which('uv') or '/opt/homebrew/bin/uv'
    command=[uv,'run','--offline','--with-requirements',str(new/'runtime/requirements.txt'),'python','-m','src.q3.full_run',
        '--run-dir',str(new),'--q2-run',str(Path(original['q2_run'])),'--gap','.03','--seconds','120',
        '--workers','2','--solver-threads','4','--solver-backend','highs','--formulation','legacy',
        '--solver-focus','default','--production-rescue','--hard-06-seconds','35','--hard-other-seconds','8','--main-only']
    resume='#!/bin/sh\nset -eu\ncd '+shlex.quote(str(new/'runtime'))+'\nexport Q3_WORKSPACE_ROOT='+shlex.quote(str(ROOT))+'\nexport OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 NUMEXPR_NUM_THREADS=1\nexec '+shlex.join(command)+'\n'
    (new/'resume.sh').write_text(resume,encoding='utf-8');(new/'resume.sh').chmod(0o755)
    report={'old_run':str(old),'new_run':str(new),'old_signature':original['signature'],'new_signature':after.signature(),
        'days_byte_identical':len(state['days']),'nodes_revalidated':len(records),'rescued_unfinished_nodes':rescued,
        'hard_06_seconds':hard_06,'hard_other_seconds':hard_other,'solver':'HiGHS 1.15.1','threads':4,
        'formulation':'legacy fast exact-equivalent','model_parameters_unchanged':True,'legacy_slices_copied':False,
        'old_directory_preserved':True,'FD_rows':len(content['rows']),'FD_rows_sha256':rows_digest,
        'terminal_calibration_rows':len(calibration),'terminal_calibration_sha256':calibration_sha,
        'terminal_calibration_is_cache_subset':True,'resume_command':command,'records':records}
    write_json(new/'migration.json',report);return report


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--old',type=Path,required=True);parser.add_argument('--new',type=Path,required=True)
    parser.add_argument('--hard-06',type=float,default=35.);parser.add_argument('--hard-other',type=float,default=8.)
    args=parser.parse_args();result=migrate(args.old,args.new,args.hard_06,args.hard_other)
    print(json.dumps({'days':result['days_byte_identical'],'nodes':result['nodes_revalidated'],
                      'rescued':result['rescued_unfinished_nodes'],'signature':result['new_signature']}))
