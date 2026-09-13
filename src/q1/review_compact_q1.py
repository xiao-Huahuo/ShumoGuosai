"""Independent numerical evidence for the compact Q1 manuscript review.

Run: uv run --with scipy --with openpyxl python src/q1/review_compact_q1.py
Input timestamps are provisionally interval endpoints; energies are bus-side.
These are audit experiments, not an official result1 submission.
"""

import hashlib
import json
from pathlib import Path

import numpy as np
import scipy
from openpyxl import load_workbook
from scipy.optimize import Bounds, LinearConstraint, linprog, milp
from scipy.sparse import csc_matrix


ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "docs/CUMCM2026Problems/C题/附件"
MANUSCRIPT = Path("/Users/slumpyfufu/Library/Containers/com.tencent.xinWeChat/Data/Documents/xwechat_files/wxid_upurj1c0hwme22_9950/temp/drag/Q1_精简修订版_公式兼容Obsidian.md")
# Captured on the first successful run, before WeChat's temporary file disappeared.
MANUSCRIPT_SHA256 = "84bac79a12fb2a3db018b230b9d93653fb3154ef1e48682ad7f209816a8634b3"


def solve(p, load, pv, physical=False, integer=False, ec=0.9, ed=0.9,
          q=5000/6, lower=1200, upper=10800, initial=6000,
          service="both", internal_power=False, epsilon=0, free_x=False,
          range_index=None):
    n = len(p)
    names = ["gL", "gB", "vL", "vB", "z", "u"] if physical else ["x", "y", "z"]
    index = {name: np.arange(k*n, (k+1)*n) for k, name in enumerate(names)}
    index["E"] = np.arange(len(names)*n, (len(names)+1)*n+1)
    size = (len(names)+1)*n+1
    if integer:
        index["b"] = np.arange(size, size+n)
        size += n
    lo, hi = np.zeros(size), np.full(size, np.inf)
    lo[index["E"]], hi[index["E"]] = lower, upper
    lo[index["E"][[0, -1]]] = initial
    hi[index["E"][[0, -1]]] = initial
    if integer:
        hi[index["b"]] = 1
    if free_x:
        lo[index["x"]] = -np.inf
    charge = ["gB", "vB"] if physical else ["x", "y"]
    d, r = np.maximum(load-pv, 0), np.maximum(pv-load, 0)
    if not physical:
        hi[index["y"]], hi[index["z"]] = r, d
        if service in ("grid", "none"):
            hi[index["y"]] = 0
        if service in ("pv", "none"):
            hi[index["x"]] = 0
        if service == "none":
            hi[index["z"]] = 0
    cost, throughput = np.zeros(size), np.zeros(size)
    if physical:
        cost[index["gL"]], cost[index["gB"]] = p, p
        constant = 0
    else:
        cost[index["x"]], cost[index["z"]] = p, -p
        constant = float(p @ d)
    for name in charge:
        throughput[index[name]] = ec
    throughput[index["z"]] = 1/ed
    eq, rhs, ub, limits = [], [], [], []

    def row(terms):
        result = np.zeros(size)
        for column, value in terms:
            result[column] = value
        return result

    for t in range(n):
        if physical:
            eq.append(row([(index[k][t], 1) for k in ["gL", "vL", "z"]]))
            rhs.append(load[t])
            eq.append(row([(index[k][t], 1) for k in ["vL", "vB", "u"]]))
            rhs.append(pv[t])
        eq.append(row([(index["E"][t+1], 1), (index["E"][t], -1),
                       (index["z"][t], 1/ed)] + [(index[k][t], -ec) for k in charge]))
        rhs.append(0)
        qc, qd = (q/ec, q*ed) if internal_power else (q, q)
        ub.append(row([(index[k][t], 1) for k in charge]
                      + ([(index["b"][t], -qc)] if integer else [])))
        limits.append(0 if integer else qc)
        ub.append(row([(index["z"][t], 1)]
                      + ([(index["b"][t], qd)] if integer else [])))
        limits.append(qd)
    eq, rhs, ub, limits = map(np.array, (eq, rhs, ub, limits))
    integrality = np.zeros(size)
    if integer:
        integrality[index["b"]] = 1

    def optimize(objective, extra_eq=None, extra_rhs=None, cost_cap=None):
        aeq = eq if extra_eq is None else np.vstack([eq, extra_eq])
        beq = rhs if extra_rhs is None else np.r_[rhs, extra_rhs]
        aub = ub if cost_cap is None else np.vstack([ub, cost])
        bub = limits if cost_cap is None else np.r_[limits, cost_cap]
        if integer:
            result = milp(objective, integrality=integrality, bounds=Bounds(lo, hi),
                          constraints=[LinearConstraint(csc_matrix(aeq), beq, beq),
                                       LinearConstraint(csc_matrix(aub), -np.inf, bub)],
                          options={"mip_rel_gap": 1e-10, "time_limit": 30})
        else:
            result = linprog(objective, A_eq=aeq, b_eq=beq, A_ub=aub, b_ub=bub,
                             bounds=list(zip(lo, hi)), method="highs")
        if not result.success:
            raise RuntimeError(result.message)
        return result

    first = optimize(cost)
    second = optimize(throughput, cost, first.fun) if epsilon == 0 else optimize(throughput, cost_cap=first.fun+epsilon)
    solution = second.x
    c = sum(solution[index[k]] for k in charge)
    z, e = solution[index["z"]], solution[index["E"]]
    grid = solution[index["gL"]]+solution[index["gB"]] if physical else d-z+solution[index["x"]]
    curt = solution[index["u"]] if physical else r-solution[index["y"]]
    summary = {"primary_cost": float(first.fun+constant), "cost": float(cost @ solution+constant),
               "internal_throughput": float(throughput @ solution), "grid_kwh": float(grid.sum()),
               "charge_kwh": float(c.sum()), "discharge_kwh": float(z.sum()),
               "curtail_kwh": float(curt.sum()), "state_min": float(e.min()), "state_max": float(e.max()),
               "state_initial": float(e[0]), "state_final": float(e[-1]),
               "max_equation_residual": float(np.max(np.abs(eq @ solution-rhs))),
               "max_inequality_violation": float(max(0, np.max(ub @ solution-limits))),
               "max_bound_violation": float(max(0, np.max(lo-solution), np.max(solution-hi))),
               "max_simultaneous_kwh": float(np.minimum(c,z).max()),
               "whole_day_energy_residual": float(abs(grid.sum()+pv.sum()-curt.sum()-load.sum()-(1-ec)*c.sum()-(1/ed-1)*z.sum()))}
    if integer:
        summary["primary_mip_gap"] = float(first.mip_gap)
    if range_index is not None:
        name, t = range_index
        objective = row([(index[name][t], 1)])
        a = np.vstack([cost, throughput])
        b = np.array([first.fun, second.fun])
        summary["optimal_face_range"] = [float(optimize(objective, a, b).fun),
                                         float(-optimize(-objective, a, b).fun)]
    return summary, {"grid": grid.tolist(), "charge": c.tolist(), "discharge": z.tolist(),
                     "state": e.tolist(), "curtail": curt.tolist()}


