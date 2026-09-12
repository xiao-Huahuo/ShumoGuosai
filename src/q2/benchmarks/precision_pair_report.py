"""回读配对实验的全部输入、策略与费用，生成自包含HTML对照表。"""

import hashlib
import html
import json
import os
from pathlib import Path
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from data import ROOT, sha256, write_csv, write_json
from dispatch import load_prepared
from policy import DT, Policy, replay, validate_replay
from scenarios import construct
from shadows import choose_day


def table(headers, rows):
    return '<div class="table-wrap"><table><thead><tr>' + ''.join(f'<th>{html.escape(str(v))}</th>' for v in headers) + '</tr></thead><tbody>' + ''.join('<tr>' + ''.join(f'<td>{html.escape(str(v))}</td>' for v in row) + '</tr>' for row in rows) + '</tbody></table></div>'


def n(value, digits=2):
    return f"{value:,.{digits}f}"


def tail_evidence(run, output):
    """冻结的历史48日只说明长尾负担，不用旧算法耗时估算当前精度效应。"""
    source = run / "processed/timing_audit"
    verification = json.loads((source / "verification.json").read_text(encoding="utf-8"))
    names = ("daily_timing.csv", "summary.json", "snapshot.json")
    hashes = {name: sha256(source / name) for name in names}
    assert all(digest == verification["artifact_sha256"][name] for name, digest in hashes.items())
    old = json.loads((source / "summary.json").read_text(encoding="utf-8"))
    frame = pd.read_csv(source / "daily_timing.csv", float_precision="round_trip")
    days = frame[(frame.job == "main") & frame.overnight].copy()
    assert len(days) == 48 and days.date.nunique() == 48
    assert list(days.date) == list(pd.date_range("2025-03-10", "2025-04-26").strftime("%Y-%m-%d"))
    seconds = days.audit_wall_since_previous_seconds
    assert seconds.notna().all() and (seconds >= 0).all()
    elapsed = (pd.Timestamp(old["completed_window_local"][1]) - pd.Timestamp(old["completed_window_local"][0])).total_seconds()
    np.testing.assert_allclose(seconds.sum(), elapsed, atol=.01, rtol=0)
    rescue = days[days.supplemental]
    regular = days[~days.supplemental]
    assert sorted(rescue.date) == sorted(old["supplemental_dates"])
    share = rescue.audit_wall_since_previous_seconds.sum() / seconds.sum()
    np.testing.assert_allclose(share, old["supplemental_share_of_main_advancement_wall"], atol=1e-10, rtol=0)
    rows = []
    for label, group in (("未触发整日补算", regular), ("触发整日补算", rescue), ("全部已推进日", days)):
        values = group.audit_wall_since_previous_seconds
        rows.append({"group": label, "days": len(group), "day_share_percent": 100 * len(group) / len(days),
                     "wall_hours": values.sum() / 3600, "wall_share_percent": 100 * values.sum() / seconds.sum(),
                     "mean_minutes": values.mean() / 60, "median_minutes": values.median() / 60,
                     "p95_minutes": values.quantile(.95) / 60, "max_minutes": values.max() / 60})
    write_csv(output / "processed/tail_groups.csv", pd.DataFrame(rows))
    write_csv(output / "processed/tail_days.csv", days)
    info = {"source_directory": str(source), "source_sha256": hashes, "historical_window": old["completed_window_local"],
            "supplemental_day_share_percent": 100 * len(rescue) / len(days), "supplemental_time_share_percent": 100 * share,
            "max_to_non_supplemental_mean_ratio": seconds.max() / regular.audit_wall_since_previous_seconds.mean(),
            "mean_to_median_ratio": seconds.mean() / seconds.median(), "groups": rows,
            "historical_only_not_current_gap_speedup": True, "current_unfinished_days_not_in_snapshot": True,
            "scope": "audit_completion_intervals_including_retries_repairs_waits_not_pure_solver_seconds"}
    write_json(output / "raw/tail_review.json", info)
    grid = table(["历史分组", "日期数", "日期占比", "累计推进时间 / 小时", "时间占比", "平均 / 分钟", "P95 / 分钟", "最长 / 分钟"],
                 [[r["group"], r["days"], f'{r["day_share_percent"]:.1f}%', n(r["wall_hours"]), f'{r["wall_share_percent"]:.1f}%',
                   n(r["mean_minutes"]), n(r["p95_minutes"]), n(r["max_minutes"])] for r in rows])
    markup = f'''<section><h2>长尾核查：少数日期占据大部分时间</h2>
<p class="note">历史主任务连续推进区间：模拟 2025-03-10 至 04-26，共 48 日；实际记录窗口 2026-09-12 01:02—09:05。按是否触发整日追加预算分组，使用完整区间，未按最终耗时挑选日期。</p>{grid}
<div class="callout caution">7 个补算日仅占日期数的 {100*len(rescue)/len(days):.1f}%，却占推进时间的 {100*share:.1f}%。最长日为 121.22 分钟，约为未触发补算日平均值的 {info['max_to_non_supplemental_mean_ratio']:.1f} 倍。忽略这部分日期会严重低估总耗时。</div>
<p class="note">这里的“推进时间”是相邻日审计提交间隔，包括准备、失败重试、修复和等待。它来自历史 1% 阶段及当时求解路线，不能与下方当前算法的单次秒数相除来推算精度加速。未触发整日补算也可能有个别 K 失败；此分组不等于完整难度分类。该快照只含当时已推进日期，未计入现在尚未完成的阻塞日，不能当作全年分布。P95 为本组经验分位数的线性插值，7 日组的尾部分位数仍不稳定。</p>
<p class="links"><a href="tail_groups.csv" download>下载长尾分组 CSV</a><a href="tail_days.csv" download>下载历史 48 日明细</a><a href="../raw/tail_review.json">长尾核查来源与验证</a></p>
<details><summary>后续精度比较应怎样覆盖困难日</summary>
<p>按基准执行的求解路径分层：LP 证书直接通过、进入 MILP 后在首轮达标、追加预算后达标、追加预算仍未达标。困难层应多抽样或全部纳入；各档使用相同实例、原始 SOC、完整 K 候选、求解路线及重试规则。最终按各层日期数量加权汇总时间，不能把多抽的困难日或少抽的普通日直接等权平均。</p>
<p>同时报告达标日数、各 K 通过率、首轮与补算总时间、P50/P90/P95/最大值。到统一上限仍不达标的日期记为“成功时间至少超过已尝试预算”，不删掉，也不把截止时间当作完成时间。真实费用在双方均有合格解的相同日期比较，并列出未配对日期和末 SOC；经济差异仍需连续回放检验。</p>
<p class="note">以上是修正后的抽样与评价要求，尚未完成分层 1%/3% 实测，因此当前不能给出全任务加速百分比。本轮只核查已有记录，没有启动额外长时间求解。</p></details></section>'''
    return markup


