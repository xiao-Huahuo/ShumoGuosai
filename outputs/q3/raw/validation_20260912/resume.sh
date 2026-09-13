#!/bin/zsh
set -e
cd /Users/slumpyfufu/Desktop/Projects/ShumoGuosai/outputs/q3/raw/validation_20260912/runtime
export Q3_WORKSPACE_ROOT=/Users/slumpyfufu/Desktop/Projects/ShumoGuosai
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 PYTHONUNBUFFERED=1 PYTHONUTF8=1
exec /opt/homebrew/bin/uv run --offline --with-requirements /Users/slumpyfufu/Desktop/Projects/ShumoGuosai/src/q3/requirements.txt python -m src.q3.validation --main-run /Users/slumpyfufu/Desktop/Projects/ShumoGuosai/outputs/q3/raw/full_priority_parallel_20260912 --output /Users/slumpyfufu/Desktop/Projects/ShumoGuosai/outputs/q3/raw/validation_20260912 --scope pending --workers 4
