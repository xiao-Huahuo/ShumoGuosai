"""Q3七图：固定数据绘制，不调用任何求解器。"""
from pathlib import Path
import argparse
import html
import json
import warnings
import numpy as np
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm
from .common import setup

plt, FONT = setup()
ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT/'outputs/processed/figures/q3_paper_final_20260913'
DATA = OUT/'data'
NAVY='#103B62'; BLUE='#1263A0'; MID='#3988C1'; PALE='#74ADD4'
GRAY='#62778A'; LIGHT='#DDEAF3'; RED='#B76667'
COLORS=[PALE,MID,BLUE,NAVY]
STYLES=['--','-.',':','-']
MARKERS=['o','s','^','D']
SEQ=LinearSegmentedColormap.from_list('q3_blues',['#F2F7FC','#BDD9ED','#78AED3','#337CB2','#103B62'])
DIV=LinearSegmentedColormap.from_list('q3_signed',['#678C99','#A8C2CB','#DCE9EE','#FAFCFE','#BDDCEF','#6CA8D1','#104775'])
STYLE={'font.size':11,'axes.titlesize':11.5,'axes.titleweight':'medium','axes.labelsize':10.5,
       'xtick.labelsize':9.5,'ytick.labelsize':9.5,'legend.fontsize':9,'legend.frameon':False,
       'axes.edgecolor':'#9CA9B5','axes.linewidth':.7,'axes.labelcolor':NAVY,'text.color':NAVY,
       'xtick.color':GRAY,'ytick.color':GRAY,'grid.color':LIGHT,'grid.alpha':.8,'grid.linewidth':.55,
       'lines.linewidth':1.7,'mathtext.fontset':'dejavusans','svg.fonttype':'path',
       'axes.spines.top':False,'axes.spines.right':False,
       'figure.constrained_layout.h_pad':.085,'figure.constrained_layout.w_pad':.07}
MANIFEST=[]


def read(name):
    return pd.read_csv(DATA/name,float_precision='round_trip')


def title(ax,text,pad=10):
    ax.set_title(text,loc='left',pad=pad)


def clean(ax):
    ax.grid(True,axis='y');ax.grid(False,axis='x');ax.tick_params(length=3,width=.6)


def timeaxis(ax):
    ax.set_xlim(0,24);ax.set_xticks([0,6,12,18,24]);ax.set_xlabel('时刻 / h')


def boundaries(ax):
    for h in [6,12,18]:ax.axvline(h,color=GRAY,ls=':',lw=.8,alpha=.7)


def save(fig,name,text,caption,data):
    with warnings.catch_warnings():
        warnings.filterwarnings('error',message='Glyph .* missing from font')
        fig.canvas.draw()
        for suffix in ('png','svg'):
            fig.savefig(OUT/f'{name}.{suffix}',dpi=400,facecolor='white',transparent=False)
    MANIFEST.append({'question':'q3','name':name,'title':text,'caption':caption,'data':data,
        'png':name+'.png','svg':name+'.svg','width_inches':fig.get_figwidth(),
        'height_inches':fig.get_figheight(),'dpi':400,'font':FONT,
        'script':'src/plots/q3_paper_final.py','necessity':'第三问正文图或局部敏感性附图'})
    plt.close(fig)
    print(name,flush=True)


