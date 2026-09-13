"""新版边际价值分析的科研图、可阅读报告和完整CSV入口。"""

import html
import re

from model import PHYS_TOL_KWH, ECONOMIC_VALUE_TOL
from report import html_table


def analysis_figures(a, output):
    """兼容原入口；绘图实现统一维护于src/plots/q1_legacy.py。"""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from src.plots.q1_legacy import analysis_figures as render
    return render(a, output)


def interpretations(a):
    b, diag = a["benefits"], a["lp_diagnosis"]
    main = next(r for r in a["scenarios"] if r["scenario"] == "main_l100_pv100")
    local = a["main_marginals"]
    texts = [
        f"无储能费用为{a['baseline_rows'][0]['cost_yuan']:.6f}元，仅光伏消纳储能为{a['baseline_rows'][1]['cost_yuan']:.6f}元，完整MILP为{diag['milp_cost_yuan']:.6f}元。"
        f"两步增量节约分别为{b['pv_increment_yuan']:.6f}元和{b['flex_increment_yuan']:.6f}元，总计{b['total_saving_yuan']:.6f}元；它们依赖基准设置，不是唯一的光伏/套利因果分解。",
        f"连续松弛费用{diag['lp_cost_yuan']:.9f}元，整数松弛间隙{diag['integer_gap']:.3e}；分数模式{diag['fractional_modes']}个，同时充放电{diag['simultaneous_periods']}个。"
        "仅说明本算例的松弛紧度，不能推出MILP与LP普遍等价，也不使用松弛解替换正式调度。",
        "固定MILP最优模式后，用母线等式 G−C+D−W=L−S+b 的右端项导数定义μ；用状态等式 Eₜ−Eₜ₋₁−ηC+D/η=h 的负导数定义λ。"
        "h表示在第t时段末额外注入内部电量，初始储量和日末目标保持不变；这与直接抬高Eₜ下限或日末目标不是同一扰动。"
        "μ、λ仅适用于所选最优模式附近，模式切换、活跃边界和对偶退化都可能改变它们。",
        "充电倾向条件为μ<ηλ，待机区间为ηλ≤μ≤λ/η，放电倾向条件为μ>λ/η。"
        "等号表示边际无差异，允许出现非零充放电；固定模式不允许的方向不能仅凭阈值执行。"
        f"本次主方案有{sum(r['mode_blocks_tendency'] for r in local)}个时段的严格阈值倾向受固定模式限制。"
        f"对固定模式LP的144个母线需求和144个内部注入方向分别作±0.01kWh重求，其中{a['rhs_nonsmooth_or_one_sided_count']}项为非光滑或单侧情况，"
        "保留两侧差分与不可行状态，并检验影子价格位于可行方向的差分区间内；不伪称每个点都有唯一导数。",
        f"主模型的未来电价须严格超过当前电价的{main['arbitrage_price_multiplier']:.9f}倍，忽略其他约束时才有正的外网跨期收益。"
        "等价阈值pₛ>pₜ/(ηcηd)仅是经济条件，不保证计划可执行；原本将被弃置的光伏不适用外网购电倍率。",
    ]
    texts.append(f"另对原MILP的全部288项RHS作双侧扰动，共576次整数重求，允许全部模式改变。"
                 f"其中{a['milp_rhs_mismatch_count']}项固定模式影子价格不能同时匹配原MILP两侧差分，"
                 f"{a['milp_rhs_nonsmooth_count']}项原MILP出现非光滑或单侧情况。"
                 "对应点只报告两侧有限差分，不将固定模式μ、λ解释为原MILP的唯一边际价格，也不据此生成全局充停放指令。")
    for resource, label in (("storage_upper", "安全储能上限提高"), ("storage_lower", "安全储能下限降低"),
                            ("charge_power", "充电功率提高"), ("discharge_power", "放电功率提高")):
        rows = [r for r in a["bottlenecks"] if r["scenario"] == main["scenario"] and r["resource"] == resource]
        one = rows[0]
        values = "、".join(f"{r['value_per_unit_day']:.9f}" for r in rows)
        texts.append(f"{label}基准活跃{one['active_count']}个时段；分别放宽1、10、100个单位后的单位日价值为{values}（{one['unit']}）。"
                     + ("该边界活跃且多步长单位价值稳定为正，存在稳定的数值节约。" if one["numerical_bottleneck"] else
                        "所测步长单位价值在数值容差内为零。" if all(abs(r["value_per_unit_day"]) <= ECONOMIC_VALUE_TOL for r in rows) else
                        "所测步长的单位价值未满足稳定正值判据，应按有限增量逐项解释。")
                     + "题目未给经济显著性门槛或设备成本，不据此认定投资意义上的经济瓶颈。")
    texts.append("储能空间与功率价值的单位不同，不能直接按数值大小推导设备投资优先级；安全上限放宽是分析实验，原正式结果仍采用10800kWh与5000kW。")
    central = {r["efficiency_name"]: r for r in a["scenarios"] if r["load_delta"] == r["pv_delta"] == 0}
    lo, hi = central["eta085"], central["eta095"]
    texts.append(f"效率由0.95降至0.85时，套利倍率由{hi['arbitrage_price_multiplier']:.6f}升至{lo['arbitrage_price_multiplier']:.6f}，"
                 f"充电总量由{hi['charge_kwh']:.6f}变为{lo['charge_kwh']:.6f}kWh，放电总量由{hi['discharge_kwh']:.6f}变为{lo['discharge_kwh']:.6f}kWh。"
                 "本算例效率降低后充电量增加、放电量下降，不支持二者同时下降的预期。")
    for factor, label, other in (("load_delta", "负荷", "pv_delta"), ("pv_delta", "光伏", "load_delta")):
        minus, plus = [next(r for r in a["scenarios"] if r["efficiency_name"] == "main" and r[factor] == v and r[other] == 0) for v in (-.05,.05)]
        norm = next(r for r in a["normalized_sensitivity"] if r["efficiency_name"] == "main" and r["factor"] == factor)
        texts.append(f"{label}从−5%增加至+5%：费用{minus['cost_yuan']:.6f}→{plus['cost_yuan']:.6f}元，购电{minus['grid_kwh']:.6f}→{plus['grid_kwh']:.6f}kWh，"
                     f"弃光{minus['curtail_kwh']:.6f}→{plus['curtail_kwh']:.6f}kWh；SOC下界活跃{minus['E_min_active_count']}→{plus['E_min_active_count']}个时段，"
                     f"空间价值{minus['storage_upper_value']:.6f}→{plus['storage_upper_value']:.6f}，放电功率价值{minus['discharge_power_value']:.6f}→{plus['discharge_power_value']:.6f}。"
                     f"归一化成本敏感度为{norm['normalized_sensitivity']:.9f}。")
    rt = central["roundtrip090"]
    texts.append(f"改用对称往返0.90口径后，成本{rt['cost_yuan']:.6f}元，套利倍率{rt['arbitrage_price_multiplier']:.9f}；"
                 f"空间/充电/放电功率单位日价值分别为{rt['storage_upper_value']:.9f}、{rt['charge_power_value']:.9f}、{rt['discharge_power_value']:.9f}。"
                 "与主口径逐项对照，正式CSV仍只交付双单程0.9解。")
    texts.append("本次主效率口径下，负荷增加未提高放电功率边际价值；光伏增加未导致弃光或储能空间单位价值上升。"
                 "因此这些预期趋势不应写成实证结论，费用及活跃程度的实际变化以上述数值为准。")
    order_ok = sum(r["charge_weighted_price"] < r["discharge_weighted_price"] for r in a["scenarios"])
    pv_ok = sum(abs(r["pv_surplus_kwh"] - r["pv_surplus_absorbed_kwh"]) <= PHYS_TOL_KWH for r in a["scenarios"])
    texts.append(f"36个组合中，{order_ok}组充电加权电价低于放电加权电价，{pv_ok}组吸收全部光伏净富余；"
                 "全部所选模式均通过非零动作与允许方向边际条件检查。"
                 "情景CSV同时列出动作变化时段数、最大储电轨迹差异和活跃边界计数；最优调度可能不唯一，动作差异不能单独解释为模型不稳健。")
    return texts


