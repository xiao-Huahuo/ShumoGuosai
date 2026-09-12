"""第三问预报误差热图；只读已生成统计，PNG/SVG及来源清单。"""
from pathlib import Path
import hashlib
import json
import pandas as pd
from .common import setup, save, cost_palette


def forecast_heatmaps(metrics: pd.DataFrame, output: Path) -> str:
    plt, font = setup()
    output.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(1, 3, figsize=(13, 3.8), layout='constrained')
    for ax, key in zip(axes, ('MAE', 'RMSE', 'Bias')):
        values = metrics.pivot(index='issue_hour', columns='horizon', values=key).to_numpy()
        limits = {'vmin': -abs(values).max(), 'vmax': abs(values).max()} if key == 'Bias' else {}
        plotted = ax.imshow(values, aspect='auto', cmap='RdBu_r' if key == 'Bias' else cost_palette(), **limits)
        ax.set_xticks([0, 5, 11, 17, 23], [1, 6, 12, 18, 24]); ax.set_yticks(range(4), ['00:00', '06:00', '12:00', '18:00'])
        ax.set_title(key+' / kW'); ax.set_xlabel('预报提前量 / h'); ax.grid(False)
        fig.colorbar(plotted, ax=ax, fraction=.05)
    save(fig, output, 'forecast_error_heatmaps')
    (output/'manifest.json').write_text(json.dumps({'script': 'src/plots/q3.py',
        'source': str(output.parent/'forecast_metrics.csv'), 'source_sha256': hashlib.sha256((output.parent/'forecast_metrics.csv').read_bytes()).hexdigest(),
        'outputs': ['forecast_error_heatmaps.png', 'forecast_error_heatmaps.svg'], 'font': font,
        'description': '四发布时间×24小时提前量MAE/RMSE/Bias；年末无真值目标排除而不填零'}, ensure_ascii=False, indent=2), encoding='utf-8')
    return font
