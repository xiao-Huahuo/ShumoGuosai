"""正式设置下3日Q42、2日Q43连续执行，验证后提供全年时间估计。"""
import time
import pandas as pd
from .config import ROOT, Config, write_csv, write_json
from .data import read_inputs
from .diagnostics import baseline_metrics, write_window_policy
from .rolling import run_period
from .export import export_workbook, write_tables


def main():
    folder=ROOT/'outputs/q4/raw/rescue_lp_vertical_20260913'
    data=read_inputs(ROOT/'inputs/q4/rescue_processed')
    config=Config()
    summary={}
    for mode,end in [('4-2',34),('4-3',33)]:
        started=time.perf_counter()
        output=folder/mode
        frame=run_period(data,mode,config,output,end=end)
        elapsed=time.perf_counter()-started
        write_tables(frame,output)
        workbook=export_workbook(frame,output,mode,config,smoke=True)
        daily_count=end-31
        summary[mode]=dict(days=daily_count,seconds=elapsed,estimated_full_seconds=elapsed/daily_count*334,
                           cost=float(frame.total_cost.sum()),emergency=float(frame.emergency.sum()),
                           charge=float(frame.charge.sum()),discharge=float(frame.discharge.sum()),
                           max_balance_error=float(abs(frame.called+frame.discharge+frame.emergency-frame.net_kwh-frame.charge-frame.spill).max()),
                           template=workbook)
        print(summary[mode],flush=True)
    summary['baseline']=baseline_metrics(data)
    write_window_policy(folder)
    write_json(folder/'vertical_summary.json',summary)
    print(summary,flush=True)


if __name__=='__main__':
    main()
