"""全量队列的故障隔离、重启识别与完成收据；合成数据只在临时目录。"""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from checkpoint import atomic_json
from full_run import (DEPENDENT, LEGACY_OR_DEVELOPMENT_ONLY, eligible,
                      experiment_category, guard_memory, job_names, read, reconcile, worker)


class FullRunTests(unittest.TestCase):
    def test_repeated_crash_isolated_after_three_attempts(self):
        with tempfile.TemporaryDirectory() as tmp:
            job = {"status": "running", "attempt": "crash", "receipt": "absent.json", "pid": 123}
            with patch("full_run.owned_process", return_value=False):
                for i in range(3):
                    job["status"] = "running"
                    reconcile(Path(tmp), {"main": job})
                    self.assertEqual(job["status"], "pending" if i < 2 else "failed")

    def test_memory_guard_only_stops_largest_verified_worker(self):
        import subprocess
        with tempfile.TemporaryDirectory() as tmp:
            jobs = {name: {"status": "running", "attempt": name, "receipt": name+".json", "pid": i+100}
                    for i, name in enumerate(("small", "large", "unrelated"))}
            with patch("full_run.owned_process", side_effect=lambda job: job["attempt"] != "unrelated"), \
                    patch("full_run.subprocess.run", side_effect=[subprocess.CompletedProcess([], 0, "5000000"),
                                                                  subprocess.CompletedProcess([], 0, "6000000")]), \
                    patch("full_run.terminate_worker") as kill:
                guard_memory(Path(tmp), jobs)
            self.assertEqual(kill.call_args.args[0], 101)
            self.assertEqual(kill.call_count, 1)
            self.assertFalse((Path(tmp)/"small.json").exists())
            self.assertFalse(read(Path(tmp)/"large.json")["complete"])

    def test_failed_main_keeps_independent_jobs_and_blocks_dependencies(self):
        self.assertEqual(job_names(6000.), ["main"])
        self.assertEqual(experiment_category("main"), "required_for_paper")
        self.assertEqual(experiment_category("forecast"), "optional_diagnostics")
        self.assertEqual(experiment_category("horizon_1"), "legacy_or_development_only")
        jobs = {name: {"status": "pending"} for name in job_names(
            6000., include_optional=True, include_legacy=True)}
        self.assertTrue(set(LEGACY_OR_DEVELOPMENT_ONLY).issubset(jobs))
        jobs["main"]["status"] = "failed"
        jobs["window_28"]["requires_main"] = True
        jobs["initial_6000"]["requires_main"] = True
        self.assertTrue(eligible(jobs))
        self.assertFalse(DEPENDENT.intersection(eligible(jobs)))
        self.assertNotIn("window_28", eligible(jobs))
        self.assertNotIn("initial_6000", eligible(jobs))
        self.assertIn("initial_1200", eligible(jobs))
        jobs["main"]["status"] = "complete"
        self.assertTrue(DEPENDENT.issubset(eligible(jobs)))
        self.assertIn("window_28", eligible(jobs))

    def test_restart_preserves_live_worker_and_requeues_only_interrupted_job(self):
        with tempfile.TemporaryDirectory() as tmp:
            jobs = {name: {"status": "running", "attempt": name, "receipt": name+".json", "pid": i+1}
                    for i, name in enumerate(("live", "interrupted", "failed", "done"))}
            for name, complete in (("failed", False), ("done", True)):
                atomic_json(Path(tmp)/(name+".json"), {"attempt": name, "job": name, "complete": complete,
                                                       "finished": "test", "exit_code": 0 if complete else 2})
            with patch("full_run.owned_process", side_effect=lambda job: job["attempt"] == "live"):
                reconcile(Path(tmp), jobs)
            self.assertEqual([jobs[name]["status"] for name in jobs], ["running", "pending", "failed", "complete"])

    def test_failure_receipt_does_not_claim_success_or_prevent_next_job(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            with patch("experiments.run_experiments", return_value={"horizon_1": {"complete": False}}):
                self.assertEqual(worker(path, "horizon_1", "a", "receipt/a.json"), 2)
            self.assertFalse(read(path/"receipt/a.json")["complete"])
            with patch("experiments.run_experiments", return_value={"horizon_2": {"complete": True}}) as run:
                self.assertEqual(worker(path, "horizon_2", "b", "receipt/b.json"), 0)
                self.assertIsNone(run.call_args.kwargs["rescue_seconds"])
            self.assertTrue(read(path/"receipt/b.json")["complete"])


if __name__ == "__main__":
    unittest.main()
