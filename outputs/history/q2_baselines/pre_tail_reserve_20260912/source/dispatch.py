"""第二问最终方案运行入口；旧run.py继续承担数据诊断。"""

import argparse
import datetime as dt
import importlib.metadata
import json
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
from openpyxl import load_workbook

from data import ROOT, endpoint_minutes, read_attachment, sha256, write_csv, write_json
from export_dispatch import export_result, write_tables
from protocol import PLAN, PROTOCOL, signature
from rolling import ComputationalLimit, run_rollout, warm_start
from shadows import build_shadow_library, open_library

FORECAST_FILES = ("data.py", "forecast.py", "shadows.py", "scenarios.py", "policy.py", "protocol.py", "requirements.txt")


def input_data(directory):
    directory.mkdir(parents=True, exist_ok=True)
    attachment2 = ROOT/"docs/CUMCM2026Problems/C题/附件/附件2.xlsx"
    attachment1 = ROOT/"docs/CUMCM2026Problems/C题/附件/附件1.xlsx"
    frame, _ = read_attachment(attachment2, directory/"quality_checks.csv")
    frame["day_of_year"] = pd.to_datetime(frame.date).dt.dayofyear
    workbook = load_workbook(attachment1, read_only=True, data_only=True)
    rows = list(workbook.active.values); workbook.close()
    if len(rows) != 145 or rows[0][1] != "电价":
        raise ValueError("附件1电价表结构不符")
    if [endpoint_minutes(row[0]) for row in rows[1:]] != list(range(10, 1441, 10)):
        raise ValueError("附件1电价右端点序列不符")
    prices = np.array([row[1] for row in rows[1:]], dtype=float)
    if not np.isfinite(prices).all() or (prices <= 0).any():
        raise ValueError("电价必须有限且为正")
    write_csv(directory/"prices.csv", pd.DataFrame({"slot": np.arange(1, 145), "price_yuan_per_kwh": prices}))
    write_csv(directory/"timeseries.csv", frame)
    write_json(directory/"source_manifest.json", {str(path.relative_to(ROOT)): sha256(path) for path in (attachment1, attachment2)})
    dates = pd.DatetimeIndex(frame.date.unique())
    actual = frame[["load_kw", "pv_kw"]].to_numpy().reshape(365, 144, 2)
    return actual, dates, prices


def forecast_hashes():
    return {name: sha256(ROOT/"src/q2"/name) for name in FORECAST_FILES}


def prepared_hashes(path):
    files = [p for directory in (path/"inputs/processed", path/"raw/shadows")
             for p in directory.rglob("*") if p.is_file()]
    return {str(p.relative_to(path)): sha256(p) for p in sorted(files)}


