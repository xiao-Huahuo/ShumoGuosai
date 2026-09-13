"""十二张高密度补充图：无区域边框/阴影、纯色曲线和TeX中文。"""
from pathlib import Path
import argparse,json,warnings
import numpy as np
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap,Normalize
from matplotlib.text import Text
from matplotlib.patches import Rectangle
from .q4_paper_final import fonts,STYLE,plt,INK,DARK,BLUE,PERI,ICE,LILAC,APRICOT,GRAY,SEQ
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'outputs/processed/figures/project_expansion_20260913';DATA=OUT/'data'
COLORS={'Q2':DARK,'Q3':BLUE,'Q4-2':PERI,'Q4-3':'#8472B8'}
DIV=LinearSegmentedColormap.from_list('signed_flat',[DARK,ICE,'#FBFCFF','#FFE8CA',APRICOT])
MANIFEST=[]


def read(name):return pd.read_csv(DATA/name,float_precision='round_trip')
def title(ax,s,pad=10):ax.set_title(s,loc='left',pad=pad)
def clean(ax):ax.grid(True,axis='y');ax.grid(False,axis='x')
def timeaxis(ax):ax.set_xlim(0,24);ax.set_xticks([0,6,12,18,24]);ax.set_xlabel('时刻 / h')
def noframe(ax):
    ax.grid(False)
    for spine in ax.spines.values():spine.set_visible(False)


def save(fig,num,name,caption,data):
    for t in fig.findobj(Text):
        s=t.get_text()
        if '$' in s and any('\u4e00'<=c<='\u9fff' for c in s):t.set_fontfamily('FandolSong')
    with warnings.catch_warnings():
        warnings.filterwarnings('error',message='Glyph .* missing from font')
        fig.canvas.draw()
        for suffix in ['png','svg']:fig.savefig(OUT/f'S{num:02}_{name}.{suffix}',dpi=400,facecolor='white',transparent=False)
    status=json.loads((OUT/'status.json').read_text(encoding='utf-8'));item=status['items'][num-1]
    item.update({'png':f'S{num:02}_{name}.png','svg':f'S{num:02}_{name}.svg','status':'已生成，待最终验收'})
    status['stage']=f'已成图 {len(MANIFEST)+1}/12 · 正在继续绘制与检查'
    MANIFEST.append({'question':'cross','name':f'S{num:02}_{name}','title':f'补充图S{num:02} '+item['title'],'caption':caption,'data':data,
                     'png':item['png'],'svg':item['svg'],'width_inches':fig.get_figwidth(),'height_inches':fig.get_figheight(),'dpi':400,
                     'font':'FandolSong / Latin Modern Roman / Computer Modern','script':'src/plots/project_expansion.py','necessity':'全项目补充图，按正文论证需要选用'})
    temp=OUT/'status.pending';temp.write_text(json.dumps(status,ensure_ascii=False,indent=2),encoding='utf-8');temp.replace(OUT/'status.json')
    (OUT/'manifest.json').write_text(json.dumps(MANIFEST,ensure_ascii=False,indent=2),encoding='utf-8')
    plt.close(fig);print(f'S{num:02} '+name,flush=True)


