"""交付前独立复核：统计配对、结算、库存、原件哈希与图文件。"""
from pathlib import Path
import hashlib
import json
import xml.etree.ElementTree as ET
import numpy as np
import pandas as pd
from PIL import Image
from .q3_paper_data import ROOT,OUT,DATA


def check():
    read=lambda name:pd.read_csv(DATA/name,float_precision='round_trip')
    p=json.loads((DATA/'provenance.json').read_text(encoding='utf-8'))
    for name,digest in p['source_sha256'].items():
        assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==digest,name
    f=read('forecast_pairs.csv');m=read('forecast_metrics.csv');r=read('revision_pairs.csv')
    assert f.groupby(['date','issue_hour']).size().eq(24).all() and f.date.nunique()==333
    assert not f.duplicated(['issue','target']).any()
    for row in m.itertuples():
        s=f[(f.issue_hour==row.issue_hour)&(f.horizon_hours==row.horizon_hours)]
        e=(s.forecast_kw-s.actual_kw).to_numpy()
        np.testing.assert_allclose([abs(e).mean(),np.sqrt((e*e).mean()),e.mean()],[row.MAE,row.RMSE,row.Bias],atol=1e-10,rtol=0)
    old=f[['issue','target','forecast_kw']].copy();old['issue']=(pd.to_datetime(old.issue)+pd.Timedelta(hours=6)).astype(str)
    pair=r.merge(old,on=['issue','target'],suffixes=('','_previous'),validate='one_to_one')
    np.testing.assert_allclose(pair.old_forecast_kw,pair.forecast_kw_previous,atol=0,rtol=0)
    assert r.groupby('issue_hour').size().eq(1998).all()
    d=read('formal_dispatch.csv');source=pd.read_csv(ROOT/'outputs/q3/raw/full_priority_rescue_7h_20260912/main/dispatch.csv',float_precision='round_trip')
    pd.testing.assert_frame_equal(d[source.columns],source,check_exact=False,atol=1e-10,rtol=0)
    dg=d.grid-d.g0;adjust=d.price*(1.5*dg.clip(lower=0)+.5*dg.clip(upper=0))
    np.testing.assert_allclose(d.adjustment_cost,adjust,atol=1e-8,rtol=0)
    balance=d.grid+d.discharge+d.emergency-d.net_kwh-d.charge-d.spill
    np.testing.assert_allclose(balance,0,atol=1e-8,rtol=0)
    for date,s in d.groupby('date'):
        e=np.r_[s.initial_soc.iloc[0],s.soc]
        np.testing.assert_allclose(np.diff(e),.9*s.charge-s.discharge/.9,atol=1e-8,rtol=0)
        assert (e>=1200-1e-6).all() and (e<=10800+1e-6).all()
        assert np.array_equal(s.slot,np.arange(144))
    daily=read('formal_daily.csv');np.testing.assert_allclose(daily.soc_start.iloc[1:],daily.soc_end.iloc[:-1],atol=1e-8,rtol=0)
    costs=['planned_cost','adjustment_cost','emergency_cost','total_cost']
    np.testing.assert_allclose(d.groupby('date')[costs].sum(),daily[costs],atol=1e-6,rtol=0)
    baseline=daily.set_index('date')
    sensitivity=read('local_sensitivity.csv')
    for s in sensitivity.itertuples():
        expected=(s.total_cost/baseline.loc[s.date,'total_cost']-1)*100
        np.testing.assert_allclose(s.delta_cost_pct,expected,atol=1e-9,rtol=0)
    typical=read('typical_dispatch.csv');c=read('typical_candidates.csv');scale=read('typical_selection_scale.csv').set_index('feature')
    values=c[scale.index].to_numpy();dist=np.sqrt((((values-scale.formal_median.to_numpy())/scale.formal_IQR.to_numpy())**2).sum(axis=1))
    np.testing.assert_allclose(c.median_state_distance,dist,atol=1e-10,rtol=0)
    assert typical.date.nunique()==1 and typical.date.iloc[0]==c.date.iloc[dist.argmin()]
    tf=read('typical_forecasts_active.csv');assert tf.groupby('issue_hour').size().eq(6).all()
    assert ((tf.target_hour>tf.issue_hour)&(tf.target_hour<=tf.issue_hour+6)).all()
    quality=read('formal_solver_quality.csv');assert len(quality)==1336 and quality.reliable.sum()==847
    images=[]
    manifests=[(OUT/'manifest.json',None),(OUT/'core/manifest.json',None)]
    for path,_ in manifests:
        for item in json.loads(path.read_text(encoding='utf-8')):
            image_path=path.parent/item['png'];svg=path.parent/item['svg']
            with Image.open(image_path) as im:
                assert im.format=='PNG' and all(abs(x-400)<.05 for x in im.info['dpi'])
                expected=np.array([item['width_inches'],item['height_inches']])*400
                assert np.max(abs(np.asarray(im.size)-expected))<=1.01
                size=im.size
            xml=ET.parse(svg);assert not xml.findall('.//{http://www.w3.org/2000/svg}text')
            images.append({'name':item['name'],'pixels':size,'dpi':400,'svg_text':'glyph paths'})
    for name in ['core_render.log','extended_render.log']:
        log=(ROOT/'docs/plots/q3_paper_final'/name).read_text(encoding='utf-8')
        assert all(x not in log.lower() for x in ['glyph','warning','dummy','traceback'])
    report={'status':'passed','source_hashes_verified':len(p['source_sha256']),'forecast_cells':96,'paired_days':333,
        'formal_days':334,'formal_slots':len(d),'formal_nodes':1336,'certified_nodes':847,'limited_nodes':489,
        'typical_date':typical.date.iloc[0],'user_cancelled':'FIV/OUV图6-4；未运行新实验',
        'figures_rendered_and_checked':images,'max_energy_balance_residual':float(abs(balance).max()),
        'all_original_results_unchanged':True,'scope':'numerical/source/export verification; visual QA separately documented'}
    (OUT/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print({k:v for k,v in report.items() if k!='figures_rendered_and_checked'})


if __name__=='__main__':check()
