"""7.6—7.8：4-2日前48h、4-3四节点24h滚动与真实价格逐槽回放。"""
from dataclasses import asdict
from contextlib import contextmanager
from pathlib import Path
import hashlib
import json
import os
import numpy as np
import pandas as pd
from .physics import DispatchPolicy as Policy
from .config import Config, DT, E_INITIAL, E_MIN, E_MAX, ETA_C, ETA_D, CAP, MODEL_VERSION, TOL, write_csv, write_json
from .data import Inputs
from .optimization import LimitedSolve, solve
from .physics import adjustment_quantity, replay
from .scenarios import construct


@contextmanager
def run_lock(path: Path):
    """跨平台单写入者文件锁；进程退出后由操作系统释放。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as stream:
        if stream.tell() == 0:
            stream.write(b"0")
            stream.flush()
        if os.name == "nt":
            import msvcrt
            stream.seek(0)
            try:
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as error:
                raise RuntimeError("同一问题四输出目录已有写入者") from error
        else:
            import fcntl
            try:
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as error:
                raise RuntimeError("同一问题四输出目录已有写入者") from error
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == "nt":
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def date_of(day: int) -> pd.Timestamp:
    return pd.Timestamp("2025-01-01") + pd.Timedelta(days=day)


def _execute(data: Inputs, day: int, hour: int, policy: Policy, initial: float) -> pd.DataFrame:
    start, end = hour * 6, hour * 6 + len(policy.grid)
    if end > 144:
        raise ValueError("正式提交块不得跨过当日午夜")
    actual = data.q3.actual[day, start:end]
    net = (actual[:, 0] - actual[:, 1]) * DT
    response = replay(policy, net, initial)
    return pd.DataFrame({
        "date": str(date_of(day).date()),
        "slot": np.arange(start, end),
        "timestamp": date_of(day) + pd.to_timedelta((np.arange(start, end) + 1) * 10, unit="min"),
        "node_hour": hour,
        "net_kwh": net,
        "load_kw": actual[:, 0],
        "pv_kw": actual[:, 1],
        "price": data.actual_prices[day, start:end],
        "price_forecast": data.price.values[day, start:end],
        "grid": policy.grid,
        "charge_plan": policy.charge,
        "discharge_plan": policy.discharge,
        **response,
    })


def _cold_start(data: Inputs, day: int, initial: float, mode: str) -> tuple[pd.DataFrame, dict]:
    zero = np.zeros(144)
    policy = Policy(zero, zero, zero)
    frame = _execute(data, day, 0, policy, initial)
    frame["g0"] = zero
    frame["initial_soc"] = initial
    frame["planned_cost"] = 0.0
    frame["adjustment_cost"] = 0.0
    frame["emergency_cost"] = 5 * frame.price * frame.emergency
    frame["total_cost"] = frame.emergency_cost
    return frame, {"date": str(date_of(day).date()), "mode": mode, "cold_start": True,
                   "reason": "inherit Q2/Q3 Jan1-Jan7 unavailable-load stationary-storage protocol"}


def run_day_q42(data: Inputs, day: int, initial: float, config: Config) -> tuple[pd.DataFrame, dict]:
    if day < 7:
        return _cold_start(data, day, initial, "4-2")
    scenarios = construct(data, day, 0, 288, config)
    solution = solve(scenarios, initial, config)
    committed = solution.policy.part(0, 144)
    frame = _execute(data, day, 0, committed, initial)
    frame["g0"] = frame.grid
    frame["initial_soc"] = initial
    frame["planned_cost"] = frame.price * frame.grid
    frame["adjustment_cost"] = 0.0
    frame["emergency_cost"] = 5 * frame.price * frame.emergency
    frame["total_cost"] = frame.planned_cost + frame.emergency_cost
    audit = {
        "date": str(date_of(day).date()),
        "mode": "4-2",
        "initial_soc": initial,
        "committed_slots": 144,
        "roles": ["current_formal"] * 144 + ["next_day_continuation"] * 144,
        "solver": solution.audit,
        "scenarios": scenarios.audit,
        "grid": solution.policy.grid.tolist(),
        "charge": solution.policy.charge.tolist(),
        "discharge": solution.policy.discharge.tolist(),
    }
    validate_frame(frame, "4-2", config)
    return frame, audit


def run_day_q43(data: Inputs, day: int, initial: float, config: Config) -> tuple[pd.DataFrame, dict]:
    if day < 7:
        return _cold_start(data, day, initial, "4-3")
    soc = initial
    g0 = None
    frames, audits = [], []
    nodes = list(config.nodes)
    for position, hour in enumerate(nodes):
        next_hour = nodes[position + 1] if position + 1 < len(nodes) else 24
        committed_slots = (next_hour - hour) * 6
        scenarios = construct(data, day, hour, 144, config)
        reference = None if hour == 0 else g0[hour * 6:]
        solution = solve(scenarios, soc, config, reference=reference, today=144 - hour * 6)
        if hour == 0:
            g0 = solution.policy.grid.copy()
        committed = solution.policy.part(0, committed_slots)
        executed = _execute(data, day, hour, committed, soc)
        executed["g0"] = g0[hour * 6:next_hour * 6]
        executed["initial_soc"] = initial
        frames.append(executed)
        audits.append({
            "hour": hour,
            "initial_soc": soc,
            "committed_slots": committed_slots,
            "roles": ["committed" if slot < committed_slots else
                      "today_provisional" if slot < 144 - hour * 6 else "next_day_continuation"
                      for slot in range(144)],
            "solver": solution.audit,
            "scenarios": scenarios.audit,
            "grid": solution.policy.grid.tolist(),
            "charge": solution.policy.charge.tolist(),
            "discharge": solution.policy.discharge.tolist(),
            "delta_from_g0": (solution.policy.grid[:144 - hour * 6] - g0[hour * 6:]).tolist(),
        })
        soc = float(executed.soc.iloc[-1])
    frame = pd.concat(frames, ignore_index=True)
    frame["planned_cost"] = frame.price * frame.g0
    frame["adjustment_cost"] = frame.price * adjustment_quantity(frame.grid.to_numpy(), frame.g0.to_numpy())
    frame["emergency_cost"] = 5 * frame.price * frame.emergency
    frame["total_cost"] = frame.planned_cost + frame.adjustment_cost + frame.emergency_cost
    audit = {"date": str(date_of(day).date()), "mode": "4-3", "initial_soc": initial,
             "settlement": "final_effective_relative_to_00", "nodes": audits}
    validate_frame(frame, "4-3", config)
    return frame, audit


def validate_frame(frame: pd.DataFrame, mode: str, config: Config, *, full: bool = False) -> None:
    if mode not in ("4-2", "4-3") or frame.empty:
        raise ValueError("回放模式或数据为空")
    times = pd.to_datetime(frame.timestamp)
    dates = pd.to_datetime(frame.date)
    if times.duplicated().any() or not times.diff().dropna().eq(pd.Timedelta(minutes=10)).all():
        raise ValueError("真实回放时序不连续")
    if not dates.eq((times - pd.Timedelta(minutes=10)).dt.normalize()).all():
        raise ValueError("10分钟右端点日期归属错误")
    last = None
    for _, day in frame.groupby("date", sort=False):
        if len(day) != 144 or not np.array_equal(day.slot, np.arange(144)):
            raise ValueError("每日必须恰含144个时段")
        initial = float(day.initial_soc.iloc[0])
        if last is not None and abs(initial - last) > TOL:
            raise ValueError("跨日SOC断裂")
        np.testing.assert_allclose(day.net_kwh, (day.load_kw - day.pv_kw) * DT, atol=TOL, rtol=0)
        np.testing.assert_allclose(day.called + day.discharge + day.emergency,
                                   day.net_kwh + day.charge + day.spill, atol=TOL, rtol=0)
        np.testing.assert_allclose(day.unused + day.spill, day.total_surplus, atol=TOL, rtol=0)
        np.testing.assert_allclose(day.planned_cost, day.price * day.g0, atol=TOL, rtol=0)
        expected_adjustment = (np.zeros(144) if mode == "4-2" else
                               day.price.to_numpy() * adjustment_quantity(day.grid.to_numpy(), day.g0.to_numpy()))
        np.testing.assert_allclose(day.adjustment_cost, expected_adjustment, atol=TOL, rtol=0)
        np.testing.assert_allclose(day.emergency_cost, 5 * day.price * day.emergency, atol=TOL, rtol=0)
        np.testing.assert_allclose(day.total_cost,
                                   day.planned_cost + day.adjustment_cost + day.emergency_cost, atol=TOL, rtol=0)
        if not np.isfinite(day.select_dtypes(include=[np.number]).to_numpy()).all():
            raise ValueError("回放含非有限值")
        for key in ('grid', 'called', 'unused', 'charge', 'discharge', 'emergency', 'spill'):
            if day[key].min() < -TOL:
                raise ValueError(f"负值：{key}")
        if (day.called > day.grid + TOL).any() or (day.charge + day.discharge > CAP + TOL).any():
            raise ValueError("调用额度或储能功率越界")
        if day.soc.min() < E_MIN - TOL or day.soc.max() > E_MAX + TOL:
            raise ValueError("SOC越界")
        np.testing.assert_allclose(day.soc, initial + np.cumsum(ETA_C * day.charge - day.discharge / ETA_D), atol=TOL, rtol=0)
        np.testing.assert_allclose(day.charge, day.charge_plan, atol=TOL, rtol=0)
        np.testing.assert_allclose(day.discharge, day.discharge_plan, atol=TOL, rtol=0)
        last = float(day.soc.iloc[-1])
    if full and (len(frame) != 334 * 144 or dates.min() != pd.Timestamp("2025-02-01")
                 or dates.max() != pd.Timestamp("2025-12-31")):
        raise ValueError("拒绝将部分日期发布为完整问题四结果")


def run_period(data: Inputs, mode: str, config: Config, output: Path, *, end: int = 365) -> pd.DataFrame:
    if mode not in ("4-2", "4-3"):
        raise ValueError("模式只能为4-2或4-3")
    if config.allow_limited:
        raise ValueError("正式q42/q43禁止allow_limited")
    if not 31 < end <= 365:
        raise ValueError("正式期从Feb1开始，end必须在32..365")
    if mode == '4-3' and config.nodes != (0, 6, 12, 18):
        raise ValueError("正式Q4-3必须使用全部四时点")
    if config.residual_window != 56 or not config.joint or config.dro_scale <= 0:
        raise ValueError("正式计算固定W=56并保留联合残差与Wasserstein")
    output.mkdir(parents=True, exist_ok=True)
    with run_lock(output / "run.lock"):
        signature = config.signature()
        sources = hashlib.sha256(json.dumps(data.provenance, sort_keys=True).encode("utf-8")).hexdigest()
        state_path = output / "state.json"
        state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {
            "signature": signature, "sources": sources, "mode": mode, "days": [], "soc": E_INITIAL,
            "config": asdict(config), "model_version": MODEL_VERSION, "formal_start_day": 31,
            "integer_variables": 0, "initial_soc": E_INITIAL,
        }
        if state["signature"] != signature or state["sources"] != sources or state["mode"] != mode:
            raise ValueError("续算模型、输入或模式变化，禁止混用已有前缀")
        frames = []
        runner = run_day_q42 if mode == "4-2" else run_day_q43
        write_json(output / "source_manifest.json", data.provenance)
        for position, day in enumerate(range(31, end)):
            date = str(date_of(day).date())
            dispatch_path = output / "days" / f"{date}.csv"
            audit_path = output / "audit" / f"{date}.json"
            if position < len(state["days"]):
                receipt = state["days"][position]
                if receipt["day"] != day:
                    raise ValueError("续算日期顺序损坏")
                for key, path in (("dispatch", dispatch_path), ("audit", audit_path)):
                    if hashlib.sha256(path.read_bytes()).hexdigest() != receipt["hashes"][key]:
                        raise ValueError("已提交日文件摘要变化")
                frame = pd.read_csv(dispatch_path, float_precision="round_trip")
            else:
                write_json(output / "active.json", {"status": "solving", "mode": mode, "date": date,
                                                     "completed_days": len(state["days"])})
                try:
                    frame, audit = runner(data, day, state["soc"], config)
                except LimitedSolve as error:
                    write_json(output / "failures" / f"{date}.json", error.audit)
                    write_json(output / "active.json", {"status": "failed", "date": date, "reason": error.audit})
                    raise
                validate_frame(frame, mode, config)
                solver_audits = [audit['solver']] if mode == '4-2' else [node['solver'] for node in audit['nodes']]
                if not all(item['status'] == 'Optimal' and item['reliable'] and
                           item['solution_source'] == 'optimal_solver' and item['integer_variables'] == 0
                           for item in solver_audits):
                    raise ValueError("拒绝未认证或fallback策略正式落盘")
                write_csv(dispatch_path, frame)
                write_json(audit_path, audit)
                hashes = {"dispatch": hashlib.sha256(dispatch_path.read_bytes()).hexdigest(),
                          "audit": hashlib.sha256(audit_path.read_bytes()).hexdigest()}
                state["days"].append({"day": day, "hashes": hashes})
                state["soc"] = float(frame.soc.iloc[-1])
                write_json(state_path, state)
                print(f"{mode} {date} SOC={state['soc']:.3f} committed", flush=True)
            frames.append(frame)
        result = pd.concat(frames, ignore_index=True)
        validate_frame(result, mode, config)
        formal = result[pd.to_datetime(result.date) >= pd.Timestamp("2025-02-01")].copy()
        write_csv(output / "dispatch.csv", formal)
        write_json(output / "active.json", {"status": "calculation_complete", "mode": mode, "completed_days": end - 31})
        return formal