def forecast_quality():
    metrics=read('forecast_metrics.csv');r=read('revision_summary.csv')
    fig,axes=plt.subplots(2,2,figsize=(9.6,6.6),layout='constrained')
    for ax,key,label in zip(axes.ravel()[:3],['MAE','RMSE','Bias'],['(a) 平均绝对误差 MAE','(b) 均方根误差 RMSE','(c) 平均偏差 Bias']):
        v=metrics.pivot(index='issue_hour',columns='horizon_hours',values=key).to_numpy()
        norm=TwoSlopeNorm(vmin=-abs(v).max(),vcenter=0,vmax=abs(v).max()) if key=='Bias' else None
        im=ax.imshow(v,cmap=DIV if key=='Bias' else SEQ,norm=norm,vmin=None if norm else 0,
            aspect='auto',extent=(.5,24.5,3.5,-.5),interpolation='nearest')
        ax.set_yticks(range(4),['00:00','06:00','12:00','18:00']);ax.set_ylabel('预报发布时间')
        ax.set_xticks([1,6,12,18,24]);ax.set_xlabel('预报提前量 / h');ax.grid(False)
        for spine in ax.spines.values():spine.set_visible(False)
        title(ax,label);fig.colorbar(im,ax=ax,pad=.025,shrink=.9,label='kW')
    ax=axes[1,1];x=np.arange(3);w=.3
    ax.bar(x-w/2,r.old_MAE,width=w,color=PALE,label='上一时点预报',edgecolor=BLUE,lw=.5)
    ax.bar(x+w/2,r.new_MAE,width=w,color=BLUE,label='更新后预报')
    for i,row in enumerate(r.itertuples()):
        for offset,value,color in [(-w/2,row.old_MAE,GRAY),(w/2,row.new_MAE,BLUE)]:
            ax.text(i+offset,value+7,f'{value:.0f}' if value>=1 else f'{value:.1g}',ha='center',fontsize=8.5,color=color)
    ax.set_xticks(x,['06:00','12:00','18:00']);ax.set_xlabel('预报更新时点');ax.set_ylabel('同目标 MAE / kW')
    ax.set_ylim(0,max(r.old_MAE.max(),r.new_MAE.max())*1.3);title(ax,'(d) 下一6小时的配对误差');clean(ax)
    ax.legend(loc='upper right',fontsize=8);ax.text(.98,.62,'各时点 n=1,998',transform=ax.transAxes,ha='right',fontsize=8,color=GRAY)
    save(fig,'fig6_1_forecast_quality','图6-1 四时点光伏预报质量与同目标更新',
         '共同预测起点为2025-02-01至12-30的333日，每个热图单元n=333，误差=官方小时预报−小时右端点实际功率。年末无真值目标不填充。右下图在每次更新后1至6小时的同一目标上比较上一时点预报与新预报，每时点1998对，包含夜间零功率目标。这是预测诊断，不是费用节约或信息价值估计。',
         ['forecast_metrics.csv','forecast_pairs.csv','revision_pairs.csv','revision_summary.csv'])


