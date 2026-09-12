"""从已验收的Q1运行代整理论文CSV与图表；不重新优化或改写原结果。"""
from pathlib import Path
import csv
import hashlib
import html
import json
import math
import shutil
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[2]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_csv(path):
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def write_csv(path, rows):
    with path.open("w", encoding="utf-8", newline="") as stream:
        csv.writer(stream).writerows(rows)
    with path.open(encoding="utf-8", newline="") as stream:
        reread = list(csv.reader(stream))
    expected = [[str(value) for value in row] for row in rows]
    if reread != expected:
        raise ValueError(f"CSV关闭回读不一致：{path.name}")


def close(actual, expected, tolerance=1e-6):
    if not math.isfinite(actual) or abs(actual - expected) > tolerance:
        raise ValueError(f"论文数据核验失败：{actual} != {expected}")


def table_html(rows, caption):
    def cell(value):
        if str(value).isdigit():
            return str(value)
        try:
            number = float(value)
            # HTML统一显示六位；CSV不截断精度，时间段与中文文本原样显示。
            return f"{number:.6f}" if math.isfinite(number) else str(value)
        except (ValueError, TypeError):
            return str(value)
    header = "".join(f"<th>{html.escape(str(v))}</th>" for v in rows[0])
    body = "".join("<tr>" + "".join(f"<td>{html.escape(cell(v))}</td>" for v in row) + "</tr>" for row in rows[1:])
    return f"<div class='scroll'><table><caption>{html.escape(caption)}</caption><thead><tr>{header}</tr></thead><tbody>{body}</tbody></table></div>"


