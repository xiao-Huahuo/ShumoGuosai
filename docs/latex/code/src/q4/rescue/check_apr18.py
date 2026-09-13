from pathlib import Path
import sys,json,time
root=Path(__file__).resolve().parents[3];sys.path.insert(0,str(root))
from src.q4.data import read_inputs
from src.q4.config import Config
from src.q4.rolling import run_day_q43
if __name__=='__main__':
    data=read_inputs(root/'inputs/q4/rescue_processed')
    state=json.loads((root/'outputs/q4/raw/rescue_lp_q43_20260913_v2/state.json').read_text())
    started=time.perf_counter();frame,audit=run_day_q43(data,107,state['soc'],Config())
    result={'seconds':time.perf_counter()-started,'nodes':[n['solver'] for n in audit['nodes']], 'day_total_cost':float(frame.total_cost.sum())}
    assert all(n['reliable'] for n in result['nodes'])
    assert result['nodes'][-1]['matrix_digest']=='a87d00484bf5057d0e3595ed2dff1b1aa7998d3725df158f238249c09431648d'
    (root/'docs/4/rescue_lp/apr18_verified.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Apr18 four nodes all Optimal; same failed-node matrix; seconds',result['seconds'])