def timeline():
    from matplotlib.patches import FancyBboxPatch,FancyArrowPatch,Rectangle
    fig,ax=plt.subplots(figsize=(10,6.1));fig.subplots_adjust(left=.025,right=.98,bottom=.025,top=.97)
    ax.set(xlim=(-5,44),ylim=(-2.7,7.4));ax.axis('off')
    ax.axvspan(0,24,ymin=.21,ymax=.79,color='#F0F6FB',lw=0)
    ax.axvspan(24,42,ymin=.21,ymax=.79,color='#F7F9FB',lw=0)
    ax.text(12,5.5,'当日',ha='center',fontsize=11,color=BLUE)
    ax.text(33,5.5,'次日暂定部分',ha='center',fontsize=11,color=GRAY)
    def box(x,y,w,h,text,face='#E7F1F9',size=10):
        ax.add_patch(FancyBboxPatch((x,y),w,h,boxstyle='round,pad=.07,rounding_size=.14',facecolor=face,edgecolor=BLUE,lw=.9))
        ax.text(x+w/2,y+h/2,text,ha='center',va='center',fontsize=size,color=NAVY)
    def arrow(a,b,ls='-',color=BLUE):
        ax.add_patch(FancyArrowPatch(a,b,arrowstyle='-|>',mutation_scale=11,lw=1.1,ls=ls,color=color))
    box(-4.6,6.05,10.9,.7,'已知观测 + 真实 SOC',size=10)
    box(9,6.05,11,.7,'更新预测与历史场景',size=10)
    box(22.7,6.05,9.6,.7,'优化未来24 h',size=10)
    box(35,6.05,8.2,.7,'仅执行首6 h',size=10)
    for a,b in [(6.4,8.8),(20.1,22.5),(32.4,34.8)]:arrow((a,6.4),(b,6.4))
    for i,(h,color) in enumerate(zip([0,6,12,18],COLORS)):
        y=4.6-i*1.1
        ax.text(-1,y+.26,f'{h:02d}:00',ha='right',va='center',fontsize=10.5,weight='bold',color=color)
        ax.add_patch(Rectangle((h,y),24,.52,facecolor='#E3EFF8',edgecolor=color,lw=1,ls='--'))
        ax.add_patch(Rectangle((h,y),6,.52,facecolor=color,edgecolor=color,lw=1))
        ax.text(h+3,y+.26,'执行6 h',ha='center',va='center',fontsize=9,color='white' if i else NAVY)
        ax.text(h+15,y+.26,'其余18 h 暂定',ha='center',va='center',fontsize=9,color=GRAY)
        if i<3:
            arrow((h+6,y-.02),(h+6,y-.54))
            ax.text(h+6.45,y-.36,'真实SOC',fontsize=8,color=GRAY)
    arrow((0,.65),(42.8,.65),color=NAVY)
    for h in range(0,43,6):
        ax.plot([h,h],[.60,.70],color=NAVY,lw=.8)
        ax.text(h,.39,str(h) if h<=24 else f'+{h-24}',ha='center',va='top',fontsize=9,color=GRAY)
    ax.text(42.8,.38,'h',va='top',fontsize=9,color=GRAY)
    box(-3.8,-.82,45.7,.66,'当日结算：各时段最终有效购电量，相对本日00:00计划计调整费用',size=10)
    ax.text(19,-1.42,r'$\mathrm{Cost}_t = p_t g_t^0 + p_t[1.5(G_t-g_t^0)_+ - 0.5(g_t^0-G_t)_+] + 5p_tB_t$',ha='center',fontsize=12)
    ax.text(19,-2.04,'已执行段不回改  ·  未来真值不进入决策  ·  次日00:00继承真实SOC并建立新基准',ha='center',fontsize=9,color=GRAY)
    save(fig,'fig6_2_rolling_mechanism','图6-2 四节点滚动决策与最终有效量结算',
         '每天00/06/12/18点更新信息并优化未来24小时，图中深色首6小时进入真实执行，后18小时仅暂定。下一个节点继承实际反馈后的SOC；储能动作在已确定节点策略下使用当前10分钟观测。图示为方法机制，不是性能数据。次日00点重新建立本日基准，最终有效购电量只对所属日g0计算一次调整结算。',
         ['execution_config.json'])


