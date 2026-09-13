"""CR-13：每个展示公式/新增关键行内公式→具体赋值行→测试→本代证据。"""

import hashlib
from pathlib import Path

from model import ROOT, write_csv, write_json

PAPER = 'docs/1/final/第一问_MILP_边际价值强化版.md'

# 展示公式按源文出现顺序编号；相同公式的重复展示共用同一精确实现。
# 纯术语/能流示意也标注其作用，不伪称它们是新增约束。
GROUPS = [
 ('1 2 40 41 42 47 48 49 50', 'model.py', 'for name, coefficient in', 'test_q1.py', 'test_corrupted_schedules_rejected', 'raw/validation.json#main/metrics/11.1_balance_max_abs_kwh', '母线来源、去向与平衡'),
 ('3 4', 'model.py', 'result = milp(', 'test_review.py', 'test_official_attachment_fresh_solve_golden_and_csv', 'raw/solution_main.json#solver', '模型类型说明，由整数求解调用落实'),
 ('5 22', 'model.py', 'DT = 1 / 6', 'test_q1.py', 'test_time_and_unit_examples', 'inputs/processed/parameters.json#dt_hours', '时长'),
 ('6 7 14 44 51 53 59', 'model.py', 'T = 144', 'test_q1.py', 'test_time_and_unit_examples', 'inputs/processed/timeseries.csv', '时段数和索引域'),
 ('8 9 10 11 12 13', 'model.py', 'if endpoint != t * 10:', 'test_q1.py', 'test_time_and_unit_examples', 'inputs/processed/timeseries.csv', '时间映射'),
 ('15 16 17 18 19 20 21', 'model.py', '"load_kwh": pl * DT, "pv_kwh": ppv * DT', 'test_q1.py', 'test_time_and_unit_examples', 'inputs/processed/timeseries.csv', 'ZOH等效常量与单位转换'),
 ('23 24 25 26 64 83 136', 'model.py', 'Q_MAX = 5000 * DT', 'test_analysis.py', 'test_independent_power_limits_and_csv_nonfinite_rejected', 'inputs/processed/parameters.json#max_energy_kwh', '紧物理功率上界'),
 ('27 28 30 32 43 78', 'model.py', 'names = ("G", "C", "D", "E", "W", "u")', 'test_q1.py', 'test_export_csv_matches_all_variables_and_inputs', 'raw/solution_main.json', '变量定义与输出列'),
 ('29 31 33 34 36 52 55', 'model.py', 'a[n + t, index["C"][t]] = -eta_c', 'test_review.py', 'test_independent_efficiencies_analytical_case', 'raw/validation.json#main/metrics/11.2_soc_max_abs_kwh', '充电效率与状态方程'),
 ('29 31 33 34 36 52 55', 'model.py', 'a[n + t, index["D"][t]] = 1 / eta_d', 'test_review.py', 'test_independent_efficiencies_analytical_case', 'raw/validation.json#main/metrics/11.2_soc_max_abs_kwh', '独立放电效率与状态方程'),
 ('35 54 84 126 147', 'model.py', 'SCENARIOS = {"main": 0.90', 'test_q1.py', 'test_all_actual_scenarios', 'raw/solution_main.json#eta_c', '主效率口径'),
 ('37 39', 'model.py', 'upper[index["W"]] = pv', 'test_q1.py', 'test_curtailment_is_available_when_absorption_is_limited', 'raw/validation.json#main/metrics/11.7_curtail_bound_violation_kwh', '弃光范围'),
 ('38', 'model.py', 'g + pv - w + d - load - c', 'test_q1.py', 'test_corrupted_schedules_rejected', 'raw/validation.json#main/metrics/11.1_balance_max_abs_kwh', '有效光伏'),
 ('45', 'model.py', 'lower, upper = np.zeros(size)', 'test_q1.py', 'test_corrupted_schedules_rejected', 'raw/validation.json#main/metrics/11.6_nonnegative_violation_kwh', '变量非负性'),
 ('46 68 96', 'model.py', 'integer[index["u"]] = 1', 'test_review.py', 'test_binary_tolerance_is_independent_of_physical', 'raw/validation.json#main/metrics/9_binary_distance', '二元域'),
 ('56', 'model.py', 'row["soc_fraction"] = solution["E"][t] / 12000', 'test_q1.py', 'test_csv_roundtrip_and_tamper_rejection', 'processed/result1.csv#soc_fraction', '额定容量用于比例显示，不替代安全上限'),
 ('57 58', 'model.py', 'lower[index["E"]], upper[index["E"]] = e_min, e_max', 'test_review.py', 'test_active_sets_use_current_limits_and_lower_space', 'raw/validation.json#main/metrics/11.3_soc_bound_violation_kwh', '安全范围'),
 ('60 61', 'model.py', 'lb[n + t] = ub[n + t] = E_INITIAL if t == 0 else 0', 'test_q1.py', 'test_corrupted_schedules_rejected', 'raw/validation.json#main/metrics/11.8_initial_error_kwh', '初始时刻与6000kWh状态'),
 ('62 63', 'model.py', 'lower[index["E"][-1]] = upper[index["E"][-1]] = E_INITIAL', 'test_q1.py', 'test_corrupted_schedules_rejected', 'raw/validation.json#main/metrics/11.8_terminal_error_kwh', '终端时刻与6000kWh状态'),
 ('65 69 73 74', 'model.py', 'a[2 * n + t, index["u"][t]] = -qc', 'test_analysis.py', 'test_independent_power_limits_and_csv_nonfinite_rejected', 'raw/validation.json#main/metrics/9_binary_coupling_violation_kwh', '充电Big-M及模式含义'),
 ('66 70 71 72', 'model.py', 'a[3 * n + t, index["u"][t]] = qd', 'test_analysis.py', 'test_independent_power_limits_and_csv_nonfinite_rejected', 'raw/validation.json#main/metrics/9_binary_coupling_violation_kwh', '放电Big-M及模式含义'),
 ('67 75', 'model.py', '"11.5_simultaneous_kwh"', 'test_q1.py', 'test_corrupted_schedules_rejected', 'raw/validation.json#main/metrics/11.5_simultaneous_kwh', '67为被排除反例；75为互斥结果'),
 ('76 77', 'model.py', 'p, pl, ppv = map(float, row[1:])', 'test_q1.py', 'test_corrupted_inputs_rejected', 'inputs/processed/timeseries.csv#price_yuan_per_kwh', '电价与单位'),
 ('79', 'model.py', 'row["cost_yuan"] = record["price_yuan_per_kwh"] * solution["G"][t]', 'test_q1.py', 'test_export_csv_matches_all_variables_and_inputs', 'processed/result1.csv#cost_yuan', '逐时费用'),
 ('80 81', 'model.py', 'objective[index["G"]] = p', 'test_review.py', 'test_official_attachment_fresh_solve_golden_and_csv', 'raw/solution_main.json#solver/objective_yuan', '单一目标'),
 ('82', 'model.py', 'objective[index["G"]] = p', 'test_review.py', 'test_official_attachment_fresh_solve_golden_and_csv', 'raw/validation.json#main', '完整MILP：目标，约束分别见同表49/52/58/60/63/69/70/39/45/46'),
 ('85', 'model.py', 'TOLERANCES = {', 'test_review.py', 'test_binary_tolerance_is_independent_of_physical', 'inputs/processed/parameters.json#tolerances', '分量纲数值容差'),
 ('86 88', 'model.py', '"11.1_balance_max_abs_kwh"', 'test_q1.py', 'test_corrupted_schedules_rejected', 'raw/validation.json#main/metrics/11.1_balance_max_abs_kwh', '母线残差'),
 ('87 88', 'model.py', '"11.2_soc_max_abs_kwh"', 'test_q1.py', 'test_corrupted_schedules_rejected', 'raw/validation.json#main/metrics/11.2_soc_max_abs_kwh', '状态残差'),
 ('89', 'model.py', '"11.3_soc_bound_violation_kwh"', 'test_q1.py', 'test_corrupted_schedules_rejected', 'raw/validation.json#main/metrics/11.3_soc_bound_violation_kwh', '安全界验收'),
 ('90', 'model.py', '"11.4_power_bound_violation_kwh"', 'test_q1.py', 'test_corrupted_schedules_rejected', 'raw/validation.json#main/metrics/11.4_power_bound_violation_kwh', '功率界验收'),
 ('91', 'model.py', '"11.8_terminal_error_kwh"', 'test_q1.py', 'test_corrupted_schedules_rejected', 'raw/validation.json#main/metrics/11.8_terminal_error_kwh', '首尾状态验收'),
 ('92 93', 'model.py', '"11.9_objective_recalculation_error_yuan"', 'test_q1.py', 'test_corrupted_schedules_rejected', 'raw/validation.json#main/metrics/11.9_objective_recalculation_error_yuan', '费用独立复算'),
 ('94 95', 'model.py', 'metrics["11.2_relative_global_gap"]', 'test_q1.py', 'test_corrupted_schedules_rejected', 'raw/validation.json#main/metrics/11.2_relative_global_gap', '全局Gap'),
 ('97 98 99 100', 'analysis.py', '"integer_gap":', 'test_analysis.py', 'test_lp_relaxation_keeps_big_m_coupling', 'processed/lp_diagnosis.csv', 'LP诊断及松弛间隙'),
 ('101', 'analysis.py', '"fractional_modes":', 'test_analysis.py', 'test_lp_relaxation_keeps_big_m_coupling', 'processed/lp_diagnosis.csv#fractional_modes', '分数模式'),
 ('102', 'analysis.py', '"simultaneous_periods":', 'test_analysis.py', 'test_lp_relaxation_keeps_big_m_coupling', 'processed/lp_diagnosis.csv#simultaneous_periods', '同时动作'),
 ('103 104', 'model.py', 'upper[index["C"]] = upper[index["D"]] = 0', 'test_analysis.py', 'test_nested_baselines_and_analytic_no_ess', 'processed/baseline_comparison.csv', 'No-ESS'),
 ('105', 'model.py', 'upper[index["C"]] = np.maximum(pv - load, 0)', 'test_review.py', 'test_pv_only_source_with_zero_price_and_surplus', 'raw/analysis_validation.json#checks/pv_only', 'PV-only充电界'),
 ('106 107', 'model.py', 'upper[index["D"]] = np.maximum(load - pv, 0)', 'test_review.py', 'test_pv_only_source_with_zero_price_and_surplus', 'raw/analysis_validation.json#checks/pv_only', 'PV-only放电界'),
 ('108 109 110', 'analysis.py', 'if not jm <= jpv + COST_TOL_YUAN', 'test_analysis.py', 'test_nested_baselines_and_analytic_no_ess', 'processed/baseline_comparison.csv', '基准嵌套及成本次序'),
 ('111 112 113 114', 'analysis.py', 'benefits = {', 'test_analysis.py', 'test_nested_baselines_and_analytic_no_ess', 'processed/incremental_benefits.csv', '依赖基准的增量节约'),
 ('115', 'model.py', 'lower[index["u"]] = upper[index["u"]] = mode', 'test_analysis.py', 'test_analytic_shadow_sign_and_price_threshold', 'raw/analysis_solutions.json#scenarios', '固定模式'),
 ('116 117', 'analysis.py', 'mu, lam = result.eqlin.marginals', 'test_analysis.py', 'test_analytic_shadow_sign_and_price_threshold', 'processed/marginal_values.csv', '局部影子价及符号'),
 ('118 119 120', 'analysis.py', 'low, high = ec * lam[i], lam[i] / ed', 'test_review.py', 'test_independent_efficiencies_analytical_case', 'processed/marginal_values.csv', '阈值与独立效率'),
 ('121 122', 'model.py', '"roundtrip_efficiency":', 'test_review.py', 'test_independent_efficiencies_analytical_case', 'processed/efficiency_comparison.csv', '母线与内部能量效率'),
 ('123 124 125 127 151', 'analysis.py', '"future_price_threshold":', 'test_analysis.py', 'test_analytic_shadow_sign_and_price_threshold', 'processed/arbitrage_thresholds.csv', '跨期价差阈值'),
 ('128 129 130 133', 'analysis.py', 'for key, var, limit in', 'test_review.py', 'test_active_sets_use_current_limits_and_lower_space', 'processed/active_constraints.csv', '按当前储能上下限识别活跃界'),
 ('131', 'analysis.py', '("charge", "C", settings["charge_kw"] * DT)', 'test_review.py', 'test_active_sets_use_current_limits_and_lower_space', 'processed/active_constraints.csv', '按当前充电功率识别活跃界'),
 ('132', 'analysis.py', '("discharge", "D", settings["discharge_kw"] * DT)', 'test_review.py', 'test_active_sets_use_current_limits_and_lower_space', 'processed/active_constraints.csv', '按当前放电功率识别活跃界'),
 ('134 135 138 139 152', 'analysis.py', '"value_per_unit_day": saving / step', 'test_analysis.py', 'test_all_36_scenarios_and_432_relaxations', 'processed/bottleneck_values.csv', '四方向有限增量价值'),
 ('137', 'analysis.py', '"increment_period_kwh": step if parameter', 'test_analysis.py', 'test_all_36_scenarios_and_432_relaxations', 'processed/bottleneck_values.csv#increment_period_kwh', '功率扰动单位转换'),
 ('140 141', 'analysis.py', '"economic_significance": "not_assessed_no_economic_threshold"', 'test_review.py', 'test_active_sets_use_current_limits_and_lower_space', 'processed/bottleneck_values.csv#economic_significance', '概念比较；经济显著性未擅自设门槛'),
 ('142 148', 'model.py', '"roundtrip090": float(np.sqrt(0.90))', 'test_q1.py', 'test_all_actual_scenarios', 'processed/efficiency_comparison.csv', '效率情景'),
 ('143', 'analysis.py', 'return [{**r, "load_kw":', 'test_analysis.py', 'test_full_input_output_csv_and_normalized_sensitivity', 'raw/analysis_schedules.csv', '输入缩放'),
 ('144', 'analysis.py', '"load_deltas":', 'test_analysis.py', 'test_all_36_scenarios_and_432_relaxations', 'processed/sensitivity_scenarios.csv', '扰动网格'),
 ('145', 'model.py', '"cost_yuan": float(p @ g)', 'test_analysis.py', 'test_all_36_scenarios_and_432_relaxations', 'processed/sensitivity_scenarios.csv', '汇总电量和费用'),
 ('146', 'analysis.py', '"normalized_sensitivity": (plus', 'test_analysis.py', 'test_full_input_output_csv_and_normalized_sensitivity', 'processed/normalized_sensitivity.csv', '归一化敏感度'),
 ('149', 'export.py', '"12.4_cost_error_yuan":', 'test_review.py', 'test_official_attachment_fresh_solve_golden_and_csv', 'raw/validation.json#csv', '按用户要求改CSV关闭回读'),
 ('150 153 154', 'run.py', 'analysis = run_analysis(', 'test_review.py', 'test_pipeline_analysis_and_test_failure_do_not_publish', 'raw/run_manifest.json', '流程/章节小结；各计算公式见单独映射'),
]


