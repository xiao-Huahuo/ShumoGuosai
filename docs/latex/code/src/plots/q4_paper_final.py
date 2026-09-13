"""Q4六张图：蓝莲花渐变、TeX中文字体、真实运行数据。"""
from pathlib import Path
import argparse,json,warnings,html
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.colors import LinearSegmentedColormap,LogNorm,to_rgb
from matplotlib.patches import Rectangle,FancyBboxPatch,FancyArrowPatch,PathPatch
from matplotlib.path import Path as MPath
from matplotlib.text import Text

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'outputs/processed/figures/q4_paper_final_20260913';DATA=OUT/'data'
INK='#002254';DARK='#19309A';BLUE='#4B69EF';PERI='#7E96FE';ICE='#B6D8F7';APRICOT='#FFB967';LILAC='#CDBFE2';CREAM='#FFFEF0';GRAY='#64748B'
SEQ=LinearSegmentedColormap.from_list('blue_lotus',['#FBFCFF',ICE,PERI,BLUE,DARK,INK])
STYLE={'font.family':['Latin Modern Roman','FandolSong'],'font.size':11,'axes.titlesize':12,'axes.labelsize':10.5,
       'xtick.labelsize':10,'ytick.labelsize':10,'legend.fontsize':9,'legend.frameon':False,'axes.titleweight':'regular',
       'axes.spines.top':False,'axes.spines.right':False,'axes.edgecolor':'#A0AEC0','axes.linewidth':.7,
       'axes.labelcolor':INK,'text.color':INK,'xtick.color':GRAY,'ytick.color':GRAY,
       'axes.axisbelow':True,'axes.unicode_minus':False,'grid.color':'#DDE5F1','grid.alpha':.75,'grid.linewidth':.55,
       'mathtext.fontset':'cm','svg.fonttype':'path','figure.facecolor':'white','savefig.facecolor':'white',
       'figure.constrained_layout.h_pad':.09,'figure.constrained_layout.w_pad':.07}
MANIFEST=[]


def fonts():
    available=[ROOT/'assets/q4_fonts',Path('/usr/local/texlive/2026/texmf-dist/fonts/opentype/public')]
    for filename,sub in [('FandolSong-Regular.otf','fandol'),('lmroman10-regular.otf','lm')]:
        paths=[available[0]/filename,available[1]/sub/filename]
        p=next((p for p in paths if p.exists()),None)
        if p is None:raise RuntimeError('缺少TeX字体：'+filename)
        font_manager.fontManager.addfont(str(p))


def read(name):return pd.read_csv(DATA/name,float_precision='round_trip')
def title(ax,text,pad=10):ax.set_title(text,loc='left',pad=pad)
def clean(ax):ax.grid(True,axis='y');ax.grid(False,axis='x')
def timeaxis(ax):ax.set_xlim(0,24);ax.set_xticks([0,6,12,18,24])
def nodes(ax):
    for h in [6,12,18]:ax.axvline(h,color=GRAY,ls=':',lw=.8,alpha=.65)


def gradient_rect(ax,x,y,width,height,color,orientation='vertical',alpha=1):
    """矩形真实尺寸不变，仅将填色从浅色渐变到指定色。"""
    lo,hi=sorted([y,y+height]);light=tuple(.75+.25*np.asarray(to_rgb(color)))
    cm=LinearSegmentedColormap.from_list('bar_tint',[light,color])
    values=np.linspace(0,1,256).reshape(-1,1) if orientation=='vertical' else np.linspace(0,1,256)[None]
    ax.imshow(values,extent=(x,x+width,lo,hi),origin='lower',aspect='auto',cmap=cm,alpha=alpha,interpolation='bicubic',zorder=2)
    ax.add_patch(Rectangle((x,lo),width,hi-lo,facecolor='none',edgecolor=color,lw=.7,zorder=3))