def overview():
    f=read('information_boundaries.csv');fig,(ax,bt)=plt.subplots(2,1,figsize=(12.1,7.7),gridspec_kw={'height_ratios':[1.65,1]},layout='constrained');ax.axis('off')
    tab=ax.table(cellText=f.values,colLabels=f.columns,cellLoc='center',bbox=(0,0,1,.93),colWidths=[.12]+[.176]*5)
    tab.auto_set_font_size(False);tab.set_fontsize(10.2)
    for (i,j),cell in tab.get_celld().items():
        cell.set_edgecolor('none');cell.set_linewidth(0)
        cell.set_facecolor(ICE if i==0 else '#ECF0FA' if j==0 else '#F6F8FC' if i%2 else '#FFFFFF')
        cell.get_text().set_color(INK)
    title(ax,'(a) 同一物理系统中的信息边界与决策方式')
    labels=['问题一','问题二','问题三','问题4-2','问题4-3'];H=[24,72,24,48,24];B=[24,24,6,24,6]
    for i,(h,b) in enumerate(zip(H,B)):
        bt.barh(i,h,color=ICE,height=.54,edgecolor='none',lw=0)
        bt.barh(i,b,color=DARK if i%2==0 else BLUE,height=.54,edgecolor='none',lw=0)
        bt.text(b/2,i,f'执行{b}h',ha='center',va='center',fontsize=9,color='white')
        if h>b:bt.text(b+(h-b)/2,i,'前瞻代理',ha='center',va='center',fontsize=9,color=INK)
        if i==1:bt.plot([48,48],[i-.34,i+.34],color=GRAY,ls=':',lw=1);bt.text(74,i,'按日选择48/72 h',va='center',fontsize=9,color=GRAY)
    bt.set_yticks(range(5),labels);bt.invert_yaxis();bt.set_xlim(0,95);bt.set_xticks([0,6,24,48,72]);bt.set_xlabel('单次优化窗口中的相对时间 / h');noframe(bt)
    title(bt,'(b) 优化前瞻与实际执行长度分开理解')
    save(fig,1,'information_boundaries','五列分开描述不同题目的信息、策略和风险表示，不能用不同评价范围和电价口径的总费用直接排名。问题二为当前正式实际48/72h选择，局部K=1实验不混入此表；问题三与4-3全天四节点，此处时间带仅表示一次节点优化。问题三正式轨迹含限时可行节点。', ['information_boundaries.csv'])


def worst_distribution():
    f=read('dro_example.csv').sort_values('cost');y=np.arange(len(f));fig,axes=plt.subplots(1,3,figsize=(11.3,6.5),sharey=True,layout='constrained')
    ax=axes[0];ax.barh(y,f.cost/10000,color=ICE,edgecolor='none');ax.set_yticks(y,[f'S{n:02}' for n in f.scenario]);ax.invert_yaxis();ax.set_xlabel('同一策略的场景费用 / 万元');title(ax,'(a) 按损失排序的20个场景');clean(ax)
    ax=axes[1]
    for yy,p,w in zip(y,f.empirical_p,f.worst_p):ax.plot([p,w],[yy,yy],color=PERI,lw=1.6)
    ax.scatter(f.empirical_p,y,color=PERI,s=32,marker='o',edgecolors='none',label='经验概率')
    ax.scatter(f.worst_p,y,color=DARK,s=30,marker='D',edgecolors='none',label='最坏概率')
    ax.set_xlim(-.009,max(f.empirical_p.max(),f.worst_p.max())*1.23);ax.set_xlabel('概率');title(ax,'(b) 概率重分配');ax.legend(loc='lower right',fontsize=9);clean(ax)
    ax=axes[2];ax.barh(y,f.delta_contribution/1000,color=[BLUE if v>=0 else LILAC for v in f.delta_contribution],edgecolor='none');ax.axvline(0,color=GRAY,lw=.8)
    ax.set_xlabel('概率变化带来的费用贡献 / 千元');title(ax,'(c) 贡献可正可负，合计为溢价');clean(ax)
    ep=np.dot(f.empirical_p,f.cost);wp=np.dot(f.worst_p,f.cost)
    fig.suptitle(f'Q4-3 · 2025-07-01 00:00    经验期望 {ep:,.2f} 元 → 最坏期望 {wp:,.2f} 元',fontsize=12,color=INK)
    save(fig,2,'worst_distribution','使用预先指定高联合风险日7月1日0点原审计的20个场景，S编号为原审计顺序，纵向只按同一固定策略的场景费用排序。贡献=(最坏概率−经验概率)×场景费用，各贡献之和等于最坏期望相对经验期望的风险溢价。连线连接同一个场景的概率值，不表示已知的场景间运输路径；风险溢价不是实际费用节约。',['dro_example.csv'])


