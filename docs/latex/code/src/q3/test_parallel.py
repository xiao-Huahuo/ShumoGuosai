"""串并行数值一致性、因果FD、FIV配对、独立SOC链和异常传播。"""
from dataclasses import replace
from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
import pandas as pd
from .config import ROOT, Config
from .parallel import process_pool, run_rollout_jobs, validate_parallelism
from .optimization import LimitedSolve, solve
from .physics import Policy
from .scenarios import Scenarios
from .data import read_inputs
from .terminal import TerminalValues
from .rolling import fiv, run_period


def raise_limited(_: int) -> None:
    raise LimitedSolve({'status': 'deliberate_test_limit', 'reliable': False})


class ParallelMathTests(unittest.TestCase):
    def test_cpu_budget_rejects_oversubscription(self) -> None:
        with self.assertRaises(ValueError): validate_parallelism(0, 1)
        with self.assertRaises(ValueError): validate_parallelism(2, 0)
        with self.assertRaises(ValueError): validate_parallelism(100000, 2)

    def test_native_concurrent_exact_mapping(self) -> None:
        load = np.array([[0., 12000., 400., 10000.], [6000., 300., 10000., 200.]])
        pv = np.array([[3000., 0., 5000., 0.], [0., 6000., 0., 800.]])
        scenes = Scenarios(load, pv, np.array([.4, .6]), {})
        policy = Policy(np.array([200., 400., 200., 100.]), np.full(4, 100.), np.full(4, 200.))
        results = [solve(scenes, np.ones(4), 1250., Config(seconds=15, solver_threads=t),
                         fixed=policy, terminal=.2) for t in (1, 2)]
        self.assertEqual(results[1].audit['solve_method'], 'SCIP_solveConcurrent')
        self.assertTrue(all(r.audit['reliable'] for r in results))
        self.assertAlmostEqual(results[0].audit['objective'], results[1].audit['objective'], places=6)
        for left, right in zip(results[0].responses, results[1].responses):
            for key in left: np.testing.assert_allclose(left[key], right[key], atol=1e-6)

    def test_process_exception_preserves_original_audit(self) -> None:
        with process_pool(2) as executor:
            with self.assertRaises(LimitedSolve) as result:
                list(executor.map(raise_limited, [1]))
        self.assertEqual(result.exception.audit['status'], 'deliberate_test_limit')

    def test_duplicate_checkpoint_paths_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            with self.assertRaises(ValueError):
                run_rollout_jobs([{'output': path}, {'output': path}], 2, path/'status.json')


class ParallelRealTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.data = read_inputs(ROOT/'outputs/q2/dispatch_runs/20260911_224501')

    def test_fd_causal_batch_and_fiv_pair_equal(self) -> None:
        config = Config(seconds=15, deterministic=True)
        sequential = TerminalValues(self.data, config)
        expected, expected_audit = sequential.value(31, 6)
        reference = np.ones(108)*500
        old, old_branches = fiv(self.data, sequential, 31, 6, 6000., reference, config)
        with process_pool(2) as executor:
            concurrent = TerminalValues(self.data, config, executor)
            actual, actual_audit = concurrent.value(31, 6)
            new, new_branches = fiv(self.data, concurrent, 31, 6, 6000., reference, config)
        self.assertEqual(expected_audit, actual_audit)
        self.assertAlmostEqual(expected, actual, places=10)
        self.assertTrue(all(row['complete_at_slot'] <= 31*144 for row in concurrent.cache.values()))
        self.assertAlmostEqual(old['FIV_block'], new['FIV_block'], places=6)
        self.assertEqual([r['branch'] for r in new_branches], ['stale', 'updated'])
        for left, right in zip(old_branches, new_branches):
            np.testing.assert_allclose(left['real_cost'], right['real_cost'], atol=1e-6)
            np.testing.assert_allclose(left['soc'], right['soc'], atol=1e-6)

    def test_parallel_independent_soc_chains_equal(self) -> None:
        config = Config(seconds=15, deterministic=True)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            jobs = [dict(data=self.data, config=replace(config, nodes=nodes), output=root/f'parallel{index}',
                         end=9, with_fiv=False) for index, nodes in enumerate(((0,), (0, 6, 12, 18)))]
            results = run_rollout_jobs(jobs, 2, root/'jobs.json')
            self.assertTrue(all(row['status'] == 'complete' for row in results))
            self.assertEqual(len({row['pid'] for row in results}), 2)
            for index, job in enumerate(jobs):
                path = root/f'serial{index}'
                run_period(self.data, job['config'], path, end=9, with_fiv=False, workers=2 if index == 0 else 1)
                expected = pd.read_csv(path/'warmup.csv')
                actual = pd.read_csv(job['output']/'warmup.csv')
                pd.testing.assert_frame_equal(expected, actual, atol=1e-7, rtol=0)
            manifest = json.loads((root/'jobs.json').read_text(encoding='utf-8'))
            self.assertFalse(manifest['nested_process_pools'])

    def test_parallel_failures_do_not_publish_complete_comparison(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            # 故意给空日期范围，验证worker错误记录和父进程拒绝完整比较。
            jobs = [dict(data=self.data, config=Config(), output=root/'bad', end=0, with_fiv=False)]
            with self.assertRaises(RuntimeError): run_rollout_jobs(jobs, 2, root/'jobs.json')
            value = json.loads((root/'jobs.json').read_text(encoding='utf-8'))
            self.assertEqual(value['jobs'][0]['status'], 'failed')

    def test_all_required_experiment_chains_are_dispatched(self) -> None:
        from .analysis import run_experiments
        with tempfile.TemporaryDirectory() as folder:
            with patch('src.q3.parallel.run_rollout_jobs', side_effect=RuntimeError('stop_after_dispatch')) as dispatcher:
                with self.assertRaisesRegex(RuntimeError, 'stop_after_dispatch'):
                    run_experiments(self.data, Config(), Path(folder), pd.DataFrame(), workers=4)
            jobs, workers, _ = dispatcher.call_args.args
            self.assertEqual(workers, 4)
            self.assertEqual(len(jobs), 40)  # 9×4敏感性链+3个额外OUV链+M0；已有主链不重复。
            self.assertEqual(len({str(job['output']) for job in jobs}), 40)
            self.assertEqual(sum(job['config'].deterministic for job in jobs), 1)
            self.assertEqual(sum(job['with_fiv'] for job in jobs), 9)

    def test_stress_day_process_preserves_settlement_values(self) -> None:
        from .analysis import settlement_job
        config = Config(seconds=15, deterministic=True)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            sequential = settlement_job((self.data, config, root/'serial', 31, 6000., 0.))
            with process_pool(2) as executor:
                concurrent = list(executor.map(settlement_job, [(self.data, config, root/'parallel', 31, 6000., 0.)]))[0]
            pd.testing.assert_frame_equal(pd.DataFrame(sequential), pd.DataFrame(concurrent), atol=1e-6, rtol=0)


if __name__ == '__main__':
    unittest.main(verbosity=2)
