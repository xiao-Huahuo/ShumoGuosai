from pathlib import Path
import subprocess,os,json,hashlib,shutil,sys,shlex
root=Path(__file__).resolve().parents[3];sys.path.insert(0,str(root))
from src.q4.config import Config,production_sources,SOURCE,MODEL_VERSION
assert (root/'docs/4/rescue_lp/apr18_verified.json').exists()
cfg=Config();saved=root/'docs/4/rescue_lp/frozen_source_v3';manifest={}
for p in production_sources()+[SOURCE]:
    if p.name.startswith('test_'):continue
    relative=p.relative_to(root);dest=saved/relative;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dest)
    manifest[str(relative)]=hashlib.sha256(p.read_bytes()).hexdigest()
(saved/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
shutil.copy2(root/'docs/4/rescue_lp/frozen_source_v2/requirements.txt',saved/'requirements.txt')
out=root/'outputs/q4/raw/rescue_lp_q43_20260913_v3';out.mkdir(parents=True,exist_ok=True)
assert not (out/'state.json').exists()
args=[str(root/'.venv/bin/python'),'-u','-m','src.q4.run','q43','--output',str(out)]
env=dict(os.environ,OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',VECLIB_MAXIMUM_THREADS='1',MKL_NUM_THREADS='1',PYTHONUTF8='1')
with (out/'run.log').open('ab') as stream:
    p=subprocess.Popen(args,cwd=root,env=env,stdout=stream,stderr=subprocess.STDOUT,start_new_session=True)
metadata={'pid':p.pid,'command':args,'signature':cfg.signature(),'model_version':MODEL_VERSION,'python':sys.version,'frozen_sources':str(saved)}
(out/'launch.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding='utf-8')
resume='#!/bin/zsh\nset -e\ncd '+shlex.quote(str(root))+'\nexport OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONUTF8=1\nexec '+shlex.join(args)+'\n'
(out/'resume.sh').write_text(resume,encoding='utf-8');(out/'resume.sh').chmod(0o755)
(root/'docs/4/rescue_lp/launch_q43_v3.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(metadata,ensure_ascii=False,indent=2))
