"""第一问完整论文图：读取验收结果，补算设备扫描，保存全部绘图数据与脚本来源。"""
import html
import json
from pathlib import Path
import shutil
import sys
import tempfile

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from src.plots.common import COLORS as C, cost_palette, digest, read_csv, save, setup
from src.q1.device_sensitivity import prepare
from src.q1.model import DT, check_solution, write_csv, write_json

FIGURES = [
    ('01_data_features', '负荷、光伏与电价的日内变化特征', '可选：背景说明', 'data_features.csv',
     '负荷与光伏采用144段阶梯线；浅绿区域仅表示光伏超过负荷的部分。电价独立成面板，不使用双纵轴或预测置信区间。'),
    ('02_optimal_dispatch', '最优购电计划与储能运行轨迹', '必选：核心结果', 'dispatch_power.csv;storage_145.csv',
     '无储能与最优购电功率共享纵轴；充电向上、放电向下，限值为±5000 kW；145个储电量点含日初状态。状态条依据实际C、D及1e-6 kWh容差判定。'),
    ('03_cost_waterfall', '逐步放宽调度限制的购电费用变化', '建议：结果解释', 'cost_waterfall.csv;baseline_metrics.csv',
     '中间基准为仅吸收富余光伏的储能方案；两项节约依赖这一嵌套顺序，不能解释为唯一的光伏收益与套利收益分解。'),
    ('04_device_sensitivity', '设备边界与最优购电费用', '可选：瓶颈分析', 'device_one_dimensional.csv',
     '每条曲线只改变横轴对应边界，其余设备参数保持基准。圆点全部为独立MILP求解值；连接线仅帮助阅读。'),
    ('05_joint_contour', '储电上限与共同功率上限的联合敏感性', '可选：联合敏感性', 'device_joint_grid.csv',
     '110个网格点分别求解MILP，二维纵轴同时改变充、放电功率。等值线在网格之间作绘图插值；储电上限放宽实验不等同于实际扩容投资分析。'),
    ('06_efficiency', '储能效率变化下的费用与运行轨迹', '可选：效率稳健性', 'efficiency_metrics.csv;efficiency_storage.csv',
     '四种效率情景独立求解；往返0.90采用两侧效率均为sqrt(0.90)，不得与单程0.90混用。'),
    ('07_input_sensitivity', '负荷与光伏输入扰动下的购电费用', '可选：输入稳健性', 'input_sensitivity.csv',
     '固定两侧效率0.90，只展示已计算的九组负荷、光伏−5%、0、+5%扰动。每格标注费用，不冒充设备二维敏感性。'),
    ('08_fixed_mode_diagnostic', '固定模式边际价格的局部诊断', '备查：局部诊断，不建议放正文', 'fixed_mode_marginals.csv;milp_rhs_checks.csv',
     '固定整数模式的LP影子价格属于局部诊断。与原MILP双侧扰动的对照数量及不匹配位置见图，不能据此直接生成普适充停放策略。'),
]


def numbers(rows, key):
    return np.array([float(r[key]) for r in rows])


def time_axis(ax):
    ax.set(xlim=(0, 24), xticks=np.arange(0, 25, 2), xlabel='当天时刻')
    ax.set_xticklabels([f'{h:02}:00' for h in range(0, 25, 2)])


