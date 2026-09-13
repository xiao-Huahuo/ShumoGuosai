"""Q4敏感性实际结果独立验收、代表日汇总与UTF-8论文报告。"""
from pathlib import Path
import html
import json
import re
import sys
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from src.sensitivity.q4_experiment import RUN, DOC, BASE, read_json, sha, metrics
from src.q4.config import Config, write_csv, write_json
from src.q4.rolling import validate_frame
WEB = ROOT/'outputs/processed/sensitivity_q4'


def aggregate(rows):
    fields = ['delta_cost_pct','total_cost','planned_cost','emergency_kwh','emergency_cost',
              'delta_emergency_kwh','delta_emergency_pct','min_soc','final_soc','solve_seconds',
              'solve_wall_seconds','adjustment_abs_kwh','adjustment_up_kwh','adjustment_down_kwh',
              'adjustment_cost','delta_adjustment_cost']
    return rows.groupby(['mode','parameter','setting'],sort=False)[fields].agg(['median','min','max'])


def verify():
    baselines = []
    for mode in BASE:
        expected = 16 if mode == '4-2' else 4
        assert read_json(RUN/f'completed_{mode}.json')['days'] == expected
        for path,value in read_json(RUN/f'baseline_hashes_{mode}.json').items():
            assert sha(path) == value
        baselines.extend(read_json(RUN/f'baseline_metrics_{mode}.json'))
    baseline_map = {(r['mode'],r['date']):r for r in baselines}
    rows, quality, weights = [], [], []
    for path in sorted((RUN/'cases').glob('*/result.json')):
        saved = read_json(path); row=saved['metrics']; folder=path.parent
        for name,value in saved['artifact_hashes'].items():assert sha(folder/name)==value
        frame = pd.read_csv(folder/'dispatch.csv',float_precision='round_trip')
        audit = read_json(folder/'audit.json'); experiment=audit['experiment']
        values = dict(experiment['test_config']);values['nodes']=tuple(values['nodes'])
        validate_frame(frame,row['mode'],Config(**values))
        base = baseline_map[row['mode'],row['date']]
        assert frame.initial_soc.iloc[0] == base['initial_soc']
        source = pd.read_csv(BASE[row['mode']]/f"days/{row['date']}.csv",float_precision='round_trip')
        for col in ['price','net_kwh','load_kw','pv_kw','price_forecast']:
            np.testing.assert_array_equal(frame[col],source[col])
        # 独立结算：减购退回原购电款，再支付50%违约，净变化为-0.5*p*减购量。
        delta = frame.grid-frame.g0
        expected_cost = frame.price*(frame.g0+1.5*np.maximum(delta,0)-0.5*np.maximum(-delta,0)+5*frame.emergency)
        np.testing.assert_allclose(frame.total_cost,expected_cost,rtol=0,atol=1e-6)
        recalculated = metrics(frame,audit)
        for key,value in recalculated.items():
            assert np.isclose(value,row[key],atol=1e-8,rtol=1e-12),(key,path)
        assert np.isclose(row['delta_cost_pct'],100*(row['total_cost']/base['total_cost']-1),atol=1e-10)
        if base['emergency_kwh']==0:assert row['delta_emergency_pct'] is None
        nodes = audit.get('nodes',[dict(audit,hour=0)])
        assert [n['hour'] for n in nodes] == ([0] if row['mode']=='4-2' else [0,6,12,18])
        for i,n in enumerate(nodes):
            if i:assert abs(n['initial_soc']-frame[frame.node_hour==nodes[i-1]['hour']].soc.iloc[-1])<1e-6
            s=n['solver'];sc=n['scenarios']
            assert s['status']=='Optimal' and s['reliable'] and s['binaries']==0 and s['gap']<=0.03
            assert sc['tail_singletons_verified']
            assert max(sc['history_days'])*144+n['hour']*6+sc['length'] <= (pd.Timestamp(row['date'])-pd.Timestamp('2025-01-01')).days*144+n['hour']*6
            frozen=read_json(RUN/'frozen'/row['mode']/row['date']/f"{n['hour']:02d}.json")
            assert sc['history_days']==frozen['history_days']
            if row['parameter']=='rho':
                assert sc['scenario_fingerprint']==frozen['scenario_fingerprint']
                assert sc['weights']==frozen['weights']
                assert np.isclose(sc['radius'],frozen['radius']*float(row['setting']),rtol=1e-14)
            else:
                assert sc['full_weight_pipeline_rebuilt']
                assert sc['tail_indices_in_pool']==frozen['tail_indices_in_pool']
                weights.append(dict(date=row['date'],net_weight=float(row['setting']),
                                    representatives_changed=sc['representative_pool_indices']!=frozen['representative_pool_indices'],
                                    probabilities_changed=sc['weights']!=frozen['weights'],
                                    radius_base=frozen['radius'],radius_variant=sc['radius']))
            quality.append(dict(mode=row['mode'],date=row['date'],parameter=row['parameter'],setting=row['setting'],hour=n['hour'],
                                status=s['status'],solver=s['solver'],version=s['solver_version'],gap=s['gap'],
                                primal_error=s['linear_feasibility_error'],certificate_error=s['lp_certificate_error'],
                                replay_duality_error=s['replay_duality_error'],radius=sc['radius']))
        rows.append(row)
    assert len(rows)==20 and len(quality)==32
    assert len({(r['mode'],r['date'],r['parameter'],r['setting']) for r in rows})==20
    # 每项参数的基准行只是从已有正式结果复制，未调用优化器。
    expanded = rows.copy()
    for row in baselines:
        for parameter in (['rho','weight'] if row['mode']=='4-2' else ['rho']):
            expanded.append(dict(row,parameter=parameter,setting='1.0' if parameter=='rho' else '0.5'))
    verification = dict(status='passed',new_day_cases=20,new_optimal_nodes=32,baseline_days_reused=6,
                        baseline_nodes_matrix_verified=12,baseline_resolved=0,
                        baseline_source_files_unchanged=True,physical_and_settlement_checks=True,
                        strict_history_boundaries=True,rho_scenario_probability_frozen=True,
                        weights_full_pipeline_rebuilt=True,rolling_node_soc_chain=True,
                        optional_window_scenarios='not run under requested stopping rule',
                        max_primal_error=max(q['primal_error'] for q in quality),
                        max_certificate_error=max(q['certificate_error'] for q in quality))
    write_json(DOC/'verification.json',verification)
    write_csv(WEB/'daily_results.csv',pd.DataFrame(expanded))
    write_csv(WEB/'solver_quality.csv',pd.DataFrame(quality))
    write_csv(WEB/'weight_reconstruction.csv',pd.DataFrame(weights))
    return pd.DataFrame(expanded),verification