def dro_annual():
    f=read('dro_nodes.csv');f=f[f.model=='Q4-3'];fig,axes=plt.subplots(1,3,figsize=(10.3,5.8),sharey=True,layout='constrained')
    dates=sorted(f.date.unique());positions=[0,59,120,181,242,303,333]
    for ax,key,label in zip(axes,['rho','ESS','premium_pct'],['(a) 标定Wasserstein半径','(b) 条件历史有效样本量','(c) 最坏期望风险溢价 / %']):
        v=f.pivot(index='date',columns='hour',values=key).to_numpy();im=ax.imshow(v,aspect='auto',cmap=SEQ,interpolation='nearest',origin='upper',extent=(-.5,3.5,334,0),vmin=0)
        ax.set_xticks(range(4),['00','06','12','18']);ax.set_yticks(np.array(positions)+.5,[dates[i][5:] for i in positions]);ax.set_xlabel('节点 / h');noframe(ax);title(ax,label)
        fig.colorbar(im,ax=ax,pad=.03,shrink=.86,label={'rho':'距离单位','ESS':'等效历史轨迹数','premium_pct':'%'}[key])
    axes[0].set_ylabel('2025年正式日期')
    save(fig,3,'dro_annual_diagnostics','Q4-3正式334日×4节点的原始半径、ESS和风险溢价，逐节点显示，不按月份平滑。ESS由历史条件概率计算；风险溢价=100×(最坏期望/经验期望−1)，分母为同一策略的场景经验期望，非真实日费；零分母若出现则留空。三个面板色标单位不同。',['dro_nodes.csv'])


def storage_pair(models,num):
    den=read('soc_density.csv');pr=read('action_profiles.csv');daily=read('daily_states.csv');fig,axes=plt.subplots(2,3,figsize=(11.2,7),layout='constrained')
    for i,model in enumerate(models):
        ax=axes[i,0];g=den[den.model==model];v=g.pivot(index='soc_low',columns='slot0',values='probability').to_numpy()*100
        im=ax.imshow(v,aspect='auto',origin='lower',extent=(0,24,1.2,10.8),cmap=SEQ,vmin=0,vmax=100,interpolation='nearest')
        ax.set_yticks([1.2,6,10.8]);ax.set_ylabel('SOC / MWh');timeaxis(ax);noframe(ax);title(ax,f'({chr(97+3*i)}) {model} 时刻—SOC占用')
        fig.colorbar(im,ax=ax,pad=.02,shrink=.87,label='该时刻日期占比 / %')
        ax=axes[i,1];g=pr[pr.model==model]
        ax.stackplot(g.hour,g.charge_fraction*100,g.discharge_fraction*100,g.idle_fraction*100,colors=[PERI,ICE,'#F0EDF7'],edgecolor='none',linewidth=0,labels=['充电','放电','闲置'])
        ax.set_ylim(0,100);ax.set_ylabel('动作日期比例 / %');timeaxis(ax);clean(ax);title(ax,f'({chr(98+3*i)}) {model} 日内动作结构');ax.legend(loc='lower left',bbox_to_anchor=(0,1.0),ncol=3,fontsize=8.5);ax.set_title(f'({chr(98+3*i)}) {model} 日内动作结构',loc='left',pad=27)
        ax=axes[i,2];v=np.sort(daily[daily.model==model].end_soc.to_numpy()/1000);p=np.arange(1,len(v)+1)/len(v)
        ax.step(v,p,where='post',color=COLORS[model],lw=1.8);ax.set_xlim(1.0,11);ax.set_ylim(0,1.02);ax.set_xlabel('日末SOC / MWh');ax.set_ylabel('累计日期比例');clean(ax)
        title(ax,f'({chr(99+3*i)}) {model} 日末库存分布');ax.text(.98,.10,f'n=334日\n中位数 {np.median(v):.3f} MWh',transform=ax.transAxes,ha='right',fontsize=9,color=GRAY)
    save(fig,num,'storage_'+('_'.join(models)),'每个时刻均有334个正式日，SOC以400kWh分箱，每列概率合计100%；只有浮点容差内的越界值归入边界箱，原始轨迹完整保存。充/放电状态以1e-5kWh阈值识别，余者为闲置，类别互斥。各图共用0–100%色标和1200–10800kWh范围；末库存ECDF保留全部334日。这是运行方式描述，各模型预测来源、信息和策略不同，不能据占用形态直接宣称经济优劣。',['soc_density.csv','action_profiles.csv','daily_states.csv'])


