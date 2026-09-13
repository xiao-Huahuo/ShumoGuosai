"""用户图5-1..5-5及全年热图：科研技能风格、真实数据、PNG/SVG。"""
from pathlib import Path
import json,hashlib,shutil,warnings
import numpy as np
import pandas as pd
from .common import setup
from .q2_paper_data import ROOT,OUT,DATA

BLUE='#1263A0';NAVY='#103B62';TEAL='#3988C1';ORANGE='#4F97C8';PURPLE='#285785';RED='#B76667';GRAY='#62778A';LIGHT='#DDEAF3'
plt,FONT=setup()
STYLE={'font.size':11,'axes.titlesize':11.5,'axes.titleweight':'medium','axes.labelsize':10.5,'xtick.labelsize':9.5,'ytick.labelsize':9.5,
       'legend.fontsize':9,'legend.frameon':False,'axes.edgecolor':'#9CA9B5','axes.linewidth':.7,'axes.labelcolor':NAVY,'text.color':NAVY,
       'xtick.color':GRAY,'ytick.color':GRAY,'grid.color':LIGHT,'grid.alpha':.8,'grid.linewidth':.55,'lines.linewidth':1.65,
       'mathtext.fontset':'dejavusans','svg.fonttype':'path','axes.spines.top':False,'axes.spines.right':False,
       'figure.constrained_layout.h_pad':.065,'figure.constrained_layout.w_pad':.055,'savefig.facecolor':'white'}
MANIFEST=[]


def read(name):return pd.read_csv(DATA/name,float_precision='round_trip')
def title(ax,text):ax.set_title(text,loc='left',pad=10)
def clean(ax):ax.grid(True,axis='y');ax.grid(axis='x',visible=False);ax.tick_params(length=3,width=.6)
def time_axis(ax):ax.set_xlim(0,24);ax.set_xticks(np.arange(0,25,4));ax.set_xlabel('时刻 / h')


def save(fig,name,title_text,caption,data):
    fig.canvas.draw()
    with warnings.catch_warnings():
        warnings.filterwarnings('error',message='Glyph .* missing from font')
        for suffix in ('png','svg'):fig.savefig(OUT/f'{name}.{suffix}',dpi=400,facecolor='white',transparent=False)
    MANIFEST.append({'name':name,'title':title_text,'caption':caption,'data':data,'png':name+'.png','svg':name+'.svg',
                     'width_inches':float(fig.get_figwidth()),'height_inches':float(fig.get_figheight()),'dpi':400,'font':FONT,'svg_text':'glyph paths',
                     'script':'src/plots/q2_paper_final.py'})
    plt.close(fig)