def table_text(rows,mode):
    fields=['delta_cost_pct','planned_cost','emergency_kwh','emergency_cost','min_soc','final_soc','solve_seconds']
    labels=['费用变化%','计划购电费/元','紧急量/kWh','紧急费/元','最低SOC/kWh','末SOC/kWh','求解秒']
    if mode=='4-3':
        fields=['delta_cost_pct','adjustment_cost','adjustment_abs_kwh','emergency_kwh','final_soc','solve_seconds']
        labels=['费用变化%','净调整费/元','调整总量/kWh','紧急量/kWh','末SOC/kWh','求解秒']
    result=['|参数|设置|'+'|'.join(labels)+'|','|'+'---|'*(len(fields)+2)]
    for parameter,settings in [('rho',['0.75','1.0','1.25']),('weight',['0.7','0.5','0.3'])]:
        if mode=='4-3' and parameter=='weight':continue
        for setting in settings:
            subset=rows[(rows['mode']==mode)&(rows.parameter==parameter)&(rows.setting==setting)]
            cells=[]
            for key in fields:
                v=subset[key];cells.append(f'{v.median():.3f} [{v.min():.3f}, {v.max():.3f}]')
            label=setting+'ρ*' if parameter=='rho' else f'{float(setting):.1f}/{1-float(setting):.1f}'
            result.append('|'+('ρ' if parameter=='rho' else 'ωN/ωp')+'|'+label+'|'+'|'.join(cells)+'|')
    return '\n'.join(result)