def reserve():
    f=read('reserve_day.csv');x=f.hour.to_numpy();fig,axes=plt.subplots(3,1,figsize=(10.1,7.5),sharex=True,layout='constrained')
    ax=axes[0];ax.plot(x,f.net_kwh,color=DARK,lw=1.7,label='实际净负荷');ax.plot(x,f.forecast_net_kwh,color=PERI,ls='--',lw=1.5,label='点预测净负荷');ax.step(x,f.grid,where='pre',color=BLUE,ls=':',lw=1.5,label='冻结购电 G')
    ax.axhline(0,color=GRAY,lw=.65);ax.set_ylabel('电量 / (kWh/10 min)');title(ax,'(a) 预测误差与冻结购电',pad=29);ax.legend(loc='lower left',bbox_to_anchor=(0,1.01),ncol=3,fontsize=9)
    ax=axes[1];soc=np.r_[f.initial_soc.iloc[0],f.soc];xx=np.arange(145)/6
    ax.plot(xx,soc,color=DARK,lw=1.8,label='真实SOC');ax.step(xx,np.r_[f.reserve_threshold,f.reserve_threshold.iloc[-1]],where='post',color=BLUE,ls='--',lw=1.45,label=r'$E_{min}+R_t$ 放电保留阈值')
    ax.fill_between(xx,1200,np.r_[f.reserve_threshold,f.reserve_threshold.iloc[-1]],step='post',color=ICE,alpha=.4,lw=0);ax.axhline(1200,color=GRAY,lw=.65,ls=':');ax.set_ylim(450,11400);ax.set_ylabel('库存 / kWh');title(ax,'(b) 历史信息预先确定的安全裕度',pad=29);ax.legend(loc='lower left',bbox_to_anchor=(0,1.01),ncol=2,fontsize=9)
    ax=axes[2];ax.bar(x-1/12,f.discharge,width=.15,color=BLUE,label='实际放电',edgecolor='none');ax.bar(x-1/12,f.emergency,bottom=f.discharge,width=.15,color=APRICOT,label='紧急补购',edgecolor='none')
    ax.set_ylabel('缺口电量 / kWh');ax.set_ylim(bottom=0);title(ax,'(c) 储能后缺口的实际去向',pad=29);ax.legend(loc='lower left',bbox_to_anchor=(0,1.01),ncol=2,fontsize=9)
    for ax in axes:timeaxis(ax);clean(ax)
    for ax in axes[:-1]:ax.set_xlabel('')
    fig.suptitle(f'问题二 · {f.date.iloc[0]} · 正式期紧急量最大日，合计 {f.emergency.sum():,.1f} kWh',fontsize=12)
    save(fig,6,'dynamic_reserve_and_risk','按正式334日紧急电量最大值客观选择2025-06-01。放电可用能量=.9×max(Eprev−1200−R,0)，实际放电还受冻结上限和当期缺口限制；图中阈值不是额外SOC硬约束，不能把SOC低于当前变动阈值误判为物理越界。下方放电与紧急堆叠合计等于正缺口。全部来自同一正式轨迹，不作无裕度反事实收益解释。',['reserve_day.csv'])