def structure():
    fig,axes=plt.subplots(2,2,figsize=(8.8,6.5),layout='constrained')
    profiles=read('fig51_weekday_profiles.csv');ax=axes[0,0]
    for (name,color,style) in [('周一至周五',BLUE,'-'),('周六及周日',ORANGE,'--')]:
        f=profiles[profiles.group==name];x=f.hour.to_numpy()
        ax.fill_between(x,f.p25_kw.to_numpy(),f.p75_kw.to_numpy(),color=color,alpha=.11,lw=0)
        ax.plot(x,f.mean_kw,color=color,ls=style,label=name)
    ax.set_ylabel('平均负荷功率 / kW');time_axis(ax);title(ax,'(a) 工作日与周末负荷');ax.legend(loc='upper left',ncol=1)
    ax.text(.98,.04,'阴影：25%–75%分位范围',transform=ax.transAxes,ha='right',va='bottom',fontsize=8,color=GRAY)
    seasonal=read('fig51_seasonal_pv.csv');ax=axes[0,1]
    for month,color,style,label in [(1,NAVY,'--','1月 · 冬'),(4,PURPLE,'-.','4月 · 春'),(7,BLUE,'-','7月 · 夏'),(10,TEAL,':','10月 · 秋')]:
        f=seasonal[seasonal.month==month];ax.plot(f.hour,f.mean_pv_kw,color=color,ls=style,label=label,lw=1.9)
    ax.set_ylabel('平均光伏功率 / kW');ax.set_ylim(bottom=0);time_axis(ax);title(ax,'(b) 代表月份光伏日曲线');ax.legend(loc='upper left',ncol=1,columnspacing=1,handlelength=2)
    f=read('fig51_load_lag_correlation.csv');ax=axes[1,0]
    ax.plot(f.lag,f.rho,color=BLUE,lw=1.35)
    for lag,label in [(144,'144 = 1日'),(288,'288 = 2日'),(1008,'1008 = 7日')]:
        ax.axvline(lag,color=GRAY,ls='--',lw=.8,alpha=.6)
        ax.plot(lag,float(f.loc[f.lag==lag,'rho'].iloc[0]),'o',color=BLUE,ms=4)
        ax.text(lag+9,.04,label,transform=ax.get_xaxis_transform(),rotation=90,va='bottom',fontsize=8,color=GRAY)
    ax.set_xlim(0,1040);ax.set_ylim(float(f.rho.min())-.055,1.05);ax.set_xticks([0,144,288,504,720,1008]);ax.set_xlabel('滞后时段 k（每段10分钟）');ax.set_ylabel(r'$\rho_L(k)$');title(ax,'(c) 负荷滞后相关结构')
    f=read('fig51_pv_residual_acf.csv');ax=axes[1,1]
    ax.fill_between(f.lag.to_numpy()[1:],f.reference_lower.to_numpy()[1:],f.reference_upper.to_numpy()[1:],color=GRAY,alpha=.19,lw=0,label='95% Bartlett参考带')
    ax.plot(f.lag,f.acf,color=BLUE,lw=1.4,label='去周期光伏残差')
    ax.axhline(0,color=GRAY,lw=.65);ax.set_xlim(0,288);ax.set_xticks([0,48,96,144,192,240,288]);ax.set_ylim(min(float(f.acf.min()),float(f.reference_lower.min()))-.04,1.05)
    ax.set_xlabel('滞后时段 k（每段10分钟）');ax.set_ylabel('残差自相关');title(ax,'(d) 去除日周期后的光伏残差');ax.legend(loc='upper right',fontsize=8)
    for ax in axes.ravel():clean(ax)
    save(fig,'fig5_1_source_load_structure','图5-1 源荷结构与预测特征依据组合图',
         '全年2025年数据的事后结构展示。工作日指周一至周五；分位带是跨日25%–75%范围。光伏以每月×时刻均值去周期，未将全样本统计用于滚动预测。负荷为配对Pearson相关；残差带为逐点Bartlett参考带。',
         ['fig51_weekday_profiles.csv','fig51_seasonal_pv.csv','fig51_load_lag_correlation.csv','fig51_pv_residual_acf.csv','fig51_pv_deseasonalized.csv'])


def forecast():
    fig,axes=plt.subplots(1,2,figsize=(8.8,4.25),layout='constrained');f=read('fig52_paired_errors.csv');colors=[ORANGE,BLUE,NAVY]
    values=[f[f.horizon==h].error_kwh.to_numpy() for h in range(3)]
    ax=axes[0];bp=ax.boxplot(values,positions=[0,1,2],widths=.46,patch_artist=True,showfliers=True,
            medianprops={'color':NAVY,'lw':1.6},whiskerprops={'color':GRAY,'lw':1},capprops={'color':GRAY,'lw':1},
            flierprops={'marker':'.','markersize':2,'markeredgewidth':0,'markerfacecolor':GRAY,'alpha':.14})
    for patch,color in zip(bp['boxes'],colors):patch.set(facecolor=color,alpha=.50,edgecolor=color,lw=1.3)
    ax.axhline(0,color=GRAY,ls='--',lw=.85,alpha=.85)
    ax.set_xticks([0,1,2],['h=0\n第1日前瞻','h=1\n第2日前瞻','h=2\n第3日前瞻']);ax.set_ylim(-425,600)
    ax.set_ylabel('净负荷误差 / (kWh/10 min)');title(ax,'(a) 同源预测误差分布')
    for h,v in enumerate(values):
        med=np.median(v);iqr=np.quantile(v,.75)-np.quantile(v,.25)
        ax.text(h,570,f'中位 {med:.2f}\nIQR {iqr:.2f}',ha='center',va='top',fontsize=8,color=colors[h])
    ax.set_xlabel(f'共同304日；每组 n={len(values[0]):,}\n误差=真实值−预测值；保留全部尾部',fontsize=8.5,color=GRAY)
    ax=axes[1];coverage=read('fig52_paired_coverage.csv')
    for nominal,color,marker,style in [(.8,BLUE,'o','-'),(.9,TEAL,'s','--')]:
        g=coverage[np.isclose(coverage.nominal,nominal)].sort_values('horizon')
        ax.plot(g.horizon,g.picp,color=color,marker=marker,ms=6,ls=style,lw=1.6,label=f'{nominal:.0%}预测区间')
        ax.axhline(nominal,color=color,ls=':',lw=1,alpha=.55)
        ax.text(2.13,nominal,f'名义{nominal:.0%}',ha='right',va='bottom',fontsize=8,color=color)
        for h,v in zip(g.horizon,g.picp):ax.annotate(f'{v:.1%}',(h,v),xytext=(0,-15 if nominal==.8 else 8),textcoords='offset points',ha='center',fontsize=9,color=color)
    ax.set_xlim(-.22,2.18);ax.set_ylim(.60,1.0);ax.set_yticks(np.arange(.6,1.01,.1));ax.yaxis.set_major_formatter(__import__('matplotlib').ticker.PercentFormatter(1))
    ax.set_xticks([0,1,2],['h=0','h=1','h=2']);ax.set_xlabel('前瞻日索引');ax.set_ylabel('经验覆盖率 PICP');title(ax,'(b) 场景区间覆盖率校准');ax.legend(loc='upper left',fontsize=8.5)
    for ax in axes:clean(ax)
    save(fig,'fig5_2_forecast_and_calibration','图5-2 不同前瞻日的误差分布与场景校准',
         '仅使用三个前瞻日均有正式场景且目标真值完整的304个共同预测起点，每个h为43,776时段。误差为同forecast-origin真实净负荷减点预测，单位kWh/10min。箱线须为1.5IQR，点保留全部离群值；PICP由覆盖数/样本数计算。',
         ['fig52_paired_errors.csv','fig52_error_quantiles.csv','fig52_paired_coverage.csv','fig52_all_available_coverage.csv'])


