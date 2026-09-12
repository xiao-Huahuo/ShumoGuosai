"""2.1.14–2.1.15：由实算诊断形成候选依据与可见报告，明确尚未建模的部分。"""

import html

import pandas as pd

from data import SERIES, write_csv
from figures import LABELS


def candidate_models(diagnostics):
    """仅接受 initial_history 诊断，避免用全年证据回填首次决策。"""
    lags, spectra = diagnostics["lag_correlations"], diagnostics["spectral_targets"]
    if set(lags.scope) != {"initial_history"} or set(spectra.scope) != {"initial_history"}:
        raise ValueError("候选集必须来自首次预测前的可见历史诊断")
    rows = []
    for variable in SERIES[:2]:
        def r(lag, form="raw"):
            return float(lags.loc[(lags.series == variable) & (lags.lag == lag) & (lags.form == form), "pearson_r"].iloc[0])
        daily = spectra.loc[(spectra.series == variable) & (spectra.form == "raw") & (spectra.target_period_days == 1)].iloc[0]
        weekly = spectra.loc[(spectra.series == variable) & (spectra.form == "daily_profile_residual") & (spectra.target_period_days == 7)].iloc[0]
        evidence = f"r144={r(144):.6f}; r1008={r(1008):.6f}; 去平均日曲线r1008={r(1008, 'daily_profile_residual'):.6f}; 日频局部峰={daily.local_peak}; 残差周频局部峰={weekly.local_peak}"
        # 无人为强弱阈值：周频局部峰还须与去日曲线后周相关强于日相关相互印证。
        # 未通过只表示证据不足，绝不等同于证明没有周效应。
        multi = bool(daily.local_peak and weekly.local_peak and r(1008, "daily_profile_residual") > r(144, "daily_profile_residual"))
        for model, status, reason in (
            ("SARIMA", "基础候选，须历史内部验证", "日季节项以144为候选；固定参数是否足够不能由单个月份定论，阶数不能由图形直接定死。"),
            ("DHR_AR", "优先比较的多季节候选" if multi else "条件保留，不预设周效应",
             "日/周频峰与相关共同支持比较多季节动态谐波回归—AR误差；仍非统计显著证明。" if multi else
             "尚未形成独立周周期的完整证据；若后续可见历史出现周证据，再比较多季节模型。"),
            ("Prophet", "条件对照", "仅在历史趋势与季节分解足够平滑时作为对照；当前未开展分解拟合及内层回测。"),
            ("RF_or_GBDT", "暂不引入", "须先有传统模型无法解释非线性残差的回测证据，不能仅凭原始曲线判定。"),
        ):
            rows.append({"series": variable, "model": model, "status": status, "reason": reason,
                         "evidence": evidence, "evidence_scope": "initial_history", "fitted": False,
                         "selection_rule": "所有估计/参数选择仅用各预测日可见历史；不能读取full_year诊断"})
    return pd.DataFrame(rows)