def concentration():
    f=read('risk_concentration.csv');shares=read('risk_shares.csv');fig,axes=plt.subplots(2,2,figsize=(10,6.9),layout='constrained')
    for j,models in enumerate([['Q2','Q3'],['Q4-2','Q4-3']]):
        ax=axes[0,j]
        for model,ls in zip(models,['-','--']):
            g=f[f.model==model];ax.plot(g.day_fraction*100,g.cumulative_cost_fraction*100,color=COLORS[model],ls=ls,lw=1.8,label=model)
        ax.plot([0,100],[0,100],color=GRAY,ls=':',lw=.8);ax.set_xlim(0,100);ax.set_ylim(0,102);ax.set_xlabel('从风险高到低纳入的日期比例 / %');ax.set_ylabel('累计紧急费用占比 / %');title(ax,f'({chr(97+j)}) 各策略内部的风险集中程度');clean(ax);ax.legend(loc='lower right')
        ax=axes[1,j];x=np.arange(3)
        for i,model in enumerate(models):
            g=shares[shares.model==model].sort_values('nominal_fraction');xx=x+(i-.5)*.32
            ax.bar(xx,g.share*100,width=.31,color=ICE if i==0 else LILAC,edgecolor='none',label=model)
            for p,v in zip(xx,g.share*100):ax.text(p,v+1,f'{v:.1f}',ha='center',fontsize=9,color=COLORS[model])
        ax.set_ylim(0,100);ax.set_xticks(x,['前5%\n17日','前10%\n34日','前20%\n67日']);ax.set_ylabel('紧急费用占比 / %');title(ax,f'({chr(99+j)}) 高风险日期的费用贡献');ax.legend(loc='upper left',ncol=2);clean(ax)
    save(fig,7,'tail_risk_concentration','对每个模型分别按334日紧急费用从高到低排序，累积归一化分母为该模型自己的全年紧急费用；不是把不同价格口径的绝对费用直接比较。5/10/20%采用ceil，实际纳入17/34/67日，各模型高风险日期集合可不同。所有日期包含在累计曲线中。',['risk_concentration.csv','risk_shares.csv'])


def event_geometry():
    f=read('emergency_events.csv');fig,axes=plt.subplots(2,2,figsize=(10.3,7.2),sharex=True,sharey=True,layout='constrained');norm=Normalize(f.weighted_price.min(),f.weighted_price.max())
    for ax,model,label in zip(axes.ravel(),COLORS,['a','b','c','d']):
        g=f[f.model==model];im=ax.scatter(g.duration_h,g.energy_kwh,c=g.weighted_price,cmap=SEQ,norm=norm,s=12,alpha=.65,edgecolors='none')
        ax.set_xscale('log');ax.set_yscale('log');ax.set_xlabel('连续事件持续时间 / h（对数）');ax.set_ylabel('事件紧急电量 / kWh（对数）');clean(ax)
        title(ax,f'({label}) {model} · {len(g):,}次事件');ax.text(.98,.04,f'最长 {g.duration_h.max():.2f} h\n最大 {g.energy_kwh.max():,.1f} kWh',transform=ax.transAxes,ha='right',fontsize=9,color=GRAY)
    fig.colorbar(im,ax=axes.ravel().tolist(),pad=.02,shrink=.8,label='紧急电量加权实价 / (元/kWh)')
    save(fig,8,'emergency_event_geometry','统一以单时段紧急量>1e-5kWh定义事件，连续144以外的跨午夜事件不人为拆开；因此计数可与原按日重置的事件表不同。持续时间=时段数/6h，总量为逐槽紧急量之和，颜色=Σ(pq)/Σq。全部事件为正值并保留，双对数仅用于同时观察大小事件，没有删除极端值。各模型采用共同色标。',['emergency_events.csv'])