def timeline():
    from matplotlib.patches import FancyBboxPatch,FancyArrowPatch,Rectangle,Circle
    fig,ax=plt.subplots(figsize=(9.6,5.6));fig.subplots_adjust(left=.025,right=.98,bottom=.035,top=.965);ax.set(xlim=(0,1),ylim=(0,1));ax.axis('off')
    def box(x,y,w,h,text,face='#EFF5F8',edge=BLUE,size=10,weight='normal'):
        patch=FancyBboxPatch((x,y),w,h,boxstyle='round,pad=0.010,rounding_size=0.012',facecolor=face,edgecolor=edge,lw=1)
        ax.add_patch(patch);ax.text(x+w/2,y+h/2,text,ha='center',va='center',fontsize=size,color=NAVY,weight=weight)
    def arrow(a,b,color=GRAY,style='-',connection='arc3,rad=0',lw=1.15):
        ax.add_patch(FancyArrowPatch(a,b,arrowstyle='-|>',mutation_scale=11,color=color,lw=lw,ls=style,connectionstyle=connection))
    ax.text(.01,.96,'日前：已知信息 → 预测与优化',fontsize=12,weight='bold',color=NAVY)
    box(.015,.745,.15,.13,r'$\mathcal{I}_d$'+'\n'+r'$E_{d,0}$'+'  '+r'$p_t$',size=11)
    ax.text(.09,.71,r'第 $d$ 日 0:00',ha='center',fontsize=9,color=GRAY)
    box(.215,.775,.14,.07,'源荷预测');box(.405,.775,.17,.07,'联合场景构造');box(.625,.775,.14,.07,'随机优化')
    for a,b in [((.17,.81),(.205,.81)),((.36,.81),(.395,.81)),((.58,.81),(.615,.81))]:arrow(a,b)
    box(.215,.51,.55,.18,'',face='#E7F1F9',edge=BLUE)
    ax.text(.49,.665,'0:00 一次确定并冻结',ha='center',fontsize=10.5,weight='bold',color=TEAL)
    for x,text in [(.25,r'$G_t$'),(.42,r'$C_t^p$'),(.59,r'$D_t^p$')]:box(x,.58,.115,.053,text,face='white',edge=TEAL,size=13)
    ax.text(.49,.532,r'安全裕度 $R_t$ 亦由历史信息预先确定',ha='center',fontsize=8.5,color=GRAY)
    arrow((.697,.765),(.697,.70),color=TEAL)
    ax.text(.015,.455,'日内：只用当前观测执行冻结反馈',fontsize=11.5,weight='bold')
    box(.02,.315,.33,.085,r'$L_t^{\mathrm{real}},\;P_t^{PV,\mathrm{real}},\;E_{t-1}$',size=12,face='#F4F6F8',edge=GRAY)
    box(.415,.315,.22,.085,'冻结反馈映射',face='#E7F1F9',edge=BLUE,weight='bold')
    box(.71,.315,.22,.085,r'$C_t,\quad D_t,\quad B_t$',face='#EFF5F8',edge=BLUE,size=13)
    arrow((.355,.357),(.405,.357));arrow((.642,.357),(.70,.357));arrow((.54,.498),(.54,.41),color=TEAL,style='--')
    ax.text(.554,.462,'冻结参数',fontsize=8,color=TEAL)
    y=.265;arrow((.03,y),(.935,y),color=NAVY,lw=1.4)
    for x,text in [(.07,'0:10'),(.255,'0:20'),(.46,'⋯'),(.67,r'$t$'),(.88,'24:00')]:
        ax.plot([x,x],[y-.008,y+.012],color=NAVY,lw=.8);ax.text(x,y-.024,text,ha='center',va='top',fontsize=10)
    arrow((.17,.275),(.17,.305),color=GRAY)
    masked=Rectangle((.03,.045),.64,.115,facecolor='#F1F2F4',edgecolor='#A4ACB4',ls='--',lw=1,alpha=.80);ax.add_patch(masked)
    ax.add_patch(Circle((.07,.105),.023,fill=False,edgecolor=RED,lw=1.2));ax.plot([.054,.086],[.089,.121],color=RED,lw=1.2)
    ax.text(.385,.11,r'未来 $L_{t+1:T}^{\mathrm{real}},\;P_{t+1:T}^{PV,\mathrm{real}}$ 不可见',ha='center',va='center',fontsize=10,color=GRAY)
    ax.text(.385,.067,'仅用于事后回放，不进入当前决策',ha='center',fontsize=8,color=GRAY)
    box(.735,.07,.205,.105,r'$E_{d,144}^{\mathrm{real}}$'+'\n真实日末储电量',face='#EFF5F8',edge=BLUE,size=10)
    arrow((.88,.211),(.84,.183),color=BLUE)
    box(.81,.81,.165,.105,r'$(d+1)$ 日 0:00'+'\n继承真实 SOC',face='#EFF5F8',edge=BLUE,size=9.5)
    arrow((.95,.123),(.983,.843),color=BLUE,connection='angle3,angleA=0,angleB=90')
    arrow((.806,.89),(.088,.89),color=BLUE,style='--',connection='arc3,rad=.0');arrow((.088,.89),(.088,.884),color=BLUE)
    ax.text(.46,.911,'滚动到下一日，重新预测与优化',ha='center',fontsize=8.5,color=BLUE)
    save(fig,'fig5_3_causal_information_timeline','图5-3 非前瞻滚动调度的信息时序',
         '横向时间轴区分日前冻结与日内反馈。G为计划购电，Cp/Dp为事前反馈上限，R为历史给定安全裕度；C/D/B为实际充电/放电/紧急购电。当前映射不访问未来真实轨迹。真实日末SOC传至下一日，不重置。',[])


