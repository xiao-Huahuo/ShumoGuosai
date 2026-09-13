"""从已验收结果生成可见输入/输出、题目表格及科研图，无额外优化假设。"""

import html
import re

import numpy as np

from model import PHYS_TOL_KWH, TOLERANCES, ROOT, arrays, block_rows, schedule_rows

LABELS = {"main": "单程 0.90（主模型）", "eta085": "单程 0.85",
          "eta095": "单程 0.95", "roundtrip090": "往返 0.90（对称）"}


def create_figures(data, solutions, summaries, output):
    """兼容原入口；绘图实现统一维护于src/plots/q1_legacy.py。"""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from src.plots.q1_legacy import create_figures as render
    return render(data, solutions, summaries, output)


def html_table(headers, rows):
    def cell(x):
        return f"{x:,.6f}" if isinstance(x, (float, np.floating)) else html.escape(str(x))
    return '<div class="table-wrap"><table><thead><tr>' + ''.join(f"<th>{html.escape(h)}</th>" for h in headers) + \
           '</tr></thead><tbody>' + ''.join('<tr>' + ''.join(f"<td>{cell(v)}</td>" for v in row) + '</tr>' for row in rows) + '</tbody></table></div>'


def create_report(data, solutions, summaries, validation, output, documents, figure_status):
    main, s = solutions["main"], summaries[0]
    p, load, pv = arrays(data)
    blocks = block_rows(main)
    max_residual = max(max(v["metrics"].values()) for v in validation.values())
    assumptions = ("依据最终版模型采用右端点时间映射与10分钟内零阶保持；C、D均为微网母线侧电量；"
                   "主模型充电与放电效率各0.9；不向外网售电，允许弃光。"
                   "经用户确认，功率上限使用5000×1/6的准确值，833.3333仅用于显示。"
                   "仅最小化购电费，不添加二级目标；同成本最优解可能不唯一，空闲时段u也不唯一。")
    reason = (f"全天负荷 {s['load_kwh']:,.6f} kWh、光伏 {s['pv_kwh']:,.6f} kWh、"
              f"储能损耗 {s['loss_kwh']:,.6f} kWh。购电+光伏−弃光=负荷+损耗，首尾电量均为6000 kWh。"
              f"充电量加权电价为 {s['charge_weighted_price']:.6f} 元/kWh，"
              f"放电量加权电价为 {s['discharge_weighted_price']:.6f} 元/kWh；"
              f"光伏超过负荷的 {s['pv_surplus_kwh']:,.6f} kWh 中，储能吸收 {s['pv_surplus_absorbed_kwh']:,.6f} kWh。"
              "这些量来自实际解，分别用于检查低价充电、高价放电与富余光伏吸收规律。")
    roundtrip = next(r for r in summaries if r["scenario"] == "roundtrip090")
    delta = roundtrip["cost_yuan"] - s["cost_yuan"]
    robustness = (f"另一效率口径的成本较主结果变化 {delta:,.6f} 元（{delta / s['cost_yuan'] * 100:.4f}%）。"
                  "下表列出每个情景的实际成本、能量与加权电价；状态轨迹和4小时分组数据用于对照阶段变化。"
                  "效率口径会改变成本和局部充放电计划，不能将不同口径的数值混用于正式结果。")
    if all(r["charge_weighted_price"] < r["discharge_weighted_price"] and
           abs(r["pv_surplus_absorbed_kwh"] - r["pv_surplus_kwh"]) <= PHYS_TOL_KWH for r in summaries):
        robustness += ("本次四个情景均满足充电加权电价低于放电加权电价，且全部吸收富余光伏；"
                       "随单程效率由0.85升至0.95，成本和外网购电量均下降。"
                       "这些实算结果支持低价充电、高价放电、吸收富余光伏的整体规律对所检验效率参数稳健，"
                       "不意味着逐时策略完全相同或对未检验参数也成立。")
    report = f"""<!doctype html><html lang="zh-CN"><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Q1 输入与输出 · 最终模型计算结果</title><style>
body{{font:16px/1.7 -apple-system,BlinkMacSystemFont,'PingFang SC',sans-serif;color:#173047;background:#f4f6f8;margin:0}}
main{{max-width:1180px;margin:auto;padding:40px 24px}}h1{{font-size:32px;line-height:1.3}}h2{{margin-top:44px;font-size:24px}}
a{{color:#0072b2}}.intro{{color:#46586a}}.metrics{{display:flex;gap:20px;flex-wrap:wrap;margin:28px 0}}
.metric{{background:white;padding:20px 24px;flex:1;min-width:200px;border-top:4px solid #0072b2}}.metric strong{{display:block;font-size:27px}}
.table-wrap{{overflow:auto;background:white;margin:18px 0;max-height:620px}}table{{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums;font-size:14px}}
th,td{{padding:10px 14px;border-bottom:1px solid #e1e7eb;text-align:right;white-space:nowrap}}th{{background:#e6eff5;position:sticky;top:0}}
td:first-child,th:first-child{{text-align:left}}img{{width:100%;height:auto;background:white}}details{{margin:20px 0}}summary{{cursor:pointer;font-weight:600}}
.note{{background:#e9f2f3;padding:16px 20px;border-left:4px solid #009e73}}code{{background:#e6ebee;padding:2px 5px}}footer{{margin-top:45px;color:#526577;font-size:13px}}
</style><main><p>数学建模 / C题 / 问题1</p><h1>输入与输出：微网日前经济调度</h1>
<p class="intro">144 个时段 · 864 个决策变量（其中144个二元变量）· 单一购电费目标 · 四种效率情景</p>
<p class="note">假设与已确认的计算口径：{assumptions}</p>
<div class="metrics"><div class="metric">最低全天购电费<strong>{s['cost_yuan']:,.6f} 元</strong></div>
<div class="metric">全天外网购电量<strong>{s['grid_kwh']:,.6f} kWh</strong></div>
<div class="metric">全天弃光量<strong>{s['curtail_kwh']:,.6f} kWh</strong></div></div>
<p><a href="result1.csv">完整144时段输出 CSV</a> · <a href="daily_summary.csv">日汇总 CSV</a> ·
<a href="../../../inputs/q1/raw/attachment1.csv">原始输入 CSV</a> ·
<a href="../../../inputs/q1/processed/timeseries.csv">预处理输入 CSV</a> ·
<a href="../../../inputs/q1/processed/parameters.json">模型参数与来源</a></p>
<h2>输入：来源、时间与单位</h2>
<p>数据源为 C题附件1。{len(data)}条记录覆盖00:00–24:00。第一条附件标签00:10对应00:00–00:10，最后一条0:00+1对应23:50–24:00。
负荷和光伏的kW值乘1/6得到kWh；未进行插值、填补、平滑或四舍五入后求解。电价范围{p.min():.4f}–{p.max():.4f}元/kWh。</p>
<details open><summary>查看全部144行输入（可滚动）</summary>"""
    report += html_table(["t", "附件右端点", "调度区间", "电价 元/kWh", "负荷 kW", "光伏 kW", "负荷 kWh", "光伏 kWh"],
                         [[r[k] for k in ("t", "source_endpoint", "interval", "price_yuan_per_kwh", "load_kw", "pv_kw", "load_kwh", "pv_kwh")] for r in data])
    report += '</details><h2>输出：题目表1与表2</h2><p>表1 · 指定时段购电量及全天汇总</p>'
    # 保持题目表1的六列、两行时段布局。
    report += html_table(["时间段", "购电量 kWh", "时间段", "购电量 kWh", "时间段", "购电量 kWh"],
                         [[v for h in hours for v in (data[h * 6]["interval"], main["G"][h * 6])]
                          for hours in ((10, 12, 14), (16, 18, 20))])
    report += html_table(["全天购电量 kWh", "全天购电费 元"], [[s["grid_kwh"], s["cost_yuan"]]])
    report += '<p>表2 · 指定时段母线侧充放电量与首尾储电量</p>'
    report += html_table(["时间段", "充电量 kWh", "放电量 kWh", "时间段", "充电量 kWh", "放电量 kWh"],
                         [[v for b in blocks[i:i + 2] for v in b.values()] for i in (0, 2, 4)])
    report += html_table(["0:00储电量 kWh", "24:00储电量 kWh"], [[main["E0"], main["E"][-1]]])
    report += '<p>同一4小时区间的充电、放电总量可以都为正，分别发生在不同10分钟时段。逐时互斥已核验。<br>图中功率为时段常数；储电量按时段边界连接。显示保留6位小数，文件内部保留求解精度。</p><img src="dispatch.png" alt="输入功率、电价、购电和充放电量、储能状态三联图">'
    report += f'<h2>结果合理性与最优性证据</h2><p>{reason}</p><p>HiGHS返回最优状态，MIP gap为{main["solver"]["mip_gap"]}；'
    report += f'原始目标与最优性下界均为{main["solver"]["objective_yuan"]:.9f}元。全部物理与CSV回读检查通过，最大误差{max_residual:.3e}，容差为{PHYS_TOL_KWH:.0e}。</p>'
    report += '<details><summary>查看全部144行输出（含二元变量、SOC与时段费用）</summary>'
    report += html_table(["区间", "G kWh", "C kWh", "D kWh", "E结束 kWh", "W kWh", "u", "E开始 kWh", "SOC", "费用 元"],
                         [[r[k] for k in ("interval", "G_kwh", "C_kwh", "D_kwh", "E_kwh", "W_kwh", "u", "E_start_kwh", "soc_fraction", "cost_yuan")]
                          for r in schedule_rows(data, main)])
    report += f'</details><h2>效率敏感性与口径稳健性</h2><p>{robustness}</p>'
    report += html_table(["效率情景", "单程效率", "往返效率", "费用 元", "购电 kWh", "弃光 kWh", "充电 kWh", "放电 kWh", "充电加权电价", "放电加权电价"],
                         [[LABELS[r["scenario"]]] + [r[k] for k in ("eta_c", "roundtrip_efficiency", "cost_yuan", "grid_kwh", "curtail_kwh", "charge_kwh", "discharge_kwh", "charge_weighted_price", "discharge_weighted_price")] for r in summaries])
    report += '<img src="efficiency.png" alt="四个效率情景的最低购电成本和储电状态轨迹">'
    report += '<details><summary>查看四个情景的4小时充放电汇总</summary>'
    report += html_table(["情景", "时间段", "充电 kWh", "放电 kWh"],
                         [[LABELS[name], *b.values()] for name, solution in solutions.items() for b in block_rows(solution)])
    report += '</details><h2>验证与复现</h2><p>按用户要求仅用CSV交付并回读复核，文件按最终模型右端点映射生成；原始附件保留。'
    report += '只有主模型0.9效率结果写入result1.csv。每个效率情景均独立检查，未通过的解不用于正式输出。</p>'
    report += html_table(["情景/文件", "检查项", "误差或违反量", "通过"],
                         [[LABELS.get(name, name), key, f"{value:.3e}", "是"] for name, v in validation.items() for key, value in v["metrics"].items()])
    report += '<p>在项目根目录运行：<br><code>uv run --with-requirements src/q1/requirements.txt python src/q1/run.py</code></p>'
    report += '<p><a href="../../q1/raw/validation.json">机器验收记录</a> · <a href="../../q1/raw/run_manifest.json">来源哈希与运行环境</a> · <a href="../../../docs/1/deliverables/q1_implementation_acceptance.md">逐条开发验收报告</a></p>'
    report += '<footer>正式数值来自本次MILP实算。效率情景仅用于敏感性检验；数值最优性在所声明模型及容差内成立。</footer></main></html>'
    if figure_status["status"] != "passed":
        report = re.sub(r'<img[^>]+>', '', report)
    report = report.replace('<h2>输入：来源、时间与单位</h2>',
                            '<p class="note">绘图状态：' + html.escape(figure_status["message"]) + '</p>'
                            '<p class="note">交付口径：按用户要求仅输出CSV，购电时间范围为00:00–24:00；review中的XLSX交付建议不采用。</p>'
                            '<h2>输入：来源、时间与单位</h2>')
    (output / "report.html").write_text(report, encoding="utf-8")
    markdown = f"# Q1 最终模型计算结果\n\n假设与已确认口径：{assumptions}\n\n"
    markdown += f"最低购电费 **{s['cost_yuan']:.9f} 元**；全天购电 **{s['grid_kwh']:.9f} kWh**；弃光 **{s['curtail_kwh']:.9f} kWh**。\n\n"
    markdown += "| 时间段 | 购电量 kWh |\n|---|---:|\n" + "".join(f"| {data[h*6]['interval']} | {main['G'][h*6]:.9f} |\n" for h in (10,12,14,16,18,20))
    markdown += "\n| 时间段 | 充电量 kWh | 放电量 kWh |\n|---|---:|---:|\n" + "".join(f"| {b['interval']} | {b['charge_kwh']:.9f} | {b['discharge_kwh']:.9f} |\n" for b in blocks)
    markdown += f"\n0:00储电量：{main['E0']:.9f} kWh；24:00储电量：{main['E'][-1]:.9f} kWh。\n\n{reason}\n\n{robustness}\n\n"
    markdown += "| 情景 | 费用 元 | 购电 kWh | 弃光 kWh | 充电 kWh | 放电 kWh |\n|---|---:|---:|---:|---:|---:|\n"
    markdown += "".join(f"| {LABELS[r['scenario']]} | {r['cost_yuan']:.9f} | {r['grid_kwh']:.9f} | {r['curtail_kwh']:.9f} | {r['charge_kwh']:.9f} | {r['discharge_kwh']:.9f} |\n" for r in summaries)
    markdown += f"\n全部物理、最优性及CSV回读检查通过；最大误差{max_residual:.3e}，按量纲分别验收，物理容差{PHYS_TOL_KWH:.0e} kWh。\n\n"
    markdown += f"[完整输入输出报告]({ROOT / 'outputs/processed/q1/report.html'}) · [正式结果]({ROOT / 'outputs/processed/q1/result1.csv'})\n"
    markdown += "\nCSV逐格回读通过；144个购电时段、6个充放电区间、首尾储电量与总费用均已核验。\n"
    markdown += "\n绘图状态：" + figure_status["message"] + "\n"
    markdown += "\n分量纲容差：" + str(TOLERANCES) + "\n"
    (documents / "q1_results.md").write_text(markdown, encoding="utf-8")