def calibration():
    f=read('interval_monthly.csv');fig,axes=plt.subplots(2,2,figsize=(10.5,7.1),layout='constrained');bound=max(abs(f.bias_pp).max(),1)
    for ax,nom,label in zip(axes[0],[.8,.9],['a','b']):
        g=f[np.isclose(f.nominal,nom)];v=g.pivot(index='horizon',columns='month',values='bias_pp').reindex(index=[0,1,2],columns=range(2,13)).to_numpy()
        cm=DIV.copy();cm.set_bad('#EEF0F3');im=ax.imshow(v,cmap=cm,vmin=-bound,vmax=bound,aspect='auto',interpolation='nearest')
        for y in range(3):
            for x in range(11):ax.text(x,y,'—' if np.isnan(v[y,x]) else f'{v[y,x]:+.0f}',ha='center',va='center',fontsize=8.5,color='white' if np.isfinite(v[y,x]) and v[y,x]<-bound*.65 else INK)
        ax.set_xticks(range(11),range(2,13));ax.set_yticks(range(3),['h=0','h=1','h=2']);ax.set_xlabel('预测起点月份');noframe(ax);title(ax,f'({label}) {nom:.0%}区间：覆盖率偏差 / 百分点')
        fig.colorbar(im,ax=ax,pad=.02,shrink=.8)
    ax=axes[1,0]
    for h,c in zip([0,1,2],[DARK,BLUE,PERI]):
        for nom,ls in [(.8,'-'),(.9,'--')]:
            g=f[(f.horizon==h)&np.isclose(f.nominal,nom)].sort_values('month')
            ax.plot(g.month,g.mean_width_kwh,color=c,ls=ls,marker='o' if nom==.8 else 's',ms=3,lw=1.4,label=f'h={h} · {nom:.0%}')
    ax.set_xticks(range(2,13));ax.set_xlabel('预测起点月份');ax.set_ylabel('平均区间宽度 / (kWh/10 min)');title(ax,'(c) 不能只看覆盖率，还需看区间宽度');ax.legend(loc='upper left',ncol=3,fontsize=8);clean(ax)
    ax=axes[1,1]
    for h,c in zip([0,1,2],[DARK,BLUE,PERI]):
        g=f[(f.horizon==h)&np.isclose(f.nominal,.8)].set_index('month').reindex(range(2,13))
        ax.bar(np.arange(2,13)+(h-1)*.24,g.n.fillna(0)/144,width=.23,color=c,alpha=.65,edgecolor='none',label=f'h={h}')
    ax.set_xticks(range(2,13));ax.set_xlabel('预测起点月份');ax.set_ylabel('实际有效起点数 / 日');ax.set_ylim(0,38);title(ax,'(d) 每格统计支持与缺失来源');ax.legend(loc='upper left',ncol=3);clean(ax)
    save(fig,9,'seasonal_interval_calibration','原正式审计的selected_origin_indices与weights直接重建场景分位：真实历史误差叠加当前冻结预测，对L/PV分别截非负后算净负荷；使用原离散左分位。1942条origin×h×nominal覆盖计数与正式calibration逐条一致，无重新优化或聚类。月覆盖按覆盖时段数/总时段数加权；宽度为原区间upper−lower均值。无h=2的月份显示缺失，底部支持数为0；不同h可用起点数不同，不能解释成同起点严格配对的跨h比较。',['interval_monthly.csv','interval_origin_stats.csv','original_calibration.csv'])


def resource_gains():
    f=read('device_joint_grid.csv');m=f.pivot(index='e_max_kwh',columns='common_power_kw',values='cost_yuan').sort_index();v=m.to_numpy();ev=m.index.to_numpy()/1000;pv=m.columns.to_numpy()/1000
    gain_e=(v[:-1]-v[1:])/np.diff(ev)[:,None];gain_p=(v[:,:-1]-v[:,1:])/np.diff(pv)[None,:]
    fig,axes=plt.subplots(1,3,figsize=(11.5,5.1),layout='constrained')
    for ax,z,ys,xs,label,unit in [(axes[0],v/10000,ev,pv,'(a) 110个已求解配置','单日费用 / 万元'),(axes[1],gain_e,(ev[:-1]+ev[1:])/2,pv,'(b) 扩充容量的有限步长收益','元/日 / MWh'),(axes[2],gain_p,ev,(pv[:-1]+pv[1:])/2,'(c) 扩充功率的有限步长收益','元/日 / MW')]:
        im=ax.imshow(z,origin='lower',aspect='auto',cmap=SEQ,interpolation='nearest');ix=np.unique(np.linspace(0,len(xs)-1,5).astype(int));iy=np.unique(np.linspace(0,len(ys)-1,6).astype(int))
        ax.set_xticks(ix,[f'{xs[i]:g}' for i in ix]);ax.set_yticks(iy,[f'{ys[i]:g}' for i in iy]);ax.set_xlabel('共同充放电功率 / MW');ax.set_ylabel('储电上限 / MWh' if ax is not axes[1] else '容量增量区间中点 / MWh');noframe(ax);title(ax,label)
        fig.colorbar(im,ax=ax,pad=.02,shrink=.86,label=unit)
    save(fig,10,'capacity_power_marginal_gains','仅使用Q1已完成的11容量×10功率共110个原MILP结果，不做插值。容量收益=(当前费−下一容量费)/增加MWh，步长2.4MWh；功率收益按相邻1MW差计算，第三面板横坐标是功率增量区间中点。有限步长差不是连续影子导数；超过原额定上限的配置为数学约束放宽，未计投资，不是设备采购ROI。费用均为原单个典型日。',['device_joint_grid.csv','device_one_dimensional.csv'])