def result_text(frame, diagnostics, candidates, folds):
    full = diagnostics["full_year"]
    lags = full["lag_correlations"]
    def value(variable, lag):
        return float(lags.loc[(lags.series == variable) & (lags.form == "raw") & (lags.lag == lag), "pearson_r"].iloc[0])
    lines = ["# C题第二问：数据预处理与时间序列结构诊断结果", "",
             "## 实施口径与信息边界", "",
             "本结果完整覆盖 dierwen1.md 的2.1阶段。用户确认训练数据严格 timestamp < 当日0:00，等于0:00的上一日末段也不使用。",
             "预测阶段全程使用kW；仅在事后调度指标中按1/6小时转为kWh。全文统计不改变原始功率。",
             "全年诊断仅作事后描述；首次候选模型依据单独使用2025-02-01之前的4463个可见点。",
             "算法设置为实现口径而非新增题设：相关滞后至2016、Burg PACF、原长FFT周期图、ADF默认上限/BIC选滞后、KPSS自动带宽；检验同时给出1%、5%、10%临界值。",
             "工作日分组仅为周一至周五，不推定法定节假日；夜间缺少天文/天气标注，只统计零光伏而不自定夜间范围。", "",
             "## 原始输入核验", "",
             f"52560个连续10分钟观测，365个源日期，每日144段；首点{frame.timestamp.iloc[0]}，末点{frame.timestamp.iloc[-1]}。",
             f"负荷与光伏无缺失、无非有限值、无负值。光伏零值{int((frame.pv_kw == 0).sum())}个，全部保留；净负荷为负的时段{int((frame.net_load_kw < 0).sum())}个，属于光伏超过负荷的合法状态。",
             "局部转折点全部导出相邻时刻、前日、前周与既往同星期同槽位范围，仅按偏离邻点幅度排列人工复核顺序，没有设异常截断阈值，没有删除或平滑。", "",
             "## 周期证据与结果合理性", "",
             "| 变量 | 1日滞后r | 7日滞后r | 14日滞后r |", "|---|---:|---:|---:|"]
    for variable in SERIES[:2]:
        lines.append(f"| {LABELS[variable]} | {value(variable,144):.6f} | {value(variable,1008):.6f} | {value(variable,2016):.6f} |")
    lines += ["", "负荷的周滞后相关高于日滞后相关，应结合星期平均曲线及周频峰考虑多季节结构。光伏的高7日相关本身不证明星期效应，须检查去除平均日曲线后的周频局部峰。",
              "周期图同时保留原始与日曲线残差结果，目标1/7周期/日通常不恰落在离散FFT格点上，CSV公开实际频率及分辨率；局部峰不是显著性检验。", ""]
    weekday_means = frame.groupby("weekday").load_kw.mean()
    lines += ["### 与通常工作日/周末预期不一致的观测", "",
              "按附件真实2025年日期映射，低负荷主要出现在星期五、星期六；星期日多数时段接近其他高负荷日。"
              "原始日期、星期和末段归属已独立核对，不能为了符合通常的周末预期而平移日期或修改功率。"
              "这一现象仅是附件数据的统计特征，数据未提供成因，不能据此断言居民作息或数据生成原因。", "",
              "| 星期 | 全日平均负荷 / kW |", "|---|---:|"]
    lines += [f"| 星期{'一二三四五六日'[int(day)-1]} | {value:.3f} |" for day, value in weekday_means.items()]
    lines += ["", "因此星期一至星期日应分别分析；周一至周五/周六日的分组图仅为描述对照，不能作为已证实的行为分类。", ""]
    for variable in SERIES[:2]:
        stability = full["monthly_stability"].loc[lambda x: x.series == variable]
        lines += [f"{LABELS[variable]}月均功率范围{stability.mean_kw.min():.3f}–{stability.mean_kw.max():.3f} kW；"
                  f"月内1日相关范围{stability.daily_lag_r.min():.6f}–{stability.daily_lag_r.max():.6f}，"
                  f"7日相关范围{stability.weekly_lag_r.min():.6f}–{stability.weekly_lag_r.max():.6f}。"
                  "这些差异须用于后续检验参数和季节性是否随时间变化，不能仅据全年高相关固定参数。", ""]
    lines += ["## 平稳性检验的解释", "",
              "ADF原假设为存在单位根，KPSS原假设为水平(c)或趋势(ct)平稳；原始、日差分、周差分、日后周差分分别检验。",
              "KPSS表外p值只给上/下界，警告原文保留；ADF输出0是数值近似，不能解释为精确零概率。拒绝单位根不证明消除了季节性或异方差；同时查看各变换的月均值和标准差。日后周差分包含重复季节因子，可能过度差分，只用于诊断，未据此规定最终模型。", "",
              "| 变量 | 变换 | ADF(c) p | KPSS(c) p口径 |", "|---|---|---:|---|"]
    tests = full["stationarity_tests"]
    for variable in SERIES[:2]:
        for form in ("raw", "diff144", "diff1008", "diff144_then1008"):
            part = tests.loc[(tests.series == variable) & (tests.form == form) & (tests.regression == "c")].set_index("test")
            lines.append(f"| {LABELS[variable]} | {form} | {part.loc['ADF','p_value']:.5g} | {part.loc['KPSS','p_value_type']} {part.loc['KPSS','p_value']:.5g} |")
    lines += ["", "## 候选模型与回测规则", "",
              "下表仅据首次回测前的可见历史。全年图形不能回流为2月1日的模型选择信息。", "",
              "| 变量 | 候选 | 状态 |", "|---|---|---|"]
    lines += [f"| {LABELS[r.series]} | {r.model} | {r.status} |" for r in candidates.itertuples(index=False)]
    first, last = folds.iloc[0], folds.iloc[-1]
    lines += ["", f"回测起止为{first.origin.date()}至{last.origin.date()}，共{len(folds)}日，每日0:00一次预测未来144段。",
              f"首日历史{first.history_points}点，最后可见时刻为{first.history_last_timestamp}；末日预测最后一个时段的右端点为{last.target_last}。",
              "负荷与光伏分别调用新的预测器，输入仅为该变量历史与未来日历；两者相减得到净负荷。不得随机划分，拟合、缩放、选阶与调参均限历史内部。",
              "三类预测均实现MAE/RMSE；总RMSE从全部时段平方误差计算。事后调度指标实现紧急购电电量、时段数/比例、连续事件数、发生天数与总费用。",
              "紧急电量来自事后实际供给缺口×1/6小时，不能拿净负荷预测误差直接代替。费用=计划电量×正常电价+紧急电量×当期电价×5；未用电的计划电量仍计费。",
              "2–12月费用只可称评价期总费用；没有1月策略就不能伪称全年费用。接口只有收到365个完整日的调度明细后才标记完整自然年。", "",
              "## 本阶段完成状态与后续边界", "",
              "2.1.1–2.1.15所要求的数据重构、诊断图表/统计、候选依据、回测规则与评价接口已实现。",
              "原方案未给出预测模型阶数/拟合策略、调度优化和场景风险模型，因此真实预测误差、紧急购电与费用目前未计算；没有填零、模拟或以代理指标冒充真实结果。",
              "下一建模阶段应在上述候选中用历史内层时间回测确定模型，并提供调度策略后运行已实现的预测与调度评价接口。", "",
              "## 数值方法依据", "",
              "- [Burg PACF](https://www.statsmodels.org/v0.14.6/generated/statsmodels.tsa.stattools.pacf_burg.html)",
              "- [ADF](https://www.statsmodels.org/v0.14.6/generated/statsmodels.tsa.stattools.adfuller.html) 与 [KPSS](https://www.statsmodels.org/v0.14.6/generated/statsmodels.tsa.stattools.kpss.html)",
              "- [SciPy周期图及功率谱单位](https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.periodogram.html)"]
    return "\n".join(lines) + "\n"


