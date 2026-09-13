"""用户补充清单的三张核心图；图6-4经用户明确取消。"""
from pathlib import Path
import argparse
import json
import numpy as np
from matplotlib import font_manager
from matplotlib.patches import Rectangle, FancyArrowPatch
from . import q3_paper_final as base

plt=base.plt
NAVY,BLUE,MID,PALE,GRAY,RED=base.NAVY,base.BLUE,base.MID,base.PALE,base.GRAY,base.RED
read=base.read


def save_core(fig, *args):
    # MathText对混合字体不逐字回退；含中文的数学标签显式给宋体外层。
    from matplotlib.text import Text
    for text in fig.findobj(Text):
        value=text.get_text()
        if '$' in value and any('\u4e00'<=c<='\u9fff' for c in value):
            text.set_fontfamily('Songti SC')
    base.save(fig, *args)


def evidence():
    m=read('forecast_metrics.csv');r=read('revision_summary.csv')
    fig,axes=plt.subplots(1,2,figsize=(10,4.35),layout='constrained')
    ax=axes[0];v=m.pivot(index='issue_hour',columns='horizon_hours',values='MAE').to_numpy()
    im=ax.imshow(v,cmap=base.SEQ,vmin=0,aspect='auto',extent=(.5,24.5,3.5,-.5),interpolation='nearest')
    ax.set_yticks(range(4),['00:00','06:00','12:00','18:00']);ax.set_ylabel('预报发布时间')
    ax.set_xticks([1,6,12,18,24]);ax.set_xlabel('预测提前量 / h');ax.grid(False)
    for spine in ax.spines.values():spine.set_visible(False)
    base.title(ax,'(a) 发布时间 × 提前量 MAE');fig.colorbar(im,ax=ax,pad=.025,shrink=.9,label='MAE / kW')
    ax=axes[1]
    for i,row in enumerate(r.itertuples()):
        ax.plot([i,i],[row.old_MAE,row.new_MAE],color=MID,lw=3,zorder=2)
        ax.plot(i,row.old_MAE,'o',ms=7,color=MID,mfc='white',mew=1.5,label='旧预报' if i==0 else None,zorder=3)
        ax.plot(i,row.new_MAE,'D',ms=6,color=NAVY,label='新预报' if i==0 else None,zorder=4)
        improvement=(row.old_MAE-row.new_MAE)/row.old_MAE*100
        if i<2:
            for value in [row.old_MAE,row.new_MAE]:
                ax.annotate(f'{value:.1f}',(i,value),xytext=(10,0),textcoords='offset points',va='center',fontsize=9,color=BLUE)
        else:
            ax.annotate(f'旧 {row.old_MAE:.4f}\n新 {row.new_MAE:.5f} kW',(i,row.old_MAE),xytext=(0,20),textcoords='offset points',ha='center',fontsize=9,color=GRAY)
        ax.text(i,412,f'改善 {improvement:.1f}%',ha='center',fontsize=9,color=BLUE)
    ax.text(2,135,'夜间光伏接近零',ha='center',fontsize=9,color=GRAY)
    ax.set_xlim(-.35,2.5);ax.set_ylim(-12,480);ax.axhline(0,color=GRAY,lw=.6)
    ax.set_xticks([0,1,2],['06:00','12:00','18:00']);ax.set_xlabel('更新节点（同目标未来1–6 h）');ax.set_ylabel('配对目标区间 MAE / kW')
    base.title(ax,'(b) 相邻旧/新预报的同目标增益');base.clean(ax)
    ax.legend(loc='upper right',ncol=2,fontsize=9)
    save_core(fig,'core6_1_forecast_error','图6-1 不同发布时间下光伏预报误差结构及更新增益',
        '2025-02-01至12-30共同333日，热图各格n=333；右图每节点1998个相同目标小时配对，旧预报为上一发布节点、其h=7–12，新预报为当前节点h=1–6。改善率=(旧MAE−新MAE)/旧MAE。18:00之后光伏接近零，绝对改善很小，不应把相对百分比解释成经济价值或异常预测能力。全年误差诊断不回流为当前预测信息。',
        ['forecast_metrics.csv','forecast_pairs.csv','revision_pairs.csv','revision_summary.csv'])


