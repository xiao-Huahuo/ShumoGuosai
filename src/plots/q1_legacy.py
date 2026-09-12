"""Q1原有四组图的唯一实现；由原管线兼容入口调用。"""
import numpy as np
from src.q1.model import DT, E_MAX, E_MIN, arrays

LABELS = {"main": "单程 0.90（主模型）", "eta085": "单程 0.85",
          "eta095": "单程 0.95", "roundtrip090": "往返 0.90（对称）"}
COLORS = {"main": "#0072B2", "eta085": "#D55E00", "eta095": "#009E73", "roundtrip090": "#CC79A7"}


def create_figures(data, solutions, summaries, output):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    fonts = {f.name for f in font_manager.fontManager.ttflist}
    selected = next((f for f in ("PingFang SC", "Heiti TC", "Arial Unicode MS", "Noto Sans CJK SC", "Songti SC", "Hiragino Sans GB") if f in fonts), None)
    if selected is None:
        raise RuntimeError("没有可用中文字体，拒绝输出乱码图表")
    plt.rcParams.update({"font.family": selected, "axes.unicode_minus": False, "font.size": 10,
                         "axes.spines.top": False, "axes.spines.right": False,
                         "axes.grid": True, "grid.alpha": 0.17, "svg.fonttype": "none"})
    p, load, pv = arrays(data)
    edges = np.arange(145) * DT
    center = (edges[1:] + edges[:-1]) / 2
    main = solutions["main"]
    fig, axes = plt.subplots(3, 1, figsize=(12, 10), sharex=True, layout="constrained")
    axes[0].stairs(load / DT, edges, color="#0072B2", label="小区负荷", linewidth=1.5)
    axes[0].stairs(pv / DT, edges, color="#E69F00", label="光伏预测", linewidth=1.5)
    axes[0].set(ylabel="功率 / kW", title="A  输入 · 144 个 10 min 时段，区间内零阶保持")
    tariff = axes[0].twinx()
    tariff.stairs(p, edges, color="#666666", label="购电价格", linewidth=1, linestyle="--")
    tariff.set_ylabel("电价 /（元/kWh）")
    tariff.grid(False)
    handles, labels = axes[0].get_legend_handles_labels()
    h2, l2 = tariff.get_legend_handles_labels()
    axes[0].legend(handles + h2, labels + l2, loc="upper left", ncols=3)
    axes[1].stairs(main["G"], edges, color="#0072B2", label="购电量 G", linewidth=1.3)
    axes[1].bar(center, main["C"], width=DT * 0.9, color="#009E73", label="充电量 C")
    axes[1].bar(center, -np.asarray(main["D"]), width=DT * 0.9, color="#D55E00", label="放电量 D（向下）")
    axes[1].set(ylabel="时段电量 / kWh", title="B  输出 · 母线侧购电与储能调度")
    axes[1].legend(loc="upper left", ncols=3)
    axes[2].plot(edges, [main["E0"], *main["E"]], color="#0072B2", linewidth=1.8, label="储电量 E")
    axes[2].axhline(E_MIN, color="#777777", linestyle="--", linewidth=1, label="安全上下限")
    axes[2].axhline(E_MAX, color="#777777", linestyle="--", linewidth=1)
    axes[2].scatter([0, 24], [main["E0"], main["E"][-1]], color="#D55E00", s=28, zorder=3)
    axes[2].set(ylabel="储电量 / kWh", xlabel="当天时刻 / h", title="C  状态 · 日初与日末均为 6000 kWh",
                ylim=(0, 12000), xticks=np.arange(0, 25, 2), xlim=(0, 24))
    axes[2].legend(loc="upper left", ncols=2)
    fig.suptitle(f"Q1 日前经济调度 | 最低购电费 {summaries[0]['cost_yuan']:,.6f} 元", fontsize=16)
    for suffix in ("png", "svg"):
        fig.savefig(output / f"dispatch.{suffix}", dpi=300, facecolor="white")
    plt.close(fig)

    order = ["eta085", "main", "roundtrip090", "eta095"]
    rows = {r["scenario"]: r for r in summaries}
    fig, axes = plt.subplots(2, 1, figsize=(12, 8), layout="constrained")
    bars = axes[0].bar([LABELS[k] for k in order], [rows[k]["cost_yuan"] for k in order],
                       color=[COLORS[k] for k in order], width=0.6)
    axes[0].bar_label(bars, labels=[f"{rows[k]['cost_yuan']:,.2f}" for k in order], padding=4)
    axes[0].set(ylabel="最低购电费 / 元", title="A  成本 · 每个效率情景独立求解同一 MILP")
    axes[0].set_ylim(0, max(r["cost_yuan"] for r in summaries) * 1.16)
    for i, key in enumerate(order):
        axes[1].plot(edges, [solutions[key]["E0"], *solutions[key]["E"]],
                     color=COLORS[key], label=LABELS[key], linewidth=1.4,
                     linestyle=["--", "-", ":", "-."][i])
    axes[1].axhline(E_MIN, color="#777777", linewidth=0.8, linestyle="--")
    axes[1].axhline(E_MAX, color="#777777", linewidth=0.8, linestyle="--")
    axes[1].set(xlabel="当天时刻 / h", ylabel="储电量 / kWh", xticks=np.arange(0, 25, 2),
                xlim=(0, 24), ylim=(0, 12000), title="B  轨迹 · 对比阶段规律，具体时段策略可以变化")
    axes[1].legend(loc="upper left", ncols=2)
    fig.suptitle("Q1 储能效率稳健性检验", fontsize=16)
    for suffix in ("png", "svg"):
        fig.savefig(output / f"efficiency.{suffix}", dpi=300, facecolor="white")
    plt.close(fig)


