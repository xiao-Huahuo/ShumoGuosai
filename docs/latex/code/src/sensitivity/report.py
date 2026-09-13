"""报告已有代表日局部变化，不预设单调性或参数稳健结论。"""
import json
import numpy as np
import pandas as pd
from .common import ROOT,RUN,write_json,file_hash,comparison


def generate(records):
    rows=[];seen=set()
    for record in records:
        row={k:v for k,v in record.items() if not isinstance(v,(dict,list))};rows.append(row)
        if record.get('status') in ('complete','limited'):
            key=(record['question'],record['parameter'],record['date'])
            if key not in seen:
                seen.add(key);base_value={'beta_R':1.,'rho_tail':.2,'S':20,'lambda_E':1.,'S_tail':2}[record['parameter']]
                meta=json.loads((RUN/'inputs'/record['question']/record['date']/'metadata.json').read_text())
                solvers=[meta['baseline_solver']] if record['question']=='q2' else [n['baseline_solver'] for n in meta['nodes']]
                seconds=sum(a.get('solve_seconds',a.get('seconds',0)) for a in solvers)
                certified=sum(bool(a.get('reliable')) for a in solvers)
                rows.append({'id':'baseline_'+record['id'],'question':record['question'],'parameter':record['parameter'],'value':base_value,'date':record['date'],'role':record['role'],
                             **record['baseline'],**comparison(record['baseline'],record['baseline']),'seconds':seconds,'status':'baseline_reused',
                             'reliable':certified==len(solvers),'nodes':len(solvers),'certified_nodes':certified,'physical_verified':True})
    detailed=pd.DataFrame(rows)
    for index,row in detailed.iterrows():
        path=(RUN/'inputs'/row.question/row.date/'baseline_dispatch.csv') if row.status=='baseline_reused' else (RUN/'jobs'/row.id/'dispatch.csv')
        if path.exists():
            frame=pd.read_csv(path,float_precision='round_trip')
            detailed.loc[index,'soc_upper_fraction']=float(np.mean(frame.soc>=10800-1e-5))
            detailed.loc[index,'soc_lower_fraction']=float(np.mean(frame.soc<=1200+1e-5))
    detailed.to_csv(RUN/'daily_results.csv',index=False,encoding='utf-8',float_format='%.17g')
    valid=detailed[detailed.status.isin(['complete','limited','baseline_reused'])]
    measures=['delta_cost_pct','delta_emergency_kwh','delta_emergency_pct','total_cost','planned_cost','adjustment_cost','emergency_kwh','emergency_cost','min_soc','final_soc','seconds','throughput_kwh','soc_upper_fraction','soc_lower_fraction']
    aggregates=[]
    for (question,parameter,value),group in valid.groupby(['question','parameter','value'],sort=False):
        row={'question':question,'parameter':parameter,'value':value,'days':len(group),'certified_days':int(group.reliable.sum()),'contains_uncertified':not bool(group.reliable.all())}
        for m in measures:
            series=pd.to_numeric(group[m],errors='coerce').dropna()
            row.update({m+'_median':float(series.median()) if len(series) else None,m+'_min':float(series.min()) if len(series) else None,m+'_max':float(series.max()) if len(series) else None,m+'_n':len(series)})
        aggregates.append(row)
    aggregate=pd.DataFrame(aggregates);aggregate.to_csv(RUN/'aggregate_results.csv',index=False,encoding='utf-8',float_format='%.17g')
    report=['# 问题二与问题三局部敏感性分析','', '4个代表日、单因素扰动；基准直接复用。本文仅描述选定工况下的局部变化，不能外推为全年敏感性。', '',
            'Q3场景数经用户确认改为10/20/28，固定同一28条历史条件池。Q2正式场景数为26，安全裕度与尾部比例实验均固定26。', '',
            '表格格式为中位数 [最小值, 最大值]，只对4个代表日作描述统计，不作bootstrap或显著性检验。基准紧急量为0时，百分比留空并报告绝对变化。', '',
            '重要精度口径：保持正式求解设置和3%目标；Q3沿用原35/8秒限时可行策略。未认证的基准或变体可能把求解误差混入参数变化，因此不据此宣称最优解稳定或单调性。基准耗时为原正式运行记录，与当前机器的局部重求解时间不作速度比结论。', '']
    def cell(row,key):
        if pd.isna(row[key+'_median']):return '不适用'
        return f"{row[key+'_median']:.3f} [{row[key+'_min']:.3f}, {row[key+'_max']:.3f}]"
    for q in ['q2','q3']:
        keys=['delta_cost_pct','planned_cost' if q=='q2' else 'adjustment_cost','emergency_kwh','emergency_cost','min_soc','final_soc','seconds']
        extra='计划费用/元' if q=='q2' else '调整费用/元'
        report += ['## '+q.upper(),'',f'| 参数 | 参数值 | 成本变化/% | {extra} | 紧急量/kWh | 紧急费用/元 | 最低SOC/kWh | 末SOC/kWh | 耗时/s | 已认证日数 |','|---|---:|---|---|---|---|---|---|---|---:|']
        for row in aggregates:
            if row['question']==q:
                value=f"{row['value']:.0%}" if row['parameter']=='rho_tail' else str(row['value'])
                report.append('| '+row['parameter']+' | '+value+' | '+' | '.join(cell(row,k) for k in keys)+f" | {row['certified_days']}/{row['days']} |")
        variant=valid[(valid.question==q)&(valid.status!='baseline_reused')]
        if len(variant):
            report+=['',f"实际变体成本变化范围：{variant.delta_cost_pct.min():.3f}% 至 {variant.delta_cost_pct.max():.3f}%；紧急购电绝对变化范围：{variant.delta_emergency_kwh.min():.3f} 至 {variant.delta_emergency_kwh.max():.3f} kWh。"]
    # 定向响应只如实逐日计数，不把非单调结果改写为预期结论。
    directions=[]
    for q,param in [('q2','beta_R'),('q2','rho_tail'),('q3','lambda_E'),('q3','S')]:
        for date,g in valid[(valid.question==q)&(valid.parameter==param)].groupby('date'):
            g=g.sort_values('value')
            directions.append({'question':q,'parameter':param,'date':date,'values':g.value.tolist(),'costs':g.total_cost.tolist(),'emergency':g.emergency_kwh.tolist(),
                               'emergency_nonincreasing':bool(np.all(np.diff(g.emergency_kwh)<=1e-6)),'all_certified':bool(g.reliable.all())})
    write_json(RUN/'direction_checks.json',directions)
    report+=['','## 对实验问题的实际回答','', '以下仅为相同日初状态、相同信息与原求解预算下的局部响应。3%间隙针对模型内目标，并不是实际回放费用的±3%误差带，不能据此直接扣除或解释实际费用变化。']
    for q,param in [('q2','beta_R'),('q2','rho_tail'),('q3','S'),('q3','lambda_E'),('q3','S_tail')]:
        groups=valid[(valid.question==q)&(valid.parameter==param)]
        changes=groups[groups.status!='baseline_reused']
        if changes.empty:continue
        counts={'increase':0,'decrease':0,'same':0};cost_deltas=[];risk_deltas=[]
        for date,g in groups.groupby('date'):
            g=g.sort_values('value')
            if len(g)<3:continue
            difference=float(g.emergency_kwh.iloc[-1]-g.emergency_kwh.iloc[0])
            counts['increase' if difference>1e-5 else 'decrease' if difference< -1e-5 else 'same']+=1
        maximum=float(abs(changes.delta_cost_pct).max())
        report+=['',f"- {q.upper()} {param}：变体相对同日基准的最大绝对成本变化为{maximum:.3f}%；从最低参数档升至最高档，紧急量下降{counts['decrease']}日、上升{counts['increase']}日、不变{counts['same']}日。风险变化并不预先假定单调。"]
        if not bool(groups.reliable.all()):report.append('  该组含未认证的基准或变体；所列变化混有求解预算影响，不能判定为精确最优策略的参数效应。')
    report+=['',f"所有已获得可行轨迹的SOC位于[{valid.min_soc.min():.6f}, 10800]kWh的数值可行范围；未出现容量/功率越界或能量平衡失败。上界停留比例与吞吐量详见daily_results.csv。", '',
             '主要经济结论的边界：仅凭这些扰动不能证明动态SOC裕度或尾部机制相对无机制策略的全年净收益，也不能宣称某个参数理论最优。若不同代表日响应方向相反，应报告工况依赖；未设置新的主观百分比阈值来把结果自动归类为“稳定”。']
    quality=[]
    for record in records:
        if record['status'] not in ('complete','limited'):continue
        audit=json.loads((RUN/'jobs'/record['id']/'audit.json').read_text())
        nodes=[{'hour':0,'solver':audit['solver']}] if record['question']=='q2' else audit['nodes']
        for node in nodes:
            solver=node['solver'];upper=solver.get('objective');lower=solver.get('lower_bound',solver.get('dual_bound'))
            quality.append({'id':record['id'],'question':record['question'],'date':record['date'],'parameter':record['parameter'],'value':record['value'],
                            'hour':node['hour'],'reliable':solver.get('reliable'), 'relative_gap':solver.get('mip_gap',solver.get('gap')),
                            'upper_bound':upper,'lower_bound':lower,'absolute_model_gap_yuan':max(0,upper-lower) if upper is not None and lower is not None else None,
                            'status':solver.get('status'),'accepted_by':solver.get('accepted_by'),'solver_seconds':solver.get('solve_seconds',solver.get('seconds'))})
    pd.DataFrame(quality).to_csv(RUN/'solver_quality.csv',index=False,encoding='utf-8',float_format='%.17g')

    report+=['','## 完整数据与边界','', 'daily_results.csv保留每个代表日及其基准；aggregate_results.csv还包含计划费用、调整费用和吞吐量的完整中位数/最小/最大。每个任务保存输入、策略、实际回放和求解审计。', '',
             f"完成扰动任务 {sum(r['status']=='complete' for r in records)}，限时可行 {sum(r['status']=='limited' for r in records)}，失败 {sum(r['status']=='failed' for r in records)}。未认证结果只作实际预算下的策略诊断，不作全局最优敏感性证明。"]
    if any(r['status']=='failed' for r in records):report+=['', '失败项：']+[f"- {r['id']}: {r.get('error')}" for r in records if r['status']=='failed']
    interpretation=ROOT/'docs/sensitivity_q2_q3/interpretation.md'
    if interpretation.exists():report+=['',interpretation.read_text(encoding='utf-8')]
    (RUN/'report.md').write_text('\n'.join(report)+'\n',encoding='utf-8')
    (ROOT/'docs/sensitivity_q2_q3/results.md').write_text('\n'.join(report)+'\n',encoding='utf-8')
    receipts=[]
    for record in records:
        folder=RUN/'jobs'/record['id']
        if record['status'] in ('complete','limited'):
            assert file_hash(folder/'dispatch.csv')==record['dispatch_sha256'];assert file_hash(folder/'audit.json')==record['audit_sha256']
            assert record['physical_verified'];receipts.append(record['id'])
    write_json(RUN/'acceptance.json',{'jobs':len(records),'verified_dispatch_audit_pairs':len(receipts),'baseline_reused_no_optimization':True,
                                   'no_full_year_rerun':True,'no_bootstrap':True,'all_core_jobs_have_outcome':len(records)>=32,'failed':sum(r['status']=='failed' for r in records),
                                   'local_inference_only':True,'q3_S28_user_approved':True})