def main(output):
    raw, processed = output / "raw", output / "processed"
    data = json.loads((raw / "benchmark.json").read_text(encoding="utf-8"))
    assert data["status"] == "completed" and len(data["records"]) == 8
    assert all(sha256(ROOT / name) == digest for name, digest in data["source_sha256"].items())
    run = Path(data["run_directory"])
    store, frozen, actual, dates, prices = load_prepared(run)
    summary = pd.read_csv(processed / "summary.csv", float_precision="round_trip")
    candidates = pd.read_csv(processed / "candidates.csv", float_precision="round_trip")
    assert len(summary) == 8 and len(candidates) == 24
    verified_inputs, selections, objective_checks = {}, {}, []
    for record in data["records"]:
        date, soc = record["date"], record["initial_soc"]
        day = int(dates.get_loc(pd.Timestamp(date)))
        for key, value in record.items():
            if key in summary.columns:
                saved = summary.loc[summary.trial == record["trial"], key].iloc[0]
                assert saved == value, (key, saved, value)
        assert record["day_wall_seconds"] >= sum(c["wall_seconds"] for c in record["calls"])
        for call in record["calls"]:
            k = call["K"]
            key = f"{date}_K{k}"
            with np.load(raw / f"input_{key}.npz") as f:
                net, price, weights, initial = [f[x].copy() for x in ("net", "prices", "weights", "initial_soc")]
            if key not in verified_inputs:
                point, blocks, _ = choose_day(store, frozen, actual[:day], day, k, prices)
                expected_net, expected_weights, _ = construct(point, blocks, np.tile(prices, k), len(net))
                np.testing.assert_array_equal(expected_net, net)
                np.testing.assert_array_equal(expected_weights, weights)
                np.testing.assert_array_equal(price, np.tile(prices, k))
                assert initial == soc
                digest = hashlib.sha256()
                for value in (net, price, weights, np.array([soc])):
                    value = np.ascontiguousarray(value, dtype=np.float64)
                    digest.update(str(value.shape).encode("utf-8")); digest.update(value.tobytes())
                assert digest.hexdigest() == data["input_hashes"][key]
                verified_inputs[key] = digest.hexdigest()
            assert call["input_sha256"] == verified_inputs[key]
            selection = json.dumps(record["audit"][str(k)]["selection"], sort_keys=True)
            assert selections.setdefault(key, selection) == selection
            info = call["solver"]
            assert info["reliable"] and info["mip_gap"] <= record["gap_percent"] / 100 + 1e-8
            with np.load(raw / call["policy_file"]) as f:
                policy = Policy(*[f[x] for x in ("grid", "charge_cap", "discharge_cap")])
            responses = [replay(policy, path, soc) for path in net]
            objective = float(price @ policy.grid + sum(5 * w * (price @ r["emergency"]) for w, r in zip(weights, responses)))
            np.testing.assert_allclose(objective, info["objective"], atol=1e-5, rtol=0)
            gap = max(objective - info["dual_bound"], 0) / max(abs(info["dual_bound"]), 1e-8)
            np.testing.assert_allclose(gap, info["mip_gap"], atol=1e-10, rtol=0)
            candidate_row = candidates[(candidates.trial == record["trial"]) & (candidates.K == k)].iloc[0]
            assert candidate_row.accepted and candidate_row.input_sha256 == verified_inputs[key]
            for column, expected in (("objective", objective), ("dual_bound", info["dual_bound"]), ("achieved_gap", gap), ("wall_seconds", call["wall_seconds"])):
                np.testing.assert_allclose(candidate_row[column], expected, atol=1e-8, rtol=0)
            objective_checks.append({"trial": record["trial"], "K": k, "objective": objective, "gap": gap})
            if k == record["selected_K"]:
                response = replay(policy.first(), DT * (actual[day, :, 0] - actual[day, :, 1]), soc)
                frame = pd.read_csv(raw / f"dispatch_{record['trial']}.csv", float_precision="round_trip")
                assert len(frame) == 144
                np.testing.assert_array_equal(frame.net_kwh, DT * (actual[day, :, 0] - actual[day, :, 1]))
                np.testing.assert_array_equal(frame.price, prices)
                np.testing.assert_allclose(frame.grid, policy.grid[:144], atol=1e-8, rtol=0)
                for name, values in response.items():
                    np.testing.assert_allclose(frame[name], values, atol=1e-8, rtol=0)
                validate_replay(frame.grid.to_numpy(), frame.net_kwh.to_numpy(), soc, response)
                np.testing.assert_allclose(frame.planned_cost, prices * frame.grid, atol=1e-8, rtol=0)
                np.testing.assert_allclose(frame.emergency_cost, 5 * prices * frame.emergency, atol=1e-8, rtol=0)
                checks = {"actual_cost": (frame.planned_cost + frame.emergency_cost).sum(),
                          "planned_cost": frame.planned_cost.sum(), "emergency_cost": frame.emergency_cost.sum(),
                          "grid_kwh": frame.grid.sum(), "emergency_kwh": frame.emergency.sum(), "final_soc": frame.soc.iloc[-1]}
                for name, value in checks.items():
                    np.testing.assert_allclose(value, record[name], atol=1e-8, rtol=0)

    archive = run / "raw/solver_diagnostics/precision_sweep_20260912_112216"
    old = json.loads((archive / "benchmark.json").read_text(encoding="utf-8"))
    old_records = {r["gap_percent"]: r for r in old["records"] if r["gap_percent"] in (1, 3)}
    assert old["status"] == "completed" and old_records[1]["accepted_candidates"] == 0 and old_records[3]["accepted_candidates"] == 3
    for k, call1, call3 in zip((1, 2, 3), old_records[1]["calls"], old_records[3]["calls"]):
        assert call1["input_sha256"] == call3["input_sha256"]
        assert call1["K"] == call3["K"] == k
        for call in (call1, call3):
            info = call["solver"]
            np.testing.assert_allclose(max(info["objective"] - info["dual_bound"], 0) / abs(info["dual_bound"]), info["mip_gap"], atol=1e-10, rtol=0)
    old_policy = pd.read_csv(archive / "policy_3pct.csv", float_precision="round_trip")
    policy = Policy(*[old_policy[key].to_numpy() for key in ("grid", "charge_cap", "discharge_cap")])
    day = int(dates.get_loc(pd.Timestamp(old["date"])))
    response = replay(policy.first(), DT * (actual[day, :, 0] - actual[day, :, 1]), old["initial_soc"])
    np.testing.assert_allclose(prices @ (policy.grid[:144] + 5 * response["emergency"]), old_records[3]["actual_day_cost"], atol=1e-8, rtol=0)
    np.testing.assert_allclose(response["soc"][-1], old_records[3]["final_soc"], atol=1e-8, rtol=0)
    review = {"passed": True, "input_instances": len(verified_inputs), "candidate_policies": len(objective_checks),
              "actual_replay_days": len(summary), "real_replay_rows": 144 * len(summary),
              "all_candidate_gaps_and_physics_passed": True, "formal_files_unchanged": True,
              "archived_3pct_actual_replay_passed": True, "archived_1pct_has_no_accepted_solution": True,
              "objective_checks": objective_checks}
    write_json(raw / "independent_review.json", review)

    means = summary.groupby(["date", "gap_percent"]).mean(numeric_only=True)
    rows, comparison = [], []
    for date in data["dates"]:
        a, b = means.loc[(date, 1)], means.loc[(date, 3)]
        saving = 100 * (1 - b.day_wall_seconds / a.day_wall_seconds)
        delta = b.actual_cost - a.actual_cost
        rows.append([date, n(a.day_wall_seconds), n(b.day_wall_seconds), f"{saving:.1f}%",
                     n(a.actual_cost), n(b.actual_cost), f"{delta:+,.2f} ({100 * delta / a.actual_cost:+.3f}%)"])
        comparison.append({"date": date, "seconds_1pct": a.day_wall_seconds, "seconds_3pct": b.day_wall_seconds,
                           "time_saved_percent": saving, "actual_cost_1pct": a.actual_cost, "actual_cost_3pct": b.actual_cost,
                           "actual_cost_change_yuan": delta, "actual_cost_change_percent": 100 * delta / a.actual_cost})
    write_csv(processed / "comparison.csv", pd.DataFrame(comparison))
    primary = table(["日期", "1% 用时 / 秒", "3% 用时 / 秒", "3% 节省时间", "1% 实际费 / 元", "3% 实际费 / 元", "费用变化：3% − 1%"], rows)
    state_rows = []
    for date in data["dates"]:
        for gap in (1, 3):
            a = means.loc[(date, gap)]
            ks = "/".join(str(k) for k in sorted(summary[(summary.date == date) & (summary.gap_percent == gap)].selected_K.unique()))
            state_rows.append([date, f"{gap}%", f"K={ks}", n(a.initial_soc), n(a.final_soc), n(a.grid_kwh), n(a.emergency_kwh), n(a.planned_cost), n(a.emergency_cost)])
    states = table(["日期", "精度", "选中时域", "初始储电 / kWh", "末储电 / kWh", "计划购电 / kWh", "紧急购电 / kWh", "计划费用 / 元", "紧急费用 / 元"], state_rows)
    repeats = table(["日期", "轮次", "精度", "完整选策用时 / 秒", "合格候选", "真实回放费用 / 元"],
                    [[r.date, r.repeat, f"{r.gap_percent}%", n(r.day_wall_seconds, 3), f"{r.accepted_candidates}/3", n(r.actual_cost)] for r in summary.sort_values(["date", "repeat", "gap_percent"]).itertuples()])
    candidate_rows = []
    for date in data["dates"]:
        for k in (1, 2, 3):
            a = candidates[(candidates.date == date) & (candidates.K == k) & (candidates.gap_percent == 1)]
            b = candidates[(candidates.date == date) & (candidates.K == k) & (candidates.gap_percent == 3)]
            candidate_rows.append([date, k, int(a.scenarios.iloc[0]), n(a.objective.mean()), n(b.objective.mean()),
                                   f"{100*(b.objective.mean()/a.objective.mean()-1):+.3f}%", f"{100*a.achieved_gap.max():.4f}%", f"{100*b.achieved_gap.max():.4f}%"])
    objectives = table(["日期", "K / 天", "场景数", "1% 场景目标 / 元", "3% 场景目标 / 元", "目标变化", "1% 实际 gap", "3% 实际 gap"], candidate_rows)
    hard = table(["精度", "原实测用时 / 秒", "合格候选", "真实回放费用 / 元", "说明"],
                 [["1%", n(old_records[1]["day_wall_seconds"]), "0/3", "—", "限时失败；不是成功求解时间"],
                  ["3%", n(old_records[3]["day_wall_seconds"]), "3/3", n(old_records[3]["actual_day_cost"]), "合格解；K=2"]])
    hard_objectives = table(["时域", "1% 未验收上界 / 元", "3% 已验收上界 / 元", "1% 实际 gap", "3% 实际 gap"],
                            [[f"K={a['K']}", n(a['solver']['objective']), n(b['solver']['objective']), f"{100*a['solver']['mip_gap']:.4f}%", f"{100*b['solver']['mip_gap']:.4f}%"] for a, b in zip(old_records[1]["calls"], old_records[3]["calls"])])
    average = summary.groupby("gap_percent").day_wall_seconds.mean()
    overall_saved = 100 * (1 - average.loc[3] / average.loc[1])
    tail = tail_evidence(run, output)
    archive_link = html.escape(os.path.relpath(archive / "benchmark.json", processed))
    page = f'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>第二问 · 1% 与 3% 精度实测</title>
