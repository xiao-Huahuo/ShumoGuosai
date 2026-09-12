"""全项目绘图清单：脚本、数据、成图路径和论文必要性集中登记。"""
import csv
import html
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main():
    rows = []
    new = ROOT / 'outputs/processed/figures/q1'
    with (new / 'figure_index.csv').open(encoding='utf-8', newline='') as stream:
        for row in csv.DictReader(stream):
            rows.append({'question':'q1','name':row['figure'],'title':row['title'],'necessity':row['role'],
                         'script':row['script'],'data':';'.join(str((new/p).relative_to(ROOT)) for p in row['data_csv'].split(';')),
                         'png':str((new/(row['figure']+'.png')).relative_to(ROOT)),
                         'svg':str((new/(row['figure']+'.svg')).relative_to(ROOT))})
    for name,title in [('dispatch','原报告输入与运行组合图'),('efficiency','原报告效率图'),
                       ('marginal_analysis','原报告边际分析组合图'),('bottleneck_analysis','原报告局部边界价值图')]:
        rows.append({'question':'q1','name':name,'title':title,'necessity':'历史报告，正文优先使用新图',
                     'script':'src/plots/q1_legacy.py','data':'outputs/q1_current/raw;outputs/q1_current/processed',
                     'png':f'outputs/processed/q1/{name}.png','svg':f'outputs/processed/q1/{name}.svg'})
    import json
    q2 = json.loads((ROOT/'outputs/q2_current/raw/figure_manifest.json').read_text(encoding='utf-8'))
    titles={'timeseries_7d':'连续7天原始功率','timeseries_30d':'连续30天原始功率','annual_heatmaps':'全年日期—时间热力图','monthly_profiles':'12个月平均日曲线','weekday_profiles':'星期平均日曲线','weekday_weekend':'工作日与周末平均日曲线','acf_pacf':'自相关与Burg偏自相关','spectra':'日周周期频谱验证','monthly_stability':'月度周期稳定性','seasonal_moments':'季节处理后的月度均值与波动','daily_peaks':'每日峰值与峰值时刻'}
    for row in q2:
        name=row['name']
        folder=ROOT/'outputs/processed/figures/q2'
        if not (folder/(name+'.png')).exists(): folder=ROOT/'outputs/processed/q2/figures'
        rows.append({'question':'q2','name':name,'title':titles[name],'necessity':'第二问数据诊断，按其章节选用',
                     'script':'src/plots/q2.py','data':';'.join('outputs/processed/q2/'+p for p in row['source_csv']),
                     'png':str((folder/(name+'.png')).relative_to(ROOT)),'svg':str((folder/(name+'.svg')).relative_to(ROOT))})
    for row in rows:
        for field in ['script','data','png','svg']:
            for path in row[field].split(';'):
                if not (ROOT/path).exists(): raise ValueError(f'绘图登记路径缺失：{path}')
    folder=ROOT/'src/plots'
    with (folder/'figure_registry.csv').open('w',encoding='utf-8',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
    output=ROOT/'outputs/processed/figures'; output.mkdir(parents=True,exist_ok=True)
    content='<!doctype html><html lang="zh-CN"><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>项目图集</title>'
    content+='<style>body{font:16px/1.65 -apple-system,BlinkMacSystemFont,"PingFang SC",sans-serif;color:#253d56;background:#f3f6f8;margin:0}main{max-width:1200px;margin:auto;padding:30px 20px}.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(290px,1fr));gap:22px}article{background:white;padding:18px;border-radius:8px}img{width:100%;height:230px;object-fit:contain}a{color:#0072b2}h2{font-size:18px}p{font-size:14px}</style><main><h1>项目图集与绘图脚本</h1><p><a href="q1/index.html">第一问论文图集与必要性说明</a> · <a href="../../../src/plots/README.md">统一绘图说明</a> · <a href="../../../src/plots/figure_registry.csv">全图清单 CSV</a></p><div class="cards">'
    for row in rows:
        link=lambda path:html.escape(os.path.relpath(ROOT/path,output))
        content+=f'<article><p>{html.escape(row["question"].upper()+" · "+row["necessity"])}</p><h2>{html.escape(row["title"])}</h2><a href="{link(row["png"])}"><img src="{link(row["png"])}" alt="{html.escape(row["title"])}"></a><p><a href="{link(row["svg"])}">SVG</a> · <a href="{link(row["script"])}">绘图脚本</a></p></article>'
    (output/'index.html').write_text(content+'</div></main></html>',encoding='utf-8')
    print(f'已登记{len(rows)}组图：src/plots/figure_registry.csv')


if __name__=='__main__':
    main()
