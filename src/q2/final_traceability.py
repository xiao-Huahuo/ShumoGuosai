"""最终方案逐源行/句子追溯；代码定位与真实验收分列，文件存在不等于模型已通过。"""

import ast
import re
from functools import lru_cache
from pathlib import Path

import pandas as pd

from data import ROOT, sha256, write_csv, write_json
from protocol import PLAN

# 逐节审查后的语义对应；展示公式每行保留原文，禁止沿用旧方案的265句验收。
RULES = {
    "2.1": ("rolling.py#run_rollout;policy.py#respond;optimization.py#build_model", "test_dispatch.py#test_load_priority_and_soc_clipping", "main"),
    "2.2": ("dispatch.py#input_data", "test_q2.py#Q2Tests", "prepare"),
    "2.2.1": ("data.py#read_attachment;dispatch.py#input_data", "test_q2.py#Q2Tests", "prepare"),
    "2.2.2": ("data.py#calendar_for_day;policy.py#respond", "test_dispatch.py#test_load_priority_and_soc_clipping", "prepare"),
    "2.2.3": ("shadows.py#build_shadow_library;rolling.py#run_rollout;shadows.py#choose_day", "test_forecast_dispatch.py#test_execution_cannot_call_optimizer_and_prefix_cannot_see_future", "forecast"),
    "2.2.4": ("data.py#read_attachment;data.py#jump_context", "test_q2.py#Q2Tests", "prepare"),
    "2.2.5": ("rolling.py#warm_start;experiments.py#run_experiments", "test_forecast_dispatch.py#test_deterministic_certificate_matches_exact_model", "warm_and_initials"),
    "2.3": ("final_diagnostics.py#descriptive_corrections", "test_q2.py#Q2Tests", "diagnostic"),
    "2.3.1": ("../plots/q2.py#create_figures;diagnostics.py#describe", "test_q2.py#Q2Tests", "diagnostic"),
    "2.3.2": ("diagnostics.py#lag_analysis;../plots/q2.py#create_figures", "test_q2.py#Q2Tests", "diagnostic"),
    "2.3.3": ("final_diagnostics.py#descriptive_corrections;forecast.py#harmonic_forecast", "test_forecast_dispatch.py#test_dhr_orders_and_diagnostics_use_fixed_dictionary", "diagnostic"),
    "2.3.4": ("diagnostics.py#spectral_analysis;../plots/q2.py#create_figures", "test_q2.py#test_spectrum_known_daily_weekly_peaks_and_parseval", "diagnostic"),
    "2.3.5": ("diagnostics.py#stability_analysis;final_diagnostics.py#descriptive_corrections", "test_q2.py#Q2Tests", "diagnostic"),
    "2.3.6": ("final_diagnostics.py#descriptive_corrections;../plots/q2_dispatch.py#create", "test_q2.py#test_transforms_match_four_term_identity", "diagnostic"),
    "2.4": ("forecast.py#seasonal;experiments.py#forecast_audit", "test_forecast_dispatch.py#ForecastTests", "forecast"),
    "2.4.1": ("forecast.py#seasonal;experiments.py#structural_rollout;experiments.py#forecast_audit", "test_forecast_dispatch.py#test_recursive_seasonal_uses_its_own_previous_prediction", "structure"),
    "2.4.2": ("forecast.py#load_features;forecast.py#lightgbm_forecast;shadows.py#freeze_lightgbm", "test_forecast_dispatch.py#test_exact_eight_load_features_and_actual_candidate;test_forecast_dispatch.py#test_freezing_cannot_use_february_hyperparameter_performance", "forecast"),
    "2.4.3": ("forecast.py#harmonic_forecast;shadows.py#choose_day;protocol.py#PROTOCOL;experiments.py#run_experiments", "test_forecast_dispatch.py#test_dhr_orders_and_diagnostics_use_fixed_dictionary", "predictor_economics"),
    "2.4.4": ("shadows.py#choose_day;forecast.py#economic_metrics;forecast.py#select_pipeline", "test_forecast_dispatch.py#test_four_to_one_loss_and_lexicographic_selection;test_forecast_dispatch.py#test_real_selection_metadata_serializes_numpy_origin_indices", "forecast_and_main"),
    "2.5": ("shadows.py#build_shadow_library;scenarios.py#joint_blocks", "test_dispatch.py#ScenarioTests", "scenarios"),
    "2.5.1": ("shadows.py#build_shadow_library;shadows.py#choose_day;scenarios.py#joint_blocks", "test_dispatch.py#test_complete_origin_horizon_and_window_fallback", "scenarios"),
    "2.5.2": ("scenarios.py#eligible_origins;scenarios.py#history_window", "test_dispatch.py#test_complete_origin_horizon_and_window_fallback", "scenarios"),
    "2.5.3": ("scenarios.py#history_window;shadows.py#choose_day", "test_dispatch.py#test_complete_origin_horizon_and_window_fallback", "scenarios"),
    "2.5.4": ("scenarios.py#joint_blocks;scenarios.py#construct", "test_dispatch.py#test_no_bootstrap_below_forty_and_physical_projection", "scenarios"),
    "2.5.5": ("scenarios.py#medoids;scenarios.py#construct;rolling.py#select_resolution", "test_dispatch.py#test_tail_protection_and_cluster_probability", "scenario_sensitivity"),
    "2.6": ("forecast.py#economic_metrics;scenarios.py#weighted_quantile;experiments.py#no_storage_quantile", "test_dispatch.py#test_no_storage_optimizer_is_eighty_percent_quantile;test_dispatch.py#test_weighted_quantile_uses_discrete_probability", "quantile"),
    "2.7": ("policy.py#Policy;policy.py#respond;optimization.py#build_model", "test_dispatch.py#PolicyTests", "main"),
    "2.7.1": ("rolling.py#make_day;rolling.py#run_rollout", "test_forecast_dispatch.py#RollingTests", "horizons"),
    "2.7.2": ("policy.py#Policy;optimization.py#build_model;rolling.py#run_rollout", "test_dispatch.py#test_frozen_parameters_and_causal_prefix", "main"),
    "2.7.3": ("policy.py#respond;optimization.py#build_model", "test_dispatch.py#test_load_priority_and_soc_clipping;test_dispatch.py#test_exact_indicator_mapping_fixed_random_paths", "main"),
    "2.7.4": ("policy.py#respond;policy.py#validate_replay;optimization.py#build_model", "test_dispatch.py#test_exact_indicator_mapping_fixed_random_paths", "main"),
    "2.7.5": ("policy.py#respond;policy.py#validate_replay;optimization.py#build_model", "test_dispatch.py#test_load_priority_and_soc_clipping", "main"),
    "2.7.6": ("optimization.py#build_model;optimization.py#solve_policy;optimization.py#certify_policy;relaxation.py#recourse_bound;linear_policy.py#build_linear_policy;linear_policy.py#solve_linear_policy", "test_dispatch.py#test_unfixed_policy_replay_matches_solver;test_forecast_dispatch.py#test_lower_bound_is_not_executed_and_oracles_are_nested;test_linear_policy.py#LinearPolicyTests", "compute"),
    "2.8": ("optimization.py#build_model;optimization.py#solve_policy", "test_dispatch.py#test_unfixed_policy_replay_matches_solver", "main"),
    "2.8.1": ("optimization.py#build_model;rolling.py#make_day;linear_policy.py#build_linear_policy", "test_dispatch.py#test_unfixed_policy_replay_matches_solver;test_linear_policy.py#test_maximum_charge_cap_dominates_for_each_realized_step", "main"),
    "2.8.2": ("optimization.py#solve_policy", "", "optional_cvar"),
    "2.9": ("rolling.py#run_rollout;export_dispatch.py#export_result", "test_forecast_dispatch.py#ExportTests;test_forecast_dispatch.py#RollingTests", "main"),
    "2.9.1": ("rolling.py#warm_start;shadows.py#build_shadow_library", "test_forecast_dispatch.py#test_deterministic_certificate_matches_exact_model", "warm"),
    "2.9.2": ("rolling.py#make_day;rolling.py#run_rollout;checkpoint.py#read_checkpoint", "test_forecast_dispatch.py#RollingTests", "main"),
    "2.9.3": ("rolling.py#dispatch_frame;export_dispatch.py#emergency_events;export_dispatch.py#export_result", "test_forecast_dispatch.py#test_complete_template_roundtrip_and_partial_rejection;test_forecast_dispatch.py#test_cross_midnight_events_and_empty_events", "export"),
    "2.10": ("experiments.py#run_experiments", "test_forecast_dispatch.py#ComparatorTests", "experiments"),
    "2.10.1": ("experiments.py#forecast_audit;shadows.py#choose_day", "test_forecast_dispatch.py#ForecastTests;test_forecast_dispatch.py#RollingTests", "forecast_and_main"),
    "2.10.2": ("experiments.py#forecast_audit;rolling.py#run_rollout", "test_dispatch.py#test_complete_origin_horizon_and_window_fallback", "calibration"),
    "2.10.3": ("rolling.py#select_resolution;scenarios.py#quantile_comparison;experiments.py#scenario_audit;experiments.py#run_experiments", "test_dispatch.py#test_tail_protection_and_cluster_probability", "scenario_sensitivity"),
    "2.10.4": ("experiments.py#run_experiments;scenarios.py#eligible_origins", "test_dispatch.py#test_complete_origin_horizon_and_window_fallback", "minimums"),
    "2.10.5": ("rolling.py#dispatch_frame;comparators.py#rigid_schedule;experiments.py#run_experiments", "test_forecast_dispatch.py#test_execution_cannot_call_optimizer_and_prefix_cannot_see_future", "ablations"),
    "2.10.6": ("rolling.py#warm_start;experiments.py#run_experiments", "test_forecast_dispatch.py#test_resume_replays_frozen_policy_and_rejects_corrupted_checkpoint", "initials"),
    "2.10.7": ("rolling.py#make_day;experiments.py#run_experiments", "test_forecast_dispatch.py#test_real_selection_metadata_serializes_numpy_origin_indices", "horizons"),
    "2.10.8": ("experiments.py#no_storage_quantile;scenarios.py#weighted_quantile", "test_dispatch.py#test_no_storage_optimizer_is_eighty_percent_quantile", "quantile"),
    "2.10.9": ("experiments.py#run_experiments;comparators.py#rigid_schedule", "test_forecast_dispatch.py#ComparatorTests", "ablations"),
    "2.10.10": ("experiments.py#richer_policy_diagnostic;optimization.py#build_model;policy.py#respond", "test_forecast_dispatch.py#test_richer_policy_contains_main_policy_at_soc_boundaries", "richer"),
    "2.10.11": ("comparators.py#oracle_pair;experiments.py#run_experiments", "test_forecast_dispatch.py#test_lower_bound_is_not_executed_and_oracles_are_nested", "oracles"),
    "2.11": ("dispatch.py#run_main;experiments.py#run_experiments;policy.py#respond", "test_dispatch.py#PolicyTests;test_forecast_dispatch.py#RollingTests", "all"),
}