def save(fig,name,text,caption,data):
    for t in fig.findobj(Text):
        value=t.get_text()
        if '$' in value and any('\u4e00'<=c<='\u9fff' for c in value):t.set_fontfamily('FandolSong')
    with warnings.catch_warnings():
        warnings.filterwarnings('error',message='Glyph .* missing from font')
        fig.canvas.draw()
        for suffix in ['png','svg']:fig.savefig(OUT/f'{name}.{suffix}',dpi=400,facecolor='white',transparent=False)
    MANIFEST.append({'question':'q4','name':name,'title':text,'caption':caption,'data':data,'png':name+'.png','svg':name+'.svg',
                     'width_inches':fig.get_figwidth(),'height_inches':fig.get_figheight(),'dpi':400,
                     'font':'FandolSong / Latin Modern Roman / Computer Modern math','script':'src/plots/q4_paper_final.py',
                     'necessity':'问题四科研图，正文或补充选用'})
    plt.close(fig);print(name,flush=True)


def mechanism():
    fig,ax=plt.subplots(figsize=(10.1,6.4));fig.subplots_adjust(left=.018,right=.985,top=.97,bottom=.025)
    ax.set(xlim=(0,1),ylim=(0,1));ax.axis('off')
    def box(x,y,w,h,text,color=BLUE,size=10):
        clip=FancyBboxPatch((x,y),w,h,boxstyle='round,pad=.008,rounding_size=.012',edgecolor=color,lw=.85,facecolor='none',zorder=3);ax.add_patch(clip)
        cm=LinearSegmentedColormap.from_list('box',['#FAFBFF',tuple(.88+.12*np.asarray(to_rgb(color)))])
        im=ax.imshow(np.linspace(0,1,120)[None],extent=(x-.008,x+w+.008,y-.008,y+h+.008),origin='lower',aspect='auto',cmap=cm,zorder=1);im.set_clip_path(clip)
        ax.text(x+w/2,y+h/2,text,ha='center',va='center',fontsize=size,color=INK,zorder=4)
    def arrow(a,b,color=BLUE,ls='-'):
        ax.add_patch(FancyArrowPatch(a,b,arrowstyle='-|>',mutation_scale=11,color=color,lw=1.05,ls=ls,zorder=4))
    ax.text(.02,.955,'严格因果的联合不确定性',fontsize=13,color=DARK)
    box(.025,.81,.24,.09,'0点冻结：负荷与48h电价预测\n节点更新：最新PV、已实现信息',size=9.5)
    box(.335,.81,.27,.09,'同一历史日的净负荷—电价残差\n56日窗口 · 联合距离 · 尾部保留',size=9.5)
    box(.675,.81,.29,.09,'Wasserstein DRO\n经验概率 + 标定半径 → 最坏期望',color=DARK,size=10)
    arrow((.274,.855),(.32,.855));arrow((.61,.855),(.66,.855))
    ax.text(.04,.726,'4-2  日前机制',fontsize=12,color=BLUE)
    ax.text(.54,.726,'4-3  四时点机制',fontsize=12,color=DARK)
    box(.03,.445,.43,.24,'',color=BLUE);box(.53,.445,.43,.24,'',color=DARK)
    ax.text(.245,.642,'00:00 优化未来48 h',ha='center',fontsize=11)
    ax.text(.745,.642,'00 / 06 / 12 / 18 各优化未来24 h',ha='center',fontsize=11)
    for x,w,c,label in [(.065,.18,BLUE,'当日24 h 执行'),(.245,.18,ICE,'次日24 h 前瞻')]:
        ax.add_patch(Rectangle((x,.558),w,.047,facecolor=c,edgecolor=BLUE,lw=.65,zorder=3));ax.text(x+w/2,.5815,label,ha='center',va='center',fontsize=8.7,color='white' if c==BLUE else INK,zorder=4)
    for x,w,c,label in [(.565,.09,DARK,'首6 h'),(.655,.27,LILAC,'其余18 h 暂定')]:
        ax.add_patch(Rectangle((x,.558),w,.047,facecolor=c,edgecolor=DARK,lw=.65,zorder=3));ax.text(x+w/2,.5815,label,ha='center',va='center',fontsize=9,color='white' if c==DARK else INK,zorder=4)
    ax.text(.245,.491,'预提交 g / c / r；当日不再重优化',ha='center',fontsize=10)
    ax.text(.745,.491,'冻结已执行块；下一节点继承真实SOC',ha='center',fontsize=10)
    arrow((.765,.8),(.745,.697),color=DARK)
    arrow((.73,.788),(.245,.697),color=BLUE)
    box(.08,.273,.32,.096,'结算账本：额度 G 与本日基准 $g^0$\n实际电价 p · 单次净调整 · 5p紧急费',color=DARK,size=9.8)
    box(.59,.273,.32,.096,'物理执行：冻结 c / r\n实际源荷只决定调用、紧急与弃电',color=BLUE,size=9.8)
    ax.plot([.245,.245,.745,.745],[.435,.405,.405,.435],color=GRAY,lw=.9)
    ax.text(.495,.421,'共同执行与核算',ha='center',fontsize=8.7,color=GRAY)
    arrow((.495,.404),(.24,.382));arrow((.495,.404),(.75,.382),color=DARK)
    box(.07,.08,.36,.11,r'$G=x+u$'+'\n结算额度 = 实际调用 + 未调用',color=DARK,size=11)
    box(.565,.08,.36,.11,r'$x+r+q^{em}=N+c+w$'+'\n调用 + 放电 + 紧急 = 净负荷 + 充电 + 弃电',color=BLUE,size=9.5)
    arrow((.24,.263),(.24,.203));arrow((.75,.263),(.75,.203))
    ax.text(.5,.025,'未调用额度 u 不进入物理能量流；实际弃电 w 单独核算。所有时段均保留真实价格。',ha='center',fontsize=9,color=GRAY)
    save(fig,'fig7_1_joint_dro_mechanism','图7-1 严格因果DRO的双机制决策、结算与执行',
         '价格与负荷预测在当天0点冻结，4-3各节点更新PV及截至当前已实现的信息。4-2优化48h并执行首24h；4-3优化24h并执行首6h。g/c/r均为节点共享计划，实际充放电按承诺计划执行，不能画成事后全路径自适应。x=called、u=unused、w=spill；未调用额度不是弃电。两分支共享方法框架，各自独立运行SOC链，箭头不表示4-2结果作为4-3输入。',
         ['provenance.json','solver_quality.csv'])