def create_analysis_report(a, output, documents, figure_status):
    texts = interpretations(a)
    setting = ("沿用右端点、ZOH、母线侧电量、双单程0.9、不售电与允许弃光；Qmax按5000/6准确计算，按用户要求仅用CSV交付。"
               "容差按物理、费用、整数、Gap、边际价值分别设置；36情景的储能上下限/充放功率均取步长1、10、100 kWh/kW；固定LP与原MILP的RHS步长均为±0.01 kWh。"
               "这些是数值分析设置，模型原稿和设备基准参数未改写。")
    links = {"baseline_comparison.csv": "三种基准", "incremental_benefits.csv": "增量节约", "lp_diagnosis.csv": "LP松弛诊断",
             "marginal_values.csv": "全部5184行局部边际量", "marginal_rhs_validation.csv": "288项双侧扰动",
             "milp_rhs_validation.csv": "288项原MILP双侧扰动",
             "bottleneck_values.csv": "432项容量上下限/功率放宽", "sensitivity_scenarios.csv": "36组情景汇总",
             "normalized_sensitivity.csv": "归一化敏感度", "active_constraints.csv": "全部活跃约束",
             "arbitrage_thresholds.csv": "跨期价格阈值", "../../q1/raw/analysis_schedules.csv": "36组完整输入与输出"}
    body = '<h1>Q1 · 边际价值、经济瓶颈与稳健性</h1><p><a href="report.html">返回主结果与输入输出</a></p>'
    body += f'<p class="note">假设与数值设置：{html.escape(setting)}</p>'
    body += '<p>' + ' · '.join(f'<a href="{k}">{v} CSV</a>' for k,v in links.items()) + '</p>'
    body += '<h2>结果解释</h2>' + ''.join(f'<p>{html.escape(t)}</p>' for t in texts)
    body += '<img src="marginal_analysis.png" alt="固定模式边际阈值、基准费用和九组负荷光伏敏感性"><img src="bottleneck_analysis.png" alt="容量、充电功率和放电功率三种步长的日价值">'
    body += '<h2>基准费用与增量节约</h2>' + html_table(["基准", "费用 元", "购电 kWh", "充电 kWh", "放电 kWh", "弃光 kWh"], [[r[k] for k in ("baseline","cost_yuan","grid_kwh","charge_kwh","discharge_kwh","curtail_kwh")] for r in a["baseline_rows"]])
    body += '<details open><summary>主方案144行边际价值与充停放解释</summary>' + html_table(
        ["时间段", "μ 元/kWh", "λ 元/kWh", "ηλ", "λ/η", "阈值倾向", "实际动作", "固定u", "模式阻止倾向"],
        [[r[k] for k in ("interval","mu_yuan_per_kwh","lambda_yuan_per_kwh","charge_threshold","discharge_threshold","tendency","actual_action","fixed_u","mode_blocks_tendency")] for r in a["main_marginals"]]) + '</details>'
    body += '<p>charge=充电，discharge=放电，idle=待机，idle_band=待机区间，indifferent_boundary=边界无差异；模式阻止倾向1表示该方向在固定LP中不允许。</p>'
    body += '<details open><summary>全部36个情景汇总与经济瓶颈</summary>' + html_table(
        ["情景", "费用 元", "购电 kWh", "充电 kWh", "放电 kWh", "弃光 kWh", "储能空间 元/(kWh·日)", "充电功率 元/(kW·日)", "放电功率 元/(kW·日)", "动作变化时段"],
        [[r[k] for k in ("scenario","cost_yuan","grid_kwh","charge_kwh","discharge_kwh","curtail_kwh","storage_upper_value","charge_power_value","discharge_power_value","action_changed_periods")] for r in a["scenarios"]]) + '</details>'
    body += '<details><summary>主方案十二项容量与功率步长对照</summary>' + html_table(
        ["放宽边界", "增加量", "节约 元", "单位日价值", "单位", "活跃时段", "稳定正值且活跃（数值判据）"],
        [[r[k] for k in ("resource","increment","saving_yuan","value_per_unit_day","unit","active_count","numerical_bottleneck")] for r in a["bottlenecks"] if r["scenario"]=="main_l100_pv100"]) + '</details>'
    body += '<h2>核验与复现</h2><p>每个扰动都重新求解保留整数互斥的原MILP；固定模式LP与原MILP目标一致，LP原始/对偶数值检查、分析CSV逐单元回读均通过。</p>'
    body += '<p><a href="../../q1/raw/analysis_validation.json">分析验收JSON</a> · <a href="../../q1/raw/analysis_solutions.json">原始解与影子价格</a> · <a href="../../../docs/1/deliverables/q1_implementation_acceptance.md">逐句验收与审查</a></p>'
    body += '<p>影子价格符号依据 <a href="https://docs.scipy.org/doc/scipy/reference/optimize.linprog-highs-ds.html">SciPy 官方文档</a>，并由本次双侧扰动校验。</p>'
    base = (output/'report.html').read_text(encoding='utf-8')
    style = base.split('<style>',1)[1].split('</style>',1)[0]
    if figure_status['status'] != 'passed':
        body = re.sub(r'<img[^>]+>', '', body)
    body += '<p class="note">绘图状态：' + html.escape(figure_status['message']) + '</p>'
    page = '<!doctype html><html lang="zh-CN"><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Q1 边际价值强化版</title><style>' + style + '</style><main>' + body + '</main></html>'
    (output/'marginal_report.html').write_text(page,encoding='utf-8')
    base = base.replace('<h2>输入：来源、时间与单位</h2>', '<p class="note"><a href="marginal_report.html">查看新版完整分析：边际价值、经济瓶颈、36组敏感性情景及全部CSV</a></p><h2>输入：来源、时间与单位</h2>')
    (output/'report.html').write_text(base,encoding='utf-8')
    document = documents/'q1_marginal_analysis.md'
    content = '# Q1 边际价值强化版分析结果\n\n假设与数值设置：' + setting + '\n\n'
    content += '\n\n'.join(texts) + '\n\n'
    content += '\n'.join(f'- [{v} CSV](../../../outputs/processed/q1/{k})' for k,v in links.items())
    content += '\n\n[完整可视分析](../../../outputs/processed/q1/marginal_report.html)\n\n'
    content += '影子价格的右端项导数与符号参见[SciPy官方文档](https://docs.scipy.org/doc/scipy/reference/optimize.linprog-highs-ds.html)，并已作实际扰动复核。\n'
    document.write_text(content,encoding='utf-8')
    result_doc = documents/'q1_results.md'
    with result_doc.open('a',encoding='utf-8') as f:
        f.write('\n新版第11.3–11.8节完整分析见[边际价值与经济瓶颈](q1_marginal_analysis.md)。\n')
