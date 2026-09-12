"""论文图的中文字体、语义配色及PNG/SVG导出。"""
import csv
import hashlib
import warnings

COLORS = {'load': '#41464D', 'pv': '#E69F00', 'grid': '#0072B2',
          'charge': '#009E88', 'discharge': '#8B5FBF', 'muted': '#7B8792', 'energy': '#253D56'}


def read_csv(path):
    with path.open(encoding='utf-8', newline='') as stream:
        return list(csv.DictReader(stream))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def setup():
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    fonts = {f.name for f in font_manager.fontManager.ttflist}
    selected = next((f for f in ('PingFang SC', 'Heiti TC', 'Arial Unicode MS', 'Noto Sans CJK SC', 'Songti SC') if f in fonts), None)
    if selected is None:
        raise RuntimeError('缺少中文字体，拒绝输出乱码图')
    plt.rcParams.update({'font.family': selected, 'font.size': 10, 'axes.titlesize': 12,
                         'axes.labelsize': 10, 'legend.fontsize': 9, 'axes.unicode_minus': False,
                         'axes.spines.top': False, 'axes.spines.right': False, 'axes.grid': True,
                         'axes.axisbelow': True, 'grid.alpha': .17, 'svg.fonttype': 'path',
                         'figure.facecolor': 'white', 'savefig.facecolor': 'white'})
    return plt, selected


def cost_palette():
    from matplotlib.colors import LinearSegmentedColormap
    return LinearSegmentedColormap.from_list('cost_ocean', ['#ECF5F2', '#8FC6CC', '#4384AC', '#223B66'])


def save(fig, output, name):
    import matplotlib.pyplot as plt
    with warnings.catch_warnings():
        warnings.filterwarnings('error', message='Glyph .* missing from font')
        for suffix in ('png', 'svg'):
            fig.savefig(output / f'{name}.{suffix}', dpi=300)
    plt.close(fig)
