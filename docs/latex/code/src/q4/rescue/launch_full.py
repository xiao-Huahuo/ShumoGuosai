"""仅启动已通过测试的v2全量运行；新目录，独立日志，保留依赖与源码快照。"""
from pathlib import Path
import subprocess,os,json,hashlib,shutil,sys,shlex
root=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(root))
from src.q4.config import Config,production_sources,SOURCE,MODEL_VERSION
cfg=Config();saved=root/'docs/4/rescue_lp/frozen_source_v2'
if 'OK' not in (root/'docs/4/rescue_lp/tests_all_v2.txt').read_text(encoding='utf-8').splitlines()[-1]:
    raise RuntimeError('Tests must finish successfully')
manifest={}
for p in production_sources()+[SOURCE]:
    if p.name.startswith('test_'):continue
    relative=p.relative_to(root);dest=saved/relative;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dest)
    manifest[str(relative)]=hashlib.sha256(p.read_bytes()).hexdigest()
(saved/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
req=subprocess.check_output(['uv','pip','freeze','--python',str(root/'.venv/bin/python')],text=True)
(saved/'requirements.txt').write_text(req,encoding='utf-8')
processes={}
for command in ['q42','q43']:
    out=root/f'outputs/q4/raw/rescue_lp_{command}_20260913_v2';out.mkdir(parents=True,exist_ok=True)
    if (out/'state.json').exists():raise RuntimeError('Fresh directory required')
    args=[str(root/'.venv/bin/python'),'-u','-m','src.q4.run',command,'--output',str(out)]
    env=dict(os.environ,OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',VECLIB_MAXIMUM_THREADS='1',MKL_NUM_THREADS='1',PYTHONUTF8='1')
    with (out/'run.log').open('ab') as stream:
        p=subprocess.Popen(args,cwd=root,env=env,stdout=stream,stderr=subprocess.STDOUT,start_new_session=True)
    metadata={'pid':p.pid,'command':args,'signature':cfg.signature(),'model_version':MODEL_VERSION,'python':sys.version,'frozen_sources':str(saved)}
    (out/'launch.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding='utf-8')
    resume='#!/bin/zsh\nset -e\ncd '+shlex.quote(str(root))+'\nexport OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONUTF8=1\nexec '+shlex.join(args)+'\n'
    (out/'resume.sh').write_text(resume,encoding='utf-8');(out/'resume.sh').chmod(0o755)
    processes[command]=metadata
print(json.dumps(processes,ensure_ascii=False,indent=2))
(root/'docs/4/rescue_lp/launches_v2.json').write_text(json.dumps(processes,ensure_ascii=False,indent=2),encoding='utf-8')