def marginal_validation():
    f=read('milp_rhs_checks.csv');m=read('fixed_mode_marginals.csv');g=f[f.kind=='internal_injection'];fig,axes=plt.subplots(2,2,figsize=(10.6,7),layout='constrained')
    ax=axes[0,0]
    for key,c,ls,label in [('fixed_shadow_dJ_db',DARK,'-','固定模式影子斜率'),('minus_slope',PERI,'--','原MILP负向扰动'),('plus_slope',BLUE,':','原MILP正向扰动')]:ax.plot(g.t/6,g[key],color=c,ls=ls,lw=1.6,label=label)
    ax.set_ylabel('内部注入的费用斜率 / (元/kWh)');timeaxis(ax);title(ax,'(a) 局部边际值随时刻变化');ax.legend(loc='lower right',fontsize=8);clean(ax)
    ax=axes[0,1];keys=['E_min_active','E_max_active','charge_max_active','discharge_max_active'];v=m[keys].to_numpy().T
    ax.imshow(v,aspect='auto',cmap=LinearSegmentedColormap.from_list('binding',['#F2F5FA',BLUE]),vmin=0,vmax=1,interpolation='nearest',extent=(0,24,3.5,-.5))
    ax.set_yticks(range(4),['SOC下界','SOC上界','充电上限','放电上限']);timeaxis(ax);noframe(ax);title(ax,'(b) 同一最优解的约束活跃时段')
    ax=axes[1,0]
    for kind,c in [('bus_demand',BLUE),('internal_injection',PERI)]:
        g=f[f.kind==kind]
        for key,marker in [('minus_slope','o'),('plus_slope','^')]:ax.scatter(g.fixed_shadow_dJ_db,g[key],s=18,color=c,marker=marker,alpha=.5,edgecolors='none')
    lo=min(f.fixed_shadow_dJ_db.min(),f.minus_slope.min(),f.plus_slope.min());hi=max(f.fixed_shadow_dJ_db.max(),f.minus_slope.max(),f.plus_slope.max());ax.plot([lo,hi],[lo,hi],color=GRAY,ls='--',lw=.9)
    ax.set_xlabel('固定模式斜率 / (元/kWh)');ax.set_ylabel('原MILP有限差分 / (元/kWh)');title(ax,'(c) 两类扰动的双侧核验（576个值）');clean(ax)
    ax=axes[1,1];group=f.groupby('kind').fixed_shadow_matches_milp_both_sides.agg(['sum','count']);order=['bus_demand','internal_injection'];ratios=group.loc[order,'sum']/group.loc[order,'count']
    ax.bar([0,1],ratios*100,color=[ICE,LILAC],edgecolor='none',width=.55)
    for i,k in enumerate(order):ax.text(i,ratios.iloc[i]*100+2,f'{int(group.loc[k,"sum"])}/{int(group.loc[k,"count"])}',ha='center',fontsize=11,color=DARK)
    ax.set_xticks([0,1],['母线需求扰动','内部注入扰动']);ax.set_ylim(0,115);ax.set_ylabel('双侧与固定模式吻合比例 / %');title(ax,'(d) 局部适用边界：步长0.01 kWh');clean(ax)
    save(fig,11,'marginal_value_validation','Q1已有288条(kind,t)核查，每条正负两侧各0.01kWh，图中576个实际差分值；不是新求解。母线需求144/144双侧吻合，内部注入119/144吻合，反映模式切换处固定模式边际值不能随意推广。负的内部注入费用斜率意味着增加注入降低费用，与正经济价值符号相反。上限活跃状态直接取原CSV；蓝块仅标约束活跃，不表示新实验。',['milp_rhs_checks.csv','fixed_mode_marginals.csv'])