def create_report(frame, diagnostics, candidates, folds, figures, output):
    text = result_text(frame, diagnostics, candidates, folds)
    (output / "results.md").write_text(text, encoding="utf-8")
    write_csv(output / "model_candidates.csv", candidates)
    write_csv(output / "rolling_folds.csv", folds)
    status = pd.DataFrame([{"metric": m, "status": "not_computed_model_not_specified", "value": None,
                            "reason": "本方案止于预测前诊断与评价规则，未指定拟合预测器/调度模型"}
                           for m in ("load_mae_kw", "load_rmse_kw", "pv_mae_kw", "pv_rmse_kw", "net_load_mae_kw",
                                     "net_load_rmse_kw", "emergency_kwh", "emergency_frequency", "total_cost_yuan")])
    write_csv(output / "evaluation_status.csv", status)
    cards = []
    for figure in figures:
        links = " · ".join(f'<a href="{html.escape(s)}">{html.escape(s)}</a>' for s in figure["source_csv"])
        cards.append(f'<figure id="{figure["name"]}"><h2>{html.escape(figure["name"])}</h2>'
                     f'<img src="figures/{figure["name"]}.png" alt="{html.escape(figure["caption"])}">'
                     f'<figcaption>{html.escape(figure["caption"])} '
                     f'<a href="figures/{figure["name"]}.svg">SVG</a> · {links}</figcaption></figure>')
    tables = []
    for scope, results in diagnostics.items():
        for name in ("summary", "lag_correlations", "spectral_targets", "monthly_stability", "stationarity_tests"):
            table = results[name].to_html(index=False, border=0, float_format=lambda v: f"{v:.6g}", na_rep="无定义/不适用")
            tables.append(f'<details><summary>{scope} / {name}</summary><a href="{scope}_{name}.csv">完整CSV</a><div class="table">{table}</div></details>')
    downloads = "\n".join(f'<li><a href="{p.name}">{p.name}</a></li>' for p in sorted(output.glob("*.csv")))
    navigation = " · ".join(f'<a href="#{f["name"]}">{f["name"]}</a>' for f in figures)
    page = f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>C题第二问 · 时间序列结构诊断</title><style>
