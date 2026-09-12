"""一条命令：附件→MILP→分析→CSV→回读→当前代码测试→原子发布。"""

import argparse
import datetime as dt
import hashlib
import platform
import shutil
import sys
import tempfile
from pathlib import Path

import numpy as np
import openpyxl
import scipy

from export import export_csv_output
from model import (DT, TOLERANCES, E_INITIAL, E_MAX, E_MIN, Q_MAX, ROOT, SCENARIOS,
                   arrays, check_solution, read_inputs, schedule_rows,
                   solve, summary, write_csv, write_json)
from report import create_report
from analysis import ANALYSIS_SETTINGS, run_analysis
from analysis_report import create_analysis_report
from traceability import generate_traceability
from pipeline import publish_generation, render_figures, run_tests


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_pipeline(root=ROOT, plots=True):
    root = Path(root).resolve()
    started = dt.datetime.now(dt.timezone.utc).isoformat()
    source = root / "docs/CUMCM2026Problems/C题/附件"
    generations = root / "outputs/.q1-runs"
    generations.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix="run-", dir=generations))
    try:
        input_raw, input_processed = staging / "inputs/raw", staging / "inputs/processed"
        output_raw, output, documents = staging / "raw", staging / "processed", staging / "docs"
        for directory in (input_raw, input_processed, output_raw, output, documents):
            directory.mkdir(parents=True)
        provenance = []
        for name, original in {"attachment1.xlsx": source / "附件1.xlsx"}.items():
            copied = input_raw / name
            shutil.copy2(original, copied)
            if sha256(original) != sha256(copied):
                raise ValueError("原始输入副本校验失败")
            provenance.append({"source": str(original.relative_to(root)),
                               "copy": f"inputs/q1/raw/{name}", "sha256": sha256(copied)})
        data = read_inputs(input_raw / "attachment1.xlsx")
        write_csv(input_raw / "attachment1.csv", [{k: r[k] for k in
                  ("source_endpoint", "price_yuan_per_kwh", "load_kw", "pv_kw")} for r in data])
        write_csv(input_processed / "timeseries.csv", data)
        params = {"model_source": "docs/1/final/第一问_MILP_边际价值强化版.md", "period_count": 144,
                  "dt_hours": DT, "max_power_kw": 5000, "max_energy_kwh": Q_MAX,
                  "max_energy_precision_decision": "5000×1/6准确计算及验收；833.3333仅用于显示",
                  "rated_capacity_kwh": 12000, "min_energy_kwh": E_MIN, "max_storage_kwh": E_MAX,
                  "initial_and_terminal_kwh": E_INITIAL, "tolerances": TOLERANCES,
                  "efficiency_scenarios": SCENARIOS, "delivery_format": "用户明确要求仅CSV；review中的XLSX建议不采用",
                  "analysis_settings": ANALYSIS_SETTINGS,
                  "assumptions": ["右端点标记", "10分钟内零阶保持", "充放电量为微网母线侧",
                                  "主模型双单程效率均0.9；函数支持独立效率", "不售电且允许弃光",
                                  "只最小化购电费，无二级目标", "无经济显著性门槛时不判断投资意义"]}
        write_json(input_processed / "parameters.json", params)
        write_json(input_raw / "manifest.json", provenance)
        solutions, validation, summaries = {}, {}, []
        for name, efficiency in SCENARIOS.items():
            solution = solve(data, efficiency)
            validation[name] = check_solution(data, solution)
            solutions[name] = solution
            row = {"scenario": name, **summary(data, solution)}
            summaries.append(row)
            write_json(output_raw / f"solution_{name}.json", solution)
            write_csv(output_raw / f"schedule_{name}.csv", schedule_rows(data, solution))
            print(f"{name}: 费用={row['cost_yuan']:.9f}元；MIP gap={solution['solver']['mip_gap']}；物理检查通过", flush=True)
        analysis = run_analysis(data, solutions, output_raw, output)
        validation["csv"] = export_csv_output(output, data, solutions["main"])
        write_json(output_raw / "validation.json", validation)
        write_csv(output / "efficiency_comparison.csv", summaries)
        write_json(output / "summary.json", summaries[0])
        figure_status = render_figures(data, solutions, summaries, analysis, staging, enabled=plots)
        write_json(output_raw / "figure_status.json", figure_status)
        create_report(data, solutions, summaries, validation, output, documents, figure_status)
        create_analysis_report(analysis, output, documents, figure_status)
        # 旧稿审查证据不属于本次求解；原样保留并在manifest标明，避免历史链接失效。
        historical = []
        for path in sorted((root / "outputs/q1/raw").glob("*review*.json")):
            shutil.copy2(path, output_raw / path.name)
            historical.append({"file": path.name, "sha256": sha256(path), "role": "historical_review_only"})
        run_tests(staging)
        p, load, pv = arrays(data)
        record = {"started_utc": started, "finished_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
                  "generation": staging.name, "python": sys.version, "platform": platform.platform(),
                  "command": "uv run --with-requirements src/q1/requirements.txt python src/q1/run.py",
                  "versions": {"numpy": np.__version__, "scipy": scipy.__version__, "openpyxl": openpyxl.__version__},
                  "inputs": provenance, "model_sha256": sha256(root / params["model_source"]),
                  "code_sha256": {str(f.relative_to(ROOT)): sha256(f) for f in sorted([*(ROOT / "src/q1").glob("*.py"), ROOT / "src/plots/q1_legacy.py"])},
                  "input_statistics": {"records": len(data), "price_min": float(p.min()), "price_max": float(p.max()),
                                       "load_kwh": float(load.sum()), "pv_kwh": float(pv.sum())},
                  "output_sha256": {str(f.relative_to(staging)): sha256(f) for f in sorted(staging.rglob("*")) if f.is_file()},
                  "historical_artifacts": historical, "all_physical_csv_checks_passed": True,
                  "analysis_checks_passed": analysis["all_checks_passed"], "analysis_scenarios": len(analysis["scenarios"]),
                  "tests_passed": True, "figure_status": figure_status,
                  "publication": "single atomic q1_current symlink replacement after all numerical gates"}
        write_json(output_raw / "run_manifest.json", record)
        generate_traceability(staging)
        record["output_sha256"] = {str(f.relative_to(staging)): sha256(f) for f in sorted(staging.rglob("*"))
                                   if f.is_file() and f != output_raw / "run_manifest.json"}
        write_json(output_raw / "run_manifest.json", record)
        publish_generation(staging, root)
    except BaseException:
        # 从未发布的generation移除；上一次正式结果保持可用。
        if (root / "outputs/q1_current").resolve() != staging:
            shutil.rmtree(staging)
        raise
    print(f"CSV回读和当前代码测试通过，已发布：{root / 'outputs/processed/q1/result1.csv'}", flush=True)
    print(f"绘图状态：{figure_status['status']}；{figure_status['message']}", flush=True)
    return staging


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-plots", action="store_true", help="只生成数值、可读报告和提交文件")
    args = parser.parse_args()
    run_pipeline(plots=not args.no_plots)