def price_clock():
    clock=read('price_clock.csv');raw=read('dispatch_4-2.csv');meta=json.loads((DATA/'provenance.json').read_text(encoding='utf-8'))
    fig=plt.figure(figsize=(9.8,5.2),layout='constrained');gs=fig.add_gridspec(1,2,width_ratios=[1,1.12])
    ax=fig.add_subplot(gs[0,0],projection='polar');theta=(clock.hour.to_numpy()+.5)*2*np.pi/24
    xx=np.r_[theta,theta[0]+2*np.pi]
    close=lambda x:np.r_[x,x[0]]
    ax.set_theta_zero_location('N');ax.set_theta_direction(-1)
    ax.fill_between(xx,close(clock.actual_p10.to_numpy()),close(clock.actual_p90.to_numpy()),color=ICE,alpha=.45,lw=0,label='实价10%–90%跨日带')
    ax.plot(xx,close(clock.actual_median.to_numpy()),color=DARK,lw=2,label='实际小时均价的中位数')
    ax.plot(xx,close(clock.forecast_median.to_numpy()),color=BLUE,ls='--',lw=1.6,label='预测小时均价的中位数')
    ax.set_ylim(0,clock.actual_p90.max()*1.1);ax.set_xticks(np.arange(0,24,3)*2*np.pi/24,[f'{h:02d}:00' for h in range(0,24,3)]);ax.set_rlabel_position(135)
    ax.spines['polar'].set_color('#C8D5E8');ax.grid(True,color='#CDD8E9',lw=.65)
    title(ax,'(a) 24小时电价时钟',pad=20)
    ax.legend(loc='upper center',bbox_to_anchor=(.5,-.23),fontsize=8.8)
    ax.text(.5,-.17,'半径：电价 / (元/kWh)；每小时 n=334日',ha='center',transform=ax.transAxes,fontsize=9,color=GRAY)
    ax=fig.add_subplot(gs[0,1]);limit=max(raw.price.max(),raw.price_forecast.max())*1.025
    hist=ax.hist2d(raw.price_forecast,raw.price,bins=65,range=[[0,limit],[0,limit]],norm=LogNorm(vmin=1),cmap=SEQ,cmin=1)
    ax.plot([0,limit],[0,limit],color=GRAY,ls='--',lw=1,label='预测=实际')
    ax.set(xlim=(0,limit),ylim=(0,limit),xlabel='预测电价 / (元/kWh)',ylabel='实际电价 / (元/kWh)');ax.set_aspect('equal');ax.grid(False)
    fig.colorbar(hist[3],ax=ax,pad=.02,shrink=.80,label='每格样本数（对数色阶）')
    title(ax,'(b) 全时段预测—实价密度')
    ax.text(.04,.97,f'n = 48,096\nMAE = {meta["price_MAE"]:.4f}\nRMSE = {meta["price_RMSE"]:.4f}',transform=ax.transAxes,ha='left',va='top',fontsize=10,color=INK)
    save(fig,'fig7_2_price_clock_and_density','图7-2 电价的日内时钟与严格因果预测密度',
         '正式334日。左图先对每天每小时的6个10分钟值求均值，再跨日计算中位数与10%–90%分位带；分位带不是置信区间。以小时中点定位，首尾连接仅体现日周期统计。右图65×65等宽格统计全部48096点，色阶为对数计数，空格留空，没有裁去极值。实价与预测由两个正式策略共同使用，误差基于10分钟原值重算。',
         ['price_clock.csv','hourly_prices.csv','dispatch_4-2.csv'])


