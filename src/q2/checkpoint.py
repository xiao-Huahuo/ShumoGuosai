"""完整日前缀验收；数值损坏、跨日断链及未提交的CSV均禁止续算。"""

import json
import os
import shutil

import numpy as np
import pandas as pd

from data import sha256, write_csv, write_json
from export_dispatch import validate_dispatch
from policy import DT, PHYSICAL_TOL, Policy, replay

TABLES = ("dispatch.csv", "daily.csv", "calibration.csv")


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_name(path.name+".pending")
    write_json(pending, value)
    with pending.open("rb") as stream:
        os.fsync(stream.fileno())
    pending.replace(path)


def _matches(output, manifest):
    return (set(manifest.get("sha256", {})) == set(TABLES)
            and all((output/name).exists() and sha256(output/name) == digest
                    for name, digest in manifest["sha256"].items()))


def recover_checkpoint(output):
    """仅恢复有提交中断标记的事务；无标记的摘要损坏仍拒绝，不静默重封存。"""
    marker = output/"checkpoint_transaction.json"
    if not marker.exists():
        return
    transaction = json.loads(marker.read_text(encoding="utf-8"))
    manifest = output/"checkpoint.json"
    if (manifest.exists() and json.loads(manifest.read_text(encoding="utf-8")) == transaction["target"]
            and _matches(output, transaction["target"])):
        marker.unlink()
        return
    base = transaction["base"]
    if base is None:
        for name in (*TABLES, "checkpoint.json"):
            (output/name).unlink(missing_ok=True)
    else:
        backup = output/"checkpoint_previous"
        if not _matches(backup, base):
            raise ValueError("提交中断且上一完整检查点备份摘要不符，禁止自动覆盖")
        for name in TABLES:
            pending = output/(name+".recovery")
            shutil.copyfile(backup/name, pending)
            with pending.open("rb") as stream:
                os.fsync(stream.fileno())
            pending.replace(output/name)
        atomic_json(manifest, base)
    marker.unlink()
    atomic_json(output/"checkpoint_recovery.json", {
        "restored_days": base["days"] if base else 0,
        "discarded_uncommitted_days": transaction["target"]["days"],
        "reason": "interrupted_multi_csv_commit_restored_last_verified_checkpoint"})


def save_checkpoint(output, frame, daily, calibration):
    recover_checkpoint(output)
    manifest = output/"checkpoint.json"
    base = json.loads(manifest.read_text(encoding="utf-8")) if manifest.exists() else None
    if base is not None:
        if not _matches(output, base):
            raise ValueError("保存前检查点摘要不符，禁止覆盖已提交结果")
        backup = output/"checkpoint_previous"
        backup.mkdir(exist_ok=True)
        for name in TABLES:
            shutil.copyfile(output/name, backup/name)
            with (backup/name).open("rb") as stream:
                os.fsync(stream.fileno())
        atomic_json(backup/"checkpoint.json", base)
    for name, table in zip(TABLES, (frame, pd.DataFrame(daily), pd.DataFrame(calibration))):
        pending = output/(name+".pending")
        write_csv(pending, table)
        with pending.open("rb") as stream:
            os.fsync(stream.fileno())
    target = {"days": len(daily), "sha256": {name: sha256(output/(name+".pending")) for name in TABLES}}
    atomic_json(output/"checkpoint_transaction.json", {"base": base, "target": target})
    for name in TABLES:
        (output/(name+".pending")).replace(output/name)
    atomic_json(manifest, target)
    (output/"checkpoint_transaction.json").unlink()


def read_checkpoint(output, actual, dates, prices, initial_soc, start, end, settings):
    recover_checkpoint(output)
    status = json.loads((output/"run_status.json").read_text(encoding="utf-8"))
    if status.get("settings") != settings or status.get("start_index") != start or status.get("end_index") != end:
        raise ValueError("已有回放与当前实验设置不同，拒绝覆盖")
    manifest = output/"checkpoint.json"
    if manifest.exists():
        hashes = json.loads(manifest.read_text(encoding="utf-8"))["sha256"]
        if any(sha256(output/name) != digest for name, digest in hashes.items()):
            raise ValueError("检查点摘要不符或CSV事务尚未完整提交")
    previous = pd.read_csv(output/"dispatch.csv", parse_dates=["date", "timestamp"], float_precision="round_trip")
    completed = previous.date.nunique()
    if completed > end-start or not np.array_equal(previous.date.unique(), dates[start:start+completed].to_numpy()):
        raise ValueError("回放检查点不是完整连续前缀")
    rigid = settings.get("kind") == "rigid"
    validate_dispatch(previous, rigid=rigid)
    np.testing.assert_allclose(previous.initial_soc.iloc[0], initial_soc, atol=PHYSICAL_TOL, rtol=0)
    expected_net = DT*(actual[start:start+completed, :, 0]-actual[start:start+completed, :, 1]).ravel()
    np.testing.assert_allclose(previous.net_kwh, expected_net, atol=PHYSICAL_TOL, rtol=0)
    np.testing.assert_array_equal(previous.price, np.tile(prices, completed))
    daily = pd.read_csv(output/"daily.csv", float_precision="round_trip")
    calibration = pd.read_csv(output/"calibration.csv", float_precision="round_trip")
    if len(daily) != completed or daily.date.tolist() != [str(d.date()) for d in dates[start:start+completed]]:
        raise ValueError("逐日摘要与检查点日期不一致")
    for i, (date, day) in enumerate(previous.groupby("date", sort=False)):
        audit = json.loads((output/f"daily_audit/{date.date()}.json").read_text(encoding="utf-8"))
        frozen = pd.read_csv(output/f"frozen_plans/{date.date()}.csv", float_precision="round_trip")
        k = audit["selected_K"]
        if len(frozen) != k*144 or not audit[str(k)]["selected_solver"]["reliable"]:
            raise ValueError("冻结策略长度或求解验收状态不符")
        for key in ("grid", "charge_cap", "discharge_cap"):
            np.testing.assert_array_equal(frozen[key].iloc[:144], day[key])
        if not rigid:
            policy = Policy(day.grid, day.charge_cap, day.discharge_cap)
            response = replay(policy, day.net_kwh.to_numpy(), float(day.initial_soc.iloc[0]))
            for key, values in response.items():
                np.testing.assert_allclose(day[key], values, atol=PHYSICAL_TOL, rtol=0)
        row = daily.iloc[i]
        np.testing.assert_allclose([row.initial_soc, row.final_soc, row.cost, row.emergency_kwh],
                                   [day.initial_soc.iloc[0], day.soc.iloc[-1],
                                    (day.planned_cost+day.emergency_cost).sum(), day.emergency.sum()],
                                   atol=PHYSICAL_TOL, rtol=0)
        observed = calibration[calibration.origin == str(date.date())]
        expected = {(h, nominal) for h in range(min(k, len(dates)-start-i)) for nominal in (.8, .9)}
        if len(observed) != len(expected) or set(zip(observed.horizon, observed.nominal)) != expected:
            raise ValueError("预测步长覆盖率记录缺失或重复")
    return previous, daily.to_dict("records"), calibration.to_dict("records")
