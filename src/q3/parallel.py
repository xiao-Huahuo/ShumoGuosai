"""有界spawn进程池：只提交彼此独立、输入已冻结的计算。"""
from concurrent.futures import ProcessPoolExecutor
from contextlib import contextmanager
import multiprocessing as mp
import os
import time
from pathlib import Path
from typing import Iterator
from threadpoolctl import threadpool_limits
from .optimization import Solution, solve


def limit_native_libraries() -> None:
    for name in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'VECLIB_MAXIMUM_THREADS', 'NUMEXPR_NUM_THREADS'):
        os.environ[name] = '1'
    threadpool_limits(limits=1)


def validate_parallelism(workers: int, solver_threads: int) -> None:
    if not isinstance(workers, int) or not isinstance(solver_threads, int) or min(workers, solver_threads) < 1:
        raise ValueError('进程数和求解线程数必须为正整数')
    available = len(os.sched_getaffinity(0)) if hasattr(os, 'sched_getaffinity') else os.cpu_count()
    if available is not None and workers*solver_threads > available:
        raise ValueError(f'{workers}进程×{solver_threads}求解线程超过当前可见CPU数{available}')


@contextmanager
def process_pool(workers: int, solver_threads: int = 1) -> Iterator[ProcessPoolExecutor | None]:
    validate_parallelism(workers, solver_threads)
    if workers == 1:
        yield None
        return
    # fork继承已初始化的SCIP/BLAS状态可能死锁；macOS显式使用spawn。
    limit_native_libraries()
    with ProcessPoolExecutor(max_workers=workers, mp_context=mp.get_context('spawn'),
                             initializer=limit_native_libraries) as executor:
        yield executor


def solve_job(request: dict) -> Solution:
    return solve(**request)


def rollout_job(request: dict) -> dict:
    """每条完整SOC链在一个worker中顺序执行；不再启动子进程池。"""
    from .rolling import run_period
    started = time.perf_counter()
    try:
        frame = run_period(**request, workers=1)
        return {'path': str(request['output']), 'status': 'complete', 'rows': len(frame),
                'seconds': time.perf_counter()-started, 'pid': os.getpid()}
    except Exception as error:
        # 父进程保存所有独立分支完成/失败状态后统一拒绝出具完整对照结果。
        return {'path': str(request['output']), 'status': 'failed', 'error_type': type(error).__name__,
                'error': str(error), 'seconds': time.perf_counter()-started, 'pid': os.getpid()}


def run_rollout_jobs(requests: list[dict], workers: int, manifest: Path) -> list[dict]:
    from .config import write_json
    if len({str(job['output'].resolve()) for job in requests}) != len(requests):
        raise ValueError('并行任务输出目录重叠，禁止并发写同一检查点')
    threads = max((job['config'].solver_threads for job in requests), default=1)
    results = []
    with process_pool(workers, threads) as executor:
        iterator = executor.map(rollout_job, requests) if executor is not None else map(rollout_job, requests)
        for result in iterator:
            results.append(result)
            write_json(manifest, {'workers': workers, 'threads_per_worker': threads,
                'nested_process_pools': False, 'jobs': results, 'expected_jobs': len(requests)})
    failed = [result for result in results if result['status'] != 'complete']
    if failed:
        raise RuntimeError(f'{len(failed)}条独立实验链未完成，见{manifest}；已完成结果保留，未生成完整比较')
    return results
