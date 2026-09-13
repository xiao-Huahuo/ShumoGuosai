"""逐条保留模型源文与代码/验收对应；结构覆盖不冒充全年数值验证。"""
import ast
import hashlib
import re
from pathlib import Path
import pandas as pd
from .config import ROOT, SOURCE, write_csv, write_json

# source section -> concrete implementation symbols, acceptance mechanism.
MAPPING = {
    '3.1': ('rolling.run_day;optimization.solve;analysis.run_experiments', '四节点真实回放和分层实验入口'),
    '3.2': ('optimization.solve;multistage.solve_tree;analysis.run_experiments', 'test_actual_small_multistage_solve'),
    '3.3': ('data.Inputs;terminal.TerminalValues;rolling.run_period', 'test_future_poison_not_used_by_node;test_cold_start_no_future_or_soc_reset;test_terminal_causal_and_delta_stability'),
    '3.4': ('config.Config;physics.replay', 'test_energy_balance_saturation'),
    '3.5': ('data.read_inputs', 'test_origin_alignment_and_nodes'),
    '3.6': ('data.Inputs', 'test_origin_alignment_and_nodes;test_pchip_preserves_hourly_knots'),
    '3.7': ('data.Inputs;data.read_inputs', 'test_48h_predictor_identity_frozen;test_completed_trajectory_horizon'),
    '3.8': ('scenarios.construct;scenarios.pool_indices;scenarios.reduce_errors;scenarios.medoids', 'test_recent_then_expand_and_condition;test_reduction_probability_tail_original_support;test_no_artificial_samples'),
    '3.9': ('physics.adjustment;rolling.run_day', 'test_settlement_cancellation_and_repeated_proxy'),
    '3.10': ('physics.no_storage_decision', 'test_no_storage_deadband；只作退化解释，不施加于完整模型'),
    '3.11': ('rolling.run_day', 'test_real_day_rollout_and_template'),
    '3.12': ('rolling.run_day', 'test_real_day_rollout_and_template'),
    '3.13': ('optimization.solve;physics.Policy', 'test_exact_milp_matches_fixed_min'),
    '3.14': ('optimization.add_path;physics.replay', 'test_exact_milp_matches_fixed_min'),
    '3.15': ('optimization.add_path;physics.validate;rolling.validate_frame', 'test_energy_balance_saturation'),
    '3.16': ('optimization.solve;optimization.objective', 'test_solution_objective_uses_residual_not_real_cost'),
    '3.17': ('optimization.scheduled_cost;optimization.add_path;optimization.solve', 'test_exact_milp_matches_fixed_min;test_settlement_cancellation_and_repeated_proxy'),
    '3.18': ('rolling.run_day', 'test_real_day_rollout_and_template'),
    '3.19': ('physics.replay;rolling.frame_for', 'test_energy_balance_saturation;test_real_day_rollout_and_template'),
    '3.20': ('physics.replay;optimization.add_path', 'test_lag_does_not_observe_current;test_exact_milp_matches_fixed_min'),
    '3.21': ('physics.adjustment;rolling.validate_frame;export.summaries', 'test_settlement_cancellation_and_repeated_proxy;test_solution_objective_uses_residual_not_real_cost'),
    '3.22': ('rolling.fiv;analysis.information_summary;analysis.paired_summary', 'test_fiv_common_support_and_state_independence；全年FIV/OUV按用户指令未执行'),
    '3.23': ('multistage.conditional_tree;multistage.solve_tree;multistage.replay_tree;analysis.stress_dates;analysis.run_experiments', 'test_tree_conditioning_and_uncertainty;test_actual_small_multistage_solve；正式stress集合未全跑'),
    '3.24': ('analysis.forecast_diagnostics', 'diagnostics/forecast_metrics.csv、forecast_block_mae.csv及真实渲染热图'),
    '3.25': ('analysis.variants;analysis.run_experiments', '所有配置入口已实现；完整事后实验按用户指令未执行'),
    '3.26': ('rolling.validate_frame;physics.validate;config.Config;multistage.conditional_tree;data.Inputs', 'tests.txt；未来污染、冻结策略、费用、SOC、模板、树结构实际核验'),
    '3.27': ('export.export_workbook;export.emergency_events;export.write_tables', 'test_real_day_rollout_and_template；正式334天工作簿未生成'),
    '3.28': ('rolling.run_period;run.main;analysis.run_experiments', '命令行默认benchmark；full显式隔离；test_real_day_rollout_and_template'),
    '3.29': ('run.main;analysis.run_experiments', '整体结构总结，数值结论等待授权全量后按实际结果生成'),
}


def generate() -> dict:
    source_lines = SOURCE.read_text(encoding='utf-8').splitlines()
    symbols = {}
    for path in (ROOT/'src/q3').glob('*.py'):
        for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
            if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                symbols[f'{path.stem}.{node.name}'] = f'{path.relative_to(ROOT)}:{node.lineno}'
    rows, section = [], '3.1'
    for line_no, content in enumerate(source_lines, 1):
        match = re.match(r'#+\s+(3\.\d+)', content)
        if match:
            section = match.group(1)
        if not content.strip():
            continue
        implementations, validation = MAPPING[section]
        references = [symbols[symbol] for symbol in implementations.split(';')]
        rows.append({'requirement_id': f'Q3-L{line_no:04d}', 'section': section, 'source_line': line_no,
                     'source_text': content, 'implementation_symbols': implementations,
                     'code_locations': ';'.join(references), 'acceptance': validation,
                     'status': 'implemented; bounded-tests-only; full-numerical-evaluation-not-run'})
    frame = pd.DataFrame(rows)
    write_csv(ROOT/'docs/3/source_line_acceptance.csv', frame)
    files = sorted((ROOT/'src/q3').glob('*.py'))+[ROOT/'src/plots/q3.py']
    audit = {'source_lines': len(source_lines), 'nonblank_lines_mapped': len(rows),
             'all_nonblank_source_lines_covered': len(rows) == sum(bool(line.strip()) for line in source_lines),
             'sections': sorted(set(frame.section), key=lambda s: int(s.split('.')[1])),
             'all_symbols_resolve': True, 'full_run_executed': False,
             'limits': '逐行映射提供定位；公式语义由人工逐节复核及独立数学/真实小样本测试补足，不宣称仅靠存在性证明正确。',
             'source_sha256': hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
             'code_sha256': {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in files}}
    write_json(ROOT/'docs/3/traceability_audit.json', audit)
    return audit


if __name__ == '__main__':
    print(generate())
