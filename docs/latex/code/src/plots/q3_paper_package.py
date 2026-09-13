"""三核心图、四扩展图及只读数据的独立ZIP交付。"""
from pathlib import Path
import csv
import hashlib
import html
import json
import shutil
import zipfile
from .q3_paper_data import ROOT,OUT,DATA

PACKAGE=ROOT/'outputs/processed/deliverables/问题三科研图_蓝色渐变完整版_20260913'
DOCS=ROOT/'docs/plots/q3_paper_final'


def prepare_package():
    PACKAGE.mkdir(parents=True,exist_ok=True)
    core=json.loads((OUT/'core/manifest.json').read_text(encoding='utf-8'))
    extra={r['name']:r for r in json.loads((OUT/'manifest.json').read_text(encoding='utf-8'))}
    selection=[(r,OUT/'core','核心图',name) for r,name in zip(core,['图6-1_预报误差与更新增益','图6-2_滚动窗口与承诺机制','图6-3_代表日预报购电储能'])]
    for key,name in [('fig6_3_forecast_and_plan_updates','A1_高更新日计划修订'),('fig6_4_pressure_day_dispatch','A2_压力日储能分轴'),('fig6_5_cost_structure','A3_月度费用结构'),('fig6_6_annual_storage_and_revisions','A4_全年储能与购电修订')]:
        selection.append((extra[key],OUT,'扩展备选图',name))
    manifest=[];registry=[]
    for row,folder,group,name in selection:
        target=PACKAGE/group;target.mkdir(exist_ok=True)
        item={**row,'title':row['title'] if group=='核心图' else '备选'+name.replace('_',' ')}
        for suffix in ['png','svg']:
            shutil.copy2(folder/row[suffix],target/f'{name}.{suffix}')
            item[suffix]=f'{group}/{name}.{suffix}'
        manifest.append(item)
        registry.append({**row,'title':item['title'],'png':str((folder/row['png']).relative_to(OUT)),
                         'svg':str((folder/row['svg']).relative_to(OUT))})
    (OUT/'delivery_manifest.json').write_text(json.dumps(registry,ensure_ascii=False,indent=2),encoding='utf-8')
    (PACKAGE/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    shutil.copytree(DATA,PACKAGE/'data',dirs_exist_ok=True)
    for name in ['第三问科研图方案.md','第三问_必须绘制的核心图及绘图细节.md','图后分析与论文插入建议.md','acceptance.md']:
        shutil.copy2(DOCS/name,PACKAGE/name)
    shutil.copy2(OUT/'verification.json',PACKAGE/'verification.json')
    sources=PACKAGE/'src/plots';sources.mkdir(parents=True,exist_ok=True)
    for name in ['common.py','q3_paper_final.py','q3_paper_core.py','q3_paper_data.py','q3_paper_verify.py','q3_paper_package.py']:
        shutil.copy2(ROOT/'src/plots'/name,sources/name)
    for path in [PACKAGE/'src/__init__.py',sources/'__init__.py']:path.write_text('',encoding='utf-8')
    (PACKAGE/'requirements.txt').write_text('numpy==2.3.5\npandas==2.2.3\nmatplotlib==3.10.8\nPillow==12.3.0\nopenpyxl==3.1.5\n',encoding='utf-8')
    (PACKAGE/'captions.md').write_text('# 交付图注\n\n'+'\n\n'.join('## '+r['title']+'\n\n'+r['caption'] for r in manifest)+'\n',encoding='utf-8')
    readme='''# 第三问科研图 ZIP

包含3张正文核心图和4张扩展备选图，每张提供400dpi PNG及SVG。主色为多强度蓝色；核心图按补充文档改为宋体与Times New Roman。

**图6-4（FIV/OUV）经用户明确要求取消。** 当前没有全年配对反事实数据，本包没有用预测误差、调整费用或示意数据替代，也没有为此启动新实验。

## 文件内容

| 路径 | 内容 |
|---|---|
| 核心图/ | 图6-1同目标预报误差增益、图6-2 B/P/C滚动窗口、图6-3同日预报—购电—储能三联图；正文优先使用 |
| 扩展备选图/ | A1高更新日实例、A2压力日分轴、A3月度费用、A4全年热图；可选用，不建议全塞正文 |
| 第三问科研图方案.md | 最终图组方案、客观选日规则、插入位置与统计范围 |
| 第三问_必须绘制的核心图及绘图细节.md | 用户提供的原始清单原样保存；其中图6-4被后续用户回复取消 |
| 图后分析与论文插入建议.md | 每张图的“看到什么—如何解释—支持什么”文字 |
| captions.md | 7张交付图的完整图注 |
| data/forecast_*.csv | 333共同日的31968条小时预报/真值配对与96格MAE/RMSE/Bias |
| data/revision_*.csv | 每节点1998条同目标旧/新配对与统计，18点近零绝对量保留 |
| data/typical_*.csv | 代表日144时段、145点SOC、当块小时预报及四日距离/标准化尺度 |
| data/pressure_*.csv、update_*.csv | 两个扩展实例日的真实运行、原始预报与节点政策 |
| data/formal_dispatch.csv | 正式334日×144段全量实际执行，含SOC、费用、g0与最终grid差值 |
| data/formal_daily.csv、monthly_costs.csv | 日度与月度结算汇总 |
| data/formal_solver_quality.csv | 1336节点求解状态；847认证、489限时可行 |
| data/local_sensitivity.csv | 已完成Q3三因素、四代表日的36条记录，含12条基准；按新清单以表交付，不额外堆敏感性图 |
| data/execution_config.json、provenance.json | 正式模型配置、来源及341项源文件SHA-256 |
| src/plots/ | 绘图、数据准备、核验及打包源码，均UTF-8 |
| requirements.txt | 原绘图环境版本 |
| manifest.json、verification.json、acceptance.md | 图目与文件映射、数值/导出校验、逐条需求验收 |
| index.html | 解压后可直接打开的离线图集 |
| file_manifest.csv | 包内逐文件SHA-256，校验运输完整性 |

## 口径与使用

正式费用及热图仅含2025-02-01至12-31共334日。预测比较采用共同333日起点；小时目标与真实小时右端点一致。核心图6-3日期3月20日由指定四日与全年中位运行状态的距离客观选择。

所有图展示已执行可行结果，存在489个未达到3%证书的节点，不宣称全节点严格最优。负调整费用是结算返还，不是总利润。18点夜间光伏近零，预测相对改善不能直接解释为经济信息价值。局部S保持用户批准的10/20/28，终端库存差异不能忽略。

PNG可直接插入文档，SVG文字已转曲，可缩放；SVG热图矩阵按原像素嵌入，文字及线条为矢量。请在论文最终插入尺寸下检查字号，避免过度缩小多面板图。

## 从本包数据重绘

在解压目录安装requirements.txt所列库后运行（不调用求解器）：

```sh
python -m src.plots.q3_paper_core --data-dir data --output-dir redraw/core
python -m src.plots.q3_paper_final --data-dir data --output-dir redraw/extended
```

核心图重绘需要本机安装Times New Roman与宋体Songti SC；现成PNG/SVG无需字体。扩展脚本会复现最初设计的七张图，实际交付只选A1–A4，映射见manifest；不据此恢复已取消的FIV/OUV图。

q3_paper_data和q3_paper_verify用于完整项目环境中的原始文件追溯，需原项目数据路径；本包足够离线重绘，无需重新优化。正式结果与之前交付ZIP均未覆盖。
'''
    (PACKAGE/'README.md').write_text(readme,encoding='utf-8')
    cards=''
    for item in manifest:
        cards+=f'<article><h2>{html.escape(item["title"])}</h2><a href="{item["png"]}"><img src="{item["png"]}" alt="{html.escape(item["title"])}"></a><p>{html.escape(item["caption"])}</p><p><a href="{item["svg"]}">SVG矢量文件</a> · <a href="{item["png"]}">PNG原图</a></p></article>'
    page='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>第三问科研图 · 最终交付</title><style>body{margin:0;color:#103b62;background:#edf3f8;font:16px/1.6 -apple-system,BlinkMacSystemFont,"PingFang SC",sans-serif}main{max-width:1120px;margin:auto;padding:25px 18px}article{background:white;border-radius:12px;padding:24px;margin:24px 0}img{width:100%;height:auto}h1{font-size:27px}h2{font-size:20px}p{color:#62778a;font-size:14px}a{color:#1263a0}</style><main><h1>第三问科研图 · 蓝色渐变</h1><p>3张正文核心图 + 4张扩展备选图 · 400dpi PNG / SVG</p><p>图6-4（FIV/OUV）已按用户要求取消。运行与预测统计范围见各图图注。</p><p><a href="README.md">README</a> · <a href="第三问科研图方案.md">最终方案</a> · <a href="图后分析与论文插入建议.md">图后分析</a></p>'''+cards+'</main></html>'
    (PACKAGE/'index.html').write_text(page,encoding='utf-8')
    print('Prepared',PACKAGE)


def archive():
    rows=[]
    for p in sorted(PACKAGE.rglob('*')):
        if p.is_file() and p.name!='file_manifest.csv':
            rows.append({'path':str(p.relative_to(PACKAGE)),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
    with (PACKAGE/'file_manifest.csv').open('w',encoding='utf-8',newline='') as stream:
        w=csv.DictWriter(stream,fieldnames=['path','bytes','sha256']);w.writeheader();w.writerows(rows)
    zip_path=PACKAGE.with_suffix('.zip')
    files=[p for p in sorted(PACKAGE.rglob('*')) if p.is_file()]
    with zipfile.ZipFile(zip_path,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in files:z.write(p,str(Path(PACKAGE.name)/p.relative_to(PACKAGE)))
    with zipfile.ZipFile(zip_path) as z:
        assert z.testzip() is None and len(z.namelist())==len(files)
        for p in files:
            assert hashlib.sha256(z.read(str(Path(PACKAGE.name)/p.relative_to(PACKAGE)))).digest()==hashlib.sha256(p.read_bytes()).digest()
    receipt={'zip':str(zip_path),'bytes':zip_path.stat().st_size,'members':len(files),'figures':7,'PNG':7,'SVG':7,
        'sha256':hashlib.sha256(zip_path.read_bytes()).hexdigest(),'CRC_and_member_SHA256':'passed'}
    (DOCS/'zip_acceptance.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8')
    print(receipt)


if __name__=='__main__':
    import sys
    if '--archive' in sys.argv:archive()
    else:prepare_package()