def updates():
    f=read('update_dispatch.csv');p=read('update_forecasts.csv');g=read('update_grid_policies.csv')
    fig,axes=plt.subplots(2,1,figsize=(9.6,6.3),sharex=True,layout='constrained')
    ax=axes[0]
    ax.fill_between(f.hour_right,f.pv_kw,color=LIGHT,alpha=.65,lw=0)
    ax.plot(f.hour_right,f.pv_kw,color=GRAY,lw=1.6,label='实际光伏',zorder=2)
    for h,color,style,marker in zip([0,6,12,18],COLORS,STYLES,MARKERS):
        s=p[p.issue_hour==h]
        ax.plot(s.target_hour,s.forecast_kw,color=color,ls=style,marker=marker,ms=3,lw=1.6,label=f'{h:02d}:00预报')
    ax.set_ylabel('光伏功率 / kW');ax.set_ylim(bottom=0);title(ax,'(a) 同一目标日内的四次官方光伏预报',pad=30)
    ax.legend(loc='lower left',bbox_to_anchor=(0,1.01),ncol=5,fontsize=8,columnspacing=1.2)
    ax.text(.98,.93,str(f.date.iloc[0]),ha='right',transform=ax.transAxes,fontsize=10,color=BLUE)
    ax=axes[1]
    for h,color,style in zip([0,6,12,18],COLORS,STYLES):
        s=g[g.issue_hour==h]
        ax.step(s.target_hour,s.grid_kwh,where='pre',color=color,ls=style,lw=1.2,alpha=.7,label=f'{h:02d}:00计划')
    ax.step(f.hour_right,f.grid,where='pre',color=NAVY,lw=2.1,label='最终执行',zorder=5)
    ax.set_ylabel('购电量 / (kWh/10 min)');ax.set_ylim(bottom=0);title(ax,'(b) 节点计划修订与最终有效购电',pad=30)
    ax.legend(loc='lower left',bbox_to_anchor=(0,1.01),ncol=5,fontsize=8,columnspacing=1.2)
    for ax in axes:clean(ax);timeaxis(ax);boundaries(ax)
    axes[0].set_xlabel('')
    save(fig,'fig6_3_forecast_and_plan_updates','图6-3 高预测更新日的预报与购电计划修订',
         '2025-08-25为已完成敏感性方案预先选定的高预测更新日。上图连接附件3的小时预报点，仅显示当天剩余目标，非10分钟插值的误差检验；实际曲线为10分钟观测。下图显示各节点24h策略在当日的部分，粗深蓝曲线逐段取各节点首36时段，与正式dispatch完全一致。竖虚线为6/12/18点。不同信息集、SOC和求解状态共同影响计划，不能由本图估计因果信息价值。',
         ['update_dispatch.csv','update_forecasts.csv','update_grid_policies.csv'])


def replay():
    f=read('pressure_dispatch.csv');e=read('pressure_storage.csv');x=f.hour_right.to_numpy();dt=1/6
    fig,axes=plt.subplots(3,1,figsize=(9.6,7.6),sharex=True,layout='constrained')
    ax=axes[0]
    ax.plot(x,np.maximum(f.net_kwh,0),color=PALE,ls='--',lw=1.4,label='储能前净需求正部')
    ax.step(x,f.g0,where='pre',color=MID,ls=':',lw=1.5,label='00:00基准计划')
    ax.step(x,f.grid,where='pre',color=NAVY,lw=1.8,label='最终有效购电')
    ax.bar(x-dt/2,f.emergency,width=dt*.85,color=RED,label='紧急补购',zorder=4)
    for t,v in zip(x,f.emergency):
        if v>1e-6:ax.axvspan(t-dt,t,color=RED,alpha=.06,lw=0)
    title(ax,'(a) 购电修订与实际紧急补购',pad=30);ax.set_ylabel('电量 / (kWh/10 min)');ax.set_ylim(bottom=0)
    ax.legend(loc='lower left',bbox_to_anchor=(0,1.01),ncol=4,fontsize=8)
    ax.text(.64,.93,f'{f.date.iloc[0]}  ·  紧急量 {f.emergency.sum():.2f} kWh',transform=ax.transAxes,ha='center',fontsize=9,color=RED)
    ax=axes[1]
    ax.bar(x-dt/2,f.charge,width=dt*.9,color=MID,label='充电 +C',lw=0)
    ax.bar(x-dt/2,-f.discharge,width=dt*.9,color=NAVY,label='放电 −D',lw=0)
    ax.axhline(0,color=GRAY,lw=.7);ax.set_ylim(-960,960);ax.set_yticks([-800,-400,0,400,800]);ax.set_ylabel('储能动作 / kWh')
    title(ax,'(b) 实际充放电响应',pad=28);ax.legend(loc='lower left',bbox_to_anchor=(0,1.01),ncol=2,fontsize=8.5)
    ax=axes[2];ax.axhspan(1200,10800,color=BLUE,alpha=.035)
    ax.plot(e.hour,e.soc_kwh,color=BLUE,lw=1.9)
    for level in [1200,10800]:
        ax.axhline(level,color=GRAY,ls='--',lw=.8)
        ax.text(23.8,level+170,f'{level:,} kWh',ha='right',fontsize=8.5,color=GRAY)
    ax.scatter([0,24],[e.soc_kwh.iloc[0],e.soc_kwh.iloc[-1]],color=NAVY,s=18,zorder=5)
    ax.set_ylim(450,11650);ax.set_yticks([1200,3600,6000,8400,10800]);ax.set_ylabel('储电量 / kWh')
    title(ax,'(c) 真实SOC交接与运行边界')
    for ax in axes:clean(ax);timeaxis(ax);boundaries(ax)
    for ax in axes[:-1]:ax.set_xlabel('')
    save(fig,'fig6_4_pressure_day_dispatch','图6-4 压力代表日购电与储能真实运行',
         f'{f.date.iloc[0]}为题目指定3/20、6/21、9/23、12/21中正式紧急量最高日；紧急量{f.emergency.sum():.6f}kWh。柱高使用原值，淡红仅标记事件时段。净需求正部为max((负荷−光伏)/6,0)，不是最终购电。实际SOC含日初145点，效率两侧0.9，界限1200–10800kWh。竖虚线为信息更新节点；未将所有节点声称为严格最优。',
         ['pressure_dispatch.csv','pressure_storage.csv','pressure_candidates.csv'])


