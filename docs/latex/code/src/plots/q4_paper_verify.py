"""Q4图组的独立数据、几何与导出核验。"""
from pathlib import Path
import hashlib,json,xml.etree.ElementTree as ET
import numpy as np
import pandas as pd
from PIL import Image
from .q4_paper_data import ROOT,OUT,DATA,RUNS


def main():
    meta=json.loads((DATA/'provenance.json').read_text(encoding='utf-8'))
    for name,sha in meta['source_sha256'].items():assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==sha,name
    read=lambda name:pd.read_csv(DATA/name,float_precision='round_trip')
    max_balance=0.;max_soc=0.;originals={}
    for mode,path in RUNS.items():
        f=read('dispatch_'+mode+'.csv');raw=pd.read_csv(path/'dispatch.csv',float_precision='round_trip')
        pd.testing.assert_frame_equal(f[raw.columns],raw,check_exact=False,atol=1e-10,rtol=0)
        assert f.groupby('date').size().eq(144).all() and len(f)==334*144
        assert pd.to_datetime(f.timestamp).diff().dropna().eq(pd.Timedelta(minutes=10)).all()
        r=f.called+f.discharge+f.emergency-f.net_kwh-f.charge-f.spill;max_balance=max(max_balance,float(abs(r).max()))
        np.testing.assert_allclose(r,0,atol=1e-7,rtol=0)
        np.testing.assert_allclose(f.grid-f.called,f.unused,atol=1e-7,rtol=0)
        np.testing.assert_allclose(f.unused+f.spill,f.total_surplus,atol=1e-7,rtol=0)
        soc=f.soc-np.r_[6000,f.soc.to_numpy()[:-1]]-.9*f.charge+f.discharge/.9
        max_soc=max(max_soc,float(abs(soc).max()));np.testing.assert_allclose(soc,0,atol=1e-7,rtol=0)
        assert f.soc.between(1200-1e-6,10800+1e-6).all() and (f.charge+f.discharge<=5000/6+1e-6).all()
        np.testing.assert_allclose(f.charge,f.charge_plan,atol=1e-7,rtol=0);np.testing.assert_allclose(f.discharge,f.discharge_plan,atol=1e-7,rtol=0)
        delta=f.grid-f.g0;cost=f.price*(f.g0+1.5*delta.clip(lower=0)+.5*delta.clip(upper=0)+5*f.emergency)
        np.testing.assert_allclose(f.total_cost,cost,atol=1e-7,rtol=0)
        originals[mode]=f
    f=originals['4-2'];clock=read('price_clock.csv')
    actual=f.price.to_numpy().reshape(334,24,6).mean(axis=2);pred=f.price_forecast.to_numpy().reshape(334,24,6).mean(axis=2)
    np.testing.assert_allclose(clock.actual_median,np.median(actual,axis=0),atol=1e-12,rtol=0)
    np.testing.assert_allclose(clock.actual_p10,np.quantile(actual,.1,axis=0),atol=1e-12,rtol=0)
    np.testing.assert_allclose(clock.actual_p90,np.quantile(actual,.9,axis=0),atol=1e-12,rtol=0)
    np.testing.assert_allclose(clock.forecast_median,np.median(pred,axis=0),atol=1e-12,rtol=0)
    limit=max(f.price.max(),f.price_forecast.max())*1.025
    density,xe,ye=np.histogram2d(f.price_forecast,f.price,bins=65,range=[[0,limit],[0,limit]])
    assert density.sum()==48096
    flow=read('energy_flow.csv');summaries=read('strategy_summary.csv').set_index('mode')
    for mode in RUNS:
        g=flow[flow['mode']==mode];np.testing.assert_allclose(g[g.side=='input'].kwh.sum(),g[g.side=='output'].kwh.sum(),atol=1e-6,rtol=0)
        np.testing.assert_allclose(summaries.loc[mode,'called']+summaries.loc[mode,'unused'],summaries.loc[mode,'grid'],atol=1e-6,rtol=0)
    delta=summaries.loc['4-3']-summaries.loc['4-2'];np.testing.assert_allclose(delta[['planned_cost','adjustment_cost','emergency_cost']].sum(),delta.total_cost,atol=1e-7,rtol=0)
    pairs=read('daily_cost_pairs.csv');np.testing.assert_allclose(pairs.saving_yuan.sum(),-delta.total_cost,atol=1e-7,rtol=0)
    s=read('local_sensitivity.csv');rho=s[s.parameter=='rho'];assert len(rho)==18 and rho.all_optimal.all()
    for (mode,day),g in rho.groupby(['mode','date']):
        assert set(g.setting)=={.75,1,1.25};b=g[g.setting==1].iloc[0]
        np.testing.assert_allclose(g.delta_cost_pct,(g.total_cost/b.total_cost-1)*100,atol=1e-9,rtol=0)
        np.testing.assert_allclose(g.delta_emergency_kwh,g.emergency_kwh-b.emergency_kwh,atol=1e-9,rtol=0)
    rows=[]
    for r in json.loads((OUT/'manifest.json').read_text(encoding='utf-8')):
        with Image.open(OUT/r['png']) as im:
            assert im.format=='PNG' and all(abs(x-400)<.1 for x in im.info['dpi'])
            assert np.max(abs(np.array(im.size)-np.array([r['width_inches'],r['height_inches']])*400))<1.1
            shape=im.size
        xml=ET.parse(OUT/r['svg']);assert not xml.findall('.//{http://www.w3.org/2000/svg}text')
        rows.append({'name':r['name'],'pixels':shape,'dpi':400,'svg_glyph_paths':True})
    assert len(rows)==6
    log=(ROOT/'docs/plots/q4_paper_final/render.log').read_text(encoding='utf-8').lower()
    assert not any(term in log for term in ['warning','glyph','dummy','traceback'])
    result={'status':'passed','source_hashes':len(meta['source_sha256']),'formal_days_each':334,'slots_each':48096,
        'optimal_nodes':1670,'density_included_samples':int(density.sum()),'radius_records':18,'max_balance_residual':max_balance,
        'max_soc_residual':max_soc,'total_cost_delta_q43_minus_q42':float(delta.total_cost),'figures':rows,
        'all_source_files_unchanged':True,'caveats':'Two complete policies, different horizons and inventory paths; not pure information value.'}
    (OUT/'verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print({k:v for k,v in result.items() if k!='figures'})


if __name__=='__main__':main()
