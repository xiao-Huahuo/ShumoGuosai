"""论文图验收：磁盘回读、单位/时序/瀑布恒等式、来源及脚本集中化。"""
import ast
import json
from pathlib import Path
import sys
from xml.etree import ElementTree

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from src.plots.common import digest, read_csv
from src.q1.device_sensitivity import verify as verify_device


def close(left, right, tol=1e-6):
    np.testing.assert_allclose(np.asarray(left,dtype=float), np.asarray(right,dtype=float), atol=tol, rtol=0)


def main():
    folder = ROOT / 'outputs/processed/figures/q1'
    provenance = json.loads((folder / 'provenance.json').read_text(encoding='utf-8'))
    for path, value in provenance['code_sha256'].items():
        if digest(ROOT/path) != value: raise ValueError(f'绘图源码已变化，须重绘：{path}')
    for path, value in provenance['output_sha256'].items():
        if digest(folder/path) != value: raise ValueError(f'绘图产物被修改：{path}')
    generation = ROOT / provenance['source_generation']
    original = read_csv(generation / 'processed/result1.csv')
    power, energy, features = [read_csv(folder/name) for name in ['dispatch_power.csv','storage_145.csv','data_features.csv']]
    if (len(original),len(power),len(energy),len(features)) != (144,144,145,144):
        raise ValueError('144区间/145状态点不完整')
    for i,(source,drawn,feature) in enumerate(zip(original,power,features)):
        close([drawn['start_h'],drawn['end_h']],[i/6,(i+1)/6])
        for key, field in [('G_kwh','optimal_grid_kw'),('C_kwh','charge_kw'),('D_kwh','discharge_kw')]:
            close(float(drawn[field])/6,float(source[key]))
        state = '充电' if float(source['C_kwh'])>1e-6 else '放电' if float(source['D_kwh'])>1e-6 else '待机'
        if drawn['state']!=state: raise ValueError('状态条与实际C/D不符')
        close(float(drawn['no_ess_grid_kw']), max(float(source['load_kw'])-float(source['pv_kw']),0))
        close(float(feature['surplus_pv_kw']), max(float(source['pv_kw'])-float(source['load_kw']),0))
        close(float(energy[i+1]['energy_kwh']),float(source['E_kwh']))
    close([float(energy[0]['energy_kwh']),float(energy[-1]['energy_kwh'])],[6000,6000])
    close([float(r['time_h']) for r in energy],np.arange(145)/6)
    waterfall=read_csv(folder/'cost_waterfall.csv')
    cost={r['baseline']:float(r['cost_yuan']) for r in read_csv(folder/'baseline_metrics.csv')}
    close([float(r['bottom_yuan']) for r in waterfall],[0,cost['pv_only'],0,cost['full'],0])
    close([float(r['height_yuan']) for r in waterfall],
          [cost['no_ess'],cost['no_ess']-cost['pv_only'],cost['pv_only'],cost['pv_only']-cost['full'],cost['full']])
    if len(read_csv(folder/'efficiency_storage.csv')) != 580 or len(read_csv(folder/'input_sensitivity.csv')) != 9:
        raise ValueError('效率轨迹或九格敏感性数据不完整')
    devices=verify_device([{**r,**{k:float(r[k]) for k in ['load_kwh','pv_kwh','price_yuan_per_kwh']}} for r in original],
                          ROOT/provenance['device_analysis'])
    images=[]
    for row in read_csv(folder/'figure_index.csv'):
        with Image.open(folder/(row['figure']+'.png')) as im:
            im.verify()
        with Image.open(folder/(row['figure']+'.png')) as im:
            if min(im.size)<1300 or abs(im.info['dpi'][0]-300)>.01:
                raise ValueError('PNG尺寸或300dpi元数据错误')
            images.append({'figure':row['figure'],'pixels':list(im.size),'dpi':list(im.info['dpi'])})
        svg=ElementTree.parse(folder/(row['figure']+'.svg'))
        if not svg.findall('.//{http://www.w3.org/2000/svg}path'):
            raise ValueError('SVG没有矢量路径')
    if len(images)!=8: raise ValueError('论文图数不完整')
    imports=[]
    for path in (ROOT/'src').rglob('*.py'):
        raw=path.read_bytes(); text=raw.decode('utf-8')
        if raw.startswith(b'\xef\xbb\xbf'): raise ValueError(f'源码含BOM：{path}')
        for node in ast.walk(ast.parse(text)):
            names=[a.name for a in node.names] if isinstance(node,ast.Import) else [node.module or ''] if isinstance(node,ast.ImportFrom) else []
            if any(n.split('.')[0] in ['matplotlib','seaborn','plotly','bokeh','altair'] for n in names):
                imports.append(str(path.relative_to(ROOT)))
                if path.parent != ROOT/'src/plots': raise ValueError(f'绘图实现未集中：{path}')
    result={'passed':True,'checks':['source_and_output_hashes','144_power_intervals','145_energy_boundaries',
            'kWh_to_kW','actual_action_states','surplus_shading','waterfall_identity','efficiency_and_input_scenarios',
            'all_133_device_solutions','png_300dpi','svg_paths','all_project_plot_imports_centralized','utf8_no_bom'],
            'devices':devices,'images':images,'plot_modules':sorted(set(imports))}
    target=ROOT/'docs/plots/verification.json';target.parent.mkdir(exist_ok=True)
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False),flush=True)


if __name__=='__main__':
    main()
