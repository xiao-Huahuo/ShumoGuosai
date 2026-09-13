"""精度修订的传递、断点保留和错误协议隔离。"""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from execution import execution_settings
from full_run import worker
from policy import Policy
from protocol import PROTOCOL, signature
from rolling import ComputationalLimit, _solve, run_rollout


class ExecutionTests(unittest.TestCase):
    def revision(self, root, **changes):
        value = {"solver_gap": .02, "parent_protocol_sha256": signature(), "authorization": "test"}
        path = root/"raw/solver_precision_revision.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({**value, **changes}), encoding="utf-8")

    def test_revision_does_not_mutate_frozen_protocol_and_reaches_worker(self):
        original = signature()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(execution_settings(root), {})
            for gap in (.02, .03):
                self.revision(root, solver_gap=gap)
                settings = execution_settings(root)
                with patch("experiments.run_experiments", return_value={"horizon_1": {"complete": True}}) as run:
                    self.assertEqual(worker(root, "horizon_1", "a", "receipt.json"), 0)
                self.assertEqual(run.call_args.kwargs["solver_gap"], gap)
                self.assertEqual(run.call_args.kwargs["execution_revision"], settings["execution_revision"])
        self.assertEqual(PROTOCOL["solver_gap"], .01)
        self.assertEqual(signature(), original)

    def test_mismatched_unauthorized_or_nonfinite_revision_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for change in ({"parent_protocol_sha256": "wrong"}, {"authorization": ""},
                           {"solver_gap": float("nan")}, {"solver_gap": .001}, {"solver_gap": True}):
                with self.subTest(change=change):
                    self.revision(root, **change)
                    with self.assertRaises(ValueError):
                        execution_settings(root)

    def test_gap_reaches_both_solvers_and_certificate_without_changing_scenarios(self):
        net = np.ones((2, 3)); prices = np.ones(3); weights = np.array([.4, .6])
        policy = Policy(np.ones(3), np.zeros(3), np.zeros(3))
        bound = {"certified_gap": .025, "incumbent_cost": 3., "lower_bound": 2.9}
        with patch("rolling.deterministic_policy", return_value=(policy, [], {})), \
                patch("rolling.recourse_bound", return_value=(policy, [], bound)) as lower, \
                patch("rolling.solve_policy", return_value=(policy, [], {})) as native, \
                patch("linear_policy.solve_linear_policy", return_value=(policy, [], {})) as linear, \
                patch("rolling.certify_policy", return_value=(policy, [], {})) as certificate:
            _solve(net, prices, weights, 6000, solver_gap=.01)
            self.assertEqual(native.call_args.kwargs["gap"], .01)
            self.assertIs(native.call_args.args[0], net)
            _, _, info = _solve(net, prices, weights, 6000, solver_gap=.02)
            self.assertEqual(linear.call_args.kwargs["time_limit"], 120)
            self.assertEqual(info["execution_role"], "original_budget_equivalent_MILP_under_authorized_precision_revision")
            _solve(net, prices, weights, 6000, solver_gap=.02, solver_seconds=900)
            self.assertEqual(linear.call_args.kwargs["gap"], .02)
            self.assertEqual(linear.call_args.kwargs["time_limit"], 900)
            self.assertIs(linear.call_args.args[2], weights)
            _solve(net, prices, weights, 6000, solver_gap=.03)
            self.assertEqual(lower.call_args.kwargs["target_gap"], .03)
            self.assertEqual(certificate.call_args.args[-1], .03)

    def test_fixed_and_segmented_policies_retain_native_solver(self):
        policy = Policy(np.ones(3), np.zeros(3), np.zeros(3))
        bound = {"certified_gap": .03, "incumbent_cost": 3., "lower_bound": 2.9}
        with patch("rolling.deterministic_policy", return_value=(policy, [], {})), \
                patch("rolling.recourse_bound", return_value=(policy, [], bound)), \
                patch("rolling.solve_policy", return_value=(policy, [], {})) as native, \
                patch("linear_policy.solve_linear_policy") as linear:
            for options in ({"segments": 3}, {"fixed_policy": policy}):
                _solve(np.ones((2, 3)), np.ones(3), np.array([.4, .6]), 6000,
                       solver_gap=.02, solver_seconds=900, **options)
                for key, value in options.items():
                    self.assertIs(native.call_args.kwargs[key], value)
            linear.assert_not_called()

    def test_relaxed_resume_preserves_old_day_and_records_new_gap_and_failures(self):
        actual = np.zeros((34, 144, 2)); dates = pd.date_range("2025-01-01", periods=34)
        seen = []
        def solve(store, frozen, history, d, prices, soc, **settings):
            gap = settings["solver_gap"]; seconds = settings.get("solver_seconds", 120)
            seen.append((d, len(history), gap, seconds))
            if d == 32 and (gap == .01 or seconds == 120):
                raise ComputationalLimit({"failed_gap": gap})
            return Policy(np.zeros(144), np.zeros(144), np.zeros(144)), np.ones(1), np.zeros((1, 144)), np.zeros((1, 144, 2)), {
                "selected_K": 1, "computational_limited": False,
                "1": {"M": 14, "selected_solver": {"reliable": True, "requested_gap": gap, "mip_gap": 0.}}}
        with tempfile.TemporaryDirectory() as tmp, patch("rolling.make_day", side_effect=solve):
            root = Path(tmp)
            with self.assertRaises(ComputationalLimit):
                run_rollout({}, 0, actual, dates, np.ones(144), 6000, root, rescue_seconds=900)
            old_audit = (root/"daily_audit/2025-02-01.json").read_bytes()
            old_plan = (root/"frozen_plans/2025-02-01.csv").read_bytes()
            seen.clear()
            frame, _ = run_rollout({}, 0, actual, dates, np.ones(144), 6000, root,
                                   rescue_seconds=900, solver_gap=.02, execution_revision="verified")
            self.assertEqual(seen, [(32, 32, .02, 120), (32, 32, .02, 900), (33, 33, .02, 120)])
            self.assertEqual(frame.date.nunique(), 3)
            self.assertEqual(old_audit, (root/"daily_audit/2025-02-01.json").read_bytes())
            self.assertEqual(old_plan, (root/"frozen_plans/2025-02-01.csv").read_bytes())
            status = json.loads((root/"run_status.json").read_text(encoding="utf-8"))
            self.assertEqual(status["execution"]["gap"], .02)
            self.assertEqual(status["execution_history"][0]["execution"]["gap"], .01)
            self.assertEqual(status["execution_history"][0]["completed_days"], 1)
            new = json.loads((root/"daily_audit/2025-02-02.json").read_text(encoding="utf-8"))
            self.assertEqual(new["original_budget_failure"], {"failed_gap": .02})
            self.assertTrue(list((root/"failed_attempts").glob("previous_status_*.json")))
            with self.assertRaisesRegex(ValueError, "更严格精度"):
                run_rollout({}, 0, actual, dates, np.ones(144), 6000, root, rescue_seconds=900)

    def test_second_precision_transition_keeps_both_prior_prefixes(self):
        actual = np.zeros((34, 144, 2)); dates = pd.date_range("2025-01-01", periods=34)
        def solve(store, frozen, history, day, prices, soc, **settings):
            gap = settings["solver_gap"]
            if (day >= 32 and gap < .02) or (day >= 33 and gap < .03):
                raise ComputationalLimit({"failed_gap": gap})
            return Policy(np.zeros(144), np.zeros(144), np.zeros(144)), np.ones(1), np.zeros((1, 144)), np.zeros((1, 144, 2)), {
                "selected_K": 1, "computational_limited": False,
                "1": {"M": 14, "selected_solver": {"reliable": True, "requested_gap": gap, "mip_gap": 0.}}}
        with tempfile.TemporaryDirectory() as tmp, patch("rolling.make_day", side_effect=solve):
            root = Path(tmp)
            for gap in (.01, .02):
                with self.assertRaises(ComputationalLimit):
                    run_rollout({}, 0, actual, dates, np.ones(144), 6000, root,
                                solver_gap=gap, execution_revision=str(gap))
            preserved = {str(path.relative_to(root)): path.read_bytes()
                         for folder in ("daily_audit", "frozen_plans") for path in (root/folder).iterdir()}
            frame, _ = run_rollout({}, 0, actual, dates, np.ones(144), 6000, root,
                                   solver_gap=.03, execution_revision="three-percent")
            self.assertEqual(frame.date.nunique(), 3)
            for name, raw in preserved.items():
                self.assertEqual((root/name).read_bytes(), raw)
            status = json.loads((root/"run_status.json").read_text(encoding="utf-8"))
            self.assertEqual(status["execution"]["gap"], .03)
            self.assertEqual([x["execution"]["gap"] for x in status["execution_history"]], [.01, .02])
            self.assertEqual([x["completed_days"] for x in status["execution_history"]], [1, 2])


if __name__ == "__main__":
    unittest.main()
