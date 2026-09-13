"""从已验收的CSV/JSON重绘原有Q1四组图或Q2十一组图，不重算统计或优化。"""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from src.plots.common import digest, read_csv


def numeric(rows):
    for row in rows:
        for key, value in row.items():
            try:
                row[key] = int(value) if value.lstrip('-').isdigit() else float(value)
            except (ValueError, TypeError):
                pass
    return rows


def replot(question, output):
    generation = (ROOT / f'outputs/{question}_current').resolve(strict=True)
    manifest = json.loads((generation / 'raw/run_manifest.json').read_text(encoding='utf-8'))
    for rel, value in manifest['output_sha256'].items():
        if digest(generation / rel) != value:
            raise ValueError(f'来源产物哈希不符：{rel}')
    output = Path(output).resolve()
    # 原运行代及其任何别名都属于只读来源。
    if output == generation or generation in output.parents:
        raise ValueError('不能将重绘结果写入已验收运行代')
    output.mkdir(parents=True, exist_ok=True)
    source = generation / 'processed'
    if question == 'q1':
        from src.plots.q1_legacy import analysis_figures, create_figures
        data = numeric(read_csv(generation / 'inputs/processed/timeseries.csv'))
        solutions = {name: json.loads((generation / f'raw/solution_{name}.json').read_text(encoding='utf-8'))
                     for name in ['main', 'eta085', 'eta095', 'roundtrip090']}
        create_figures(data, solutions, numeric(read_csv(source / 'efficiency_comparison.csv')), output)
        a = {'main_marginals': [r for r in numeric(read_csv(source / 'marginal_values.csv')) if r['scenario'] == 'main_l100_pv100'],
             'baseline_rows': numeric(read_csv(source / 'baseline_comparison.csv')),
             'scenarios': numeric(read_csv(source / 'sensitivity_scenarios.csv')),
             'bottlenecks': numeric(read_csv(source / 'bottleneck_values.csv'))}
        analysis_figures(a, output)
    else:
        import pandas as pd
        from src.plots.q2 import create_figures
        frame = pd.read_csv(source / 'timeseries.csv', parse_dates=['date', 'timestamp'], float_precision='round_trip')
        diagnostics = {}
        for name in ['profiles','acf_pacf','spectrum','monthly_stability','transformed_monthly_moments','daily_statistics']:
            diagnostics[name] = pd.read_csv(source / f'full_year_{name}.csv', float_precision='round_trip',
                                            parse_dates=['date'] if name == 'daily_statistics' else None)
        profiles = diagnostics['profiles']
        numeric_groups = profiles.grouping.isin(['month', 'weekday'])
        profiles.loc[numeric_groups, 'group'] = profiles.loc[numeric_groups, 'group'].astype(int)
        figures = create_figures(frame, diagnostics, output)
        (output / 'figure_manifest.json').write_text(json.dumps(figures,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(f'{question}重绘完成：{output}', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('question', choices=['q1', 'q2'])
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    replot(args.question, args.output)
