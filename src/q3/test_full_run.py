"""切片、缓存命中、真实SIGKILL恢复、原子发布及抽样任务范围。"""
from dataclasses import replace
import hashlib
import json
import os
import signal
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
import numpy as np
from .config import ROOT, Config, write_json
from .checkpoint import run_lock
from .optimization import solve
from .scenarios import Scenarios
from .data import read_inputs
from .terminal import TerminalValues
from .rolling import run_day
from .parallel_benchmark import frozen_requests
from .sampled import DATES, sample_configs


class CheckpointTests(unittest.TestCase):
    def test_completed_node_replays_without_optimizer(self) -> None:
        scenes = Scenarios(np.full((1, 8), 1000.), np.zeros((1, 8)), np.ones(1), {})
        with tempfile.TemporaryDirectory() as folder:
            request = dict(scenarios=scenes, prices=np.ones(8), initial=6000., config=Config(), checkpoint=Path(folder))
            first = solve(**request)
            with patch('src.q3.optimization.make_model', side_effect=AssertionError('should not solve')):
                second = solve(**request)
            self.assertTrue(second.audit['restored_complete_node'])
            np.testing.assert_array_equal(first.policy.grid, second.policy.grid)
            with self.assertRaises(ValueError): solve(**{**request, 'initial': 6001.})

    def test_atomic_json_preserves_previous_on_replace_failure(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'state.json'; write_json(path, {'valid': 1})
            with patch('pathlib.Path.replace', side_effect=OSError('simulated interrupted rename')):
                with self.assertRaises(OSError): write_json(path, {'valid': 2})
            self.assertEqual(json.loads(path.read_text(encoding='utf-8')), {'valid': 1})

    def test_lock_rejects_second_writer(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            with run_lock(Path(folder)/'run.lock'):
                with self.assertRaises(RuntimeError):
                    with run_lock(Path(folder)/'run.lock'): pass

    def test_real_solver_slices_and_snapshot_validation(self) -> None:
        request = frozen_requests(1.)[0]
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            result = solve(**request, checkpoint=path, max_slices=2)
            self.assertEqual(result.audit['completed_slices'], 2)
            self.assertEqual(len(list(path.glob('slice_*.json'))), 2)
            saved = json.loads((path/'latest.json').read_text(encoding='utf-8'))
            saved['content']['policy']['grid'][0] += 1.
            (path/'latest.json').write_text(json.dumps(saved), encoding='utf-8')
            with self.assertRaises(ValueError): solve(**request, checkpoint=path)

    def test_event_checkpoint_during_solving(self) -> None:
        from .optimization import ProgressEvent
        from .checkpoint import save_snapshot
        original = ProgressEvent.__init__; saved = []
        def start_due(self, *args):
            original(self, *args); self.last -= 11
        def observe(path, signature, policy, audit):
            saved.append(audit.copy()); save_snapshot(path, signature, policy, audit)
        with tempfile.TemporaryDirectory() as folder, patch.object(ProgressEvent, '__init__', start_due), patch('src.q3.checkpoint.save_snapshot', side_effect=observe):
            solve(**frozen_requests(2.)[0], checkpoint=Path(folder))
        self.assertTrue(any(row.get('checkpoint_event') for row in saved))

    def test_sigkill_retains_and_restores_incumbent(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            code = "from pathlib import Path; import sys; from src.q3.parallel_benchmark import frozen_requests; from src.q3.optimization import solve; solve(**frozen_requests(2.)[0], checkpoint=Path(sys.argv[1]), max_slices=None)"
            child = subprocess.Popen([sys.executable, '-c', code, str(path)], cwd=ROOT,
                                     stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            try:
                deadline = time.monotonic()+20
                while not (path/'latest.json').exists() and time.monotonic() < deadline and child.poll() is None:
                    time.sleep(.05)
                self.assertTrue((path/'latest.json').exists(), 'worker must save feasible seed before kill')
                child.kill(); child.wait(timeout=10)
                saved = json.loads((path/'latest.json').read_text(encoding='utf-8'))['content']['audit']
                result = solve(**frozen_requests(2.)[0], checkpoint=path)
                self.assertTrue(result.audit['restored_incumbent'])
                self.assertLessEqual(result.audit['objective'], saved['objective']+1e-5)
            finally:
                if child.poll() is None: child.kill(); child.wait()
                child.stderr.close()

    def test_parallel_highs_sigkill_preserves_valid_bound(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)
            code="from pathlib import Path; from dataclasses import replace; import sys; from src.q3.parallel_benchmark import frozen_requests; from src.q3.optimization import solve; r=frozen_requests(1.)[0]; r['config']=replace(r['config'], gap=.03, solver_threads=4); solve(**r, checkpoint=Path(sys.argv[1]), max_slices=None)"
            child=subprocess.Popen([sys.executable,'-c',code,str(path)],cwd=ROOT,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
            try:
                deadline=time.monotonic()+25;saved=None
                while time.monotonic()<deadline and child.poll() is None:
                    if (path/'latest.json').exists():
                        saved=json.loads((path/'latest.json').read_text(encoding='utf-8'))['content']['audit']
                        if saved.get('solver_version')=='1.15.1':break
                    time.sleep(.05)
                self.assertIsNone(child.poll());self.assertIsNotNone(saved)
                self.assertEqual(saved.get('solver_version'),'1.15.1')
                child.kill();child.wait(timeout=10)
                request=frozen_requests(1.)[0];request['config']=replace(request['config'],gap=.03,solver_threads=4)
                request['require']=False
                resumed=solve(**request,checkpoint=path,max_slices=1)
                self.assertLessEqual(resumed.audit['objective'],saved['objective']+1e-5)
                self.assertGreaterEqual(resumed.audit['lower_bound'],saved['lower_bound']-1e-5)
                self.assertTrue(resumed.audit['restored_incumbent'])
            finally:
                if child.poll() is None:child.kill();child.wait(timeout=10)
                child.stderr.close()

    def test_experiments_are_four_dates_and_few_values(self) -> None:
        self.assertEqual(len(DATES), 4)
        values = sample_configs(Config(gap=.03))
        self.assertEqual(set(values), {'S10', 'S30', 'terminal08', 'terminal12', 'M0', 'K0', 'K06', 'K0612'})
        self.assertTrue(all(config.gap == .03 for config in values.values()))


class NodeResumeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.data = read_inputs(ROOT/'outputs/q2/dispatch_runs/20260911_224501')

    def test_day_resumes_after_second_node_crash(self) -> None:
        config = Config(gap=.03)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder); calls = []
            def fail_second(*args, **kwargs):
                calls.append(1)
                if len(calls) == 2: raise RuntimeError('simulated node crash')
                return solve(*args, **kwargs)
            with patch('src.q3.rolling.solve', side_effect=fail_second):
                with self.assertRaisesRegex(RuntimeError, 'simulated node crash'):
                    run_day(self.data, TerminalValues(self.data, config), 7, 6000., config, checkpoint_root=path)
            before = hashlib.sha256((path/'00/executed_block.csv').read_bytes()).hexdigest()
            frame, audit, _ = run_day(self.data, TerminalValues(self.data, config), 7, 6000., config, checkpoint_root=path)
            self.assertTrue(audit['nodes'][0]['solver']['restored_complete_node'])
            self.assertEqual(before, hashlib.sha256((path/'00/executed_block.csv').read_bytes()).hexdigest())
            self.assertEqual(len(frame), 144)

    def test_terminal_one_history_job_persisted(self) -> None:
        config = Config(gap=.03)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'cache.json'
            first = TerminalValues(self.data, config, cache_path=path).marginal(6, 0, 100.)
            with patch('src.q3.terminal.marginal_job', side_effect=AssertionError('already cached')):
                second = TerminalValues(self.data, config, cache_path=path).marginal(6, 0, 100.)
            self.assertEqual(first, second)

    def test_supervisor_restarts_killed_worker(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            master = subprocess.Popen([sys.executable, '-m', 'src.q3.full_run', '--run-dir', str(root),
                '--end-day', '9', '--main-only', '--workers', '1', '--seconds', '3'], cwd=ROOT,
                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            try:
                deadline = time.monotonic()+30
                state = root/'main/state.json'; supervisor = root/'supervisor.json'
                while time.monotonic() < deadline:
                    if state.exists() and len(json.loads(state.read_text(encoding='utf-8'))['days']) >= 7:
                        break
                    if master.poll() is not None: break
                    time.sleep(.01)
                self.assertTrue(state.exists())
                first_pid = json.loads(supervisor.read_text(encoding='utf-8'))['history'][0]['pid']
                prefix = (root/'main/days/2025-01-01.csv').read_bytes()
                os.kill(first_pid, signal.SIGKILL)
                self.assertEqual(master.wait(timeout=40), 0)
                history = json.loads(supervisor.read_text(encoding='utf-8'))['history']
                self.assertGreaterEqual(len(history), 2)
                self.assertEqual(history[0]['return_code'], -signal.SIGKILL)
                self.assertEqual(prefix, (root/'main/days/2025-01-01.csv').read_bytes())
                self.assertEqual(len(json.loads(state.read_text(encoding='utf-8'))['days']), 9)
            finally:
                if master.poll() is None: master.terminate(); master.wait(timeout=15)
                master.stderr.close()


if __name__ == '__main__':
    unittest.main(verbosity=2)
