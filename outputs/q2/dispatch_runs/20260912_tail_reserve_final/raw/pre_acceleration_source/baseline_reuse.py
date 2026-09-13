"""仅复用已经完整验收、与指定基准输入相同的主轨迹。"""

import json
from pathlib import Path
import shutil
import tempfile

import numpy as np

from checkpoint import TABLES, atomic_json, read_checkpoint
from data import sha256
from export_dispatch import write_tables
from shadows import choose_day


def main_baselines(initial):
    return {f"initial_{initial:g}", "window_28"}


def window_inputs_match(store, frozen, actual, dates, prices, main, start, end):
    """包括未选中的预测流程评分；不能只因最终选中窗口为28就认定等价。"""
    for day in range(start, end):
        audit = json.loads((main/f"daily_audit/{dates[day].date()}.json").read_text(encoding="utf-8"))
        for key, item in audit.items():
            if not key.isdigit() or "selection" not in item:
                continue
            k = int(key)
            automatic = choose_day(store, frozen, actual[:day], day, k, prices)
            try:
                fixed = choose_day(store, frozen, actual[:day], day, k, prices, window=28)
            except ValueError:
                return False
            if (not np.array_equal(automatic[0], fixed[0]) or not np.array_equal(automatic[1], fixed[1])
                    or automatic[2] != fixed[2] or fixed[2] != item["selection"]):
                return False
    return True


def reuse_main_baseline(run, name, store, frozen, actual, dates, prices, initial):
    """失败或不匹配则交给正常实验，绝不覆盖已有独立实验存档。"""
    run = Path(run)
    if name not in main_baselines(initial):
        return False
    main = run/"processed/main"
    status = json.loads((main/"run_status.json").read_text(encoding="utf-8"))
    if not status.get("complete") or status.get("settings") != {}:
        return False
    if status.get("start_index") != 31 or status.get("end_index") != 365:
        return False
    target = run/"processed/experiments"/name
    if target.exists():
        return False
    source_manifest = (main/"checkpoint.json").read_bytes()
    frame, _, _ = read_checkpoint(main, actual, dates, prices, initial, 31, 365, {})
    if name == "window_28" and not window_inputs_match(store, frozen, actual, dates, prices, main, 31, 365):
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".baseline_reuse_", dir=target.parent))
    try:
        for filename in (*TABLES, "checkpoint.json", "run_status.json"):
            shutil.copyfile(main/filename, staging/filename)
        for folder in ("daily_audit", "frozen_plans"):
            shutil.copytree(main/folder, staging/folder)
        reused_status = dict(status)
        reused_status["settings"] = {"window": 28} if name == "window_28" else {}
        atomic_json(staging/"run_status.json", reused_status)
        write_tables(frame, staging)
        # 核验复制结果及跨日物理响应；源主轨迹必须保持同一完整版本。
        read_checkpoint(staging, actual, dates, prices, initial, 31, 365, reused_status["settings"])
        if (main/"checkpoint.json").read_bytes() != source_manifest:
            raise ValueError("复用期间主轨迹版本改变")
        atomic_json(staging/"baseline_reuse.json", {
            "complete": True, "source": "processed/main", "days": 334,
            "source_checkpoint_sha256": sha256(main/"checkpoint.json"),
            "source_status_sha256": sha256(main/"run_status.json"),
            "source_execution": status.get("execution", {}),
            "source_execution_history": status.get("execution_history", []),
            "reason": "identical_initial_baseline" if name != "window_28" else "all_daily_predictor_scores_points_and_blocks_identical",
            "interpretation": "shared_baseline_not_an_independent_rerun", "extra_MILP_solves": 0})
        staging.rename(target)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return True