def cost_bridge():
    s=read('strategy_summary.csv').set_index('mode');f=read('daily_cost_pairs.csv');delta=s.loc['4-3']-s.loc['4-2']
    vals=np.array([delta.planned_cost,delta.adjustment_cost,delta.emergency_cost])/10000
    fig,axes=plt.subplots(1,2,figsize=(9.8,4.8),layout='constrained')
    ax=axes[0];current=0
    for i,v in enumerate(vals):
        gradient_rect(ax,i-.29,current,.58,v,APRICOT if v>0 else BLUE)
        ax.text(i,max(current,current+v)+4.5,f'{v:+.2f}',ha='center',fontsize=10,color=INK)
        current+=v
        if i<2:ax.plot([i+.29,i+.71],[current,current],color=GRAY,ls=':',lw=.9)
    gradient_rect(ax,2.71,0,.58,current,DARK);ax.text(3,current-3.2,f'{current:+.2f}',ha='center',fontsize=10,color=DARK)
    ax.axhline(0,color=GRAY,lw=.8);ax.set_xlim(-.55,3.55);ax.set_ylim(-42,36)
    ax.set_xticks(range(4),['基准购电费','净调整费','紧急购电费','总费用变化']);ax.tick_params(axis='x',labelsize=9)
    ax.set_ylabel('4-3 − 4-2 费用变化 / 万元');title(ax,'(a) 费用变化的分项桥图');clean(ax)
    ax.text(.02,.96,'负值：4-3支出较低',transform=ax.transAxes,fontsize=9,color=GRAY)
    ax=axes[1];v=np.sort(f.saving_yuan.to_numpy()/1000);prob=np.arange(1,len(v)+1)/len(v)
    ax.step(v,prob,where='post',color=DARK,lw=2);ax.fill_between(v,0,prob,step='post',color=ICE,alpha=.3)
    ax.axvline(0,color=GRAY,ls='--',lw=1);ax.set_ylim(0,1.02);ax.set_yticks([0,.25,.5,.75,1],['0%','25%','50%','75%','100%'])
    ax.set_xlabel('单日费用差：4-2 − 4-3 / 千元');ax.set_ylabel('累计日期比例');title(ax,'(b) 334日配对费用差的完整分布');clean(ax)
    fraction=(f.saving_yuan>0).mean();ax.text(.98,.14,f'4-3费用较低：{fraction:.1%}日期\n正式期合计少支出 {(-delta.total_cost)/10000:.2f} 万元',transform=ax.transAxes,ha='right',fontsize=9.5,color=INK)
    save(fig,'fig7_3_cost_change_bridge','图7-3 两套完整策略的费用变化与逐日配对分布',
         f'共同334日的真实结算比较。4-2总费用{s.loc["4-2","total_cost"]:.6f}元，4-3为{s.loc["4-3","total_cost"]:.6f}元；左图三分项之和精确等于总费用变化。右图保留所有正负日度差，正数表示4-3当日费用较低。两策略初始SOC均6000，最终SOC分别{s.loc["4-2","final_soc"]:.3f}/{s.loc["4-3","final_soc"]:.3f}kWh。前瞻长度、更新机会和库存轨迹均不同，结果不是纯FIV/OUV或同初态单日控制实验，不能只凭当日差排序节点价值。',
         ['strategy_summary.csv','daily_cost_pairs.csv'])