def main():
    generation = (ROOT / "outputs/q1_current").resolve(strict=True)
    source = generation / "processed"
    manifest = json.loads((generation / "raw/run_manifest.json").read_text(encoding="utf-8"))
    if not all(manifest[k] for k in ("all_physical_csv_checks_passed", "analysis_checks_passed", "tests_passed")):
        raise ValueError("来源运行没有通过完整验收")
    for rel, value in manifest["output_sha256"].items():
        if digest(generation / rel) != value:
            raise ValueError(f"来源产物哈希变化：{rel}")
    data = read_csv(source / "result1.csv")
    summary = read_csv(source / "daily_summary.csv")[0]
    parameters = json.loads((generation / "inputs/processed/parameters.json").read_text(encoding="utf-8"))
    value = lambda row, key: float(row[key])
    if len(data) != 144:
        raise ValueError("主规划表必须包含144时段")
    for t, row in enumerate(data, 1):
        if int(row["t"]) != t or int(row["start_minute"]) != (t - 1) * 10 or int(row["end_minute"]) != t * 10:
            raise ValueError(f"时段缺失或错位：{t}")
        g, c, d, e, w = (value(row, k) for k in ("G_kwh", "C_kwh", "D_kwh", "E_kwh", "W_kwh"))
        close(g + value(row, "pv_kwh") - w + d, value(row, "load_kwh") + c)
        close(e, value(row, "E_start_kwh") + value(summary, "eta_c") * c - d / value(summary, "eta_d"))
        close(value(row, "cost_yuan"), value(row, "price_yuan_per_kwh") * g)
        close(value(row, "soc_fraction"), e / parameters["rated_capacity_kwh"], 1e-8)
        if t > 1:
            close(value(row, "E_start_kwh"), value(data[t - 2], "E_kwh"))
        if min(c, d) > 1e-6 or min(g, c, d, w) < -1e-6:
            raise ValueError("负电量或同时充放电")
        if not 1200 - 1e-6 <= e <= 10800 + 1e-6 or max(c, d) > 5000 / 6 + 1e-6:
            raise ValueError("SOC或功率越界")
    for column, key in [("G_kwh", "grid_kwh"), ("C_kwh", "charge_kwh"), ("D_kwh", "discharge_kwh"), ("cost_yuan", "cost_yuan"), ("W_kwh", "curtail_kwh")]:
        close(math.fsum(value(r, column) for r in data), value(summary, key))
    close(value(data[0], "E_start_kwh"), 6000)
    close(value(data[-1], "E_kwh"), 6000)

    tables = {}
    plan_columns = [("时段序号", "t"), ("时间段", "interval"), ("电价(元/kWh)", "price_yuan_per_kwh"), ("负载电量(kWh)", "load_kwh"), ("光伏预测电量(kWh)", "pv_kwh"), ("计划购电量(kWh)", "G_kwh"), ("充电量(kWh)", "C_kwh"), ("放电量(kWh)", "D_kwh"), ("期初储电量(kWh)", "E_start_kwh"), ("期末储电量(kWh)", "E_kwh"), ("弃光电量(kWh)", "W_kwh"), ("购电费(元)", "cost_yuan")]
    plan = [[label for label, _ in plan_columns] + ["期末SOC(%)", "实际运行状态"]]
    for row in data:
        action = "充电" if value(row, "C_kwh") > 1e-6 else "放电" if value(row, "D_kwh") > 1e-6 else "待机"
        plan.append([row[key] for _, key in plan_columns] + [100 * value(row, "soc_fraction"), action])
    tables["table_144_dispatch.csv"] = ("完整最优方案：144个10分钟时段", "附录或完整结果附件", plan)

    t1 = read_csv(source / "table1_purchase.csv")
    lookup = {r["interval"]: r for r in data}
    expected_times = [f"{h:02d}:00-{h:02d}:10" for h in (10, 12, 14, 16, 18, 20)]
    if [r["interval"] for r in t1] != expected_times:
        raise ValueError("题目表1时段不符")
    for row in t1:
        close(value(row, "grid_kwh"), value(lookup[row["interval"]], "G_kwh"))
    table1 = [["时间段", "购电量(kWh)"] * 3]
    for group in (t1[:3], t1[3:]):
        table1.append([x for row in group for x in (row["interval"], row["grid_kwh"])])
    table1.append(["全天购电量(kWh)", "", summary["grid_kwh"], "全天购电费(元)", "", summary["cost_yuan"]])
    tables["table1_purchase_paper.csv"] = ("表1 微网指定时段及全天购电结果", "题目要求：论文正文", table1)

    t2 = read_csv(source / "table2_storage.csv")
    if len(t2) != 6:
        raise ValueError("题目表2须为六个4小时区间")
    for block, row in enumerate(t2):
        if row["interval"] != f"{block * 4:02d}:00-{(block + 1) * 4:02d}:00":
            raise ValueError("题目表2时段不符")
        for column, key in [("C_kwh", "charge_kwh"), ("D_kwh", "discharge_kwh")]:
            close(math.fsum(value(r, column) for r in data[24 * block:24 * (block + 1)]), value(row, key))
    table2 = [["时间段", "充电量(kWh)", "放电量(kWh)"] * 2]
    for i in (0, 2, 4):
        table2.append([x for row in t2[i:i + 2] for x in (row["interval"], row["charge_kwh"], row["discharge_kwh"])])
    table2.append(["0:00储电量(kWh)", "", summary["initial_kwh"], "24:00储电量(kWh)", "", summary["terminal_kwh"]])
    tables["table2_storage_paper.csv"] = ("表2 储能分区间充放电量及首尾储电量", "题目要求：论文正文", table2)

    baselines = read_csv(source / "baseline_comparison.csv")
    base_cost = value(next(r for r in baselines if r["baseline"] == "no_ess"), "cost_yuan")
    saving = base_cost - value(summary, "cost_yuan")
    saving_pct = 100 * saving / base_cost
    indicators = [["指标", "数值", "单位"], *[[label, summary[key], unit] for label, key, unit in [
        ("全天购电费用", "cost_yuan", "元"), ("全天购电量", "grid_kwh", "kWh"), ("全天负载电量", "load_kwh", "kWh"), ("全天光伏预测电量", "pv_kwh", "kWh"), ("全天充电量(母线侧)", "charge_kwh", "kWh"), ("全天放电量(母线侧)", "discharge_kwh", "kWh"), ("全天弃光电量", "curtail_kwh", "kWh"), ("充放电能量损耗", "loss_kwh", "kWh"), ("0:00储电量", "initial_kwh", "kWh"), ("24:00储电量", "terminal_kwh", "kWh"), ("最低储电量", "soc_min_kwh", "kWh"), ("最高储电量", "soc_max_kwh", "kWh"), ("充电加权电价", "charge_weighted_price", "元/kWh"), ("放电加权电价", "discharge_weighted_price", "元/kWh")]]]
    indicators += [["相对无储能节约费用", saving, "元/日"], ["相对无储能费用降幅", saving_pct, "%"], ["光伏电量消纳率", 100 * (1 - value(summary, "curtail_kwh") / value(summary, "pv_kwh")), "%"]]
    tables["daily_indicators.csv"] = ("主方案全日指标", "摘要、结果分析", indicators)
    param_rows = [["参数或口径", "取值", "单位或解释"]]
    for label, key, unit in [("时段数", "period_count", "个"), ("时段长度", "dt_hours", "h"), ("额定容量", "rated_capacity_kwh", "kWh"), ("储电量下限", "min_energy_kwh", "kWh"), ("储电量上限", "max_storage_kwh", "kWh"), ("最大充放电功率", "max_power_kw", "kW"), ("单时段充放电量上限", "max_energy_kwh", "kWh；精确5000/6"), ("首尾储电量", "initial_and_terminal_kwh", "kWh")]:
        param_rows.append([label, parameters[key], unit])
    param_rows += [["充电效率", summary["eta_c"], "沿用已确认的单程口径"], ["放电效率", summary["eta_d"], "沿用已确认的单程口径"], ["往返效率", summary["roundtrip_efficiency"], "充电效率乘放电效率"], ["时间标签", "右端点", "00:10对应00:00-00:10"], ["充放电量口径", "母线侧", "储电量为电池内部电量"], ["售电", "不允许", "允许弃光"], ["目标", "最小化购电费", "无二级目标"]]
    tables["model_parameters.csv"] = ("模型参数与计算口径", "符号说明、参数设置", param_rows)
    labels = {"main": "主方案：双单程0.90", "eta085": "敏感性：双单程0.85", "eta095": "敏感性：双单程0.95", "roundtrip090": "口径对照：对称往返0.90", "no_ess": "无储能", "pv_only": "仅光伏消纳储能", "full": "完整最优策略"}
    comparisons = [("efficiency_comparison.csv", "efficiency_comparison_paper.csv", "scenario", "效率口径比较"), ("baseline_comparison.csv", "baseline_comparison_paper.csv", "baseline", "嵌套基准与节约比较")]
    for filename, output, key, title in comparisons:
        rows = [["方案", "充电效率", "放电效率", "往返效率", "全天费用(元)", "购电量(kWh)", "充电量(kWh)", "放电量(kWh)", "弃光量(kWh)", "相对无储能节约(元)", "相对无储能降幅(%)"]]
        for r in read_csv(source / filename):
            rows.append([labels[r[key]]] + [r[k] for k in ("eta_c", "eta_d", "roundtrip_efficiency", "cost_yuan", "grid_kwh", "charge_kwh", "discharge_kwh", "curtail_kwh")] + [base_cost - value(r, "cost_yuan"), 100 * (base_cost - value(r, "cost_yuan")) / base_cost])
        # 不同效率必须与同效率无储能基准相比；无储能没有充放电，费用不受效率影响。
        tables[output] = (title, "结果分析或稳健性分析", rows)

    resources = {"storage_upper": "提高储电量上限", "storage_lower": "降低储电量下限", "charge_power": "提高充电功率", "discharge_power": "提高放电功率"}
    boundary = [["诊断方向", "基准边界", "放宽步长", "参数有符号变化", "费用节约(元/日)", "单位日价值", "单位", "基准活跃时段数", "三步长价值稳定", "解释边界"]]
    for r in read_csv(source / "bottleneck_values.csv"):
        if r["scenario"] == "main_l100_pv100":
            boundary.append([resources[r["resource"]]] + [r[k] for k in ("base_limit", "increment", "parameter_change", "saving_yuan", "value_per_unit_day")] + ["元/(kWh·日)" if r["resource"].startswith("storage") else "元/(kW·日)", r["active_count"], "是" if r["multistep_stable"] == "1" else "否", "仅边界诊断，不改变主方案约束；未判断投资经济显著性"])
    if len(boundary) != 13:
        raise ValueError("主方案边界实验应为12项")
    tables["boundary_values_paper.csv"] = ("主方案四类边界的三步长日价值", "边际价值分析（可选）", boundary)
    sensitivity = [["情景", "效率口径", "负荷变化(%)", "光伏变化(%)", "费用(元)", "购电量(kWh)", "充电量(kWh)", "放电量(kWh)", "弃光量(kWh)", "最低储量(kWh)", "最高储量(kWh)"]]
    for r in read_csv(source / "sensitivity_scenarios.csv"):
        sensitivity.append([r["scenario"], labels[r["efficiency_name"]], 100 * value(r, "load_delta"), 100 * value(r, "pv_delta")] + [r[k] for k in ("cost_yuan", "grid_kwh", "charge_kwh", "discharge_kwh", "curtail_kwh", "soc_min_kwh", "soc_max_kwh")])
    tables["sensitivity_36_paper.csv"] = ("36组效率、负荷及光伏情景", "稳健性分析或附录（可选）", sensitivity)

    figures = [("dispatch", "主方案调度与储电轨迹", "输入、电价、购电与充放电量、SOC的时序关系；正文优先使用"), ("efficiency", "效率口径对费用和储电轨迹的影响", "较低效率导致更高费用；主方案与往返效率口径须区分"), ("marginal_analysis", "基准比较、局部阈值及输入敏感性", "固定模式阈值只作局部诊断；25项原MILP双侧差分不匹配"), ("bottleneck_analysis", "四类边界放宽的单位日价值", "储能上限、下限、充电和放电功率单位不同；不据数值直接作投资排序")]
    parent = ROOT / "outputs/processed/q1_paper"
    parent.mkdir(parents=True, exist_ok=True)
    package_id = generation.name + "-" + digest(Path(__file__))[:8]
    destination = parent / package_id
    staging = Path(tempfile.mkdtemp(prefix=".staging-", dir=parent))
    try:
        index = [["文件", "标题", "建议用途", "数据行数", "备注"]]
        for filename, (title, use, rows) in tables.items():
            write_csv(staging / filename, rows)
            index.append([filename, title, use, len(rows) - 1, "CSV保留原数值精度；表1/表2空白单元表示题目合并表头位置"])
        for stem, title, caption in figures:
            for extension in ("png", "svg"):
                filename = f"{stem}.{extension}"
                if (source / filename).exists():
                    shutil.copyfile(source / filename, staging / filename)
                    index.append([filename, title, "论文插图", "", caption])
        write_csv(staging / "materials_index.csv", index)
        guide = f'''# 第一问论文结果材料

本包使用已验收运行 `{generation.name}`，沿用双单程效率0.90、母线侧充放电量、右端点时间标签和10分钟零阶保持；本次只整理现有最优解，不改变模型。结果表格均为UTF-8 CSV，不使用Office。CSV保留原始数值精度，HTML与下列示例显示六位小数。本文的光伏结果基于附件1预测输入，不代表实际发电保证。

## 直接取用顺序

1. [144时段完整规划表](table_144_dispatch.csv)：中文列名，含时间、电价、负荷与光伏电量、计划购电、充放电、首尾储量、SOC、弃光、费用与实际运行状态。完整表适合附录或结果附件，正文可引用题目指定表及调度图。
2. [题目表1](table1_purchase_paper.csv)：按题目三组“时间段/购电量”并排排列，末行含全天购电量与费用。
3. [题目表2](table2_storage_paper.csv)：按题目两组“时间段/充电量/放电量”并排排列，末行含0:00及24:00储电量。CSV不保存合并单元格，空白位置对应题目合并标题；导入排版软件后按题面合并即可。
4. [全日指标](daily_indicators.csv)和[模型参数](model_parameters.csv)：用于摘要、参数设置与结果概述。
5. [基准比较](baseline_comparison_paper.csv)、[效率比较](efficiency_comparison_paper.csv)、[边界价值](boundary_values_paper.csv)、[36情景表](sensitivity_36_paper.csv)：供结果分析及稳健性章节选择使用。
6. [图表目录与图注](materials_index.csv)：列出所有CSV和现有PNG/SVG；优先使用调度图，SVG可用于矢量排版。

[打开全部表格的浏览器预览](index.html)。文件独立齐全，整体目录移动后内部链接仍有效。

## 可用于论文的结果表述

在给定一天的电价、负荷及光伏预测数据下，将全天划分为144个10 min时段，以购电费用最小为目标求解混合整数线性规划。所得一组最优调度的全天购电量为{value(summary, 'grid_kwh'):.6f} kWh，购电费用为{value(summary, 'cost_yuan'):.6f}元；储能设备累计充电{value(summary, 'charge_kwh'):.6f} kWh、放电{value(summary, 'discharge_kwh'):.6f} kWh，均按微网母线侧计量。储电量保持在1200—10800 kWh，0:00与24:00均为6000 kWh，满足日周期约束。所用光伏预测电量全部被利用，弃光量为0。求解器报告MIP gap为0，该最优性结论针对当前模型和数值容差；调度本身可能不唯一。

相对于无储能基准的{base_cost:.6f}元，完整策略节约{saving:.6f}元，费用下降{saving_pct:.6f}%。此比较同时包含光伏消纳和跨时段购电调整的作用，不是对二者的唯一因果分解。全天充放电量之差{value(summary, 'loss_kwh'):.6f} kWh对应储能能量损耗；首尾储量相同并不意味着母线侧充电量与放电量相等。

## 表格口径与解释边界

- 时段00:00—00:10的“期初储量”为0:00状态，“期末储量”为00:10状态。最后一行23:50—24:00属于本日。SOC以额定容量12000 kWh为分母。
- “充电/放电/待机”由实际电量及1e-6 kWh数值容差识别；不把空闲二元变量直接当作真实运行状态。
- 表1中部分时段购电量为0，是光伏与储能共同满足负荷的结果。表2同一4小时区间内充电量和放电量都为正，表示不同10分钟时段发生不同动作，不违反时段互斥。
- 主方案效率为充电0.9、放电0.9，往返0.81。对称往返0.90是另一个对照情景，不能替换主方案表1、表2或144规划表。
- 36个情景属于确定性参数扰动，不是独立随机样本；没有由这些行构造统计显著性或置信区间。
- 25项固定模式影子价不能同时匹配原MILP双侧扰动，局部阈值图只作诊断。边界日价值未计设备投资成本，不能直接作经济投资结论。
- 较低效率下本算例充电量增加、放电量减少；提高光伏在所测情景中未造成弃光。正文应保留这些实测方向，不能写成相反趋势。

## 来源与复现

全部来源文件哈希、生成器哈希、独立物理与汇总核验记录见[材料清单JSON](provenance.json)。源码入口：src/q1/prepare_paper_materials.py；在项目根目录运行 `python3 src/q1/prepare_paper_materials.py` 可从当前已验收运行重新整理。此材料包不重新求解，后续若模型重算，须重新执行整理并采用新的运行代材料。
'''
        (staging / "README.md").write_text(guide, encoding="utf-8")
        content = ["<!doctype html><html lang='zh-CN'><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>第一问论文结果材料</title><style>body{font:16px/1.65 system-ui,sans-serif;color:#182e3e;background:#f5f7f8;margin:0}main{max-width:1400px;margin:32px auto;padding:24px}h1{color:#174d5b}a{color:#126079}section{background:white;padding:24px;margin:24px 0;border-radius:8px}.scroll{overflow:auto;max-height:640px}table{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums}th,td{padding:8px 12px;border-bottom:1px solid #dce3e7;white-space:nowrap;text-align:right}th{background:#e9f1f3;position:sticky;top:0}caption{text-align:left;font-weight:600;margin:8px 0}td:first-child,th:first-child{text-align:left}img{max-width:100%;height:auto}summary{cursor:pointer;font-weight:600}@media print{.scroll{max-height:none;overflow:visible}main{margin:0;padding:0}section{break-inside:avoid}}</style><main><h1>第一问 · 论文结果材料</h1>"]
        content.append(f"<p>来源：{generation.name}。表格均为CSV，原始数值精度保留；本页显示六位小数。主方案为双单程效率0.90。</p><p><a href='README.md'>使用说明与结果表述</a> · <a href='materials_index.csv'>全部材料索引CSV</a></p>")
        for filename in ("table1_purchase_paper.csv", "table2_storage_paper.csv", "table_144_dispatch.csv", "daily_indicators.csv", "model_parameters.csv", "baseline_comparison_paper.csv", "efficiency_comparison_paper.csv", "boundary_values_paper.csv", "sensitivity_36_paper.csv"):
            title, _, rows = tables[filename]
            rendered = table_html(rows, title)
            if filename == "table_144_dispatch.csv":
                rendered = f"<details id='dispatch'><summary>展开144个时间段的完整规划表</summary>{rendered}</details>"
            content.append(f"<section><h2>{html.escape(title)}</h2><p><a href='{filename}'>下载CSV：{html.escape(title)}</a></p>{rendered}</section>")
        content.append("<p>表1、表2末行的空白单元对应题面合并标题。完整规划表按实际电量标记充电/放电/待机；4小时内可在不同10分钟时段分别充电和放电。</p>")
        for stem, title, caption in figures:
            if (staging / f"{stem}.png").exists():
                content.append(f"<section><h2>{title}</h2><img src='{stem}.png' alt='{title}'><p>{caption}</p><a href='{stem}.svg'>SVG矢量图</a></section>")
        content.append("<p>25项固定模式影子价与原MILP双侧差分不匹配；局部阈值不能直接当成通用调控规律。边界价值未作投资显著性判断。</p></main></html>")
        (staging / "index.html").write_text("\n".join(content), encoding="utf-8")
        provenance = {"source_generation": generation.name, "source_manifest_sha256": digest(generation / "raw/run_manifest.json"), "source_artifact_sha256": manifest["output_sha256"], "generator_sha256": digest(Path(__file__)), "checks": {"passed": True, "plan_periods": 144, "table1_intervals": 6, "table2_blocks": 6, "physical_balance_soc_limits_costs": True, "all_csv_closed_readback": True, "source_all_hashes_verified": True}, "package_sha256": {p.name: digest(p) for p in staging.iterdir()}}
        (staging / "provenance.json").write_text(json.dumps(provenance, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if destination.exists():
            for p in staging.iterdir():
                if not (destination / p.name).exists() or p.read_bytes() != (destination / p.name).read_bytes():
                    raise ValueError("同一源代与生成器的材料目录已有不同内容，不覆盖")
            shutil.rmtree(staging)
        else:
            staging.rename(destination)
        archive = parent / f"{package_id}.zip"
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
            for p in sorted(destination.iterdir()):
                bundle.write(p, arcname=f"q1_paper/{p.name}")
        print(json.dumps({"directory": str(destination), "archive": str(archive), "csv_files": len(tables) + 1, "plan_rows": len(plan) - 1, "saved_yuan": saving, "saving_percent": saving_pct, "passed": True}, ensure_ascii=False, indent=2))
    finally:
        if staging.exists():
            shutil.rmtree(staging)


if __name__ == "__main__":
    main()