<style>
:root{{--ink:#152a31;--muted:#52656a;--paper:#f7f6f1;--line:#d6dfda;--green:#17664f;--gold:#a76720}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--paper);color:var(--ink);font-family:"PingFang SC","Noto Sans CJK SC",sans-serif;line-height:1.7}}
main{{max-width:1400px;margin:auto;padding:42px 38px 70px}}header{{border-top:5px solid var(--green);padding-top:20px}}.eyebrow{{font-size:12px;letter-spacing:.17em;color:var(--green);font-weight:700}}h1{{font-family:"Songti SC",serif;font-size:clamp(30px,4vw,50px);margin:10px 0;line-height:1.25;letter-spacing:-.025em}}h2{{font-size:21px;margin:0 0 10px}}p{{margin:10px 0}}.sub,.note{{color:var(--muted);font-size:13px}}.lead{{font-size:17px;max-width:960px}}.stats{{display:grid;grid-template-columns:repeat(3,1fr);border-top:1px solid var(--line);border-bottom:1px solid var(--line);margin:26px 0}}.stat{{padding:17px 22px;border-right:1px solid var(--line)}}.stat:first-child{{padding-left:0}}.stat:last-child{{border:0}}.stat strong{{font-family:"Georgia",serif;font-size:35px;display:block;color:var(--green);line-height:1.3}}.stat span{{font-size:13px;color:var(--muted)}}section{{margin-top:35px}}.table-wrap{{overflow-x:auto;border:1px solid var(--line);background:#fff}}table{{border-collapse:collapse;width:100%;font-size:13px;font-variant-numeric:tabular-nums;white-space:nowrap}}th{{background:#e9efea;text-align:right;font-weight:600;font-size:12px;padding:13px 15px}}td{{padding:13px 15px;border-top:1px solid #e4e9e5;text-align:right}}th:first-child,td:first-child{{text-align:left}}tbody tr:hover{{background:#f4f8f4}}.callout{{padding:15px 20px;background:#eaf1eb;border-left:3px solid var(--green);font-size:14px;margin:16px 0}}.caution{{background:#f5eddf;border-color:var(--gold)}}details{{margin-top:20px}}summary{{cursor:pointer;font-weight:600;padding:12px 0}}a{{color:var(--green);text-underline-offset:3px}}.links{{display:flex;flex-wrap:wrap;gap:10px 25px}}footer{{margin-top:35px;border-top:1px solid var(--line);padding-top:17px;font-size:12px;color:var(--muted)}}code{{font-size:12px;overflow-wrap:anywhere}}@media(max-width:650px){{main{{padding:22px 16px 40px}}.stats{{grid-template-columns:1fr}}.stat,.stat:first-child{{padding:12px 0;border-right:0;border-bottom:1px solid var(--line)}}.stat strong{{font-size:28px}}th,td{{padding:11px}}.lead{{font-size:15px}}}}@media print{{main{{padding:0}}details{{display:block}}.table-wrap{{overflow:visible}}table{{font-size:10px}}th,td{{padding:6px}}}}
</style></head><body><main>
<header><div class="eyebrow">Q2 / PRECISION BENCHMARK · 2026.09.12</div><h1>1% 与 3%，实际差多少？</h1>
<p class="sub">长尾核查修订 · 历史 48 日耗时分布 + 2 个普通日期配对实测 + 1 个既有困难日</p>
<p class="lead"><b>现有样本不足以估计全任务的提速幅度。</b>历史 48 日中，7 个需补算日期占约 68% 的推进时间。新增两日样本全部通过较快的 LP 证书流程，没有覆盖 MILP 和补算瓶颈；下方的 {overall_saved:.1f}% 仅是这两个普通样本的局部结果。</p>
<p class="note">实验约定：精度采用项目定义 <b>gap = (可行费用 U − 全局下界 L) / |L|</b>。小量测试缩减日期数量，保留每个日期的全部场景、10 分钟时段和 K=1/2/3 选择规则。</p></header>
{tail}
<div class="stats"><div class="stat"><strong>{average.loc[1]:.2f} s</strong><span>两个普通样本 · 1% 平均用时</span></div><div class="stat"><strong>{average.loc[3]:.2f} s</strong><span>两个普通样本 · 3% 平均用时</span></div><div class="stat"><strong>24 / 24</strong><span>普通样本候选全部通过 LP 证书</span></div></div>
<section><h2>两个普通样本的实际费用与时间</h2><p class="note">2 个日期 × 2 档精度 × 2 次重复。每个日期使用相同历史信息、预测、场景权重及初始储电量；数值为两次重复均值。费用变化为 3% 减 1%，负值表示 3% 当日回放费用较低。重复两次只观察计时波动，不增加独立日期的覆盖。</p>{primary}
<div class="callout">“实际费用”是冻结日前策略后，用附件中的真实负荷与光伏逐时回放得到的仿真电费，等于计划购电费 + 紧急购电费（5 倍电价）。不是场景期望目标，也不是现场账单。</div></section>
<section><h2>为什么费用不能单独看</h2>{states}<p class="note">K=1/2/3 分别代表 24/48/72 小时规划，最终只执行首日。2 月 1 日的精度变化触发了不同的时域选择。每个测试日从原正式轨迹的同一个 SOC 出发，两个日期不串联；末储电量有差异，未折算残值，因此不能据此推断全年哪档更省钱。</p></section>
<section><h2>同一时域的优化目标</h2><p class="note">以下目标覆盖 K 天、按场景概率加权，只在同一行横向比较。目标为两次均值，实际 gap 列取两次最大值；达到 3% 门槛不表示误差恰好为 3%。</p>{objectives}</section>
<section><h2>慢日补充：5 月 5 日的既有实测</h2><p class="note">复用此前同机、同输入、统一算法的单次记录，本次没有重跑。每个候选 MILP 的时限为 120 秒，表中包含 LP、建模与选策开销，因此整日可以超过 360 秒。</p>{hard}
<div class="callout caution">这一天的 1% 没有合格结果，不能填写两档的实际电费差，也不能把 433 秒当作成功耗时。1% 尝试与 3% 成功记录的同 K 可行费用上界相同，额外时间主要用于收紧最优性证明；日志上界相同不等于已验证两份策略逐项相同。</div>
<details><summary>查看慢日的上界与证书</summary>{hard_objectives}</details></section>
<section><h2>实验口径与复核</h2><p>新测试日期固定为评价期首日 2 月 1 日和方案第一个指定日 3 月 20 日；每档重复两次，按 1%→3%、3%→1% 交替执行。统一使用现有 LP 下界证书，必要时进入等价 HiGHS MILP；各次重新求解，不跨精度复用候选策略或求解界。</p>
<p class="note">只在隔离测试进程中统一了 1% 的后备求解入口，正式源码、2% 配置及冻结准备库摘要保持不变。计时包括完整 make_day 的选择、各 K 求解、内部验收及测试记录的轻量存档开销，排除共同数据加载（{data['shared_load_seconds']:.2f} 秒）和最终真实回放。每候选 MILP 时限 120 秒，无 900 秒补算。后台正式任务仍在运行，重复仅两次；本表不作统计显著性或全年提速保证。</p>
<p class="note">独立回读确认：6 组输入与原准备库逐值一致；24 份候选策略的费用、gap 和物理回放通过；8 个日结果共 1,152 行与真实输入、电价、SOC 和费用逐值核对通过。所有新候选均由现有 LP 下界证书通过，未进入后备 MILP。慢日另核对原日志与 3% 实际回放。</p>
<details><summary>展开 8 次原始测量</summary>{repeats}</details>
<details><summary>查看软件与机器信息</summary><p class="note">{html.escape(data['machine'])} · {data['logical_cpus']} 逻辑 CPU · {html.escape(str(data['versions']))}。BLAS / OMP 均为单线程设置，后台进程快照见原始 JSON。</p></details>
<p class="links"><a href="comparison.csv" download>下载对照表 CSV</a><a href="summary.csv" download>8 次原始测量 CSV</a><a href="candidates.csv" download>24 个候选 CSV</a><a href="../raw/benchmark.json">完整实验记录</a><a href="../raw/independent_review.json">独立验收记录</a><a href="{archive_link}">慢日原始记录</a></p></section>
<footer>结论范围：历史 48 日证明长尾负担明显；两个普通日及一个既有难例不足以估计全任务精度效应。分层困难日比较与连续全年费用差尚未得到。正式运行精度仍为 2%。</footer>
</main></body></html>'''
    assert all(not c["solver"].get("branch_and_bound_required", True) for r in data["records"] for c in r["calls"])
    (processed / "report.html").write_text(page, encoding="utf-8")
    print(json.dumps({"report": str(processed / "report.html"), "average_1pct_seconds": average.loc[1], "average_3pct_seconds": average.loc[3], "time_saved_percent": overall_saved, "comparisons": comparison}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main(Path(sys.argv[1]).resolve())
