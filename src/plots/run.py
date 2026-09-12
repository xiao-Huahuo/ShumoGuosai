"""统一绘图命令；各题使用原固定依赖，避免Q1/Q2库版本互相覆盖。"""
import argparse
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('question', choices=['q1','q2','q2-dispatch','all'], nargs='?', default='q1')
    parser.add_argument('--run-dir', type=Path, help='q2-dispatch的完整或部分真实运行目录')
    args = parser.parse_args()
    if args.question == 'q2-dispatch':
        if args.run_dir is None:
            parser.error('q2-dispatch需要--run-dir')
        subprocess.run(['uv','run','--with-requirements','src/q2/requirements.txt','python',
                        'src/plots/q2_dispatch.py','--run-dir',str(args.run_dir)], cwd=ROOT, check=True)
        return
    for question in (['q1','q2'] if args.question == 'all' else [args.question]):
        command = ['uv','run','--with-requirements',f'src/{question}/requirements.txt','python','-u']
        command += ['src/plots/q1_paper.py'] if question == 'q1' else [
            'src/plots/replot_existing.py','q2','--output','outputs/processed/figures/q2']
        subprocess.run(command, cwd=ROOT, check=True)
    subprocess.run([sys.executable,'src/plots/catalog.py'],cwd=ROOT,check=True)


if __name__ == '__main__':
    main()
