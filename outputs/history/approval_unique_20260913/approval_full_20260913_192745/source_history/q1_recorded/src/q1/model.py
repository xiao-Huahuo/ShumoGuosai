"""Q1 最终稿第 2–11 节：输入、六类变量 MILP 和独立物理复核。"""

import csv
import datetime as dt
import json
import os
import warnings
from pathlib import Path

import numpy as np
from openpyxl import load_workbook
from scipy.optimize import Bounds, LinearConstraint, linprog, milp
from scipy.sparse import csc_matrix

ROOT = Path(__file__).resolve().parents[2]
T = 144
DT = 1 / 6  # 最终稿第 2、3 节：10 min，以 h 为单位。
Q_MAX = 5000 * DT  # 用户确认精确公式；833.3333 仅作显示。
E_MIN, E_MAX, E_INITIAL = 1200.0, 10800.0, 6000.0
# CR-07：每类验收独立指定量纲；相同数值不代表可混用。
PHYS_TOL_KWH = 1e-6
COST_TOL_YUAN = 1e-6
BINARY_TOL = 1e-8
MIP_GAP_TOL = 1e-6
ECONOMIC_VALUE_TOL = 1e-6
DIMENSIONLESS_TOL = 1e-8
TOLERANCES = {"physical_kwh": PHYS_TOL_KWH, "cost_yuan": COST_TOL_YUAN,
              "binary": BINARY_TOL, "mip_gap": MIP_GAP_TOL,
              "economic_value_per_unit": ECONOMIC_VALUE_TOL,
              "dimensionless": DIMENSIONLESS_TOL}
# 测试进程指向本次staging；正常读取者固定一次generation，避免跨代读取。
ARTIFACT_ROOT = Path(os.environ.get("Q1_ARTIFACT_ROOT", ROOT / "outputs/q1_current")).resolve()
SOLVER_OPTIONS = {"mip_rel_gap": 0.0, "mip_feasibility_tolerance": 1e-9,
                  "primal_feasibility_tolerance": 1e-9, "dual_feasibility_tolerance": 1e-9}
SCENARIOS = {"main": 0.90, "eta085": 0.85, "eta095": 0.95,
             "roundtrip090": float(np.sqrt(0.90))}


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2,
                               allow_nan=False) + "\n", encoding="utf-8")


def write_csv(path, rows):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def clock_label(minutes):
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def endpoint_minutes(value):
    """新版2.1：将Excel时间、日分数、时长及文本统一为整分钟。"""
    if isinstance(value, dt.timedelta):
        minutes = value.total_seconds() / 60
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        minutes = float(value) * 1440
    else:
        minutes = None
    if minutes is not None:
        if np.isfinite(minutes) and 0 < minutes <= 1440 and abs(minutes - round(minutes)) < 1e-7:
            return round(minutes)
        raise ValueError(f"无效Excel时间数值：{value!r}")
    if isinstance(value, dt.time):
        if value.second or value.microsecond:
            raise ValueError(f"非整分钟时间：{value}")
        return 60 * value.hour + value.minute
    if isinstance(value, str):
        value = value.strip()
        if value in ("0:00+1", "00:00+1", "24:00"):
            return 1440
        parts = value.split(":")
        if len(parts) == 2 and all(part.isdigit() for part in parts):
            hour, minute = map(int, parts)
            if 0 <= hour < 24 and 0 <= minute < 60:
                return hour * 60 + minute
    raise ValueError(f"无效时间标签：{value!r}")


def read_inputs(path):
    wb = load_workbook(path, read_only=True, data_only=True)
    try:
        rows = list(wb.active.values)
    finally:
        wb.close()
    expected_header = ("时间", "电价", "小区负载", "光伏发电预测功率")
    if tuple(rows[0]) != expected_header or len(rows) != T + 1:
        raise ValueError("附件1必须具有规定四列及144条数据，不允许静默截断或补值")
    result = []
    for t, row in enumerate(rows[1:], 1):
        endpoint = endpoint_minutes(row[0])
        if endpoint != t * 10:
            raise ValueError(f"第{t}时段右端点不符：{row[0]}，应为{clock_label(t * 10)}")
        if any(isinstance(x, bool) or not isinstance(x, (int, float)) for x in row[1:]):
            raise ValueError(f"第{t}时段含缺失值或非数值")
        p, pl, ppv = map(float, row[1:])
        if not np.all(np.isfinite([p, pl, ppv])) or min(p, pl, ppv) < 0:
            raise ValueError(f"第{t}时段含非有限值、负电价或负功率")
        result.append({"t": t, "source_excel_row": t + 1,
                       "source_endpoint": str(row[0]),
                       "interval": f"{clock_label(endpoint - 10)}-{clock_label(endpoint)}",
                       "start_minute": endpoint - 10, "end_minute": endpoint,
                       "price_yuan_per_kwh": p, "load_kw": pl, "pv_kw": ppv,
                       "load_kwh": pl * DT, "pv_kwh": ppv * DT})
    return result


