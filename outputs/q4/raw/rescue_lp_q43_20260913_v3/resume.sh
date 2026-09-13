#!/bin/zsh
set -e
cd /Users/slumpyfufu/Desktop/Projects/ShumoGuosai
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONUTF8=1
exec /Users/slumpyfufu/Desktop/Projects/ShumoGuosai/.venv/bin/python -u -m src.q4.run q43 --output /Users/slumpyfufu/Desktop/Projects/ShumoGuosai/outputs/q4/raw/rescue_lp_q43_20260913_v3
