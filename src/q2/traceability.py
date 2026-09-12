"""原方案每个非空内容源行/句子均关联实际函数位置、测试和产物。"""

import ast
import re

import pandas as pd

from data import ROOT, write_csv

MAPPING = {
    "2.1": ("run.py:run_pipeline", "test_generated_artifacts_roundtrip", "report.html;results.md"),
    "2.1.1": ("data.py:history_before;backtest.py:rolling_predict", "test_future_and_midnight_perturbation_cannot_change_prediction", "rolling_folds.csv"),
    "2.1.2": ("data.py:read_attachment;data.py:calendar_for_day", "test_original_values_and_quality", "timeseries.csv"),
    "2.1.3": ("data.py:endpoint_minutes;data.py:calendar_for_day;backtest.py:dispatch_metrics", "test_right_endpoint_and_calendar", "timeseries.csv;rolling_folds.csv"),
    "2.1.4": ("data.py:read_attachment;data.py:jump_context", "test_original_values_and_quality;test_missing_and_nonfinite_rejected;test_negative_physical_values_rejected;test_duplicate_and_missing_dates_rejected;test_duplicate_missing_and_wrong_endpoints_rejected", "quality_checks.csv;jump_context.csv;full_year_pv_zero_profile.csv"),
    "2.1.5": ("data.py:read_attachment;diagnostics.py:describe;backtest.py:forecast_metrics", "test_original_values_and_quality;test_forecast_metrics_hand_calculation", "timeseries.csv;full_year_daily_statistics.csv;full_year_profiles.csv"),
    "2.1.6": ("diagnostics.py:describe;../plots/q2.py:create_figures", "test_monthly_and_weekday_profiles_and_stability;test_generated_artifacts_roundtrip", "figures/timeseries_7d.png;figures/timeseries_30d.png;figures/annual_heatmaps.png;figures/monthly_profiles.png;figures/weekday_profiles.png;figures/weekday_weekend.png"),
    "2.1.7": ("diagnostics.py:lag_analysis", "test_acf_and_pacf_computed_through_weekly_lags", "full_year_lag_correlations.csv;initial_history_lag_correlations.csv"),
    "2.1.8": ("diagnostics.py:lag_analysis;../plots/q2.py:create_figures", "test_acf_and_pacf_computed_through_weekly_lags", "full_year_acf_pacf.csv;figures/acf_pacf.png"),
    "2.1.9": ("diagnostics.py:spectral_analysis;../plots/q2.py:create_figures", "test_spectrum_known_daily_weekly_peaks_and_parseval", "full_year_spectrum.csv;full_year_spectral_targets.csv;figures/spectra.png"),
    "2.1.10": ("diagnostics.py:stability_analysis;../plots/q2.py:create_figures", "test_monthly_and_weekday_profiles_and_stability", "full_year_monthly_stability.csv;figures/monthly_stability.png"),
    "2.1.11": ("diagnostics.py:seasonal_transforms;diagnostics.py:stationarity_analysis;../plots/q2.py:create_figures", "test_transforms_match_four_term_identity;test_constant_series_not_reported_as_significant;test_generated_artifacts_roundtrip", "full_year_stationarity_tests.csv;full_year_transformed_series.csv;full_year_transformed_monthly_moments.csv;figures/seasonal_moments.png"),
    "2.1.12": ("backtest.py:rolling_folds;backtest.py:rolling_predict", "test_strict_midnight_and_334_folds;test_new_model_per_variable_per_day;test_invalid_predictions_rejected;test_future_and_midnight_perturbation_cannot_change_prediction", "rolling_folds.csv"),
    "2.1.13": ("backtest.py:forecast_metrics;backtest.py:dispatch_metrics;report.py:create_report", "test_forecast_metrics_hand_calculation;test_dispatch_metrics_plan_billing_and_fivefold_emergency;test_cross_midnight_emergency_is_one_contiguous_event", "evaluation_status.csv;report.html"),
    "2.1.14": ("report.py:candidate_models;report.py:result_text", "test_candidate_guard_rejects_full_year_information", "model_candidates.csv;results.md"),
    "2.1.15": ("run.py:run_pipeline", "test_generated_artifacts_roundtrip", "report.html;results.md"),
}


def generate_traceability(output):
    positions = {}
    for path in [*(ROOT / "src/q2").glob("*.py"), ROOT / "src/plots/q2.py"]:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                relative = str(path.relative_to(ROOT / "src"))
                key = "../plots/q2.py" if relative == "plots/q2.py" else path.name
                positions[f"{key}:{node.name}"] = f"src/{relative}:{node.lineno}-{node.end_lineno}"
    rows, section = [], None
    for line_number, line in enumerate((ROOT / "docs/2/dierwen1.md").read_text(encoding="utf-8").splitlines(), 1):
        match = re.search(r"^#{2,3}\s+(2\.1(?:\.\d+)?)", line)
        if match:
            section = match.group(1)
        if not line.strip():
            continue
        if section not in MAPPING:
            raise ValueError(f"源行{line_number}无逐句映射")
        functions, tests, artifacts = MAPPING[section]
        source_refs = ";".join(positions[f] for f in functions.split(";"))
        test_refs = ";".join(positions[f"test_q2.py:{t}"] for t in tests.split(";"))
        for artifact in artifacts.split(";"):
            if not (output / artifact).is_file():
                raise ValueError(f"验收证据缺失：{artifact}")
        for sentence in filter(str.strip, re.split(r"(?<=[。；！？])", line)):
            rows.append({"source_file": "docs/2/dierwen1.md", "source_line": line_number,
                         "section": section, "source_text": sentence, "implementation": source_refs,
                         "tests": test_refs, "runtime_evidence": artifacts,
                         "status": "protocol_and_interfaces_complete_real_metrics_pending_model" if section == "2.1.13" else
                         "conditional_candidates_no_fitted_model" if section == "2.1.14" else "implemented_and_checked"})
    write_csv(output / "source_traceability.csv", pd.DataFrame(rows))
    return {"mapped_source_lines": len({r["source_line"] for r in rows}), "mapped_sentence_rows": len(rows), "sections": len(MAPPING)-1}