INLINE = [
 ('I01', '进一步要求 $S_t>L_t', 'model.py', 'upper[index["G"][pv > load]] = 0', 'test_pv_only_source_with_zero_price_and_surplus', 'raw/analysis_validation.json#checks/pv_only', 'PV来源约束；两层基准共同施加'),
 ('I02', '二者首先由固定模式 LP', 'analysis.py', 'mu, lam = result.eqlin.marginals', 'test_independent_efficiencies_analytical_case', 'processed/marginal_values.csv', '母线RHS及状态注入RHS的导数符号'),
 ('I03', '直接固定求解器给出的空闲模式', 'analysis.py', 'changed["lb"][row] += sign * step', 'test_original_milp_rhs_all_576_results', 'processed/milp_rhs_validation.csv', '原MILP全部模式可重新选择的双侧扰动'),
 ('I04', '当三步单位价值的极差', 'analysis.py', 'stable = len(values) >= 3', 'test_active_sets_use_current_limits_and_lower_space', 'processed/bottleneck_values.csv', '多步长稳定性，不替代经济门槛'),
 ('I05', '上述数值容差不代表经济显著性。', 'analysis.py', '"economic_significance": "not_assessed_no_economic_threshold"', 'test_active_sets_use_current_limits_and_lower_space', 'processed/bottleneck_values.csv', '无经济门槛不作显著性结论'),
]