def arrays(data):
    return tuple(np.array([r[key] for r in data], dtype=float)
                 for key in ("price_yuan_per_kwh", "load_kwh", "pv_kwh"))


def build_problem(data, eta_c, eta_d=None, *, e_min=E_MIN, e_max=E_MAX, charge_kw=5000.0,
                  discharge_kw=5000.0, baseline="full", fixed_mode=None):
    """共享第10节原式；11.3–11.8只改变明确指定的边界或整数性。"""
    eta_d = eta_c if eta_d is None else eta_d
    p, load, pv = arrays(data)
    if not np.all(np.isfinite([p, load, pv])) or min(p.min(), load.min(), pv.min()) < 0:
        raise ValueError("电价、负荷、光伏必须有限且非负")
    if not (0 < eta_c <= 1 and 0 < eta_d <= 1) or not np.all(np.isfinite([e_min, e_max, charge_kw, discharge_kw])):
        raise ValueError("效率或设备边界无效")
    if not 0 <= e_min <= E_INITIAL <= e_max or min(charge_kw, discharge_kw) < 0:
        raise ValueError("设备边界与初始状态不兼容")
    if baseline not in ("full", "no_ess", "pv_only"):
        raise ValueError("未知基准")
    qc, qd = charge_kw * DT, discharge_kw * DT
    n = len(data)
    names = ("G", "C", "D", "E", "W", "u")
    index = {name: np.arange(k * n, (k + 1) * n) for k, name in enumerate(names)}
    size = len(names) * n
    objective = np.zeros(size)
    objective[index["G"]] = p
    lower, upper = np.zeros(size), np.full(size, np.inf)
    lower[index["E"]], upper[index["E"]] = e_min, e_max
    lower[index["E"][-1]] = upper[index["E"][-1]] = E_INITIAL
    upper[index["W"]] = pv
    upper[index["u"]] = 1
    if fixed_mode is not None:
        mode = np.asarray(fixed_mode)
        if mode.shape != (n,) or not np.all(np.isin(mode, [0, 1])):
            raise ValueError("固定模式必须是逐时0/1整数")
        lower[index["u"]] = upper[index["u"]] = mode
    if baseline == "no_ess":
        upper[index["C"]] = upper[index["D"]] = 0
    elif baseline == "pv_only":
        upper[index["C"]] = np.maximum(pv - load, 0)
        upper[index["D"]] = np.maximum(load - pv, 0)
    # CR-11：富余光伏时禁止购电，两层基准共同采用，保持可行域嵌套。
    if baseline in ("no_ess", "pv_only"):
        upper[index["G"][pv > load]] = 0
    integer = np.zeros(size, dtype=int)
    integer[index["u"]] = 1
    a = np.zeros((4 * n, size))
    lb, ub = np.full(4 * n, -np.inf), np.zeros(4 * n)
    for t in range(n):
        # 第7.2节：G - C + D - W = L - S。
        for name, coefficient in (("G", 1), ("C", -1), ("D", 1), ("W", -1)):
            a[t, index[name][t]] = coefficient
        lb[t] = ub[t] = load[t] - pv[t]
        # 第8节：E_t - E_(t-1) - eta_c C + D/eta_d = 0。
        a[n + t, index["E"][t]] = 1
        a[n + t, index["C"][t]] = -eta_c
        a[n + t, index["D"][t]] = 1 / eta_d
        if t:
            a[n + t, index["E"][t - 1]] = -1
        lb[n + t] = ub[n + t] = E_INITIAL if t == 0 else 0
        # 第9节：C <= Q u；D <= Q (1-u)。
        a[2 * n + t, index["C"][t]] = 1
        a[2 * n + t, index["u"][t]] = -qc
        a[3 * n + t, index["D"][t]] = 1
        a[3 * n + t, index["u"][t]] = qd
        ub[3 * n + t] = qd
    return {"objective": objective, "index": index, "integer": integer,
            "lower": lower, "upper": upper, "a": csc_matrix(a), "lb": lb, "ub": ub,
            "eta_c": eta_c, "eta_d": eta_d,
            "settings": {"e_min": e_min, "e_max": e_max, "charge_kw": charge_kw,
                         "discharge_kw": discharge_kw, "baseline": baseline}}