def flow_diagram():
    f=read('energy_flow.csv');s=read('strategy_summary.csv').set_index('mode')
    fig,axes=plt.subplots(1,2,figsize=(10.5,6.2));fig.subplots_adjust(left=.015,right=.985,top=.94,bottom=.05,wspace=.045)
    max_total=f[f.side=='input'].groupby('mode').kwh.sum().max();scale=.60/max_total
    colors={'called':DARK,'pv':BLUE,'discharge':PERI,'emergency':APRICOT,'load':DARK,'charge':PERI,'spill':LILAC}
    names={'called':'电网调用','pv':'实际光伏','discharge':'电池放电','emergency':'紧急购电','load':'负荷','charge':'电池充电','spill':'实际弃电'}
    def ribbon(ax,x0,x1,y0,y1,h,c):
        mid=(x0+x1)/2
        verts=[(x0,y0),(mid,y0),(mid,y1),(x1,y1),(x1,y1+h),(mid,y1+h),(mid,y0+h),(x0,y0+h),(x0,y0)]
        codes=[MPath.MOVETO,MPath.CURVE4,MPath.CURVE4,MPath.CURVE4,MPath.LINETO,MPath.CURVE4,MPath.CURVE4,MPath.CURVE4,MPath.CLOSEPOLY]
        patch=PathPatch(MPath(verts,codes),facecolor='none',edgecolor=c,lw=.3,zorder=3);ax.add_patch(patch)
        cm=LinearSegmentedColormap.from_list('ribbon',[tuple(.58+.42*np.asarray(to_rgb(c))),c])
        im=ax.imshow(np.linspace(0,1,200)[None],extent=(x0,x1,min(y0,y1),max(y0,y1)+h),aspect='auto',origin='lower',cmap=cm,alpha=.80,zorder=2);im.set_clip_path(patch)
    for ax,mode in zip(axes,['4-2','4-3']):
        ax.set(xlim=(0,1),ylim=(0,1));ax.axis('off');row=f[f['mode']==mode].set_index('key');total=row.loc[['called','pv','discharge','emergency'],'kwh'].sum()
        ax.text(.5,.98,f'{mode}  '+('日前48h前瞻' if mode=='4-2' else '四节点24h前瞻'),ha='center',fontsize=13,color=DARK)
        ax.text(.5,.94,'累计电量 / GWh · 带宽同尺度',ha='center',fontsize=9,color=GRAY)
        top=.86;bus_top=top;input_top=top
        for key in ['called','pv','discharge','emergency']:
            value=row.loc[key,'kwh'];h=value*scale;input_bottom=input_top-h;bus_bottom=bus_top-h
            ribbon(ax,.22,.47,input_bottom,bus_bottom,h,colors[key]);ax.add_patch(Rectangle((.207,input_bottom),.013,h,facecolor=colors[key],lw=0))
            ax.text(.193,input_bottom+h/2,f'{names[key]}\n{value/1e6:.3f}',ha='right',va='center',fontsize=9,color=INK)
            input_top=input_bottom-.026;bus_top=bus_bottom
        bus_bottom=top-total*scale;ax.add_patch(Rectangle((.47,bus_bottom),.05,total*scale,facecolor=ICE,edgecolor=BLUE,lw=.6,zorder=5))
        ax.text(.495,top+.025,'能量母线',ha='center',fontsize=9,color=GRAY)
        bus_top=top;output_top=top
        for key in ['load','charge','spill']:
            value=row.loc[key,'kwh'];h=value*scale;output_bottom=output_top-h;bus_bottom=bus_top-h
            ribbon(ax,.52,.78,bus_bottom,output_bottom,h,colors[key]);ax.add_patch(Rectangle((.78,output_bottom),.013,h,facecolor=colors[key],lw=0))
            ax.text(.807,output_bottom+h/2,f'{names[key]}\n{value/1e6:.3f}',ha='left',va='center',fontsize=9,color=INK)
            output_top=output_bottom-.026;bus_top=bus_bottom
        called=s.loc[mode,'called']/s.loc[mode,'grid'];ax.text(.5,.135,'结算额度的分拆（不属于物理流入）',ha='center',fontsize=9.5,color=GRAY)
        ax.add_patch(Rectangle((.12,.075),.76*called,.035,facecolor=BLUE,lw=0))
        ax.add_patch(Rectangle((.12+.76*called,.075),.76*(1-called),.035,facecolor=LILAC,edgecolor=GRAY,lw=.4,hatch='///'))
        ax.text(.12,.042,f'调用 {called:.1%}',ha='left',fontsize=9,color=BLUE)
        ax.text(.88,.042,f'未调用 {1-called:.1%}\n{s.loc[mode,"unused"]/1e6:.3f} GWh',ha='right',va='top',fontsize=9,color=GRAY)
    save(fig,'fig7_4_energy_flow_and_entitlement','图7-4 真实能量流与购电额度的调用分拆',
         '全年正式334日累计AC侧电量，1GWh=10^6kWh。两面板带宽统一按绝对电量绘制，输入=PV+电网调用+紧急+放电，输出=负荷+充电+实际弃电，逐日逐槽亦满足平衡。所有流带仅连接公共能量母线，不假定某一来源供给某一特定去向。下方条形各以该策略结算grid为100%，独立展示called与unused；unused没有进入物理母线，也不与spill合并。充放电为AC侧真实计划量，SOC及损耗另按0.9效率核算。',
         ['energy_flow.csv','strategy_summary.csv'])


