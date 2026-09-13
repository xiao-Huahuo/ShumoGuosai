"""本地实时看板；核对进程存活，不把旧progress.json当作运行证据。"""
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
import json
import shlex
import subprocess
import time
from urllib.parse import urlparse

ROOT=Path(__file__).resolve().parents[2]
WEB=ROOT/'outputs/processed/q3_monitor'
POINTER=ROOT/'outputs/q3/active_run.json'


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}


def worker_alive(pid: int | None, run: Path) -> bool:
    if not pid:return False
    result=subprocess.run(['ps','-p',str(pid),'-o','command='],capture_output=True,text=True,timeout=2)
    args=shlex.split(result.stdout.strip()) if result.returncode==0 else []
    return 'src.q3.full_run' in args and '--worker' in args and str(run) in args


def current() -> dict:
    pointer=read(POINTER)
    run=Path(pointer.get('run_directory',ROOT/'outputs/q3/raw/full_priority_20260912')).resolve()
    if not run.is_relative_to(ROOT/'outputs/q3/raw'):raise ValueError('非Q3运行路径')
    progress=read(run/'progress.json');state=read(run/'main/state.json');active=read(run/'main/active.json')
    date=active.get('date') or progress.get('active_date')
    candidates=list((run/'main/nodes'/date).glob('*/latest.json')) if date else []
    latest=max(candidates,key=lambda p:p.stat().st_mtime) if candidates else None
    audit=read(latest).get('content',{}).get('audit',{}) if latest else {}
    alive=worker_alive(progress.get('worker_pid'),run)
    cpu=None
    if alive:
        result=subprocess.run(['ps','-p',str(progress['worker_pid']),'-o','%cpu='],capture_output=True,text=True,timeout=2)
        if result.returncode==0 and result.stdout.strip():cpu=float(result.stdout.strip())
    ready=(run/'main_complete.json').exists()
    status='running' if alive else 'complete' if ready else pointer.get('transition','stopped')
    if status=='running' and not alive:status='stopped'
    saved=len(state.get('days',[]));formal=max(0,saved-31)
    log=''
    if (run/'worker.log').exists():
        with (run/'worker.log').open('rb') as f:
            f.seek(max(0,(run/'worker.log').stat().st_size-5000));log=f.read().decode('utf-8',errors='replace')
    val=read(ROOT/'outputs/q3/raw/validation_20260912/status.json')
    certificate=read(ROOT/'outputs/q3/raw/compute_rescue_20260912/jan14_06_strengthened.json')
    return {'status':status,'worker_alive':alive,'worker_pid':progress.get('worker_pid') if alive else None,
        'run_name':run.name,'formal_days':formal,'formal_total':334,'warm_days':min(saved,31),'warm_total':31,
        'active_date':date,'active_hour':latest.parent.name if latest else progress.get('active_hour'),
        'gap':audit.get('gap'),'target_gap':.03,'node_reliable':audit.get('reliable',False),
        'slices':audit.get('completed_slices',0),'node_seconds':audit.get('seconds'),
        'saved_ago_seconds':time.time()-latest.stat().st_mtime if latest else None,
        'soc':state.get('soc'),'solver':audit.get('solver',audit.get('solve_method','—')),
        'solver_threads':audit.get('solver_threads'),'solver_version':audit.get('solver_version'),'cpu_percent':cpu,
        'lower_bound':audit.get('lower_bound'),'objective':audit.get('objective'),
        'validation_phase':val.get('phase','未启动'),'validation_scope':val.get('scope','pending'),
        'rescue_certificate':{'seconds':certificate.get('seconds'),'gap':certificate.get('gap'),'passed':certificate.get('reliable')},
        'main_result_ready':ready,'log_lines':log.splitlines()[-12:],'observed_at':time.time()}


class Handler(SimpleHTTPRequestHandler):
    def __init__(self,*args,**kwargs):super().__init__(*args,directory=str(WEB),**kwargs)
    def log_message(self,format,*args):pass
    def do_GET(self):
        if urlparse(self.path).path=='/api/status':
            try:payload=json.dumps(current(),ensure_ascii=False,allow_nan=False).encode('utf-8');code=200
            except Exception as error:payload=json.dumps({'error':str(error)},ensure_ascii=False).encode('utf-8');code=503
            self.send_response(code);self.send_header('Content-Type','application/json; charset=utf-8')
            self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(payload)));self.end_headers();self.wfile.write(payload)
        else:super().do_GET()


if __name__=='__main__':ThreadingHTTPServer(('127.0.0.1',8764),Handler).serve_forever()