def windows():
    cfg=json.loads((base.DATA/'execution_config.json').read_text(encoding='utf-8'))
    assert cfg['nodes']==[0,6,12,18] and cfg['settlement']=='final'
    fig,ax=plt.subplots(figsize=(10.2,6.3));fig.subplots_adjust(left=.018,right=.985,bottom=.025,top=.985)
    ax.set(xlim=(-15,44),ylim=(-2.95,7.3));ax.axis('off')
    ax.text(12,6.72,'当日',ha='center',fontsize=12,color=BLUE)
    ax.text(33,6.72,'次日',ha='center',fontsize=12,color=GRAY)
    ax.axvspan(0,24,ymin=.29,ymax=.905,color='#F2F7FB',lw=0)
    ax.axvspan(24,42,ymin=.29,ymax=.905,color='#FAFBFD',lw=0)
    ax.plot([24,24],[.35,6.4],color=GRAY,lw=.85,ls='--')
    for i,h in enumerate([0,6,12,18]):
        y=5.55-i*1.37
        ax.text(-14.5,y+.5,f'{h:02d}:00',fontsize=11.5,weight='bold',color=BLUE)
        ax.text(-14.5,y+.07,'最新光伏预报 + 实际SOC',fontsize=8.8,color=GRAY)
        ax.text(-14.5,y-.30,'重新优化',fontsize=9,color=GRAY)
        if h:
            ax.add_patch(Rectangle((0,y),h,.55,facecolor='#EDF0F3',edgecolor='#A8B2BB',lw=.6,hatch='////'))
            ax.text(h/2,y+.275,'已执行 · 冻结',ha='center',va='center',fontsize=8.5,color=GRAY)
        ax.add_patch(Rectangle((h,y),6,.55,facecolor=BLUE,edgecolor=BLUE,lw=.8))
        ax.text(h+3,y+.275,r'$\mathcal{B}$',ha='center',va='center',fontsize=12,color='white')
        today=18-h
        if today:
            ax.add_patch(Rectangle((h+6,y),today,.55,facecolor='#B9D7EC',edgecolor=MID,lw=.8))
            ax.text((h+6+24)/2,y+.275,r'$\mathcal{P}_{'+str(h)+r'}$',ha='center',va='center',fontsize=12,color=NAVY)
        if h:
            ax.add_patch(Rectangle((24,y),h,.55,facecolor='#ECF4FA',edgecolor=MID,lw=.8,ls='--',hatch='..'))
            ax.text(24+h/2,y+.275,r'$\mathcal{C}_{'+str(h)+r'}$',ha='center',va='center',fontsize=12,color=NAVY)
        ax.annotate('',xy=(h+24,y+.83),xytext=(h,y+.83),arrowprops={'arrowstyle':'|-|','lw':.7,'color':GRAY})
        ax.text(h+12,y+.9,f'[{h}, {h+24}) h · 24 h 优化窗口',ha='center',fontsize=8.8,color=GRAY)
        if i<3:
            ax.add_patch(FancyArrowPatch((h+6,y-.02),(h+6,y-.47),arrowstyle='-|>',mutation_scale=10,color=BLUE,lw=1))
            ax.text(h+6.5,y-.33,'真实SOC交接',fontsize=8.5,color=GRAY)
    ax.text(12,.47,r'$\mathcal{P}_{18}=\varnothing$',ha='center',fontsize=11,color=GRAY)
    ax.add_patch(FancyArrowPatch((0,.13),(43,.13),arrowstyle='-|>',mutation_scale=10,color=NAVY,lw=1))
    for h in range(0,43,6):
        ax.plot([h,h],[.07,.19],color=NAVY,lw=.7)
        ax.text(h,-.12,f'{h}:00' if h<24 else '次日0:00' if h==24 else f'{h-24}:00',ha='center',va='top',fontsize=8.8,color=GRAY)
    ax.text(-14,-.95,r'$\mathcal{B}$  承诺执行：下一6 h',fontsize=10,color=BLUE)
    ax.text(4,-.95,r'$\mathcal{P}_k$  当日后续前瞻',fontsize=10,color=BLUE)
    ax.text(24,-.95,r'$\mathcal{C}_k$  跨日继续代理',fontsize=10,color=BLUE)
    ax.text(14,-1.6,'仅B区间进入当前执行；P、C用于估计未来经济影响。',ha='center',fontsize=10,color=NAVY)
    ax.text(14,-2.08,'最终有效购电量相对所属日00:00计划结算一次；已执行段不可回改。',ha='center',fontsize=9.5,color=GRAY)
    ax.text(14,-2.57,'次日00:00继承真实SOC并建立新基准；未来实际源荷不进入当前优化。',ha='center',fontsize=9.5,color=GRAY)
    save_core(fig,'core6_2_rolling_windows','图6-2 四时点滚动优化窗口及承诺执行机制',
        '各节点均优化[k,k+24h)，仅承诺首6h。B为承诺执行区间，P为当日其余前瞻代理，C为跨日继续代理；18点P为空。灰色斜线区为已经执行并冻结的区间。窗口内次日代理不形成当日正式交易，最终有效量相对所属日00点基准只结算一次。箭头交接真实SOC，非用预测SOC替换实测状态。',
        ['execution_config.json'])