def costs():
    f=read('monthly_costs.csv');x=f.month.to_numpy();p=json.loads((DATA/'provenance.json').read_text(encoding='utf-8'))
    fig,axes=plt.subplots(1,2,figsize=(9.6,4.35),layout='constrained')
    ax=axes[0]
    ax.bar(x,f.total_cost/10000,color=[SEQ(v) for v in np.linspace(.35,.9,11)],width=.65,label='实际总费用')
    ax.plot(x,f.planned_cost/10000,color=NAVY,ls='--',marker='o',ms=3.5,lw=1.3,label='00:00基准购电费')
    ax.set_ylabel('月费用 / 万元');ax.set_ylim(0,f.total_cost.max()/10000*1.3);title(ax,'(a) 月度费用与基准购电费');ax.legend(loc='upper left',fontsize=8.5)
    ax.text(.98,.93,f'334日合计\n{p["annual_cost_yuan"]/10000:,.2f} 万元',ha='right',va='top',transform=ax.transAxes,color=BLUE,fontsize=9.5)
    ax=axes[1];w=.32
    ax.bar(x-w/2,f.adjustment_cost/10000,width=w,color=MID,label='有符号调整费用')
    ax.bar(x+w/2,f.emergency_cost/10000,width=w,color=NAVY,label='紧急购电费')
    ax.axhline(0,color=GRAY,lw=.8);ax.set_ylabel('月费用分项 / 万元');title(ax,'(b) 调整结算与紧急购电');ax.legend(loc='upper left',fontsize=8.5)
    top=max(f.adjustment_cost.max(),f.emergency_cost.max())/10000
    ax.set_ylim(min(f.adjustment_cost.min()/10000*1.15,-.2),top*1.3)
    for ax in axes:clean(ax);ax.set_xticks(x);ax.set_xlabel('月份（2025年；1月为预热）')
    save(fig,'fig6_5_cost_structure','图6-5 正式334日月度费用结构',
         '仅2025-02-01至12-31正式334日。实际总费用=00点基准购电费+有符号调整费用+紧急购电费；下调结算可为负值，因此右图保留零线下方。两面板纵轴尺度不同，分别显示主体费用与较小分项。负调整结算不是总利润；没有将0点基准计划的购电费当作不更新策略的反事实总费用。',
         ['monthly_costs.csv','formal_daily.csv'])