def solve_milp(problem):
    """对给定矩阵求原整数问题，保留不可行状态供双侧扰动诊断。"""
    # 三个容差是HiGHS原生选项；SciPy按其提示原样传递。只屏蔽这一转发通知。
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=RuntimeWarning,
                                message=r"Unrecognized options detected: .*These will be passed to HiGHS verbatim\.")
        result = milp(problem["objective"], integrality=problem["integer"],
                      bounds=Bounds(problem["lower"], problem["upper"]),
                      constraints=LinearConstraint(problem["a"], problem["lb"], problem["ub"]),
                      options=SOLVER_OPTIONS)
    return result


def solve(data, eta_c, eta_d=None, **settings):
    """MILP全局求解；分别参数化两种效率，默认相等兼容既有调用。"""
    problem = build_problem(data, eta_c, eta_d, **settings)
    result = solve_milp(problem)
    if not result.success or result.status != 0:
        raise RuntimeError(f"MILP未获得最优解，拒绝导出：{result.message}")
    solution = {name: result.x[index].tolist() for name, index in problem["index"].items()}
    solution.update({"E0": E_INITIAL, "eta_c": problem["eta_c"], "eta_d": problem["eta_d"],
                     "settings": problem["settings"],
                     "solver": {"status": int(result.status), "message": result.message,
                                "objective_yuan": float(result.fun),
                                "dual_bound_yuan": float(result.mip_dual_bound),
                                "mip_gap": float(result.mip_gap),
                                "node_count": int(result.mip_node_count),
                                "variables": 6 * len(data), "binary_variables": len(data),
                                "linear_constraint_rows": 4 * len(data),
                                "options": SOLVER_OPTIONS}})
    return solution


def solve_lp(problem, rhs_shift=None):
    """保留所有原约束的连续LP；rhs_shift仅用于固定模式局部数值校验。"""
    n = len(problem["index"]["G"])
    rhs = problem["ub"][:2 * n].copy()
    if rhs_shift is not None:
        row, amount = rhs_shift
        rhs[row] += amount
    return linprog(problem["objective"], A_eq=problem["a"][:2 * n], b_eq=rhs,
                   A_ub=problem["a"][2 * n:], b_ub=problem["ub"][2 * n:],
                   bounds=list(zip(problem["lower"], problem["upper"])), method="highs-ds",
                   options={"primal_feasibility_tolerance": 1e-9,
                            "dual_feasibility_tolerance": 1e-9})