@lru_cache(maxsize=None)
def locate(references):
    result = []
    for item in filter(None, references.split(";")):
        filename, symbol = item.split("#")
        path = (ROOT/"src/q2"/filename).resolve()
        tree = ast.parse(path.read_text(encoding="utf-8"))
        matches = [node for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name == symbol]
        if not matches:
            matches = [node for node in ast.walk(tree) if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == symbol for t in node.targets)]
        if len(matches) != 1:
            raise ValueError(f"追溯符号不存在或不唯一：{item}")
        result.append(f"{path.relative_to(ROOT)}:{matches[0].lineno}#{symbol}")
    return ";".join(result)


def build(output, evidence):
    rows = []
    section, math = "2.1", False
    for number, raw in enumerate(PLAN.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line:
            continue
        heading = re.match(r"^#{2,3}\s+(2\.\d+(?:\.\d+)?)\s", line)
        if heading:
            section = heading[1]
        if line == "$$":
            math = not math
        markup = line.startswith("#") or line in ("$$", "---")
        kind = "markup" if markup else "formula_line" if math else "sentence"
        sentences = [line] if kind != "sentence" else [s.strip() for s in re.split(r"(?<=[。！？；])", line) if s.strip()]
        code, tests, criterion = RULES[section]
        state = evidence.get(criterion, {"accepted": False, "reason": "待真实运行验收", "artifacts": []})
        for i, sentence in enumerate(sentences, 1):
            rows.append({"id": f"Q2F-L{number:04d}-S{i}", "source_line": number, "section": section,
                         "kind": kind, "source_text": sentence, "code_locations": locate(code),
                         "test_locations": locate(tests), "criterion": criterion,
                         "implementation_linked": True, "real_acceptance": bool(state["accepted"]),
                         "evidence": ";".join(state.get("artifacts", [])), "acceptance_note": state["reason"]})
    frame = pd.DataFrame(rows)
    required = {i for i, line in enumerate(PLAN.read_text(encoding="utf-8").splitlines(), 1) if line.strip()}
    if set(frame.source_line) != required or frame.id.duplicated().any():
        raise ValueError("逐句矩阵未覆盖全部非空源行或存在重复编号")
    write_csv(output/"source_sentence_traceability.csv", frame)
    write_json(output/"traceability_audit.json", {"plan_sha256": sha256(PLAN), "nonempty_source_lines": len(required),
                                                  "records": len(frame), "source_coverage": 1.0,
                                                  "unaccepted_records": int((~frame.real_acceptance).sum()),
                                                  "scope": "code_links_and_evidence_status_do_not_imply_unrun_experiments_passed"})
    return frame
