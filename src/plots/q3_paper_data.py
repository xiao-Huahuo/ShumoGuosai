"""Q3论文图只读数据层：共同预报支持、正式执行、局部敏感性。"""
from pathlib import Path
import hashlib
import json
import numpy as np
import pandas as pd
from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parents[2]
RUN = ROOT/'outputs/q3/raw/full_priority_rescue_7h_20260912'
OUT = ROOT/'outputs/processed/figures/q3_paper_final_20260913'
DATA = OUT/'data'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(name, frame):
    frame.to_csv(DATA/name, index=False, encoding='utf-8', float_format='%.17g')


def prepare():
    DATA.mkdir(parents=True, exist_ok=True)
    actual_path = ROOT/'outputs/q2/dispatch_runs/20260911_224501/inputs/processed/timeseries.csv'
    forecast_path = ROOT/'outputs/q3/raw/validation_20260912/prepared/pv_forecasts.csv'
    attachment = ROOT/'docs/CUMCM2026Problems/C题/附件/附件3.xlsx'
    dispatch_path = RUN/'main/dispatch.csv'
    daily_path = RUN/'main/daily.csv'
    sensitivity_path = ROOT/'outputs/sensitivity_q2_q3/raw/local_20260913/daily_results.csv'
    sources = [actual_path, forecast_path, attachment, dispatch_path, daily_path, sensitivity_path, RUN/'execution.json']
    actual = pd.read_csv(actual_path, float_precision='round_trip')
    pv = actual.pv_kw.to_numpy()
    forecast = pd.read_csv(forecast_path, parse_dates=['issue', 'target'], float_precision='round_trip')
    wb = load_workbook(attachment, read_only=True, data_only=True)
    official = np.asarray([row[2:] for row in list(wb.active.values)[1:]], dtype=float).ravel()
    wb.close()
    np.testing.assert_allclose(forecast.forecast_kw, official, atol=1e-10, rtol=0)
    forecast['date'] = forecast.issue.dt.strftime('%Y-%m-%d')
    forecast['issue_hour'] = forecast.issue.dt.hour
    target_slot = ((forecast.target-pd.Timestamp('2025-01-01')).dt.total_seconds()/600).astype(int)-1
    forecast['actual_kw'] = np.nan
    valid = target_slot.between(0, len(pv)-1)
    forecast.loc[valid, 'actual_kw'] = pv[target_slot[valid]]
    formal = forecast[forecast.date.ge('2025-02-01')]
    complete = formal.groupby('date').actual_kw.apply(lambda s: len(s)==96 and s.notna().all())
    dates = complete[complete].index.tolist()
    paired = formal[formal.date.isin(dates)].copy()
    paired['error_kw'] = paired.forecast_kw-paired.actual_kw
    assert len(dates)==333 and len(paired)==333*4*24
    write('forecast_pairs.csv', paired)
    metrics = paired.groupby(['issue_hour', 'horizon_hours']).error_kw.agg(
        n='size', MAE=lambda s: s.abs().mean(), RMSE=lambda s: np.sqrt(np.mean(s*s)), Bias='mean').reset_index()
    write('forecast_metrics.csv', metrics)
    previous = paired[['issue', 'target', 'forecast_kw']].copy()
    previous['issue'] += pd.Timedelta(hours=6)
    previous = previous.rename(columns={'forecast_kw': 'old_forecast_kw'})
    revisions = paired[paired.issue_hour.gt(0)&paired.horizon_hours.le(6)].merge(previous, on=['issue', 'target'], validate='one_to_one')
    revisions['old_abs_error'] = abs(revisions.old_forecast_kw-revisions.actual_kw)
    revisions['new_abs_error'] = abs(revisions.error_kw)
    assert len(revisions)==333*3*6
    write('revision_pairs.csv', revisions)
    revision_summary = revisions.groupby('issue_hour').agg(n=('target','size'), old_MAE=('old_abs_error','mean'), new_MAE=('new_abs_error','mean')).reset_index()
    write('revision_summary.csv', revision_summary)

    dispatch = pd.read_csv(dispatch_path, float_precision='round_trip')
    daily = pd.read_csv(daily_path, float_precision='round_trip')
    assert len(dispatch)==334*144 and len(daily)==334
    np.testing.assert_allclose(dispatch[['load_kw','pv_kw']], actual[['load_kw','pv_kw']].iloc[31*144:], atol=1e-8, rtol=0)
    delta = dispatch.grid-dispatch.g0
    expected = dispatch.price*(dispatch.g0+1.5*np.maximum(delta,0)-.5*np.maximum(-delta,0)+5*dispatch.emergency)
    np.testing.assert_allclose(expected, dispatch.total_cost, atol=1e-7, rtol=0)
    residual = dispatch.grid+dispatch.discharge+dispatch.emergency-dispatch.net_kwh-dispatch.charge-dispatch.spill
    np.testing.assert_allclose(residual, 0, atol=1e-7, rtol=0)
    previous_soc = np.r_[dispatch.initial_soc.iloc[0], dispatch.soc.to_numpy()[:-1]]
    soc_residual = dispatch.soc-previous_soc-.9*dispatch.charge+dispatch.discharge/.9
    np.testing.assert_allclose(soc_residual, 0, atol=1e-7, rtol=0)
    assert dispatch.soc.between(1200-1e-6,10800+1e-6).all()
    for key in ['charge','discharge']:
        assert dispatch[key].between(-1e-6,5000/6+1e-6).all()
    assert not ((dispatch.charge>1e-6)&(dispatch.discharge>1e-6)).any()
    dispatch['hour_right'] = (dispatch.slot+1)/6
    dispatch['delta_grid_kwh'] = delta
    write('formal_dispatch.csv', dispatch)
    costs = ['planned_cost','adjustment_cost','emergency_cost','total_cost']
    summed = dispatch.groupby('date')[costs].sum()
    np.testing.assert_allclose(summed, daily.set_index('date')[costs], atol=1e-6, rtol=0)
    write('formal_daily.csv', daily)
    monthly = dispatch.assign(month=pd.to_datetime(dispatch.date).dt.month).groupby('month')[costs].sum().reset_index()
    write('monthly_costs.csv', monthly)
    candidates = daily[daily.date.isin(['2025-03-20','2025-06-21','2025-09-23','2025-12-21'])][['date','emergency']].sort_values(['emergency','date'],ascending=[False,True])
    pressure = candidates.date.iloc[0]
    update = '2025-08-25'
    write('pressure_candidates.csv', candidates)
    # 补充清单方案B：指定四日中，取最接近正式期中位运行状态的日。
    features = ['total_cost','grid','throughput','soc_end']
    medians = daily[features].median()
    scales = daily[features].quantile(.75)-daily[features].quantile(.25)
    typical_candidates = daily[daily.date.isin(candidates.date)].copy()
    typical_candidates['median_state_distance'] = np.sqrt((((typical_candidates[features]-medians)/scales)**2).sum(axis=1))
    typical_candidates = typical_candidates.sort_values(['median_state_distance','date'])
    typical = typical_candidates.date.iloc[0]
    write('typical_candidates.csv', typical_candidates)
    write('typical_selection_scale.csv', pd.DataFrame({'feature':features,'formal_median':medians.values,'formal_IQR':scales.values}))
    typical_frame = dispatch[dispatch.date.eq(typical)]
    write('typical_dispatch.csv', typical_frame)
    write('typical_storage.csv', pd.DataFrame({'hour':np.arange(145)/6,'soc_kwh':np.r_[typical_frame.initial_soc.iloc[0],typical_frame.soc]}))
    typical_forecast = forecast[forecast.date.eq(typical)&forecast.horizon_hours.le(6)].copy()
    typical_forecast['target_hour'] = (typical_forecast.target-pd.Timestamp(typical)).dt.total_seconds()/3600
    write('typical_forecasts_active.csv', typical_forecast)
    for label, day in [('pressure',pressure),('update',update)]:
        frame = dispatch[dispatch.date==day]
        write(f'{label}_dispatch.csv', frame)
        write(f'{label}_storage.csv', pd.DataFrame({'hour':np.arange(145)/6, 'soc_kwh':np.r_[frame.initial_soc.iloc[0],frame.soc]}))
    update_forecast = forecast[forecast.date.eq(update)&forecast.target.le(pd.Timestamp(update)+pd.Timedelta(days=1))].copy()
    update_forecast['target_hour'] = (update_forecast.target-pd.Timestamp(update)).dt.total_seconds()/3600
    write('update_forecasts.csv', update_forecast)
    nodes = []; policies = []
    for day in daily.date:
        path = RUN/'main/audit'/f'{day}.json'
        sources.append(path)
        audit = json.loads(path.read_text(encoding='utf-8'))
        frame = dispatch[dispatch.date==day]
        assert [n['hour'] for n in audit['nodes']]==[0,6,12,18]
        np.testing.assert_allclose(frame.g0, audit['nodes'][0]['grid'], atol=1e-7, rtol=0)
        for node in audit['nodes']:
            h = node['hour']; s = node['solver']
            np.testing.assert_allclose(frame.grid.iloc[h*6:h*6+36], node['grid'][:36], atol=1e-7, rtol=0)
            nodes.append({'date':day,'hour':h,'reliable':s['reliable'],'gap':s['gap'],'seconds':s['seconds'],'status':s['status']})
            if day==update:
                policies.extend({'date':day,'issue_hour':h,'target_hour':h+(i+1)/6,'grid_kwh':v,'executed':i<36} for i,v in enumerate(node['grid']) if h+(i+1)/6<=24)
    write('update_grid_policies.csv', pd.DataFrame(policies))
    quality = pd.DataFrame(nodes)
    write('formal_solver_quality.csv', quality)
    sensitivity = pd.read_csv(sensitivity_path, float_precision='round_trip')
    sensitivity = sensitivity[sensitivity.question.eq('q3')].copy()
    assert len(sensitivity)==36 and not sensitivity.duplicated(['parameter','value','date']).any()
    assert sensitivity.groupby(['parameter','value']).size().eq(4).all()
    write('local_sensitivity.csv', sensitivity)
    cfg = json.loads((RUN/'execution.json').read_text(encoding='utf-8'))['config']
    (DATA/'execution_config.json').write_text(json.dumps(cfg,ensure_ascii=False,indent=2),encoding='utf-8')
    result = {'formal_days':334,'paired_forecast_days':dates,'samples_per_forecast_cell':333,
        'paired_next6h_samples_per_issue':1998,'pressure_day':pressure,'update_day':update,'typical_day':typical,
        'certified_nodes':int(quality.reliable.sum()),'formal_nodes':len(quality),
        'annual_cost_yuan':float(dispatch.total_cost.sum()),'annual_adjustment_yuan':float(dispatch.adjustment_cost.sum()),
        'balance_max_residual':float(abs(residual).max()),'soc_max_residual':float(abs(soc_residual).max()),
        'source_sha256':{str(p.relative_to(ROOT)):sha(p) for p in sources}}
    (DATA/'provenance.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print({k:v for k,v in result.items() if k not in ['paired_forecast_days','source_sha256']})


if __name__=='__main__':
    prepare()