def annual_maps():
    f=read('formal_dispatch.csv');dates=pd.to_datetime(f.date.drop_duplicates());n=len(dates)
    ticks=[0,59,120,181,242,303,333]
    fig,axes=plt.subplots(1,2,figsize=(9.6,5.9),sharey=True,layout='constrained')
    values=[f.soc.to_numpy().reshape(n,144),f.delta_grid_kwh.to_numpy().reshape(n,144)]
    for ax,v,label in zip(axes,values,['(a) 实际储电量 SOC','(b) 最终购电相对00:00计划的变化']):
        signed=ax is axes[1]
        norm=TwoSlopeNorm(vmin=-abs(v).max(),vcenter=0,vmax=abs(v).max()) if signed else None
        im=ax.imshow(v,aspect='auto',origin='upper',extent=(0,24,n,0),cmap=DIV if signed else SEQ,
            norm=norm,vmin=None if signed else 1200,vmax=None if signed else 10800,interpolation='nearest',rasterized=True)
        ax.set_xticks([0,6,12,18,24]);ax.set_yticks(np.array(ticks)+.5,[dates.iloc[t].strftime('%m-%d') for t in ticks]);ax.set_xlabel('时刻 / h');ax.grid(False)
        for spine in ax.spines.values():spine.set_visible(False)
        title(ax,label);fig.colorbar(im,ax=ax,pad=.025,shrink=.9,label='kWh/10 min' if signed else 'kWh')
    axes[0].set_ylabel('日期（2025年正式334日）')
    save(fig,'fig6_6_annual_storage_and_revisions','图6-6 正式期储能状态与购电修订图谱',
         '每个像素对应一天的一个10分钟时段，共334×144点；不平滑，不补1月。左图为时段末储电量并固定物理色标1200–10800kWh。右图为最终有效grid−本日g0，蓝色为上调、蓝灰为下调、白色为零；色标按真实最大绝对值对称展开，保留全部极端值。00–06首执行块差值为零是原结算与执行机制的结果。',
         ['formal_dispatch.csv'])


def sensitivity():
    f=read('local_sensitivity.csv');fig,axes=plt.subplots(2,3,figsize=(10,6.8))
    fig.subplots_adjust(left=.08,right=.985,bottom=.12,top=.80,hspace=.46,wspace=.32)
    dates=['2025-03-12','2025-08-25','2025-07-01','2025-07-02']
    labels=['03-12 常规日','08-25 高更新日','07-01 高调整成本日','07-02 高风险日']
    for j,(parameter,xlabel,levels,baseline) in enumerate([
        ('S','场景数 S',[10,20,28],20),('lambda_E',r'终端价值系数 $\lambda_E$',[.8,1,1.2],1),('S_tail',r'尾部场景数 $S_{tail}$',[0,2,4],2)]):
        for ax in axes[:,j]:
            ax.axvline(baseline,color=GRAY,ls=':',lw=1,alpha=.65);ax.set_xticks(levels);ax.set_xlabel(xlabel);clean(ax)
        for i,(day,label,color,style,marker) in enumerate(zip(dates,labels,COLORS,STYLES,MARKERS)):
            s=f[f.parameter.eq(parameter)&f.date.eq(day)].sort_values('value')
            for row,ykey in [(0,'delta_cost_pct'),(1,'final_soc')]:
                ax=axes[row,j];ax.plot(s.value,s[ykey],color=color,ls=style,lw=1.5,label=label)
                for point in s.itertuples():
                    ax.plot(point.value,getattr(point,ykey),marker=marker,ms=5.6,color=color,
                            markerfacecolor=color if point.reliable else 'white',markeredgewidth=1.2)
        axes[0,j].axhline(0,color=GRAY,lw=.7)
        for level in [1200,10800]:axes[1,j].axhline(level,color=GRAY,ls='--',lw=.7,alpha=.7)
        axes[1,j].set_ylim(700,11300);axes[1,j].set_yticks([1200,6000,10800])
        title(axes[0,j],f'({chr(97+j)}) '+['场景规模','终端库存价值','尾部代表性'][j])
        title(axes[1,j],f'({chr(100+j)}) 日末储电量')
    axes[0,0].set_ylabel('相对基准日费用变化 / %')
    axes[1,0].set_ylabel('日末储电量 / kWh')
    from matplotlib.lines import Line2D
    handles=[Line2D([],[],color=c,ls=s,marker=m,markerfacecolor='white',label=l) for c,s,m,l in zip(COLORS,STYLES,MARKERS,labels)]
    fig.legend(handles=handles,loc='upper center',bbox_to_anchor=(.54,.99),ncol=4,fontsize=9,handlelength=2.5)
    fig.text(.54,.905,'4代表日局部实验  ·  空心：存在未认证节点  /  实心：该日全部节点达到3%证书',ha='center',fontsize=9,color=GRAY)
    fig.text(.54,.03,'日末库存随参数改变；较低当日费用不能单独解释为跨日更优或全年稳健。',ha='center',fontsize=9,color=GRAY)
    save(fig,'figS3_1_local_sensitivity','附图S3-1 场景与终端价值的局部敏感性',
         '复用已完成Q3四代表日实验，每列三水平均采用同日日初SOC和固定28条真实历史池，S按用户确认取10/20/28。尾部数0/2/4，终端系数0.8/1/1.2。虚竖线为基准，费用变化按同日基准分母计算；点间连线只辅助阅读，不代表中间参数已计算。空心点存在未认证节点，实心为四节点均达到3%证书。三个因素共24变体+12基准记录，22变体存在未认证节点，四基准日亦未全部认证。终端库存不同，不能直接外推全年经济性。',
         ['local_sensitivity.csv'])