def draw(data, solutions, source, scan, output):
    plt, font = setup()
    main = solutions['main']
    edges = np.arange(145) * DT
    center = (edges[:-1] + edges[1:]) / 2
    load, pv, price = (numbers(data, k) for k in ('load_kw', 'pv_kw', 'price_yuan_per_kwh'))
    base_rows = read_csv(source / 'baseline_comparison.csv')
    baseline = {r['baseline']: r for r in base_rows}
    no_ess = np.maximum(load - pv, 0)
    g, charge, discharge = (np.asarray(main[k]) / DT for k in ('G', 'C', 'D'))
    energy = np.r_[main['E0'], main['E']]
    states = np.where(np.asarray(main['C']) > 1e-6, 1, np.where(np.asarray(main['D']) > 1e-6, -1, 0))
    if len(energy) != 145 or len(g) != 144 or abs(sum(no_ess) * DT - float(baseline['no_ess']['grid_kwh'])) > 1e-6:
        raise ValueError('绘图时段或无储能基准错误')
    write_csv(output / 'data_features.csv', [{'t': i+1, 'start_h': edges[i], 'end_h': edges[i+1],
              'load_kw': load[i], 'pv_kw': pv[i], 'surplus_pv_kw': max(pv[i]-load[i], 0),
              'price_yuan_per_kwh': price[i]} for i in range(144)])
    write_csv(output / 'dispatch_power.csv', [{'t': i+1, 'start_h': edges[i], 'end_h': edges[i+1],
              'no_ess_grid_kw': no_ess[i], 'optimal_grid_kw': g[i], 'charge_kw': charge[i],
              'discharge_kw': discharge[i], 'state': {1:'充电', 0:'待机', -1:'放电'}[int(states[i])]} for i in range(144)])
    write_csv(output / 'storage_145.csv', [{'boundary': i, 'time_h': edges[i], 'energy_kwh': energy[i]} for i in range(145)])

    fig, axes = plt.subplots(2, 1, figsize=(11.5, 6.4), sharex=True, height_ratios=[2, 1], layout='constrained')
    axes[0].stairs(load, edges, baseline=None, color=C['load'], lw=1.6, zorder=3, label='小区负荷')
    axes[0].stairs(pv, edges, baseline=None, color=C['pv'], lw=1.6, zorder=3, label='光伏预测')
    x = np.column_stack([edges[:-1], edges[1:]]).ravel()
    axes[0].fill_between(x, np.repeat(load, 2), np.repeat(pv, 2), where=np.repeat(pv > load, 2),
                         color=C['charge'], alpha=.20, linewidth=0, label='富余光伏（光伏高于负荷）')
    axes[0].set(ylabel='功率 / kW', title='A  负荷与光伏', ylim=(0, max(load.max(), pv.max()) * 1.20))
    axes[0].legend(loc='upper left', ncols=3)
    axes[1].stairs(price, edges, baseline=None, color=C['grid'], lw=1.7)
    axes[1].set(ylabel='电价 /（元/kWh）', title='B  购电价格', ylim=(0, price.max()*1.15))
    time_axis(axes[-1]); fig.suptitle(FIGURES[0][1], fontsize=16)
    save(fig, output, FIGURES[0][0])

    fig, axes = plt.subplots(4, 1, figsize=(11.5, 9.8), sharex=True,
                             height_ratios=[2, 1.65, 1.75, .28], layout='constrained')
    axes[0].stairs(no_ess, edges, baseline=None, color=C['muted'], ls='--', lw=1.4, label='无储能购电功率')
    axes[0].stairs(g, edges, baseline=None, color=C['grid'], lw=1.6, label='MILP最优购电功率')
    axes[0].set(ylabel='购电功率 / kW', title='A  外网购电', ylim=(0, max(g.max(), no_ess.max())*1.20))
    axes[0].legend(loc='upper left', ncols=2)
    axes[1].bar(center, charge, width=DT*.91, color=C['charge'], label='充电（正）')
    axes[1].bar(center, -discharge, width=DT*.91, color=C['discharge'], label='放电（负）')
    for value in (-5000, 5000):
        axes[1].axhline(value, color=C['muted'], lw=.9, ls='--')
    axes[1].axhline(0, color=C['load'], lw=.7)
    axes[1].set(ylabel='储能功率 / kW', title='B  母线侧充放电 · 虚线为±5000 kW', ylim=(-6600, 7800), yticks=[-5000, 0, 5000])
    axes[1].legend(loc='upper left', ncols=2)
    axes[2].plot(edges, energy, color=C['energy'], lw=1.8, label='储电量（145个边界点）')
    for value in (1200, 10800):
        axes[2].axhline(value, color=C['muted'], ls='--', lw=.9)
    axes[2].scatter([0, 24], [6000, 6000], s=35, color=C['pv'], zorder=4, label='首尾均为6000 kWh')
    axes[2].set(ylabel='储电量 / kWh', title='C  储电状态 · 安全下限1200 / 上限10800 kWh',
                ylim=(0, 13500), yticks=[1200, 6000, 10800])
    axes[2].legend(loc='upper left', ncols=2)
    axes[3].bar(center, np.ones(144), width=DT, color=[{1:C['charge'], 0:'#E3E7EA', -1:C['discharge']}[int(s)] for s in states])
    axes[3].set(ylim=(0, 1), yticks=[], ylabel='状态')
    axes[3].set_ylabel('状态\n灰=待机', fontsize=8, rotation=0, ha='right', va='center')
    axes[3].grid(False); axes[3].spines['left'].set_visible(False)
    time_axis(axes[-1]); fig.suptitle(FIGURES[1][1], fontsize=16)
    save(fig, output, FIGURES[1][0])

    costs = [float(baseline[k]['cost_yuan']) for k in ('no_ess', 'pv_only', 'full')]
    gains = [costs[0]-costs[1], costs[1]-costs[2]]
    write_csv(output / 'cost_waterfall.csv', [
        {'position': i, 'role': role, 'bottom_yuan': bottom, 'height_yuan': height}
        for i, role, bottom, height in [(0,'无储能',0,costs[0]), (1,'仅光伏储能增量节约',costs[1],gains[0]),
          (2,'PV-only',0,costs[1]), (3,'放宽充电来源增量节约',costs[2],gains[1]), (4,'完整MILP',0,costs[2])]])
    shutil.copy2(source / 'baseline_comparison.csv', output / 'baseline_metrics.csv')
    fig, axes = plt.subplots(2, 1, figsize=(11.5, 6.8), height_ratios=[4, 1.05], layout='constrained')
    ax = axes[0]
    ax.grid(axis='x', visible=False)
    bars = ax.bar(range(5), [costs[0], gains[0], costs[1], gains[1], costs[2]],
                  bottom=[0, costs[1], 0, costs[2], 0], width=.62,
                  color=[C['muted'], C['charge'], C['pv'], C['charge'], C['grid']])
    for i, (bar, value) in enumerate(zip(bars, [costs[0], gains[0], costs[1], gains[1], costs[2]])):
        ax.text(bar.get_x()+bar.get_width()/2, bar.get_y()+bar.get_height()+950,
                ('−' if i in (1,3) else '')+f'{value:,.2f}', ha='center', va='bottom', fontsize=11)
    for i, level in enumerate([costs[0], costs[1], costs[1], costs[2]]):
        ax.plot([i+.31, i+1-.31], [level, level], color=C['muted'], lw=.9)
    ax.set(xticks=range(5), xticklabels=['无储能', '仅光伏储能\n增量节约', 'PV-only', '放宽充电来源\n增量节约', '完整MILP'],
           ylabel='全天购电费 / 元', ylim=(0, 56000))
    ax.set_title(f'总节约 {sum(gains):,.2f} 元 / 日（{sum(gains)/costs[0]*100:.2f}%）', loc='left', pad=14)
    axes[1].axis('off')
    table = axes[1].table(cellText=[[label]+[f'{float(baseline[k][field]):,.2f}' for field in ('grid_kwh','curtail_kwh','cost_yuan')]
                                   for label,k in [('无储能','no_ess'),('PV-only','pv_only'),('完整MILP','full')]],
                           colLabels=['调度方案','购电量 / kWh','弃光量 / kWh','购电费 / 元'], cellLoc='center', loc='center')
    table.auto_set_font_size(False); table.set_fontsize(10); table.scale(1, 1.6)
    for (row, col), cell in table.get_celld().items():
        cell.set_edgecolor('#DCE3E8'); cell.set_facecolor('#EDF3F6' if row == 0 else 'white')
    fig.suptitle(FIGURES[2][1], fontsize=16)
    save(fig, output, FIGURES[2][0])

    curves = read_csv(scan / 'one_dimensional.csv'); grid = read_csv(scan / 'joint_grid.csv')
    shutil.copy2(scan / 'one_dimensional.csv', output / 'device_one_dimensional.csv')
    shutil.copy2(scan / 'joint_grid.csv', output / 'device_joint_grid.csv')
    fig, axes = plt.subplots(1, 3, figsize=(12, 4.6), sharey=True, layout='constrained')
    for ax, resource, label, base, color in zip(axes, ('e_max','charge_kw','discharge_kw'),
            ('储电上限 / kWh','充电功率上限 / kW','放电功率上限 / kW'), (10800,5000,5000),
            (C['energy'],C['charge'],C['discharge'])):
        rows = [r for r in curves if r['resource'] == resource]
        ax.plot(numbers(rows,'limit'), numbers(rows,'cost_yuan'), '-o', color=color, lw=1.7, ms=4)
        ax.axvline(base, color=C['muted'], ls='--', lw=1)
        ax.scatter([base], [costs[2]], color='black', s=28, zorder=4)
        saving = costs[2]-float(next(r['cost_yuan'] for r in rows if float(r['limit']) == base+100))
        unit = 'kWh' if resource == 'e_max' else 'kW'
        ax.set(xlabel=label, title=f'基准 {base} {unit}\n提高100 {unit}节约 {saving:.2f} 元 / 日')
        ax.ticklabel_format(style='plain', axis='both', useOffset=False)
        ax.set_xticks([6000,10800,18000,24000,30000] if resource == 'e_max' else [0,2500,5000,7500,10000])
        ax.tick_params(axis='x', labelrotation=30)
    axes[0].set_ylabel('最低购电费 / 元')
    fig.suptitle(FIGURES[3][1]+' · 分别改变单一边界', fontsize=15)
    save(fig, output, FIGURES[3][0])

    xs = sorted({float(r['e_max_kwh']) for r in grid}); ys = sorted({float(r['common_power_kw']) for r in grid})
    lookup = {(float(r['e_max_kwh']),float(r['common_power_kw'])):float(r['cost_yuan']) for r in grid}
    z = np.array([[lookup[x,y] for x in xs] for y in ys])
    fig, ax = plt.subplots(figsize=(11.5, 6.5), layout='constrained')
    fill = ax.contourf(xs, ys, z, levels=np.linspace(26000,44000,37), cmap=cost_palette())
    contours = ax.contour(xs, ys, z, levels=np.arange(28000,44000,2000), colors='#415D70', linewidths=.7)
    positions = []
    for segments in contours.allsegs:
        vertices = max(segments, key=len)
        inside = vertices[(vertices[:,0]>xs[0]+900)&(vertices[:,0]<xs[-1]-900)&
                          (vertices[:,1]>ys[0]+450)&(vertices[:,1]<ys[-1]-450)]
        if len(inside): positions.append(inside[len(inside)//2])
    labels = ax.clabel(contours, inline=True, fontsize=9, fmt='%.0f', manual=positions)
    for label in labels:
        label.set_color(C['energy'])
        label.set_bbox({'facecolor':'white','edgecolor':'none','alpha':.88,'pad':1.5})
    xx, yy = np.meshgrid(xs,ys); ax.scatter(xx,yy,color='#253D56',s=5,alpha=.28,label='实际求解网格点')
    ax.scatter([10800],[5000],marker='*',s=180,c='white',edgecolor='#182F46',lw=1.2,zorder=5)
    ax.annotate(f'基准 (10800, 5000)\n{costs[2]:,.2f} 元', (10800,5000), xytext=(14500,6300),
                 arrowprops={'arrowstyle':'->','color':C['energy']}, color=C['energy'], fontsize=11,
                 bbox={'boxstyle':'round,pad=.45','fc':'white','ec':'none','alpha':.94})
    ax.set(xlabel='储电上限 / kWh', ylabel='共同充放电功率上限 / kW', xticks=[6000,10800,18000,24000,30000],
           yticks=[1000,3000,5000,7000,10000], title='110个网格点独立求解 · 线标注为等购电费用 / 元')
    ax.grid(False); fig.colorbar(fill, ax=ax, label='最低购电费 / 元', pad=.025, ticks=range(26000,44001,3000))
    fig.suptitle(FIGURES[4][1], fontsize=16)
    save(fig, output, FIGURES[4][0])

    efficiency = {r['scenario']: r for r in read_csv(source / 'efficiency_comparison.csv')}
    order = ['eta085','main','roundtrip090','eta095']; labels = ['单程0.85','单程0.90（基准）','往返0.90（对称）','单程0.95']
    colors = [C['pv'],C['grid'],C['discharge'],C['charge']]
    shutil.copy2(source / 'efficiency_comparison.csv', output / 'efficiency_metrics.csv')
    write_csv(output / 'efficiency_storage.csv', [{'scenario':key,'boundary':i,'time_h':edges[i],'energy_kwh':v}
              for key in order for i,v in enumerate([solutions[key]['E0'],*solutions[key]['E']])])
    fig, axes = plt.subplots(2,1,figsize=(11.5,7),layout='constrained')
    bars = axes[0].bar(labels,[float(efficiency[k]['cost_yuan']) for k in order],color=colors,width=.55)
    axes[0].grid(axis='x', visible=False)
    axes[0].bar_label(bars,fmt='%.2f',padding=5)
    axes[0].set(ylabel='最低购电费 / 元',ylim=(0,43000),title='A  每种效率情景独立求解')
    for key,label,color,style in zip(order,labels,colors,['--','-',':','-.']):
        axes[1].plot(edges,[solutions[key]['E0'],*solutions[key]['E']],color=color,ls=style,label=label,lw=1.5)
    for bound in [1200,10800]: axes[1].axhline(bound,color=C['muted'],lw=.8,ls='--')
    axes[1].set(ylabel='储电量 / kWh',ylim=(0,14000),title='B  储电轨迹与安全边界')
    axes[1].legend(ncols=2,loc='upper left'); time_axis(axes[1])
    fig.suptitle(FIGURES[5][1],fontsize=16); save(fig,output,FIGURES[5][0])

    scenarios = [r for r in read_csv(source/'sensitivity_scenarios.csv') if r['efficiency_name']=='main']
    write_csv(output/'input_sensitivity.csv',scenarios)
    values={(float(r['load_delta']),float(r['pv_delta'])):float(r['cost_yuan']) for r in scenarios}
    z=np.array([[values[l,p] for p in [-.05,0,.05]] for l in [-.05,0,.05]])
    fig,ax=plt.subplots(figsize=(8.2,5.6),layout='constrained')
    im=ax.imshow(z,cmap=cost_palette(),aspect='auto')
    for i in range(3):
        for j in range(3): ax.text(j,i,f'{z[i,j]:,.2f}',ha='center',va='center',fontsize=13,color='white' if z[i,j]>(z.min()+z.max())/2 else '#182F46')
    ax.set(xticks=[0,1,2],xticklabels=['−5%','原输入','+5%'],yticks=[0,1,2],yticklabels=['−5%','原输入','+5%'],
           xlabel='光伏规模变化',ylabel='负荷规模变化',title='双单程效率均0.90 · 九个单独求解的情景')
    ax.grid(False); fig.colorbar(im,ax=ax,label='最低购电费 / 元'); fig.suptitle(FIGURES[6][1],fontsize=15)
    save(fig,output,FIGURES[6][0])

    marginals=[r for r in read_csv(source/'marginal_values.csv') if r['scenario']=='main_l100_pv100']
    if len(marginals)!=144: raise ValueError('主情景边际诊断必须为144行')
    write_csv(output/'fixed_mode_marginals.csv',marginals)
    shutil.copy2(source/'milp_rhs_validation.csv',output/'milp_rhs_checks.csv')
    checks=read_csv(source/'milp_rhs_validation.csv')
    mismatch=sum(int(r['fixed_shadow_matches_milp_both_sides'])==0 for r in checks)
    fig,axes=plt.subplots(2,1,figsize=(11.5,6.2),sharex=True,height_ratios=[3,1],layout='constrained')
    for key,label,color,style in [('mu_yuan_per_kwh','母线边际成本 μ',C['grid'],'-'),
          ('charge_threshold','充电比较值 ηλ',C['charge'],'--'),('discharge_threshold','放电比较值 λ/η',C['discharge'],':')]:
        axes[0].stairs(numbers(marginals,key),edges,baseline=None,color=color,ls=style,lw=1.5,label=label)
    axes[0].legend(loc='upper left',ncols=3); axes[0].set(ylabel='元/kWh',ylim=(-.06,1.65),title='A  固定最优整数模式的局部LP结果')
    for i,kind in enumerate(['bus_demand','internal_injection']):
        bad=[r for r in checks if r['kind']==kind and int(r['fixed_shadow_matches_milp_both_sides'])==0]
        axes[1].scatter([(int(r['t'])-.5)*DT for r in bad],[i]*len(bad),s=32,color=C['discharge'],marker='x')
    axes[1].set(yticks=[0,1],yticklabels=['母线RHS','SOC RHS'],ylim=(-.6,1.6),
                title=f'B  原MILP双侧扰动不匹配位置 · {len(checks)*2}次重求 / {mismatch}项不匹配')
    time_axis(axes[1]); fig.suptitle(FIGURES[7][1]+' · 不用于普适动作选择',fontsize=15)
    save(fig,output,FIGURES[7][0])
    return {'font':font,'intervals':144,'energy_points':145,'rhs_mismatches':mismatch,
            'grid_points':len(grid),'figure_count':len(FIGURES),'no_ess_cost_yuan':costs[0],
            'optimal_cost_yuan':costs[2],'total_saving_yuan':sum(gains)}


def main():
    generation=(ROOT/'outputs/q1_current').resolve(strict=True)
    manifest=json.loads((generation/'raw/run_manifest.json').read_text(encoding='utf-8'))
    if not all(manifest[k] for k in ['all_physical_csv_checks_passed','analysis_checks_passed','tests_passed']):
        raise ValueError('Q1来源尚未验收')
    for name,value in manifest['output_sha256'].items():
        if digest(generation/name)!=value: raise ValueError(f'来源哈希不符：{name}')
    data=read_csv(generation/'inputs/processed/timeseries.csv')
    for row in data:
        for key in ['price_yuan_per_kwh','load_kwh','pv_kwh','load_kw','pv_kw']: row[key]=float(row[key])
    solutions={key:json.loads((generation/f'raw/solution_{key}.json').read_text(encoding='utf-8')) for key in ['main','eta085','eta095','roundtrip090']}
    for s in solutions.values(): check_solution(data,s)
    scan=prepare(data,generation)
    parent=ROOT/'outputs/processed/figures'; parent.mkdir(parents=True,exist_ok=True)
    staging=Path(tempfile.mkdtemp(prefix='.q1-pending-',dir=parent))
    try:
        checks=draw(data,solutions,generation/'processed',scan,staging)
        rows=[{'figure':name,'title':title,'role':role,'script':'src/plots/q1_paper.py',
               'data_csv':sources,'caption':caption} for name,title,role,sources,caption in FIGURES]
        write_csv(staging/'figure_index.csv',rows)
        ordered=sorted(FIGURES,key=lambda r: {'必选':0,'建议':1,'可选':2,'备查':3}[r[2][:2]])
        cards=''.join(f'<article id="{name}"><h2>{html.escape(title)}</h2><p>{role} · {html.escape(caption)}</p>'
                      f'<p><a href="{name}.png">PNG</a> · <a href="{name}.svg">SVG</a> · '+
                      ' · '.join(f'<a href="{p}">{p}</a>' for p in sources.split(';'))+
                      f'</p><img src="{name}.png" alt="{html.escape(title)}"></article>' for name,title,role,sources,caption in ordered)
        page='<!doctype html><html lang="zh-CN"><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        page+='<title>第一问论文图集</title><style>body{font:16px/1.7 -apple-system,BlinkMacSystemFont,"PingFang SC",sans-serif;background:#f3f6f8;color:#253d56;margin:0}main{max-width:1160px;margin:auto;padding:32px 20px}article{background:white;padding:24px;margin:30px 0;border-radius:8px}img{width:100%;height:auto}a{color:#0072b2}p{overflow-wrap:anywhere}h1{font-size:30px}h2{font-size:22px}</style><main>'
        page+='<h1>第一问论文图集</h1><p>核心运行结果为必选，费用对比建议放正文，其余按论证需要选用。共8张图；PNG为300 dpi，SVG中文转为矢量路径。数据表全部为CSV。<a href="figure_index.csv">图目索引</a> · <a href="../../../../src/plots/README.md">集中管理的绘图脚本</a></p>'
        page+='<nav>'+ ' · '.join(f'<a href="#{name}">{role}：{title}</a>' for name,title,role,_,_ in ordered)+'</nav>'
        page+='<p>实验口径：Emin=1200 kWh、首尾6000 kWh、两侧效率0.9。设备扫描仅改变指明的边界；Emax为储电上限，超过原额定容量的值仅用于数学约束放宽实验，不作设备投资结论。</p>'+cards+'</main></html>'
        (staging/'index.html').write_text(page,encoding='utf-8')
        code=[Path(__file__),ROOT/'src/plots/common.py',ROOT/'src/q1/device_sensitivity.py',ROOT/'src/q1/model.py']
        write_json(staging/'provenance.json',{'source_generation':str(generation.relative_to(ROOT)),
                   'source_manifest_sha256':digest(generation/'raw/run_manifest.json'),
                   'device_analysis':str(scan.relative_to(ROOT)), 'checks':checks,
                   'code_sha256':{str(p.relative_to(ROOT)):digest(p) for p in code},
                   'output_sha256':{p.name:digest(p) for p in staging.iterdir() if p.is_file()}})
        target=parent/'q1'; old=parent/'.q1-previous'
        if old.exists(): raise ValueError('发现未完成的图集替换，需先检查.q1-previous')
        if target.exists(): target.rename(old)
        try: staging.rename(target)
        except BaseException:
            if old.exists(): old.rename(target)
            raise
        if old.exists(): shutil.rmtree(old)
    except BaseException:
        if staging.exists(): shutil.rmtree(staging)
        raise
    print(json.dumps({'output':str(target),'checks':checks},ensure_ascii=False),flush=True)


if __name__=='__main__':
    main()
