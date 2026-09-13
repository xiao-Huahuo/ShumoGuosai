#!/bin/sh
set -eu
cd /Users/slumpyfufu/Desktop/Projects/ShumoGuosai/outputs/q3/raw/full_priority_rescue_7h_20260912/runtime
export Q3_WORKSPACE_ROOT=/Users/slumpyfufu/Desktop/Projects/ShumoGuosai
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 NUMEXPR_NUM_THREADS=1
exec /opt/homebrew/bin/uv run --offline --with-requirements /Users/slumpyfufu/Desktop/Projects/ShumoGuosai/outputs/q3/raw/full_priority_rescue_7h_20260912/runtime/requirements.txt python -m src.q3.full_run --run-dir /Users/slumpyfufu/Desktop/Projects/ShumoGuosai/outputs/q3/raw/full_priority_rescue_7h_20260912 --q2-run /Users/slumpyfufu/Desktop/Projects/ShumoGuosai/outputs/q2/dispatch_runs/20260911_224501 --gap .03 --seconds 120 --workers 2 --solver-threads 4 --solver-backend highs --formulation legacy --solver-focus default --production-rescue --hard-06-seconds 35 --hard-other-seconds 8 --main-only