def dispatch():
    f=read('fig54_real_dispatch.csv');e=read('fig54_storage_145.csv');edges=np.arange(145)/6;x=f.hour_center.to_numpy();dt=1/6
    fig,axes=plt.subplots(3,1,figsize=(8.8,7.7),sharex=True,layout='constrained',gridspec_kw={'height_ratios':[1.1,1,1]})
    ax=axes[0];ax.stairs(f.Z_real_kwh,edges,color=NAVY,lw=1.45,label=r'实际净外部需求 $Z_t$');ax.stairs(f.grid,edges,color=BLUE,lw=1.7,label=r'计划购电 $G_t$')
    ax.stairs(f.Z_forecast_kwh,edges,color=GRAY,lw=1,ls='--',alpha=.6,label=r'预测净外部需求 $\hat Z_t$')
    ax.bar(x,f.emergency,width=dt*.95,color=RED,alpha=.85,label=r'紧急购电 $B_t$',zorder=4)
    for t,value in zip(x,f.emergency):
        if value>1e-6:ax.axvspan(t-dt/2,t+dt/2,color=RED,alpha=.065,lw=0)
    ax.set_ylim(bottom=0);ax.set_ylabel('电量 / (kWh/10 min)');title(ax,'(a) 实际需求、计划购电与紧急补购')
    ax.legend(loc='lower left',bbox_to_anchor=(0,1.01),ncol=4,fontsize=8.0,columnspacing=1);ax.set_title('(a) 实际需求、计划购电与紧急补购',loc='left',pad=31);ax.text(.62,.95,f"{f.date.iloc[0]}\n紧急购电合计 {f.emergency.sum():.2f} kWh",transform=ax.transAxes,ha='center',va='top',fontsize=9,color=RED)
    ax=axes[1];ax.bar(x,f.charge,width=dt*.95,color=TEAL,label=r'$+C_t$ 充电',lw=0);ax.bar(x,-f.discharge,width=dt*.95,color=PURPLE,label=r'$-D_t$ 放电',lw=0)
    ax.axhline(0,color=GRAY,lw=.7);ax.set_ylim(-980,980);ax.set_yticks([-800,-400,0,400,800]);ax.set_ylabel('储能动作 / kWh');ax.set_title('(b) 冻结策略的真实充放电响应',loc='left',pad=31);ax.legend(loc='lower left',bbox_to_anchor=(0,1.01),ncol=2)
    ax=axes[2];ax.axhspan(1200,10800,color=BLUE,alpha=.035);ax.plot(e.hour,e.energy_kwh,color=NAVY,lw=1.8)
    for level,label in [(1200,r'$E_{\min}=1200$'),(10800,r'$E_{\max}=10800$')]:
        ax.axhline(level,color=GRAY,ls='--',lw=.9);ax.text(23.8,level+180,label,ha='right',va='bottom',fontsize=9,color=GRAY)
    ax.plot([0,24],[e.energy_kwh.iloc[0],e.energy_kwh.iloc[-1]],'o',color=TEAL,ms=4,zorder=5)
    ax.annotate(f"日初 {e.energy_kwh.iloc[0]:.0f}",(0,e.energy_kwh.iloc[0]),xytext=(10,-14),textcoords='offset points',fontsize=8.5,color=TEAL)
    ax.set_ylim(450,11650);ax.set_yticks([1200,3600,6000,8400,10800]);ax.set_ylabel('储电量 / kWh');title(ax,'(c) 实际储电量及运行边界')
    for ax in axes:clean(ax);ax.set_xlim(0,24);ax.set_xticks(np.arange(0,25,4))
    axes[-1].set_xlabel('时刻 / h')
    save(fig,'fig5_4_real_dispatch_20250320','图5-4 压力代表日真实购电与储能运行',
         '2025-03-20在题目四个指定日期中紧急量最高（53.567333kWh）。Z为储能之前净负荷正部，单位kWh/10min；红柱为真实紧急量，淡红时段仅标事件位置、不放大能量。充电为正、放电为负，SOC含日初共145点。',
         ['fig54_real_dispatch.csv','fig54_storage_145.csv','fig54_candidate_dates.csv'])


