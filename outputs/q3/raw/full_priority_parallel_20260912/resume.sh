#!/bin/sh
set -eu
cd /Users/slumpyfufu/Desktop/Projects/ShumoGuosai/outputs/q3/raw/full_priority_parallel_20260912/runtime
export Q3_WORKSPACE_ROOT=/Users/slumpyfufu/Desktop/Projects/ShumoGuosai
exec /opt/homebrew/bin/uv run --offline --with-requirements /Users/slumpyfufu/Desktop/Projects/ShumoGuosai/outputs/q3/raw/full_priority_parallel_20260912/runtime/requirements.txt python -m src.q3.full_run --run-dir /Users/slumpyfufu/Desktop/Projects/ShumoGuosai/outputs/q3/raw/full_priority_parallel_20260912 --gap .03 --seconds 120 --workers 2 --solver-threads 4 --main-only
