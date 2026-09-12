"""一条命令：附件2→严格核验→全年/历史诊断→CSV/图→测试→发布。"""

import datetime as dt
import importlib.metadata
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

import numpy as np
import pandas as pd

from backtest import rolling_folds
from data import (FORECAST_START, ROOT, SERIES, history_before, jump_context, read_attachment,
                  sha256, write_csv, write_json)
from diagnostics import SETTINGS, analyze_scope
from figures import create_figures
from report import candidate_models, create_report
from traceability import generate_traceability


def validate_outputs(staging, frame, diagnostics):
    """磁盘回读、源值一致与频谱积分等独立验收；失败不能发布。"""
    counts = {}
    for path in staging.rglob("*.csv"):
        raw = path.read_bytes()
        if raw.startswith(b"\xef\xbb\xbf"):
            raise ValueError(f"CSV含BOM：{path}")
        raw.decode("utf-8")
        counts[str(path.relative_to(staging))] = len(pd.read_csv(path, float_precision="round_trip"))
    saved = pd.read_csv(staging / "inputs/processed/timeseries.csv", float_precision="round_trip")
    for variable in SERIES:
        np.testing.assert_array_equal(saved[variable], frame[variable])
    for scope, results in diagnostics.items():
        targets = results["spectral_targets"]
        np.testing.assert_allclose(targets.integrated_psd_kw2, targets.population_variance_kw2, rtol=1e-12, atol=1e-10)
        if len(results["stationarity_tests"]) != 32 or not results["stationarity_tests"].status.eq("ok").all():
            raise ValueError(f"{scope}平稳性检验不完整")
    return {"csv_rows": counts, "source_values_exact": True, "psd_parseval_pass": True,
            "utf8_no_bom": True, "stationarity_tests": 64}


def publish(staging):
    """沿用项目当前结果指针结构；输入/输出统一切换，失败不替换已有结果。"""
    current = ROOT / "outputs/q2_current"
    for alias, target in ((ROOT / "inputs/q2", current / "inputs"),
                          (ROOT / "outputs/q2/raw", current / "raw"),
                          (ROOT / "outputs/processed/q2", current / "processed")):
        alias.parent.mkdir(parents=True, exist_ok=True)
        relative = os.path.relpath(target, alias.parent)
        if alias.is_symlink():
            if os.readlink(alias) != relative:
                raise ValueError(f"结果别名指向其他位置，拒绝覆盖：{alias}")
        elif alias.exists():
            raise ValueError(f"结果位置已有实体目录，拒绝覆盖：{alias}")
        else:
            alias.symlink_to(relative, target_is_directory=True)
    pending = current.with_name(".q2_current_pending")
    pending.symlink_to(os.path.relpath(staging, current.parent), target_is_directory=True)
    try:
        os.replace(pending, current)
    finally:
        pending.unlink(missing_ok=True)


def run_pipeline():
    generations = ROOT / "outputs/.q2-runs"
    generations.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix="run-", dir=generations))
    started = dt.datetime.now(dt.timezone.utc).isoformat()
    raw, output = staging / "raw", staging / "processed"
    input_raw, input_processed = staging / "inputs/raw", staging / "inputs/processed"
    for path in (raw, output, input_raw, input_processed):
        path.mkdir(parents=True)
    code_hashes = {str(p.relative_to(ROOT)): sha256(p) for p in [*(ROOT / "src/q2").glob("*.py"), ROOT / "src/plots/q2.py"]}
    plan_digest = sha256(ROOT / "docs/2/dierwen1.md")
    try:
        original = ROOT / "docs/CUMCM2026Problems/C题/附件/附件2.xlsx"
        copied = input_raw / "attachment2.xlsx"
        shutil.copy2(original, copied)
        if sha256(original) != sha256(copied):
            raise ValueError("原始附件副本哈希不一致")
        source_digest = sha256(copied)
        write_json(input_raw / "manifest.json", {"source": str(original.relative_to(ROOT)), "sha256": sha256(original),
                                                "copy": "inputs/q2/raw/attachment2.xlsx", "role": "immutable_raw_observations"})
        frame, quality = read_attachment(copied, raw / "quality_checks.csv")
        write_csv(input_processed / "timeseries.csv", frame)
        shutil.copy2(input_processed / "timeseries.csv", output / "timeseries.csv")
        shutil.copy2(raw / "quality_checks.csv", output / "quality_checks.csv")
        write_csv(output / "jump_context.csv", jump_context(frame))
        write_json(input_processed / "settings.json", {**SETTINGS, "forecast_start": "2025-02-01",
                                                       "cutoff": "timestamp < origin", "boundary_authority": "user_explicit_confirmation",
                                                       "forecast_horizon": 144, "forecast_unit": "kW", "dt_hours_dispatch_only": 1/6})
        diagnostics = {}
        for scope, view in (("initial_history", history_before(frame, FORECAST_START)), ("full_year", frame)):
            diagnostics[scope] = analyze_scope(view, scope)
            for name, values in diagnostics[scope].items():
                write_csv(output / f"{scope}_{name}.csv", values)
        candidates = candidate_models(diagnostics["initial_history"])
        folds = rolling_folds(frame)
        print("生成11张科研分析图，每张PNG与SVG", flush=True)
        figures = create_figures(frame, diagnostics["full_year"], output / "figures")
        write_json(raw / "figure_manifest.json", figures)
        create_report(frame, diagnostics, candidates, folds, figures, output)
        trace = generate_traceability(output)
        validation = validate_outputs(staging, frame, diagnostics)
        print("运行当前源码测试与真实CSV回读验收", flush=True)
        environment = {**os.environ, "Q2_GENERATION": str(staging), "PYTHONIOENCODING": "utf-8"}
        tests = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", str(ROOT / "src/q2"),
                                "-p", "test_*.py", "-v"], env=environment, capture_output=True, text=True, encoding="utf-8")
        (raw / "test_results.txt").write_text(tests.stdout + tests.stderr, encoding="utf-8")
        if tests.returncode:
            raise ValueError(f"测试失败，正式结果未更新：{raw / 'test_results.txt'}")
        if code_hashes != {str(p.relative_to(ROOT)): sha256(p) for p in [*(ROOT / "src/q2").glob("*.py"), ROOT / "src/plots/q2.py"]}:
            raise ValueError("运行中源码发生修改，需重新完整运行")
        if source_digest != sha256(original) or plan_digest != sha256(ROOT / "docs/2/dierwen1.md"):
            raise ValueError("运行中原始附件或方案发生修改，需重新完整运行")
        write_json(raw / "validation.json", {**validation, "traceability": trace, "tests_passed": True,
                                              "figure_count": len(figures), "ui_smoke": "requires_actual_browser_review"})
        manifest = {"started_utc": started, "finished_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
                    "source_sha256": source_digest, "plan_sha256": plan_digest,
                    "code_sha256": code_hashes, "python": sys.version,
                    "versions": {name: importlib.metadata.version(name) for name in
                                 ("numpy", "scipy", "pandas", "statsmodels", "matplotlib", "openpyxl", "threadpoolctl")},
                    "output_sha256": {str(p.relative_to(staging)): sha256(p) for p in staging.rglob("*") if p.is_file()},
                    "real_forecast_or_dispatch_computed": False, "all_stage_2_1_checks_passed": True}
        write_json(raw / "run_manifest.json", manifest)
        publish(staging)
    except BaseException as error:
        (raw / "failure.txt").write_text(str(error), encoding="utf-8")
        raise
    print(f"已发布：{ROOT / 'outputs/processed/q2/report.html'}", flush=True)
    return staging


if __name__ == "__main__":
    run_pipeline()
