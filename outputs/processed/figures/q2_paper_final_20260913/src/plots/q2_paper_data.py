"""Q2论文六图的数据层；保留原值、同预测起点和完整尾部。"""
from pathlib import Path
import json,hashlib
import numpy as np
import pandas as pd
from scipy.signal import correlate
from statsmodels.tsa.stattools import acf
ROOT=Path(__file__).resolve().parents[2]
RUN=ROOT/'outputs/q2/dispatch_runs/20260912_tail_reserve_final'
OUT=ROOT/'outputs/processed/figures/q2_paper_final_20260913'
DATA=OUT/'data'


def write(name,frame):frame.to_csv(DATA/name,index=False,encoding='utf-8',float_format='%.17g')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def prepare():
    DATA.mkdir(parents=True,exist_ok=True)
    source=RUN/'inputs/processed/timeseries.csv';raw=pd.read_csv(source,float_precision='round_trip')
    load=raw.load_kw.to_numpy().reshape(365,144);pv=raw.pv_kw.to_numpy().reshape(365,144)
    assert np.isfinite(load).all() and np.isfinite(pv).all()
    dates=pd.date_range('2025-01-01',periods=365);hours=np.arange(1,145)/6
    rows=[]
    for label,mask in [('周一至周五',dates.dayofweek<5),('周六及周日',dates.dayofweek>=5)]:
        values=load[mask];q=np.quantile(values,[.25,.75],axis=0)
        rows.extend({'group':label,'hour':h,'mean_kw':m,'p25_kw':lo,'p75_kw':hi,'n_days':len(values)} for h,m,lo,hi in zip(hours,values.mean(0),q[0],q[1]))
    write('fig51_weekday_profiles.csv',pd.DataFrame(rows))
    rows=[];mu=np.zeros_like(pv)
    for month in range(1,13):
        mask=dates.month==month;profile=pv[mask].mean(0);mu[mask]=profile
        if month in (1,4,7,10):rows.extend({'month':month,'hour':h,'mean_pv_kw':value,'n_days':int(mask.sum())} for h,value in zip(hours,profile))
    write('fig51_seasonal_pv.csv',pd.DataFrame(rows))
    # Pearson lag-correlation uses the paired subset's own mean, rather than biased ACF.
    y=load.ravel()-load.mean();n=len(y);lags=np.arange(1009);pairs=n-lags
    products=correlate(y,y,mode='full',method='fft')[n-1:n+1008]
    sums=np.r_[0,np.cumsum(y)];squares=np.r_[0,np.cumsum(y*y)]
    sa=sums[n]-sums[lags];sb=sums[n-lags]
    covariance=products-sa*sb/pairs
    variance_a=squares[n]-squares[lags]-sa*sa/pairs;variance_b=squares[n-lags]-sb*sb/pairs
    rho=covariance/np.sqrt(variance_a*variance_b)
    for lag in (1,144,288,1008):np.testing.assert_allclose(rho[lag],np.corrcoef(load.ravel()[lag:],load.ravel()[:-lag])[0,1],atol=1e-10,rtol=0)
    write('fig51_load_lag_correlation.csv',pd.DataFrame({'lag':lags,'rho':rho,'paired_samples':pairs}))
    residual=(pv-mu).ravel();auto,interval=acf(residual,nlags=288,fft=True,alpha=.05,bartlett_confint=True)
    write('fig51_pv_residual_acf.csv',pd.DataFrame({'lag':np.arange(289),'acf':auto,'reference_lower':interval[:,0]-auto,'reference_upper':interval[:,1]-auto}))
    write('fig51_pv_deseasonalized.csv',pd.DataFrame({'date':np.repeat(dates.strftime('%Y-%m-%d'),144),'hour':np.tile(hours,365),'pv_kw':pv.ravel(),'month_slot_mean_kw':mu.ravel(),'residual_kw':residual}))
    calibration_path=RUN/'processed/main/calibration.csv';cal=pd.read_csv(calibration_path,float_precision='round_trip')
    origins=sorted(origin for origin,g in cal.groupby('origin') if set(g.horizon)=={0,1,2})
    paired=cal[cal.origin.isin(origins)].copy()
    coverage=paired.groupby(['horizon','nominal'],as_index=False)[['covered_intervals','n']].sum();coverage['picp']=coverage.covered_intervals/coverage.n
    write('fig52_paired_coverage.csv',coverage)
    all_coverage=cal.groupby(['horizon','nominal'],as_index=False)[['covered_intervals','n']].sum();all_coverage['picp']=all_coverage.covered_intervals/all_coverage.n
    write('fig52_all_available_coverage.csv',all_coverage)
    shadow=RUN/'raw/shadows';shape=json.loads((shadow/'shape.json').read_text());store={};parts=[];audits=[]
    for origin in origins:
        day=(pd.Timestamp(origin)-dates[0]).days;assert day+2<365
        path=RUN/'processed/main/daily_audit'/f'{origin}.json';audit=json.loads(path.read_text());assert audit['selected_K']==3
        pair=audit['3']['selection']['pipeline'];audits.append(path)
        for name in pair:
            if name not in store:store[name]=np.memmap(shadow/f'{name}.dat',mode='r',dtype=shape['dtype'],shape=tuple(shape['shape']))
        for h in range(3):
            forecast=(store[pair[0]][day,h]-store[pair[1]][day,h])/6
            actual=(load[day+h]-pv[day+h])/6;error=actual-forecast
            assert np.isfinite(error).all()
            parts.append(pd.DataFrame({'origin':origin,'horizon':h,'slot':np.arange(1,145),'forecast_net_kwh':forecast,'actual_net_kwh':actual,'error_kwh':error}))
    errors=pd.concat(parts,ignore_index=True);write('fig52_paired_errors.csv',errors)
    assert len(errors)==len(origins)*3*144 and coverage.n.nunique()==1
    write('fig52_error_quantiles.csv',errors.groupby('horizon').error_kwh.quantile([0,.01,.05,.25,.5,.75,.95,.99,1]).rename('error_kwh').reset_index())
    dispatch_path=RUN/'processed/main/dispatch.csv';dispatch=pd.read_csv(dispatch_path,float_precision='round_trip')
    candidates=['2025-03-20','2025-06-21','2025-09-23','2025-12-21']
    sums=dispatch[dispatch.date.isin(candidates)].groupby('date').emergency.sum().sort_values(ascending=False,kind='stable')
    day=sums.index[0];frame=dispatch[dispatch.date==day].copy();assert len(frame)==144
    frame['hour_right']=np.arange(1,145)/6;frame['hour_center']=(np.arange(144)+.5)/6
    frame['Z_real_kwh']=np.maximum(frame.net_kwh,0);frame['Z_forecast_kwh']=np.maximum((frame.predicted_load_kw-frame.predicted_pv_kw)/6,0)
    write('fig54_real_dispatch.csv',frame)
    write('fig54_candidate_dates.csv',sums.rename('emergency_kwh').reset_index())
    energy=np.r_[frame.initial_soc.iloc[0],frame.soc.to_numpy()]
    np.testing.assert_allclose(np.diff(energy),.9*frame.charge-frame.discharge/.9,atol=1e-7,rtol=0)
    assert energy.min()>=1200-1e-5 and energy.max()<=10800+1e-5
    write('fig54_storage_145.csv',pd.DataFrame({'hour':np.arange(145)/6,'energy_kwh':energy}))
    np.savez(DATA/'figS1_annual_arrays.npz',load_kw=load,pv_kw=pv,net_kw=load-pv)
    sources=[source,calibration_path,dispatch_path,shadow/'shape.json']+[shadow/f'{name}.dat' for name in store]+audits
    audit={'formal_run':str(RUN),'paired_forecast_origins':origins,'paired_days':len(origins),'samples_per_horizon':len(origins)*144,
           'error_definition':'actual minus forecast, kWh per 10min; same-origin matched horizons',
           'PV_deseasonalization':'monthly x time-of-day mean removed; retrospective diagnostics only, never supplied to forecasts',
           'ACF_interval':'pointwise 95% Bartlett reference interval around zero; not simultaneous IID proof',
           'load_lag':'paired-subset Pearson correlation, independently checked at lags1/144/288/1008',
           'weekday_definition':'Monday-Friday vs Saturday-Sunday, not statutory-holiday classification',
           'quarter_band':'25th-75th percentile across calendar days, not confidence interval',
           'right_endpoint':'profiles begin00:10; axis00:00 is boundary, no invented sample',
           'pressure_date':day,'pressure_emergency_kwh':float(sums.iloc[0]),'Z_definition':'positive part of (load-PV)/6, before storage',
           'source_sha256':{str(p.relative_to(ROOT)):sha(p) for p in sources}}
    (DATA/'provenance.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
    print({'paired_days':len(origins),'samples_per_horizon':len(origins)*144,'pressure_date':day})
    print(errors.groupby('horizon').error_kwh.quantile([0,.25,.5,.75,1]).to_string())
    return audit


if __name__=='__main__':prepare()