def horizon():
    source=ROOT/'outputs/q2/benchmarks/horizon_figure_20260913'
    if (DATA/'fig55_horizon_summary.csv').exists():
        f=read('fig55_horizon_summary.csv');cases=read('fig55_horizon_cases.csv')
    else:
        f=pd.read_csv(source/'summary.csv');cases=pd.read_csv(source/'cases.csv')
    assert len(cases)==12 and cases.reliable.all() and (f.cases==4).all()
    if not (DATA/'fig55_horizon_summary.csv').exists():
        shutil.copy2(source/'summary.csv',DATA/'fig55_horizon_summary.csv');shutil.copy2(source/'cases.csv',DATA/'fig55_horizon_cases.csv')
    fig,ax=plt.subplots(figsize=(7.0,4.4),layout='constrained')
    for (_,row),color,marker in zip(f.iterrows(),[ORANGE,BLUE,NAVY],['o','s','^']):
        x=row.mean_solve_seconds;y=row.mean_day_cost/10000
        ax.scatter(x,y,s=95,color=color,marker=marker,edgecolor='white',linewidth=1.2,zorder=4)
        ax.annotate(f"{int(row.horizon_hours)} h",(x,y),xytext=(10,8),textcoords='offset points',fontsize=11,weight='bold',color=color)
        ax.annotate(f"{y:.3f} 万元/日",(x,y),xytext=(10,-11),textcoords='offset points',fontsize=8.5,color=GRAY)
    xmax=f.mean_solve_seconds.max();ymin=f.mean_day_cost.min()/10000;ymax=f.mean_day_cost.max()/10000
    ax.set_xlim(0,xmax*1.35+1);ax.set_ylim(ymin-.10,max(ymax+.13,ymin+.3))
    ax.set_xlabel('平均单日求解时间 / s');ax.set_ylabel('代表日平均真实费用 / (万元/日)')
    title(ax,'前瞻长度的局部费用—计算代价权衡');ax.text(.99,.96,'4个代表日 · 同机同预算\n共同场景前缀 · 非全年结果',transform=ax.transAxes,ha='right',va='top',fontsize=9,color=GRAY)
    clean(ax)
    save(fig,'fig5_5_local_horizon_tradeoff','图5-5 前瞻长度的局部费用与耗时权衡',
         '经用户确认改为当前模型4个代表日局部比较，纵轴不是全年费用。K1/2/3采用相同S26联合72h场景的前缀、同一各日日初SOC/R和同机3%预算，均独立计时。日末库存不同，较低当日费不等于更优跨日经济性。',
         ['fig55_horizon_summary.csv','fig55_horizon_cases.csv'])


