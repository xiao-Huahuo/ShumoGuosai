"""兼容Q2原运行入口；全部绘图实现集中在src/plots/q2.py。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.plots.q2 import LABELS

def create_figures(frame, diagnostics, output):
    from src.plots.q2 import create_figures as render
    return render(frame, diagnostics, output)