def unique_line(path, needle):
    lines = path.read_text(encoding='utf-8').splitlines()
    found = [(i, text) for i, text in enumerate(lines, 1) if needle in text]
    if len(found) != 1:
        raise ValueError(f'精确代码定位不唯一或已失效：{path}:{needle} ({len(found)})')
    return found[0]


def generate_traceability(staging):
    lines = (ROOT / PAPER).read_text(encoding='utf-8').splitlines()
    blocks, start = [], None
    for i, line in enumerate(lines, 1):
        if line.strip() == '$$':
            if start is None:
                start = i
            else:
                blocks.append((start, i, '\n'.join(lines[start:i - 1])))
                start = None
    if start is not None or len(blocks) != 154:
        raise ValueError('论文公式数量改变，必须逐公式重新审查映射')
    rows, covered = [], set()
    for ids, code, needle, test, test_name, evidence, meaning in GROUPS:
        line, statement = unique_line(ROOT / 'src/q1' / code, needle)
        test_line, _ = unique_line(ROOT / 'src/q1' / test, 'def ' + test_name + '(')
        if not (staging / evidence.split('#')[0]).exists():
            raise ValueError(f'缺失本轮运行证据：{evidence}')
        for number in map(int, ids.split()):
            first, last, formula = blocks[number - 1]
            covered.add(number)
            rows.append({'formula_id': f'F{number:03}', 'paper_path': PAPER, 'paper_start_line': first,
                         'paper_end_line': last, 'formula': formula, 'meaning': meaning,
                         'code_path': f'src/q1/{code}', 'code_line': line, 'code_statement': statement.strip(),
                         'unit_test_path': f'src/q1/{test}', 'unit_test_line': test_line,
                         'unit_test': test_name, 'runtime_evidence_in_generation': evidence})
    if covered != set(range(1, len(blocks) + 1)):
        raise ValueError(f'存在未映射展示公式：{set(range(1, len(blocks) + 1)) - covered}')
    for number, paper_needle, code, needle, test_name, evidence, meaning in INLINE:
        source_line, formula = unique_line(ROOT / PAPER, paper_needle)
        code_line, statement = unique_line(ROOT / 'src/q1' / code, needle)
        test_line, _ = unique_line(ROOT / 'src/q1/test_review.py', 'def ' + test_name + '(')
        if not (staging / evidence.split('#')[0]).exists():
            raise ValueError(f'缺失本轮运行证据：{evidence}')
        rows.append({'formula_id': number, 'paper_path': PAPER, 'paper_start_line': source_line,
                     'paper_end_line': source_line, 'formula': formula, 'meaning': meaning,
                     'code_path': f'src/q1/{code}', 'code_line': code_line, 'code_statement': statement.strip(),
                     'unit_test_path': 'src/q1/test_review.py', 'unit_test_line': test_line,
                     'unit_test': test_name, 'runtime_evidence_in_generation': evidence})
    write_csv(staging / 'docs/q1_source_line_traceability.csv', rows)
    write_json(staging / 'raw/traceability_validation.json', {'passed': True, 'display_formulas': len(blocks),
               'inline_items': len(INLINE), 'mapping_rows': len(rows), 'source_sha256': hashlib.sha256((ROOT / PAPER).read_bytes()).hexdigest(),
               'coverage': '154个展示公式及5项关键行内公式/判据；纯说明公式注明作用'})