def panorama():
    a=read('riskday_4-2.csv');b=read('riskday_4-3.csv');ea=read('riskday_soc_4-2.csv');eb=read('riskday_soc_4-3.csv');x=b.hour_right.to_numpy();dt=1/6
    fig,axes=plt.subplots(4,1,figsize=(10.2,9.3),sharex=True,layout='constrained')
    ax=axes[0];ax.fill_between(x,0,b.price,color=ICE,alpha=.25);ax.plot(x,b.price,color=DARK,lw=1.9,label='实际电价')
    ax.plot(x,b.price_forecast,color=BLUE,ls='--',lw=1.35,label='00:00冻结预测');ax.set_ylabel('电价 / (元/kWh)');ax.set_ylim(bottom=0)
    title(ax,'(a) 7月1日：实际电价与冻结预测',pad=28);ax.legend(loc='lower left',bbox_to_anchor=(0,1.01),ncol=2,fontsize=9)
    ax=axes[1];ax.fill_between(x,0,b.called,step='pre',color=BLUE,alpha=.25,label='实际调用 x')
    ax.fill_between(x,b.called,b.grid,step='pre',color=LILAC,alpha=.75,label='未调用 u')
    ax.step(x,b.grid,where='pre',color=DARK,lw=1.65,label='最终结算额度 G');ax.step(x,b.g0,where='pre',color=PERI,ls='--',lw=1.25,label='00:00基准 $g^0$')
    ax.bar(x-dt/2,b.emergency,width=dt*.9,color=APRICOT,label='紧急 q',lw=0,zorder=4);ax.set_ylabel('4-3电量 / kWh');ax.set_ylim(bottom=0)
    title(ax,'(b) 调用、未用额度与紧急缺口',pad=28);ax.legend(loc='lower left',bbox_to_anchor=(0,1.01),ncol=5,fontsize=8.7,columnspacing=.9)
    ax=axes[2];ax.plot(x,a.charge-a.discharge,color=PERI,ls='--',lw=1.5,label='4-2 净充放电')
    ax.plot(x,b.charge-b.discharge,color=DARK,lw=1.7,label='4-3 净充放电');ax.fill_between(x,0,b.charge-b.discharge,color=BLUE,alpha=.10)
    ax.axhline(0,color=GRAY,lw=.65);ax.set_ylim(-950,950);ax.set_yticks([-800,0,800]);ax.set_ylabel('净动作 / kWh');title(ax,'(c) 节点预提交的储能动作',pad=28)
    ax.legend(loc='lower left',bbox_to_anchor=(0,1.01),ncol=2,fontsize=9)
    ax=axes[3];ax.plot(ea.hour,ea.soc_kwh,color=PERI,ls='--',lw=1.6,label='4-2 SOC');ax.plot(eb.hour,eb.soc_kwh,color=DARK,lw=1.9,label='4-3 SOC')
    ax.fill_between(eb.hour,1200,eb.soc_kwh,color=ICE,alpha=.2)
    for level in [1200,10800]:ax.axhline(level,color=GRAY,ls=':',lw=.8)
    ax.set_ylim(450,11600);ax.set_yticks([1200,6000,10800]);ax.set_ylabel('SOC / kWh');title(ax,'(d) 独立连续库存链的真实SOC',pad=28)
    ax.legend(loc='lower left',bbox_to_anchor=(0,1.01),ncol=2,fontsize=9)
    for ax in axes:timeaxis(ax);nodes(ax);clean(ax)
    axes[-1].set_xlabel('时刻 / h')
    save(fig,'fig7_5_high_risk_panorama','图7-5 高联合风险日的价—量—库存运行全景',
         f'2025-07-01为之前Q4敏感性方案预先选定的高联合风险日。00点价格预测全天不更新。4-3面板实际调用/unused堆叠正好等于最终grid；紧急量单独按真实值展示。4-2与4-3日初SOC分别{a.initial_soc.iloc[0]:.3f}/{b.initial_soc.iloc[0]:.3f}kWh，来自各自前日，不能当作相同初态单日受控实验。两策略当日紧急量分别{a.emergency.sum():.3f}/{b.emergency.sum():.3f}kWh。g/c/r在承诺块内预先确定，储能动作不按事后场景重选；两侧效率均0.9。',
         ['riskday_4-2.csv','riskday_4-3.csv','riskday_soc_4-2.csv','riskday_soc_4-3.csv'])


