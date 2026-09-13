"""两问独立进程执行局部OFAT；结果收据可恢复，基准从不重算。"""
import argparse,json,os,subprocess,sys,time,traceback,hashlib
from pathlib import Path
from .common import ROOT,RUN,write_json,file_hash,active,comparison


def design():
    reps=json.loads((RUN/'representatives.json').read_text())
    jobs=[]
    for question,parameters in [('q2',[('beta_R',(.8,1.2)),('rho_tail',(.1,.3))]),('q3',[('S',(10,28)),('lambda_E',(.8,1.2))])]:
        for parameter,values in parameters:
            for row in reps[question]:
                for value in values:
                    jobs.append({'id':f'{question}_{parameter}_{value}_{row["date"]}','question':question,'parameter':parameter,'value':value,'date':row['date'],'role':row['role'],'status':'pending'})
    return jobs


def signature(job):
    payload={k:job[k] for k in ('id','question','parameter','value','date')}
    inputs=RUN/'inputs'/job['question']/job['date']
    payload['inputs']={p.name:file_hash(p) for p in sorted(inputs.glob('*')) if p.is_file()}
    paths=[ROOT/'src/sensitivity'/name for name in ('common.py','q2.py','q3.py','run.py')]+[ROOT/'src'/job['question']/name for name in
            (['rolling.py','scenarios.py','policy.py','optimization.py','relaxation.py','incumbent.py','linear_policy.py','protocol.py'] if job['question']=='q2' else
             ['rolling.py','scenarios.py','physics.py','optimization.py','incumbent.py','fast_solver.py','config.py','checkpoint.py'])]
    import importlib.metadata
    payload['runtime_versions']={name:importlib.metadata.version(name) for name in ('numpy','scipy','pandas','pyscipopt','highspy')}
    payload['sources']={str(p.relative_to(ROOT)):file_hash(p) for p in paths if not p.name.startswith('test_')}
    return hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()


def worker(question,limit=None,optional=False):
    from . import q2,q3
    module=q2 if question=='q2' else q3
    jobs=design() if not optional else optional_jobs()
    jobs=[j for j in jobs if j['question']==question]
    data=q3.inputs() if question=='q3' else None
    performed=0
    for job in jobs:
        folder=RUN/'jobs'/job['id'];folder.mkdir(parents=True,exist_ok=True);receipt=folder/'result.json';sig=signature(job)
        if receipt.exists():
            prior=json.loads(receipt.read_text())
            if prior['signature']!=sig:raise ValueError('已有实验源码或冻结输入变化，禁止混用结果')
            continue
        if limit is not None and performed>=limit:break
        job['started_at']=time.time();write_json(folder/'request.json',{**job,'signature':sig})
        try:
            result,baseline=module.run(job,folder,**({'data':data} if question=='q3' else {}))
            status='complete' if result['reliable'] else 'limited'
            record={**job,**result,**comparison(result,baseline),'baseline':baseline,'status':status,
                    'status_label':'完成 / 已认证' if status=='complete' else '限时可行 / 未认证','signature':sig,
                    'dispatch_sha256':file_hash(folder/'dispatch.csv'),'audit_sha256':file_hash(folder/'audit.json')}
        except Exception as error:
            record={**job,'status':'failed','status_label':'失败，已保留诊断','signature':sig,'seconds':time.time()-job['started_at'],
                    'error':str(error),'traceback':traceback.format_exc(),'details':getattr(error,'audit',getattr(error,'details',None))}
        write_json(receipt,record);print(f"{job['id']} {record['status']} {record.get('seconds',0):.2f}s",flush=True);performed+=1
    active(question,jobs[-1],'本轮队列完成',hour=None,detail='已完成记录均已原子保存，基准结果未修改')


def optional_jobs():
    reps=json.loads((RUN/'representatives.json').read_text())['q3']
    return [{'id':f'q3_S_tail_{value}_{row["date"]}','question':'q3','parameter':'S_tail','value':value,'date':row['date'],'role':row['role'],'status':'pending','optional':True} for row in reps for value in (0,4)]


def snapshot(jobs,phase,started,notes):
    records=[]
    for job in jobs:
        folder=RUN/'jobs'/job['id'];receipt=folder/'result.json';request=folder/'request.json'
        if receipt.exists():records.append(json.loads(receipt.read_text()))
        elif request.exists():records.append({**job,'status':'running','status_label':'计算中'})
        else:records.append(job)
    write_json(RUN/'status.json',{'phase':phase,'total_jobs':len(jobs),'jobs':records,'notes':notes,'started_at':started})
    return records


def launch(question,optional=False):
    args=[sys.executable,'-u','-m','src.sensitivity.run','--worker',question]+(['--optional'] if optional else [])
    stream=(RUN/f'{question}{"_optional" if optional else ""}_worker.log').open('ab')
    process=subprocess.Popen(args,cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT,env=dict(os.environ,OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',VECLIB_MAXIMUM_THREADS='1',MKL_NUM_THREADS='1',PYTHONUTF8='1'))
    stream.close();return process


def supervise():
    started=time.time();jobs=design();notes=['Q2固定正式K=3、S=26；Q3采用已确认的10/20/28，同一历史条件池。','基准直接复用；Q3沿用3%优先及35/8秒限时策略，未认证解会明确标记。']
    processes=[launch('q2'),launch('q3')]
    write_json(RUN/'launch.json',{'supervisor_pid':os.getpid(),'workers':[p.pid for p in processes],'started_at':started,'python':sys.executable})
    while any(p.poll() is None for p in processes):snapshot(jobs,'核心32项实验计算中',started,notes);time.sleep(2)
    records=snapshot(jobs,'核心实验计算结束，正在核验',started,notes)
    missing=[r for r in records if r['status'] in ('pending','running')]
    if missing:raise RuntimeError(f'工作进程提前退出，{len(missing)}项无结果，检查worker.log')
    core_seconds=time.time()-started
    # 在计算前声明可选门槛：核心<=1h、无失败且18:00前仍有20min以上。
    from datetime import datetime
    now=datetime.now();remaining=(now.replace(hour=18,minute=0,second=0,microsecond=0)-now).total_seconds()
    optional=core_seconds<=3600 and remaining>=1200 and all(r['status']!='failed' for r in records)
    write_json(RUN/'optional_decision.json',{'q2_S3':'not_applicable_formal_S26_not_S20','q3_S3_run':optional,'core_seconds':core_seconds,'seconds_to_18':remaining,'rule':'core<=3600s, no failed jobs, remaining>=1200s'})
    if optional:
        jobs+=optional_jobs();notes.append('核心实验及时完成，按方案执行可选Q3尾部名额0/2/4；Q2可选场景数因正式S非20不适用。')
        process=launch('q3',True)
        while process.poll() is None:snapshot(jobs,'核心已完成，Q3可选尾部名额实验计算中',started,notes);time.sleep(2)
    records=snapshot(jobs,'计算结束，生成汇总与验收报告',started,notes)
    from .report import generate
    generate(records)
    snapshot(jobs,'全部实验与汇总已完成' if all(r['status']!='failed' for r in records) else '实验结束，存在失败项，详见报告',started,notes)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--worker',choices=['q2','q3']);parser.add_argument('--limit',type=int);parser.add_argument('--optional',action='store_true');args=parser.parse_args()
    if args.worker:worker(args.worker,args.limit,args.optional)
    else:supervise()