def seal_prepared(path):
    """旧准备库迁移：重新读取附件逐值核对，并从此刻冻结生成文件摘要。"""
    path = Path(path)
    if (path/"raw/prepared_manifest.json").exists():
        expected = json.loads((path/"raw/prepared_manifest.json").read_text(encoding="utf-8"))["sha256"]
        if prepared_hashes(path) != expected:
            raise ValueError("已封存准备库改变，禁止重新封存掩盖差异")
        return
    protocol = json.loads((path/"raw/protocol.json").read_text(encoding="utf-8"))
    if protocol["protocol_sha256"] != signature() or protocol["forecast_source_sha256"] != forecast_hashes():
        raise ValueError("准备库与冻结预测源码不一致")
    with tempfile.TemporaryDirectory() as directory:
        actual, dates, prices = input_data(Path(directory))
    saved = pd.read_csv(path/"inputs/processed/timeseries.csv", float_precision="round_trip")
    np.testing.assert_array_equal(saved[["load_kw", "pv_kw"]].to_numpy().reshape(actual.shape), actual)
    np.testing.assert_array_equal(pd.to_datetime(saved.date.unique()), dates)
    np.testing.assert_array_equal(pd.read_csv(path/"inputs/processed/prices.csv", float_precision="round_trip").price_yuan_per_kwh, prices)
    open_library(path/"raw/shadows")
    write_json(path/"raw/prepared_manifest.json", {"sha256": prepared_hashes(path),
                                                 "sealed_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                                                 "origin": "post_generation_seal_original_inputs_independently_rechecked"})


def prepare(run_path=None):
    if PROTOCOL["history_boundary"] != "source_date_before_origin":
        raise ValueError("新方案完整日信息边界未确定")
    path = Path(run_path) if run_path else ROOT/"outputs/q2/dispatch_runs"/dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    if path.exists() and any(path.iterdir()):
        raise ValueError("准备目录非空，拒绝覆盖已有运行记录")
    path.mkdir(parents=True, exist_ok=True)
    hashes = forecast_hashes()
    write_json(path/"raw/protocol.json", {**PROTOCOL, "protocol_sha256": signature(), "plan_sha256": sha256(PLAN),
                                         "forecast_source_sha256": hashes,
                                         "versions": {name: importlib.metadata.version(name) for name in
                                                      ("numpy", "scipy", "pandas", "lightgbm", "scikit-learn", "statsmodels", "pyscipopt", "openpyxl")}})
    print(f"运行目录：{path.resolve()}", flush=True)
    actual, dates, prices = input_data(path/"inputs/processed")
    try:
        build_shadow_library(actual, dates, path/"raw/shadows", boundary=PROTOCOL["history_boundary"])
        if hashes != forecast_hashes():
            raise ValueError("影子库生成期间预测源码改变，请在新目录重算")
        write_json(path/"raw/prepare_status.json", {"complete": True, "forecast_source_sha256": hashes})
        write_json(path/"raw/prepared_manifest.json", {"sha256": prepared_hashes(path), "origin": "at_preparation_completion"})
    except BaseException as error:
        write_json(path/"raw/prepare_status.json", {"complete": False, "error": str(error)})
        raise
    print(f"影子库完整生成：{path.resolve()}", flush=True)
    return path


def load_prepared(path):
    path = Path(path)
    protocol = json.loads((path/"raw/protocol.json").read_text(encoding="utf-8"))
    if protocol["protocol_sha256"] != signature() or protocol["forecast_source_sha256"] != forecast_hashes():
        raise ValueError("准备库与当前预测源码/协议不一致；禁止混用运行代")
    manifest = json.loads((path/"inputs/processed/source_manifest.json").read_text(encoding="utf-8"))
    if any(sha256(ROOT/name) != digest for name, digest in manifest.items()):
        raise ValueError("原始输入已改变")
    sealed = path/"raw/prepared_manifest.json"
    if not sealed.exists():
        raise ValueError("准备库尚未封存；旧运行须先执行seal-prepared独立核对输入")
    if prepared_hashes(path) != json.loads(sealed.read_text(encoding="utf-8"))["sha256"]:
        raise ValueError("处理输入/影子预测库摘要改变，禁止继续求解")
    frame = pd.read_csv(path/"inputs/processed/timeseries.csv", parse_dates=["date", "timestamp"], float_precision="round_trip")
    actual = frame[["load_kw", "pv_kw"]].to_numpy().reshape(365, 144, 2)
    prices = pd.read_csv(path/"inputs/processed/prices.csv", float_precision="round_trip").price_yuan_per_kwh.to_numpy()
    store, frozen = open_library(path/"raw/shadows")
    return store, frozen, actual, pd.DatetimeIndex(frame.date.unique()), prices


def run_main(path, *, rescue_seconds=None, solver_gap=PROTOCOL["solver_gap"], execution_revision=None):
    path = Path(path)
    store, frozen, actual, dates, prices = load_prepared(path)
    output = path/"processed"
    output.mkdir(parents=True, exist_ok=True)
    sources = {p.name: sha256(p) for p in (ROOT/"src/q2").glob("*.py")}
    write_json(path/f"raw/dispatch_sources_{dt.datetime.now().strftime('%Y%m%d_%H%M%S')}.json", sources)
    write_json(path/"raw/dispatch_sources.json", sources)
    try:
        initial = warm_start(actual, dates, prices, output)
        result, _ = run_rollout(store, frozen, actual, dates, prices, initial, output/"main", rescue_seconds=rescue_seconds,
                                solver_gap=solver_gap, execution_revision=execution_revision)
        write_tables(result, output/"main")
        from final_report import verify_code
        verify_code(path)
        export_result(result, ROOT/"docs/CUMCM2026Problems/C题/附件/附件5/result2.xlsx", output/"main")
    except Exception as error:
        write_json(path/"raw/dispatch_status.json", {"complete": False, "reason": str(error), "details": getattr(error, "details", None)})
        raise
    write_json(path/"raw/dispatch_status.json", {"complete": True, "main_days": 334,
                                                "mandatory_experiments_complete": False,
                                                "execution": json.loads((output/"main/run_status.json").read_text(encoding="utf-8"))["execution"],
                                                "supplemental_days": sum("supplemental_solver_seconds" in json.loads(p.read_text(encoding="utf-8"))
                                                                         for p in (output/"main/daily_audit").glob("*.json")),
                                                "source_sha256_at_start": sources})
    print(f"主回放完成，必需敏感性仍需独立验收：{output/'main'}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    command = sub.add_parser("prepare", help="核验输入并逐日生成所有候选的因果影子库")
    command.add_argument("--run-dir", type=Path)
    for name, help_text in (("run", "执行因果预热及334日主模型"), ("experiments", "运行方案2.10的诊断/敏感性"),
                            ("seal-prepared", "独立核对旧准备库并冻结生成文件摘要")):
        command = sub.add_parser(name, help=help_text)
        command.add_argument("--run-dir", type=Path, required=True)
        if name in ("run", "experiments"):
            command.add_argument("--rescue-seconds", type=float,
                                 help="原预算整日全候选失败后追加的每次求解秒数；保留原失败记录，不放松gap")
        if name == "experiments":
            command.add_argument("--only", help="只运行一个具名实验，便于独立续算与资源控制")
    args = parser.parse_args()
    if args.command == "prepare":
        prepare(args.run_dir)
    elif args.command == "run":
        run_main(args.run_dir, rescue_seconds=args.rescue_seconds)
    elif args.command == "experiments":
        from experiments import run_experiments
        status = run_experiments(args.run_dir, only=args.only, rescue_seconds=args.rescue_seconds)
        if any(not entry.get("complete") for entry in status.values()):
            raise SystemExit(2)
    elif args.command == "seal-prepared":
        seal_prepared(args.run_dir)


if __name__ == "__main__":
    main()
