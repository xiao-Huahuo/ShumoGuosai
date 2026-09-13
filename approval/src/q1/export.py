"""用户指定 CSV 的写入—关闭—回读检查。"""

import csv
import tempfile
from pathlib import Path

import numpy as np

from model import PHYS_TOL_KWH, COST_TOL_YUAN, BINARY_TOL, DIMENSIONLESS_TOL, TOLERANCES, T, arrays, block_rows, check_solution, schedule_rows, summary, write_csv


def read_csv(path):
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def check_csv_output(directory, data, solution):
    rows = read_csv(directory / "result1.csv")
    blocks = read_csv(directory / "table2_storage.csv")
    daily = read_csv(directory / "daily_summary.csv")
    table1 = read_csv(directory / "table1_purchase.csv")
    if len(rows) != T or [r["interval"] for r in rows] != [r["interval"] for r in data]:
        raise ValueError("CSV必须具有144个正确的右端点映射时间段")
    expected_rows = schedule_rows(data, solution)
    if list(rows[0]) != list(expected_rows[0]):
        raise ValueError("CSV字段缺失或顺序不符")
    for actual, expected in zip(rows, expected_rows):
        for key in data[0]:
            if actual[key] != str(expected[key]):
                raise ValueError(f"CSV输入来源字段不一致：{key}")
    reread = {**solution}
    try:
        for name in ("G", "C", "D", "E", "W"):
            reread[name] = [float(row[f"{name}_kwh"]) for row in rows]
        reread["u"] = [float(row["u"]) for row in rows]
        reread["E0"] = float(rows[0]["E_start_kwh"])
        g = np.array(reread["G"])
        if len(daily) != 1 or list(daily[0]) != list(summary(data, solution)):
            raise ValueError("日汇总表字段不符")
        day = {k: float(v) if v else None for k, v in daily[0].items()}
        expected_day = summary(data, solution)
        if any(day[k] is None or not np.isfinite(day[k]) for k, v in expected_day.items() if v is not None):
            raise ValueError("日汇总含缺失或非有限结果")
        if any(not np.isfinite(float(r[k])) for r in rows
               for k in ("E_start_kwh", "soc_fraction", "cost_yuan")):
            raise ValueError("逐时派生结果含非有限值")
        values = np.array([[float(b["charge_kwh"]), float(b["discharge_kwh"])] for b in blocks])
        if not all(np.isfinite(float(row["grid_kwh"])) for row in table1):
            raise ValueError("表1含非有限值")
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("CSV含缺失或非数值结果") from exc
    expected_blocks = block_rows(solution)
    if [r["interval"] for r in blocks] != [r["interval"] for r in expected_blocks]:
        raise ValueError("4小时汇总区间不符")
    if [r["interval"] for r in table1] != [data[h * 6]["interval"] for h in (10, 12, 14, 16, 18, 20)]:
        raise ValueError("表1指定区间不符")
    physical = check_solution(data, reread)
    p, _, _ = arrays(data)
    metrics = {
        "12.1_count_error": abs(len(rows) - T),
        "12.2_all_variables_max_abs_error": max(float(np.max(np.abs(np.array(reread[k]) - solution[k]))) for k in ("G", "C", "D", "E", "W", "u")),
        "12.3_grid_day_error_kwh": float(abs(g.sum() - day["grid_kwh"])),
        "12.4_cost_error_yuan": float(abs(p @ g - day["cost_yuan"])),
        "12.5_block_max_abs_error_kwh": float(np.max(np.abs(values - [[b["charge_kwh"], b["discharge_kwh"]] for b in expected_blocks]))),
        "12.6_endpoint_max_abs_error_kwh": max(abs(day["initial_kwh"] - solution["E0"]), abs(day["terminal_kwh"] - solution["E"][-1])),
        "daily_summary_max_abs_error": max(abs(day[k] - v) for k, v in expected_day.items() if v is not None),
        "table1_max_abs_error_kwh": max(abs(float(row["grid_kwh"]) - solution["G"][h * 6]) for row, h in zip(table1, (10, 12, 14, 16, 18, 20))),
        "start_state_max_abs_error_kwh": max(abs(float(r["E_start_kwh"]) - e["E_start_kwh"]) for r, e in zip(rows, expected_rows)),
        "soc_fraction_max_abs_error": max(abs(float(r["soc_fraction"]) - e["soc_fraction"]) for r, e in zip(rows, expected_rows)),
        "period_cost_max_abs_error_yuan": max(abs(float(r["cost_yuan"]) - e["cost_yuan"]) for r, e in zip(rows, expected_rows)),
    }
    tolerances = {k: COST_TOL_YUAN if k.endswith("_yuan") else
                  DIMENSIONLESS_TOL if k == "soc_fraction_max_abs_error" else PHYS_TOL_KWH for k in metrics}
    # 分开检查不同单位的字段，不让汇总最大值掩盖更严格的二元/比率容差。
    for actual, expected in zip(rows, expected_rows):
        for key, tolerance in (("u", BINARY_TOL), ("soc_fraction", DIMENSIONLESS_TOL), ("cost_yuan", COST_TOL_YUAN)):
            if abs(float(actual[key]) - expected[key]) > tolerance:
                raise ValueError(f"CSV字段超出量纲容差：{key}")
    for key, value in expected_day.items():
        tol = (COST_TOL_YUAN if key == "cost_yuan" else DIMENSIONLESS_TOL if key in
               ("eta_c", "eta_d", "roundtrip_efficiency") else PHYS_TOL_KWH)
        if value is not None and abs(day[key] - value) > tol:
            raise ValueError(f"日汇总字段超出量纲容差：{key}")
    if any(not np.isfinite(v) or v > tolerances[k] for k, v in metrics.items()):
        raise ValueError(f"CSV回读一致性检查失败：{metrics}")
    return {"passed": True, "tolerances": TOLERANCES, "metric_tolerances": tolerances, "metrics": metrics, "reread_physical": physical,
            "reread_grid_kwh": float(g.sum()), "reread_cost_yuan": float(p @ g),
            "reread_initial_kwh": reread["E0"], "reread_terminal_kwh": reread["E"][-1]}


def export_csv_output(directory, data, solution):
    # 暂存CSV通过关闭后的回读核验，才替换本次正式结果。
    with tempfile.TemporaryDirectory(prefix=".q1-csv-", dir=directory.parent) as temporary:
        staging = Path(temporary)
        write_csv(staging / "result1.csv", schedule_rows(data, solution))
        write_csv(staging / "daily_summary.csv", [summary(data, solution)])
        write_csv(staging / "table2_storage.csv", block_rows(solution))
        write_csv(staging / "table1_purchase.csv", [
            {"interval": data[h * 6]["interval"], "grid_kwh": solution["G"][h * 6]}
            for h in (10, 12, 14, 16, 18, 20)])
        check_csv_output(staging, data, solution)
        for path in staging.iterdir():
            path.replace(directory / path.name)
    return check_csv_output(directory, data, solution)