def typical():
    f=read('typical_dispatch.csv');p=read('typical_forecasts_active.csv');e=read('typical_storage.csv');x=f.hour_right.to_numpy();dt=1/6
    fig,axes=plt.subplots(3,1,figsize=(9.8,8.25),sharex=True,layout='constrained')
    ax=axes[0];ax.plot(x,f.pv_kw,color=NAVY,lw=2,label=r'$P^{PV,real}$ 实际光伏')
    for h,color,ls,marker in zip([0,6,12,18],base.COLORS,base.STYLES,base.MARKERS):
        s=p[p.issue_hour.eq(h)]
        ax.plot(s.target_hour,s.forecast_kw,color=color,lw=1.35,ls=ls,marker=marker,ms=3,label=f'{h:02d}:00预报')
    ax.set_ylabel('光伏功率 / kW');ax.set_ylim(bottom=0);base.title(ax,'(a) 实际光伏与各执行块采用的最新预报',pad=30)
    ax.legend(loc='lower left',bbox_to_anchor=(0,1.01),ncol=5,fontsize=9,columnspacing=1)
    ax.text(.99,.89,f'{f.date.iloc[0]}\n预报仅画各自生效的未来6 h',transform=ax.transAxes,ha='right',va='top',fontsize=9,color=GRAY)
    ax=axes[1]
    ax.step(x,f.g0,where='pre',color=MID,ls='--',lw=1.45,label=r'$g^0$  00:00原计划')
    ax.step(x,f.grid,where='pre',color=NAVY,lw=1.9,label=r'$g^{eff}$  最终有效购电')
    ax.fill_between(x,f.g0,f.grid,step='pre',color=PALE,alpha=.18,lw=0)
    ax.bar(x-dt/2,f.emergency,width=dt*.88,color=RED,label=r'$q^{em,real}$  紧急购电',zorder=5)
    for t,value in zip(x,f.emergency):
        if value>1e-6:ax.axvspan(t-dt,t,color=RED,alpha=.065,lw=0)
    ax.set_ylabel('电量 / (kWh/10 min)');ax.set_ylim(bottom=0);base.title(ax,'(b) 原计划、最终有效购电量与紧急购电',pad=30)
    ax.legend(loc='lower left',bbox_to_anchor=(0,1.01),ncol=3,fontsize=9)
    ax.text(.53,.94,f'紧急购电合计 {f.emergency.sum():.2f} kWh',transform=ax.transAxes,ha='center',va='top',fontsize=9,color=RED)
    ax=axes[2];net=f.charge-f.discharge
    ax.bar(x-dt/2,net,width=dt*.88,color=[MID if v>=0 else '#A1C5DE' for v in net],lw=0,label=r'$c-r$  净储能动作')
    ax.axhline(0,color=GRAY,lw=.6);ax.set_ylabel('净储能动作 / kWh');ax.set_ylim(-1000,1000);ax.set_yticks([-800,-400,0,400,800])
    right=ax.twinx();right.grid(False);right.plot(e.hour,e.soc_kwh,color=NAVY,lw=2,label=r'$E_t$  储电量')
    right.set_ylim(500,11500);right.set_yticks([1200,6000,10800]);right.set_ylabel('SOC / kWh',color=NAVY)
    for level in [1200,10800]:right.axhline(level,color=GRAY,lw=.8,ls='--')
    base.title(ax,'(c) 充放电响应与真实SOC（左轴为动作，右轴为库存）',pad=30)
    h1,l1=ax.get_legend_handles_labels();h2,l2=right.get_legend_handles_labels()
    ax.legend(h1+h2,l1+l2,loc='lower left',bbox_to_anchor=(0,1.01),ncol=2,fontsize=9)
    for ax in axes:base.clean(ax);base.timeaxis(ax);base.boundaries(ax)
    for ax in axes[:-1]:ax.set_xlabel('')
    save_core(fig,'core6_3_typical_day','图6-3 代表日四时点预报更新下的购电与储能运行轨迹',
        '代表日为2025-03-20。按清单方案B，从题目四个指定日中选择[总费用、有效购电总量、充放电吞吐量、日末SOC]与正式334日对应中位数的IQR标准化欧氏距离最小者；选择尺度和四日距离均附CSV。预报只显示每节点接下来6h的真实小时预报点，旧线在下一更新节点后停止，不延长到发布之前。主策略实际使用10分钟线性插值，这里连接小时点仅作信息展示。柱为10分钟电量；SOC含日初共145点，边界1200/10800kWh；双轴分别为流量与库存。紧急柱保留真实高度，淡红仅标位置。实际路径解释机制，不证明预报的因果经济价值。',
        ['typical_dispatch.csv','typical_storage.csv','typical_forecasts_active.csv','typical_candidates.csv','typical_selection_scale.csv'])


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--data-dir',type=Path,default=base.DATA);parser.add_argument('--output-dir',type=Path,default=base.OUT/'core')
    args=parser.parse_args();base.DATA=args.data_dir.resolve();base.OUT=args.output_dir.resolve();base.OUT.mkdir(parents=True,exist_ok=True)
    fonts={f.name for f in font_manager.fontManager.ttflist}
    assert {'Times New Roman','Songti SC'}<=fonts,'核心图需要Times New Roman与宋体字体'
    style={**base.STYLE,'font.family':['Times New Roman','Songti SC'],'mathtext.fontset':'stix','font.size':11,
           'xtick.labelsize':10,'ytick.labelsize':10}
    base.FONT='Times New Roman / Songti SC';base.MANIFEST.clear()
    with plt.rc_context(style):
        evidence();windows();typical()
    for item in base.MANIFEST:item['script']='src/plots/q3_paper_core.py'
    (base.OUT/'manifest.json').write_text(json.dumps(base.MANIFEST,ensure_ascii=False,indent=2),encoding='utf-8')
    (base.OUT/'captions.md').write_text('# 三张核心图图注\n\n'+'\n\n'.join('## '+r['title']+'\n\n'+r['caption'] for r in base.MANIFEST)+'\n',encoding='utf-8')


if __name__=='__main__':main()