def heatmaps():
    from matplotlib.colors import LinearSegmentedColormap,TwoSlopeNorm
    a=np.load(DATA/'figS1_annual_arrays.npz');dates=pd.date_range('2025-01-01',periods=365)
    positions=[0,59,120,181,243,304,364];labels=[dates[i].strftime('%m-%d') for i in positions]
    fig,axes=plt.subplots(1,3,figsize=(9.6,4.9),sharey=True,layout='constrained')
    ocean=LinearSegmentedColormap.from_list('load_seq',['#F2F7FC','#BBD5E9','#659FCA','#28699E','#0A355D'])
    sun=LinearSegmentedColormap.from_list('pv_seq',['#F5F9FD','#C6DFF0','#80B6DD','#337EB6','#104775'])
    diverging=LinearSegmentedColormap.from_list('net_div',['#789FA8','#B4CCD2','#E1EDF0','#FAFCFE','#BDDCEF','#6CA8D1','#104775'])
    for ax,key,cmap,text in zip(axes,['load_kw','pv_kw','net_kw'],[ocean,sun,diverging],['(a) 小区负荷','(b) 光伏实际功率','(c) 净负荷']):
        v=a[key];norm=TwoSlopeNorm(vmin=float(v.min()),vcenter=0,vmax=float(v.max())) if key=='net_kw' else None
        im=ax.imshow(v,aspect='auto',origin='upper',extent=(0,24,365,0),cmap=cmap,norm=norm,interpolation='nearest',rasterized=True)
        ax.set_xticks([0,6,12,18,24]);ax.set_xlabel('时刻 / h');ax.set_yticks(np.asarray(positions)+.5,labels);ax.grid(False);title(ax,text)
        for spine in ax.spines.values():spine.set_visible(False)
        cbar=fig.colorbar(im,ax=ax,orientation='horizontal',pad=.07,fraction=.05,aspect=25);cbar.set_label('功率 / kW',fontsize=9);cbar.ax.tick_params(labelsize=8)
    axes[0].set_ylabel('2025年日期（月-日）')
    save(fig,'figS1_annual_source_load_heatmaps','附加图 全年源荷日期—时刻热力图',
         '52560个原始10分钟记录逐格呈现，不做平滑或缺失补值。日期自上而下，负荷/PV顺序色标，净负荷发散色标以0为中心；三个色标各自标明原始kW。SVG中的热图为栅格图元，坐标和中文标签为矢量路径。',['figS1_annual_arrays.npz'])


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    with plt.rc_context(STYLE):
        structure();forecast();timeline();dispatch();horizon();heatmaps()
    for row in MANIFEST:
        row['sha256']={ext:hashlib.sha256((OUT/row[ext]).read_bytes()).hexdigest() for ext in ('png','svg')}
    (OUT/'manifest.json').write_text(json.dumps(MANIFEST,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Rendered',len(MANIFEST),'figures; font',FONT)


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--data-dir',type=Path);parser.add_argument('--output-dir',type=Path);args=parser.parse_args()
    if args.data_dir:DATA=args.data_dir.resolve()
    if args.output_dir:OUT=args.output_dir.resolve()
    main()
