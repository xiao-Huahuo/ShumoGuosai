"""正式数据计算前固定的工程协议；题设参数仅定义在policy.py。"""

from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parents[2]
PLAN = ROOT / "docs/2/final/第二问_最终建模思路_最高优先级修订版_修订后.md"
# 以下为方案要求预注册但没有指定数值的数值计算设置，不是题设事实。
PROTOCOL = {
    "version": "q2-final-20260911",
    "history_boundary": "source_date_before_origin",
    "boundary_authority": "current_user_requests_exclusive_execution_of_new_plan_section_2.2.3_j_less_than_d",
    "forecast_horizons": [1, 2, 3], "warm_horizon": 2,
    "shadow_start": "2025-01-15", "evaluation_start": "2025-02-01",
    "minimum_blocks": 14, "history_windows_days": [28, 56, 84, None],
    "scenario_max": 40, "scenario_candidates": [10, 20, 40],
    "solver_gap": 0.01, "solver_seconds": 120.0,
    "stability_objective_relative": 0.01, "stability_grid_relative": 0.02,
    "tail_quantile_relative": 0.05, "full_pool_emergency_relative": 0.05,
    "selection_relative_tolerance": 0.01,
    "lightgbm_candidates": [
        {"num_leaves": 7, "n_estimators": 100, "learning_rate": 0.05,
         "max_depth": -1, "min_child_samples": 20, "reg_lambda": 1.0},
        {"num_leaves": 15, "n_estimators": 100, "learning_rate": 0.05,
         "max_depth": -1, "min_child_samples": 20, "reg_lambda": 1.0}],
    "lightgbm_training_window": "expanding", "lightgbm_freeze_metric": "January_h0_load_MAE",
    "dhr_harmonics": [3, 6], "dhr_ar_orders": [0, 1], "dhr_ma_orders": [0, 1],
    "dhr_history_days": 28, "dhr_order_rule": "BIC_then_AIC_then_lower_complexity",
    "dhr_max_iterations": 100, "dhr_difference_order": 0,
    "selection_history": "common_complete_origins_in_selected_window",
    "soc_segments": [0, 1/3, 2/3, 1],
    "specified_dates": ["2025-03-20", "2025-06-21", "2025-09-23", "2025-12-21"],
    "high_variation_dates_count": 3,
    "numerical_settings_origin": "implementation_preregistered_before_formal_backtest_not_problem_facts",
}


def signature():
    payload = json.dumps(PROTOCOL, sort_keys=True).encode("utf-8") + PLAN.read_bytes()
    return hashlib.sha256(payload).hexdigest()
