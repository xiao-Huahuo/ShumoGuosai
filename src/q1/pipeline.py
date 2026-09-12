"""CR-03/04：数值与图形解耦；验证完整generation后原子切换唯一指针。"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

from model import ROOT, write_json

# 原有对外路径保持可用；所有本次运行文件都通过同一个current指针访问。
ALIASES = {"inputs/q1": "inputs",
           "docs/1/deliverables/q1_source_line_traceability.csv": "docs/q1_source_line_traceability.csv", "outputs/q1/raw": "raw",
           "outputs/processed/q1": "processed",
           "docs/1/deliverables/q1_results.md": "docs/q1_results.md",
           "docs/1/deliverables/q1_marginal_analysis.md": "docs/q1_marginal_analysis.md"}


def run_tests(staging):
    environment = {**os.environ, "Q1_ARTIFACT_ROOT": str(staging)}
    completed = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "src/q1", "-p", "test_*.py", "-v"],
                               cwd=ROOT, env=environment, capture_output=True, text=True, encoding="utf-8")
    log = completed.stdout + completed.stderr
    (staging / "raw/test_log.txt").write_text(log, encoding="utf-8")
    write_json(staging / "raw/tests.json", {"passed": completed.returncode == 0, "returncode": completed.returncode,
                                           "command": "python -m unittest discover -s src/q1 -p test_*.py -v", "log": log})
    if completed.returncode:
        raise RuntimeError(f"本次staging测试未全部通过，拒绝发布：\n{log}")


def render_figures(data, solutions, summaries, analysis, staging, enabled=True):
    """图形全部在独立临时目录产生；失败可见且不会留下部分图形。"""
    directory = staging / "figures_tmp"
    directory.mkdir()
    try:
        if not enabled:
            return {"status": "skipped", "message": "按--no-plots仅执行数值、报告和交付文件"}
        from report import create_figures
        from analysis_report import analysis_figures
        create_figures(data, solutions, summaries, directory)
        analysis_figures(analysis, directory)
        for path in directory.iterdir():
            path.replace(staging / "processed" / path.name)
        return {"status": "passed", "message": "全部四组图形PNG/SVG生成成功"}
    except Exception as exc:
        return {"status": "failed", "message": f"{type(exc).__name__}: {exc}"}
    finally:
        shutil.rmtree(directory)
        if "matplotlib.pyplot" in sys.modules:
            sys.modules["matplotlib.pyplot"].close("all")


def publish_generation(staging, root=ROOT):
    """staging须已通过所有数值/交付/测试门槛；最终只调用一次os.replace切换。"""
    root = Path(root).resolve()
    current = root / "outputs/q1_current"
    if current.exists() and not current.is_symlink():
        raise ValueError("q1_current必须为generation符号链接")
    # 首次迁移保留原目录，失败逐一恢复。后续运行不会再修改别名。
    if not current.is_symlink():
        legacy = staging.parent / "legacy_before_atomic"
        legacy.mkdir()
        current.symlink_to(os.path.relpath(legacy, current.parent), target_is_directory=True)
        moved = []
        try:
            for relative, target in ALIASES.items():
                alias, old = root / relative, legacy / target
                old.parent.mkdir(parents=True, exist_ok=True)
                alias.parent.mkdir(parents=True, exist_ok=True)
                had_old = alias.exists()
                if had_old:
                    alias.rename(old)
                moved.append((alias, old, had_old))
                alias.symlink_to(os.path.relpath(current / target, alias.parent), target_is_directory=old.is_dir())
        except Exception:
            for alias, old, had_old in reversed(moved):
                if alias.is_symlink():
                    alias.unlink()
                if had_old:
                    old.rename(alias)
            current.unlink()
            shutil.rmtree(legacy)
            raise
    for relative, target in ALIASES.items():
        alias = root / relative
        expected = os.path.relpath(current / target, alias.parent)
        if not alias.is_symlink() or os.readlink(alias) != expected:
            raise ValueError(f"正式路径未指向统一generation：{relative}")
    pending = current.with_name(".q1_current_next")
    try:
        pending.symlink_to(os.path.relpath(staging, current.parent), target_is_directory=True)
        os.replace(pending, current)  # 同一文件系统的唯一发布提交点。
    finally:
        if pending.is_symlink():
            pending.unlink()