def inventory_cost():
    daily=read('daily_states.csv');a=daily[daily.model=='Q4-2'].set_index('date');b=daily[daily.model=='Q4-3'].set_index('date');f=read('q3_terminal_cases.csv')
    fig,axes=plt.subplots(1,2,figsize=(10.4,5.3),layout='constrained');ax=axes[0];x=(b.end_soc-a.end_soc)/1000;y=(b.total_cost-a.total_cost)/1000
    ax.scatter(x,y,color=BLUE,s=19,alpha=.35,edgecolors='none');ax.axhline(0,color=GRAY,lw=.7);ax.axvline(0,color=GRAY,lw=.7)
    ax.set_xlabel('日末库存差：4-3 − 4-2 / MWh');ax.set_ylabel('当日费用差：4-3 − 4-2 / 千元');title(ax,'(a) 两条全年轨迹的334个同日配对');clean(ax)
    ax=axes[1]
    for (date,g),c,ls in zip(f.groupby('date',sort=True),[DARK,BLUE,PERI,'#8C75AD'],['-','--','-.',':']):
        g=g.sort_values('value');base=g[np.isclose(g.value,1)].iloc[0];x=(g.final_soc-base.final_soc)/1000
        ax.plot(x,g.delta_cost_pct,color=c,ls=ls,lw=1.5,label=date[5:])
        for xx,row in zip(x,g.itertuples()):ax.plot(xx,row.delta_cost_pct,marker='o' if row.reliable else 'x',ms=6,color=c,ls='none')
    ax.axhline(0,color=GRAY,lw=.7);ax.axvline(0,color=GRAY,lw=.7);ax.set_xlabel('相对同日基准的日末库存变化 / MWh');ax.set_ylabel('相对同日基准的费用变化 / %');title(ax,r'(b) Q3四代表日：$\lambda_E=0.8/1/1.2$');ax.legend(loc='lower right',ncol=2,fontsize=9);clean(ax)
    save(fig,12,'inventory_cost_coupling','左图为Q4同日真实费用与日末SOC之差，包含连续库存继承及整个策略的其他差异，散点关联不估计库存因果价值。右图是已完成Q3四日λE局部OFAT实验，同日初态固定，每日1.0为自身基准；线只连三个实测点。叉号表示该案例存在未认证节点，圆点为全节点达到3%证书。日末库存明显不同，因此不能单看低当日费用认定跨日经济性更优。',['daily_states.csv','q3_terminal_cases.csv'])


def main():
    global OUT,DATA
    parser=argparse.ArgumentParser();parser.add_argument('--data-dir',type=Path,default=DATA);parser.add_argument('--output-dir',type=Path,default=OUT);args=parser.parse_args();DATA=args.data_dir.resolve();OUT=args.output_dir.resolve();fonts()
    with plt.rc_context({**STYLE,'patch.edgecolor':'none','patch.linewidth':0,'legend.fontsize':9}):
        overview();worst_distribution();dro_annual();storage_pair(['Q2','Q3'],4);storage_pair(['Q4-2','Q4-3'],5);reserve();concentration();event_geometry();calibration();resource_gains();marginal_validation();inventory_cost()
    (OUT/'captions.md').write_text('# 十二张补充图图注\n\n'+'\n\n'.join('## '+r['title']+'\n\n'+r['caption'] for r in MANIFEST)+'\n',encoding='utf-8')
    s=json.loads((OUT/'status.json').read_text(encoding='utf-8'));s['stage']='12/12张已绘制，正在完成数值与视觉验收';(OUT/'status.json').write_text(json.dumps(s,ensure_ascii=False,indent=2),encoding='utf-8')


if __name__=='__main__':main()