def analysis_figures(a, output):
    import matplotlib.pyplot as plt
    def save(fig, name):
        for suffix in ("png", "svg"):
            fig.savefig(output / f"{name}.{suffix}", dpi=300, facecolor="white")
        plt.close(fig)
    rows = a["main_marginals"]
    edges = np.arange(145) * DT
    fig, axes = plt.subplots(3, 1, figsize=(12, 10), layout="constrained")
    for field, label, color, style in (("mu_yuan_per_kwh", "母线边际成本 μ", "#0072B2", "-"),
                                       ("charge_threshold", "充电阈值 ηλ", "#009E73", "--"),
                                       ("discharge_threshold", "放电阈值 λ/η", "#D55E00", ":")):
        axes[0].stairs([r[field] for r in rows], edges, label=label, color=color, linestyle=style)
    axes[0].set(title="A  固定最优模式的局部阈值 · 等号处可有非零动作", ylabel="元/kWh", xlabel="时刻 / h", xlim=(0, 24))
    axes[0].legend(ncols=3, fontsize=9)
    bars = axes[1].bar(["无储能", "仅光伏消纳储能", "完整 MILP"],
                       [r["cost_yuan"] for r in a["baseline_rows"]], color=["#8296A6", "#E69F00", "#0072B2"])
    axes[1].bar_label(bars, fmt="%.2f", padding=4)
    axes[1].set(title="B  嵌套可行域增量节约 · 归因依赖中间基准", ylabel="全天购电费 / 元", ylim=(0, 55000))
    scenarios = [r for r in a["scenarios"] if r["efficiency_name"] == "main"]
    costs = np.array([r["cost_yuan"] for r in scenarios]).reshape(3, 3)
    im = axes[2].imshow(costs, cmap="cividis", aspect="auto")
    for i in range(3):
        for j in range(3):
            axes[2].text(j, i, f"{costs[i,j]:,.2f}", ha="center", va="center",
                         color="white" if costs[i,j] < (costs.min() + costs.max()) / 2 else "#12232e")
    axes[2].set(xticks=[0,1,2], xticklabels=["−5%", "原输入", "+5%"],
                yticks=[0,1,2], yticklabels=["−5%", "原输入", "+5%"], xlabel="光伏规模", ylabel="负荷规模",
                title="C  主效率口径下的九组负荷×光伏扰动")
    axes[2].grid(False)
    fig.colorbar(im, ax=axes[2], label="最低购电费 / 元")
    fig.suptitle("Q1 边际机制、基准比较与输入敏感性", fontsize=16)
    save(fig, "marginal_analysis")
    fig, axes = plt.subplots(2, 2, figsize=(12, 9), layout="constrained")
    for ax, resource, title, unit in zip(axes.flat, ("storage_upper", "storage_lower", "charge_power", "discharge_power"),
                                        ("安全储能上限提高", "安全储能下限降低", "充电功率上限提高", "放电功率上限提高"),
                                        ("元/(kWh·日)", "元/(kWh·日)", "元/(kW·日)", "元/(kW·日)")):
        selected = [r for r in a["bottlenecks"] if r["scenario"] == "main_l100_pv100" and r["resource"] == resource]
        vals = [r["value_per_unit_day"] for r in selected]
        bars = ax.bar([str(int(r["increment"])) for r in selected], vals, color="#0072B2")
        ax.bar_label(bars, labels=[f"{v:.6f}" for v in vals], padding=4, fontsize=9)
        ymax = max(max(vals) * 1.4, 0.01)
        ax.set(title=f"{title}\n基准活跃 {selected[0]['active_count']} 个时段", ylabel=unit,
               xlabel="增加量 / " + ("kWh" if resource.startswith("storage_") else "kW"), ylim=(-ymax * .04, ymax))
    fig.suptitle("分别放宽单一边界后重求 MILP · 有限增量日价值", fontsize=16)
    save(fig, "bottleneck_analysis")