def main():
    global DATA,OUT
    parser=argparse.ArgumentParser();parser.add_argument('--data-dir',type=Path,default=DATA);parser.add_argument('--output-dir',type=Path,default=OUT)
    args=parser.parse_args();DATA=args.data_dir.resolve();OUT=args.output_dir.resolve();OUT.mkdir(parents=True,exist_ok=True)
    with plt.rc_context(STYLE):
        for fn in [forecast_quality,timeline,updates,replay,costs,annual_maps,sensitivity]:fn()
    (OUT/'manifest.json').write_text(json.dumps(MANIFEST,ensure_ascii=False,indent=2),encoding='utf-8')
    (OUT/'captions.md').write_text('# 第三问科研图图注\n\n'+'\n\n'.join('## '+r['title']+'\n\n'+r['caption'] for r in MANIFEST)+'\n',encoding='utf-8')
    cards=''.join(f'<article><h2>{html.escape(r["title"])}</h2><a href="{r["png"]}"><img src="{r["png"]}" alt="{html.escape(r["title"])}"></a><p>{html.escape(r["caption"])}</p><a href="{r["svg"]}">SVG 矢量图</a> · <a href="{r["png"]}">PNG 原图</a></article>' for r in MANIFEST)
    page='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>第三问科研图 · 蓝色渐变</title><style>body{margin:0;background:#edf3f8;color:#103b62;font:16px/1.65 -apple-system,BlinkMacSystemFont,"PingFang SC",sans-serif}main{max-width:1160px;margin:auto;padding:30px 24px}article{background:#fff;padding:24px;margin:24px 0;border-radius:12px}h1{font-size:28px}h2{font-size:20px}img{width:100%;height:auto}p{color:#62778a;font-size:14px}a{color:#1263a0}</style><main><h1>第三问 · 预测更新与滚动调度</h1><p>6张正文图 + 1张敏感性附图 · 多强度蓝色 · 400dpi PNG / SVG · 已有真实结果</p>'''+cards+'</main></html>'
    (OUT/'index.html').write_text(page,encoding='utf-8')


if __name__=='__main__':main()