def sensitivity():
    f=read('local_sensitivity.csv');f=f[f.parameter=='rho'];fig,axes=plt.subplots(1,2,figsize=(10,5.1));fig.subplots_adjust(left=.08,right=.98,bottom=.17,top=.76,wspace=.25)
    colors=[BLUE,DARK,PERI,'#9380BA'];linestyles=['-','--','-.',':'];xlim=max(abs(f.delta_cost_pct).max(),1)*1.25;ylim=max(abs(f.delta_emergency_kwh).max(),1)*1.24
    for ax,mode in zip(axes,['4-2','4-3']):
        group=f[f['mode']==mode]
        for i,(date,g) in enumerate(group.groupby('date',sort=True)):
            g=g.sort_values('setting');color=colors[i]
            ax.plot(g.delta_cost_pct,g.delta_emergency_kwh,color=color,ls=linestyles[i],lw=1.65,label=date[5:]+' '+str(g.role.iloc[0]))
            for row in g.itertuples():
                marker={.75:'v',1.0:'o',1.25:'^'}[row.setting]
                ax.plot(row.delta_cost_pct,row.delta_emergency_kwh,marker=marker,ms=7,color=color,mfc='white' if row.setting==1 else color,mew=1)
        ax.axhline(0,color=GRAY,lw=.7);ax.axvline(0,color=GRAY,lw=.7);ax.set_xlim(-xlim,xlim);ax.set_ylim(-ylim,ylim);clean(ax)
        title(ax,mode+'  '+('4个代表日' if mode=='4-2' else '2个代表日'));ax.set_xlabel('相对同日基准成本变化 / %');ax.set_ylabel('紧急电量变化 / kWh')
        ax.legend(loc='lower center',bbox_to_anchor=(.5,1.15),ncol=2,fontsize=8.5,columnspacing=1)
    fig.text(.5,.055,'▼ 0.75ρ*     ○ 1.00ρ*（各日基准在原点）     ▲ 1.25ρ*     ·     仅连接三个实测参数点',ha='center',fontsize=10,color=GRAY)
    save(fig,'fig7_6_radius_cost_risk_paths','图7-6 鲁棒半径扰动的成本—紧急风险轨迹',
         '复用已完成敏感性实验：4-2四代表日、4-3两代表日。只绘ρ=0.75/1/1.25倍基准的18条含基准记录；共同横纵轴尺度，纵轴为紧急量绝对变化，避免零或很小分母夸大百分比。三角形分别标弱/强半径，空心圆为同日基准，线只是离散点的辅助连接，不是已计算连续前沿。全部新增节点Optimal；不能从局部日推出全年参数稳健，终端库存不同须结合原表解释。',
         ['local_sensitivity.csv'])