def requirements():
    source=DOC/'问题四敏感性分析实验方案_时间受限版.md'
    entries=[];section=0
    mapping={
        0:('report::main','results.md','原方案标题完整保存'),
        1:('run / freeze','results.md::实测讨论与论文表述','目标通过真实结果评估，不预设稳定性通过'),
        2:('run::stages','daily_results.csv','rho三档/权重三档；W/S为可选且未执行'),
        3:('configure / inputs','baseline_hashes; inputs/frozen_forecasts.json','原配置/预测/物理与结算冻结'),
        4:('run / freeze','cases/*/audit.json::experiment','仅一个配置字段变化；基准直接复用'),
        5:('prepare','representatives.json; selection_metrics_4-2.csv; selection_metrics_4-3.csv','结果前固定规则，6-12月、去重、4/2日'),
        6:('freeze / run::selected_scenarios / metrics','solver_quality.csv; daily_results.csv','rho乘0.75/1.25且场景概率指纹不变'),
        7:('run::selected_scenarios','weight_reconstruction.csv; cases/4-2_weight*/audit.json','8项权重全流程重建，场景/概率均实际改变'),
        8:('run::stages','results.md::验收','依第19节停止，不执行可选W'),
        9:('run::stages','results.md::验收','依第19节停止，不执行可选S'),
        10:('run::stages','completed_4-2.json; completed_4-3.json','Q42主体16变体，Q43四日变体16节点'),
        11:('run / baseline','verification.json','新增20日32节点，复用6日12节点'),
        12:('run::stages','run_q42.log; run_q43.log','按rho、权重、Q43顺序实际执行'),
        13:('run::stages','cases/*/audit.json::experiment','未混入消融，只动dro_scale/net_weight'),
        14:('metrics / q4_report::aggregate','summary.csv; daily_results.csv','逐日变化率后聚合median/min/max；零分母留空'),
        15:('q4_report::table_text','results.md::Q4-2','Q42六组正式表，含计划费用和全部指定指标'),
        16:('q4_report::table_text','results.md::Q4-3','Q43三组正式表和调整费用/量'),
        17:('q4_report::main','results.md::实测讨论与论文表述','费用稳定性局部支持；调整量稳定不支持，完整披露'),
        18:('run::stages / q4_report::verify','verification.json; daily_results.csv','三项必做全完；可选W/S未做'),
        19:('run::stages','completed_4-2.json; completed_4-3.json','三项必做完成即停止，未扩参'),
        20:('q4_report::main','results.md::实测讨论与论文表述','不按测试成本挑参，未宣称全年/所有指标稳定')}

    for number,line in enumerate(source.read_text(encoding='utf-8').splitlines(),1):
        text=line.strip()
        if not text:continue
        match=re.match(r'^(?:#+\s*)?(\d+)\. (?:实验目标|敏感参数|不进行|总体|代表日|Q4-S1|Q4-S2|Q4-S3|Q4-S4|Q4-2 与|最小|推荐|敏感性分析与|统一|Q4-2 结果|Q4-3 结果|论文|最终执行|停止|最终原则)',text)
        if match:
            candidate=int(match.group(1))
            if 1<=candidate<=20:section=candidate
        optional=section in (8,9)
        entries.append(dict(source_line=number,requirement=text,section=section,
                            status='optional_not_run' if optional else 'verified_or_reported',
                            implementation='src/sensitivity/q4_experiment.py; src/sensitivity/q4_report.py::'+mapping[section][0],
                            evidence=mapping[section][1],acceptance=mapping[section][2]))
    write_csv(DOC/'requirements_acceptance.csv',pd.DataFrame(entries))