body{{font:16px/1.65 system-ui,sans-serif;color:#172b3a;background:#f5f7fa;margin:0;overflow-wrap:anywhere}}main{{max-width:1280px;margin:auto;padding:28px}}
h1{{font-size:30px}}h2{{font-size:21px}}a{{color:#07588c}}a:focus,summary:focus{{outline:3px solid #d55e00}}
nav{{padding:12px 0}}figure,details,.intro{{background:white;border:1px solid #d8e1e8;border-radius:8px;padding:18px;margin:20px 0}}
figure img{{width:100%;height:auto}}figcaption{{font-size:14px}}summary{{cursor:pointer;font-weight:650}}.table{{overflow-x:auto}}
table{{border-collapse:collapse;font-size:13px;white-space:nowrap}}td,th{{padding:7px;border-bottom:1px solid #d8e1e8;text-align:right}}
pre{{white-space:pre-wrap;overflow-wrap:anywhere;font:inherit}}.badge{{color:#704600;background:#fff4d7;padding:10px}}
</style><main><h1>C题第二问 · 时间序列结构诊断</h1>
<p>365天 · 52,560点 · 10分钟 · 区间右端点 · 原始功率kW</p>
<p class="badge">本方案为2.1预测前阶段。真实预测与购电策略尚未指定，评价数值未计算；全年图表为事后诊断。</p>
<nav>{navigation} · <a href="#data">CSV与指标</a></nav>
<section class="intro"><p><strong>附件2核验通过：</strong>365天、每日144段，无缺失、负值、重复或时间断点；原始负荷与光伏逐值保留。</p>
<p>负荷的周周期证据强于日滞后；光伏以日周期为主。训练严格排除等于0:00的观测。下方11张图均提供PNG、SVG与对应数据。</p>
<details><summary>展开完整结果、实施口径与候选依据</summary><pre>{html.escape(text)}</pre></details>
<a href="results.md">下载结果说明</a> · <a href="../../../docs/2/implementation_acceptance.md">逐句验收报告</a></section>
{''.join(cards)}<section id="data"><h2>实算统计与下载</h2>{''.join(tables)}
<details><summary>334日严格滚动切分</summary><div class="table">{folds.to_html(index=False,border=0)}</div></details>
<details><summary>候选模型证据</summary><div class="table">{candidates.to_html(index=False,border=0)}</div></details>
<details><summary>后续评价数值状态</summary><div class="table">{status.assign(status="尚未指定实际预测/调度模型").fillna("未计算").rename(columns={"metric":"指标","status":"状态","value":"值","reason":"说明"}).to_html(index=False,border=0)}</div></details>
<ul>{downloads}</ul></section></main></html>'''
    (output / "report.html").write_text(page, encoding="utf-8")