def main():
    global OUT,DATA
    parser=argparse.ArgumentParser();parser.add_argument('--data-dir',type=Path,default=DATA);parser.add_argument('--output-dir',type=Path,default=OUT)
    args=parser.parse_args();DATA=args.data_dir.resolve();OUT=args.output_dir.resolve();OUT.mkdir(parents=True,exist_ok=True);fonts()
    with plt.rc_context(STYLE):
        for fn in [mechanism,price_clock,cost_bridge,flow_diagram,panorama,sensitivity]:fn()
    (OUT/'manifest.json').write_text(json.dumps(MANIFEST,ensure_ascii=False,indent=2),encoding='utf-8')
    (OUT/'captions.md').write_text('# 问题四科研图图注\n\n'+'\n\n'.join('## '+r['title']+'\n\n'+r['caption'] for r in MANIFEST)+'\n',encoding='utf-8')
    cards=''.join(f'<article><h2>{html.escape(r["title"])}</h2><a href="{r["png"]}"><img src="{r["png"]}" alt="{html.escape(r["title"])}"></a><p>{html.escape(r["caption"])}</p><a href="{r["svg"]}">SVG矢量图</a></article>' for r in MANIFEST)
    page='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>问题四 · 蓝莲花科研图</title><style>body{margin:0;background:linear-gradient(135deg,#fffef0,#edf3ff 45%,#ece8f7);color:#002254;font:16px/1.65 -apple-system,"Songti SC",serif}main{max-width:1140px;margin:auto;padding:28px 20px}article{background:white;padding:25px;margin:26px 0;border-radius:14px}img{width:100%;height:auto}h1{font-size:28px}h2{font-size:21px}p{font-size:14px;color:#64748b}a{color:#4b69ef}</style><main><h1>问题四 · 蓝莲花与月白深蓝</h1><p>六张科研图 · TeX Fandol宋体 / Latin Modern · 400dpi PNG / SVG · 334日正式结果</p>'''+cards+'</main></html>'
    (OUT/'index.html').write_text(page,encoding='utf-8')


if __name__=='__main__':main()