def check_solution(data, solution):
    """独立从物理等式复算，不依赖求解器的约束矩阵；失败即中止输出。"""
    p, load, pv = arrays(data)
    g, c, d, e, w, u = (np.asarray(solution[k], dtype=float)
                        for k in ("G", "C", "D", "E", "W", "u"))
    if any(a.shape != p.shape or not np.all(np.isfinite(a)) for a in (g, c, d, e, w, u)):
        raise ValueError("变量长度不符或含非有限值")
    e0, ec, ed = solution["E0"], solution["eta_c"], solution["eta_d"]
    settings = solution.get("settings", {})
    emin, emax = settings.get("e_min", E_MIN), settings.get("e_max", E_MAX)
    qc, qd = settings.get("charge_kw", 5000) * DT, settings.get("discharge_kw", 5000) * DT
    prior = np.r_[e0, e[:-1]]
    metrics = {
        "11.1_balance_max_abs_kwh": float(np.max(np.abs(g + pv - w + d - load - c))),
        "11.2_soc_max_abs_kwh": float(np.max(np.abs(e - prior - ec * c + d / ed))),
        "11.3_soc_bound_violation_kwh": float(max(0, np.max(emin - e), np.max(e - emax))),
        "11.4_power_bound_violation_kwh": float(max(0, np.max(c - qc), np.max(d - qd))),
        "11.5_simultaneous_kwh": float(max(0, np.max(np.minimum(c, d)))),
        "11.6_nonnegative_violation_kwh": float(max(0, -np.min([g, c, d, w]))),
        "11.7_curtail_bound_violation_kwh": float(max(0, -w.min(), np.max(w - pv))),
        "11.8_initial_error_kwh": float(abs(e0 - E_INITIAL)),
        "11.8_terminal_error_kwh": float(abs(e[-1] - E_INITIAL)),
        "11.9_objective_recalculation_error_yuan": float(abs(p @ g - solution["solver"]["objective_yuan"])),
        "9_binary_distance": float(np.max(np.abs(u - np.rint(u)))),
        "9_binary_bound_violation": float(max(0, -u.min(), u.max() - 1)),
        "9_binary_coupling_violation_kwh": float(max(0, np.max(c - qc * u), np.max(d - qd * (1 - u)))),
        "10_primal_dual_gap_yuan": float(abs(p @ g - solution["solver"]["dual_bound_yuan"])),
        "day_energy_identity_error_kwh": float(abs(g.sum() + pv.sum() - w.sum() - load.sum()
                                                  - (1 - ec) * c.sum() - (1 / ed - 1) * d.sum()
                                                  - (e[-1] - e0))),
    }
    if settings.get("baseline") == "no_ess":
        metrics["11.4_no_ess_activity_kwh"] = float(max(np.max(np.abs(c)), np.max(np.abs(d))))
    if settings.get("baseline") == "pv_only":
        metrics["11.4_pv_only_bound_violation_kwh"] = float(max(
            0, np.max(c - np.maximum(pv - load, 0)), np.max(d - np.maximum(load - pv, 0))))
    if settings.get("baseline") in ("no_ess", "pv_only"):
        metrics["11.4_surplus_grid_source_kwh"] = float(np.max(np.abs(g[pv > load]), initial=0))
    metrics["11.2_relative_global_gap"] = float(abs(p @ g - solution["solver"]["dual_bound_yuan"])
                                                 / max(1, abs(p @ g)))
    metric_tolerances = {key: COST_TOL_YUAN if key.endswith("_yuan") else
                         MIP_GAP_TOL if key.endswith("relative_global_gap") else
                         BINARY_TOL if key in ("9_binary_distance", "9_binary_bound_violation") else
                         PHYS_TOL_KWH for key in metrics}
    failed = {key: val for key, val in metrics.items()
              if not np.isfinite(val) or val > metric_tolerances[key]}
    if (solution["solver"]["status"] != 0 or not np.isfinite(solution["solver"]["mip_gap"])
            or solution["solver"]["mip_gap"] > MIP_GAP_TOL):
        failed["solver_status_or_gap"] = solution["solver"]
    if failed:
        raise ValueError(f"物理/最优性检查失败：{failed}")
    return {"passed": True, "tolerances": TOLERANCES, "metric_tolerances": metric_tolerances, "metrics": metrics}


def schedule_rows(data, solution):
    rows = []
    for t, record in enumerate(data):
        row = dict(record)
        row.update({f"{name}_kwh": solution[name][t] for name in ("G", "C", "D", "E", "W")})
        row["u"] = solution["u"][t]
        row["E_start_kwh"] = solution["E0"] if t == 0 else solution["E"][t - 1]
        row["soc_fraction"] = solution["E"][t] / 12000
        row["cost_yuan"] = record["price_yuan_per_kwh"] * solution["G"][t]
        rows.append(row)
    return rows


def summary(data, solution):
    p, load, pv = arrays(data)
    g, c, d, e, w = (np.asarray(solution[k]) for k in ("G", "C", "D", "E", "W"))
    return {"eta_c": solution["eta_c"], "eta_d": solution["eta_d"],
            "roundtrip_efficiency": solution["eta_c"] * solution["eta_d"],
            "cost_yuan": float(p @ g), "grid_kwh": float(g.sum()),
            "curtail_kwh": float(w.sum()), "charge_kwh": float(c.sum()),
            "discharge_kwh": float(d.sum()), "load_kwh": float(load.sum()),
            "pv_kwh": float(pv.sum()), "soc_min_kwh": float(e.min()),
            "soc_max_kwh": float(e.max()), "initial_kwh": solution["E0"], "terminal_kwh": float(e[-1]),
            "loss_kwh": float((1 - solution["eta_c"]) * c.sum() + (1 / solution["eta_d"] - 1) * d.sum()),
            "charge_weighted_price": float(p @ c / c.sum()) if c.sum() > PHYS_TOL_KWH else None,
            "discharge_weighted_price": float(p @ d / d.sum()) if d.sum() > PHYS_TOL_KWH else None,
            "pv_surplus_kwh": float(np.maximum(pv - load, 0).sum()),
            "pv_surplus_absorbed_kwh": float(np.minimum(c, np.maximum(pv - load, 0)).sum())}


def block_rows(solution):
    return [{"interval": f"{clock_label(h * 60)}-{clock_label((h + 4) * 60)}",
             "charge_kwh": float(sum(solution["C"][h * 6:(h + 4) * 6])),
             "discharge_kwh": float(sum(solution["D"][h * 6:(h + 4) * 6]))}
            for h in range(0, 24, 4)]
