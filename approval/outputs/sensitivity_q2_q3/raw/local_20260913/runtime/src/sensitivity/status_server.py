"""敏感性实验只读进度服务，右侧页面从真实任务状态读取进度。"""
from http.server import ThreadingHTTPServer,SimpleHTTPRequestHandler
from pathlib import Path
import json,time
ROOT=Path(__file__).resolve().parents[2]
WEB=ROOT/'outputs/processed/sensitivity_q2_q3'
RUN=ROOT/'outputs/sensitivity_q2_q3/raw/local_20260913'
class Handler(SimpleHTTPRequestHandler):
    def __init__(self,*args,**kwargs):super().__init__(*args,directory=str(WEB),**kwargs)
    def log_message(self,*args):pass
    def do_GET(self):
        if self.path.split('?')[0]=='/api/status':
            state=json.loads((RUN/'status.json').read_text(encoding='utf-8'))
            state['observed_at']=time.time()
            reps=RUN/'representatives.json'
            if reps.exists():state['representatives']=json.loads(reps.read_text(encoding='utf-8'))
            state['workers']={}
            for name in ('q2','q3'):
                p=RUN/f'{name}_active.json'
                if p.exists():state['workers'][name]=json.loads(p.read_text(encoding='utf-8'))
            data=json.dumps(state,ensure_ascii=False,allow_nan=False).encode('utf-8')
            self.send_response(200);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
        else:super().do_GET()
if __name__=='__main__':ThreadingHTTPServer(('127.0.0.1',8766),Handler).serve_forever()