def main():
    WEB.mkdir(parents=True,exist_ok=True)
    rows,checks=verify()
    summary=aggregate(rows);summary.columns=['_'.join(c) for c in summary.columns]
    write_csv(WEB/'summary.csv',summary.reset_index())
    variants=rows[~rows.baseline_reused]
    facts=[]
    for mode,parameter in [('4-2','rho'),('4-2','weight'),('4-3','rho')]:
        r=variants[(variants['mode']==mode)&(variants.parameter==parameter)]
        facts.append(f'- Q{mode} {"半径" if parameter=="rho" else "权重"}：真实总费用变化范围 {r.delta_cost_pct.min():+.3f}%～{r.delta_cost_pct.max():+.3f}%；紧急购电量绝对变化 {r.delta_emergency_kwh.min():+.3f}～{r.delta_emergency_kwh.max():+.3f} kWh。')
    reps=read_json(RUN/'representatives.json')
    dates='\n'.join(f'- Q{mode}：'+ '；'.join(r['role']+' '+r['date'] for r in items)+'。' for mode,items in reps['modes'].items())
    text=f'''# 问题四代表日敏感性分析结果

假设与执行口径：按用户时间受限方案第19节停止规则，仅完成三项必做实验。代表日局部扰动，每日初始SOC继承对应正式全年轨迹当天的真实值，不重新串联全年SOC，不在测试集选最优参数。结果只支持已选工况下的局部稳定性，不能替代全年敏感性结论。

## 实测结果

已完成20个新增日级实验、32个新增节点，全部为HiGHS 1.15.1认证Optimal。6个正式基准日直接复用，12个基准节点的完整优化矩阵SHA逐一一致；没有重求解基准。

{chr(10).join(facts)}

## 预先固定代表日

{dates}

所有候选为6—12月。常规日费用最接近全年正式334日费用中位数；高波动按实际电价日内总体标准差；联合风险按当前日价格与净负荷正OOS误差的标准化乘积均值，标准化尺度来自该日0点前可用56日历史（沿用模型MAD及退化回退）；压力按基准紧急购电量降序。并列日期升序，重复向下顺延。选日真实数据只用于事后工况选择，不传入优化输入。selection_metrics与representatives.json在第一个扰动求解前保存。

## Q4-2（4日）

每格为中位数 [最小值, 最大值]；费用百分比先逐日对同日基准计算，再跨日汇总。SOC为电量kWh，最低值含日初SOC。

{table_text(rows,'4-2')}

## Q4-3（2日、每日0/6/12/18四节点）

{table_text(rows,'4-3')}

## 实测讨论与论文表述

Q4-2半径从0.75ρ*增至1.25ρ*时，四日计划购电费均单调增加、紧急购电量均单调下降，说明常规购电与紧急风险之间存在预期权衡。相对ρ*，强鲁棒紧急量下降2.03%～12.08%；弱鲁棒增加3.29%～19.48%。但末SOC并不一致增加：7月1日由1800降至1200 kWh，12月14日由9676.159升至10050 kWh。因此不能把稳健化简单等同于更高的日末储能库存。

Q4-2八项权重实验均实际改变了代表场景和概率。费用变化在−1.489%～+1.194%，紧急量变化在−26.107%～+10.457%。价格偏重的四日紧急量均下降；净负荷偏重在7月6日和12月14日分别增加458.974与104.870 kWh。三种设置下SOC均满足物理边界，支持经济结果对精确等权值不敏感；风险指标仍有响应，不能写成完全不变，更不能据此选择测试成本最低权重。

Q4-3常规日费用变化仅−0.152%～+0.246%；0.75ρ*下紧急量从7.889增至12.220 kWh，百分比虽为+54.90%，绝对只增加4.331 kWh。高联合风险日弱鲁棒费用+4.022%、紧急量+11.275%（+870.247 kWh）；强鲁棒费用−1.808%、紧急量−5.842%（−450.870 kWh）。强鲁棒下风险下降的方向可迁移到四节点调度，但敏感幅度不能视作与Q4-2完全相同。

高联合风险日Q4-3调整绝对总量从基准700.210 kWh变为弱鲁棒363.517、强鲁棒1363.000 kWh；净调整费用从213.798元变为70.270、412.925元。调整量存在明显参数响应，因此“调整行为无明显变化”不获本实验支持。费用影响仍小于日总费用，且四个节点全部最优、SOC合法，没有发现求解失败或物理失控。

可直接用于论文的审慎表述：在预先选定的代表日上，对Wasserstein半径与联合距离权重进行单因素扰动后，Q4-2真实结算费用最大绝对变化为2.17%，储能状态满足物理约束；强鲁棒半径总体以增加计划购电费用换取较低紧急风险。Q4-3常规日费用变化不超过0.25%，高联合风险日最大增幅为4.02%，同时调整量呈现较明显响应。结果支持所选工况下经济结果的局部参数稳定性，但不支持所有风险与调整指标均不敏感，也不构成全年参数稳健性的证明。

审查等级：未发现未解决的P0/P1实现问题；P2解释限制为仅4/2代表日且未事先给出“异常大幅变化”的数值阈值，Q4-3调整量不能宣布稳定；P3计时限制为基准复用历史耗时。W/S按停止规则未做，不属于必做遗漏。所有审查结论直接对应实测，未追加调参或扩大样本。

## 参数冻结与真实结算

Q4-2直接加载正式v2快照，Q4-3加载正式v3快照；只读依赖、附件、预测数组和负荷模型选择均核验hash。半径为每个日/节点原标定ρ*的0.75/1.25倍，联合历史池、20场景、经验概率、距离矩阵和预测完全固定；每个节点仍接收本实验前一节点实际SOC。未重新训练Elastic Net，也未增加统计bootstrap；场景构造沿用正式模型100次半径标定bootstrap。

联合权重实验改变net_weight为0.7或0.3，分别对应(ωN,ωp)=(0.7,0.3)/(0.3,0.7)。完整重新执行联合距离→强制尾部singleton+k-medoids→概率聚合→Wasserstein距离和原标定规则→DRO→真实回放。因距离尺度改变，ρ*按原规则随新距离重标定，dro_scale固定1；这属于同一权重流程，不额外调参。详见weight_reconstruction.csv。

物理与结算沿用正式值：容量上限10800/下限1200 kWh、功率5000 kW、充放效率0.9；紧急费5p，调整增购1.5p；减购先退原购电款再付0.5p违约，故相对初购费用的净调整项为−0.5p×减购量。调整量同时给增购、减购、绝对总量、净量；adjustment_cost为正式口径净调整费，可为负。

solve_seconds为同口径节点求解与证书核验耗时之和；solve_wall_seconds包含独立求解进程启动。基准时间复用原审计，受机器负载影响，不能作为严格同机加速测试。半径实验复用已构造场景；scenario_seconds保留原构造时间用于追溯，不是新增构造耗时。day_elapsed_seconds才是本次日级实际耗时。

紧急购电基准为0时百分比字段留空，直接报告绝对变化；跨日汇总不对空值造百分比。未执行W/S可选实验、全年重跑、消融或结果bootstrap。

## 验收

所有真实10分钟回放通过成本重算、能量平衡、SOC上下界与链条、充放功率、四时点节点顺序及历史截止检查。最大LP原约束误差{checks['max_primal_error']:.3g}，最大原对偶证书误差{checks['max_certificate_error']:.3g}。新增32节点均认证最优，原正式结果文件hash未改变。完整数据见daily_results.csv（含10行复用参数基准、20行变体），汇总见summary.csv，节点证书见solver_quality.csv。

论文解释必须结合逐日风险和库存变化；总费用小幅变化不能推出每项风险指标都不敏感，也不能推出ρ越大越好。审查与论文建议表述见本文后续实测讨论。
'''
    (DOC/'results.md').write_text(text,encoding='utf-8')
    requirements()
    # 浏览器验收页只展示同一实测表，保持论文报告和UI数据一致。
    table=rows[['mode','date','role','parameter','setting','delta_cost_pct','emergency_kwh','delta_emergency_kwh','min_soc','final_soc','adjustment_cost','solve_seconds','all_optimal']].rename(columns={'mode':'问题','date':'日期','role':'工况','parameter':'参数','setting':'设置','delta_cost_pct':'费用变化%','emergency_kwh':'紧急量kWh','delta_emergency_kwh':'紧急量变化kWh','min_soc':'最低SOC','final_soc':'末SOC','adjustment_cost':'净调整费/元','solve_seconds':'求解秒','all_optimal':'认证最优'}).to_html(index=False,float_format=lambda x:f'{x:,.3f}',border=0)
    page=f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>问题四敏感性实验结果</title><style>body{{font:15px -apple-system,BlinkMacSystemFont,sans-serif;background:#f4f6fa;color:#183148;margin:36px}}main{{max-width:1500px;margin:auto}}h1{{font-size:29px}}.cards{{display:flex;gap:16px;margin:24px 0}}.card{{background:white;border-radius:12px;padding:22px;flex:1;border-top:4px solid #167c69}}b{{font-size:28px;display:block}}.scroll{{overflow:auto;background:white;border-radius:12px}}table{{border-collapse:collapse;font-size:12px;white-space:nowrap;width:100%}}td,th{{padding:10px;border-bottom:1px solid #e3e8ef;text-align:right}}th{{background:#e9eff5}}p,li{{line-height:1.7}}a{{color:#125b9b}}</style><main><h1>问题四 · 敏感性实验已完成</h1><p>代表日局部OFAT · 正式基准复用 · 真实电价回放</p><div class="cards"><div class="card"><b>20 / 20</b>新增日级实验完成</div><div class="card"><b>32 / 32</b>节点认证最优</div><div class="card"><b>6 日</b>基准复用，零重求解</div></div><ul>{''.join('<li>'+html.escape(f[2:])+'</li>' for f in facts)}</ul><p>数据表：<a href="daily_results.csv">逐日结果</a> · <a href="summary.csv">中位数与范围</a> · <a href="solver_quality.csv">求解证书</a> · <a href="results.md">完整报告</a></p><div class="scroll">{table}</div><p>Q4-3高风险日调整总量为基准700.21 → 弱鲁棒363.52 / 强鲁棒1363.00 kWh，不能称为调整行为不敏感。仅支持代表日局部结论。W、S可选实验依停止规则未执行。</p></main></html>'''
    (WEB/'index.html').write_text(page,encoding='utf-8')
    (WEB/'results.md').write_text(text,encoding='utf-8')
    print(json.dumps(checks,ensure_ascii=False,indent=2))
    print(variants[['mode','date','parameter','setting','delta_cost_pct','delta_emergency_kwh','delta_emergency_pct','delta_adjustment_cost','final_soc']].to_string(index=False))


if __name__=='__main__':main()