def main():
    records = list(load_workbook(BASE/"附件1.xlsx", read_only=True, data_only=True).active.values)[1:]
    a = np.array([r[1:] for r in records])
    p, load, pv = a[:, 0], a[:, 1]/6, a[:, 2]/6
    report = {"scipy_version": scipy.__version__, "assumptions": __doc__,
              "manuscript_sha256_at_first_read": {str(MANUSCRIPT): MANUSCRIPT_SHA256},
              "sha256": {str(f): hashlib.sha256(f.read_bytes()).hexdigest()
                         for f in [BASE/"附件1.xlsx", BASE/"附件5/result1.xlsx"]},
              "input": {"n": len(p), "price_min": float(p.min()), "price_max": float(p.max()),
                        "surplus_kwh": float(np.maximum(pv-load, 0).sum())}, "cases": {}, "schedules": {}}
    surplus_slot = int(np.argmax(pv-load))
    cases = {"physical_milp": {"physical": True, "integer": True},
             "canonical_milp": {"integer": True}, "canonical_lp": {"range_index": ("y", surplus_slot)},
             "no_storage": {"service": "none"}, "pv_only": {"service": "pv"},
             "grid_only": {"service": "grid"}, "roundtrip90_symmetric": {"ec": np.sqrt(.9), "ed": np.sqrt(.9)},
             "roundtrip90_c90_d100": {"ec": .9, "ed": 1}, "roundtrip90_c100_d90": {"ec": 1, "ed": .9},
             "power_internal": {"internal_power": True}, "epsilon_1e_6_yuan": {"epsilon": 1e-6},
             "missing_x_lower_bound": {"free_x": True}}
    for name, options in cases.items():
        report["cases"][name], report["schedules"][name] = solve(p, load, pv, **options)
    report["cases"]["shift_all_10min"], _ = solve(np.roll(p,1), np.roll(load,1), np.roll(pv,1))
    report["range_interval_endpoint"] = str(records[surplus_slot][0])
    rng = np.random.default_rng(20260910)
    stress = []
    for trial in range(30):
        sp = rng.choice([0., .2, 1.], 6)
        sl, sv = rng.uniform(0, 8, (2, 6))
        opts = {"q": 4, "lower": 1, "upper": 10, "initial": float(rng.choice([1, 5, 10]))}
        physical, _ = solve(sp, sl, sv, physical=True, integer=True, **opts)
        canonical, _ = solve(sp, sl, sv, **opts)
        stress.append({"trial": trial, "prices": sp.tolist(), "load": sl.tolist(), "pv": sv.tolist(),
                       "options": opts, "cost_gap": abs(physical["cost"]-canonical["cost"]),
                       "throughput_gap": abs(physical["internal_throughput"]-canonical["internal_throughput"])})
    report["stress_cases"] = stress
    report["synthetic_nonunique"], _ = solve(
        np.array([.1, .1, 1.]), np.array([0., 0., 1.]), np.zeros(3),
        q=2, lower=0, upper=2, initial=0, range_index=("x", 0))
    target = ROOT/"outputs/q1/raw/q1_compact_review_evidence.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps({"cases": report["cases"], "input": report["input"],
                      "range_interval_endpoint": report["range_interval_endpoint"],
                      "stress_count": len(stress),
                      "max_stress_cost_gap": max(s["cost_gap"] for s in stress),
                      "max_stress_throughput_gap": max(s["throughput_gap"] for s in stress)},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
