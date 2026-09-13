"""基准复用的完整轨迹、输入等价与非覆盖验收。"""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from baseline_reuse import reuse_main_baseline, window_inputs_match
from checkpoint import atomic_json, save_checkpoint
from policy import Policy
from rolling import dispatch_frame


class BaselineReuseTests(unittest.TestCase):
    def test_full_year_initial_baseline_copies_exact_committed_results(self):
        dates = pd.date_range("2025-01-01", periods=365)
        actual = np.zeros((365, 144, 2)); prices = np.ones(144)
        policy = Policy(np.zeros(288), np.zeros(288), np.zeros(288))
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp); main = run/"processed/main"; main.mkdir(parents=True)
            (main/"daily_audit").mkdir(); (main/"frozen_plans").mkdir()
            frames, daily, calibration = [], [], []
            for d in range(31, 365):
                date = str(dates[d].date())
                frames.append(dispatch_frame(dates[d], policy, np.zeros(144), 6000, prices))
                daily.append({"date": date, "initial_soc": 6000., "final_soc": 6000., "cost": 0., "emergency_kwh": 0.})
                for h in range(min(2, 365-d)):
                    for nominal in (.8, .9):
                        calibration.append({"origin": date, "horizon": h, "nominal": nominal, "covered_intervals": 144, "n": 144})
                atomic_json(main/f"daily_audit/{date}.json", {"selected_K": 2, "2": {"selected_solver": {"reliable": True}}})
                pd.DataFrame({"grid": policy.grid, "charge_cap": policy.charge_cap, "discharge_cap": policy.discharge_cap}).to_csv(
                    main/f"frozen_plans/{date}.csv", index=False, encoding="utf-8")
            atomic_json(main/"run_status.json", {"complete": True, "settings": {}, "start_index": 31, "end_index": 365,
                                                "execution": {"gap": .03}, "execution_history": [{"execution": {"gap": .02}}]})
            save_checkpoint(main, pd.concat(frames, ignore_index=True), daily, calibration)
            self.assertTrue(reuse_main_baseline(run, "initial_6000", {}, 0, actual, dates, prices, 6000))
            target = run/"processed/experiments/initial_6000"
            for name in ("dispatch.csv", "daily.csv", "calibration.csv", "checkpoint.json", "run_status.json",
                         "daily_audit/2025-02-01.json", "frozen_plans/2025-12-31.csv"):
                self.assertEqual((main/name).read_bytes(), (target/name).read_bytes())
            provenance = json.loads((target/"baseline_reuse.json").read_text(encoding="utf-8"))
            self.assertEqual(provenance["days"], 334)
            self.assertEqual(provenance["extra_MILP_solves"], 0)
            self.assertFalse(reuse_main_baseline(run, "initial_6000", {}, 0, actual, dates, prices, 6000))
            self.assertFalse(reuse_main_baseline(run, "initial_1200", {}, 0, actual, dates, prices, 6000))

    def test_window_reuse_checks_all_pipeline_scores_and_causal_history(self):
        dates = pd.date_range("2025-01-01", periods=34)
        selection = {"pipeline": ["chosen"], "window_days": 28, "scores": {"chosen": 1., "other": 2.}}
        with tempfile.TemporaryDirectory() as tmp:
            main = Path(tmp)
            atomic_json(main/"daily_audit/2025-02-01.json", {"2": {"selection": selection}})
            for changed in (False, True):
                def choose(store, frozen, history, day, k, prices, **kwargs):
                    self.assertEqual(len(history), day)
                    metadata = json.loads(json.dumps(selection))
                    if changed and kwargs.get("window") == 28:
                        metadata["scores"]["other"] = 3.
                    return np.zeros((k, 144, 2)), np.zeros((1, k, 144, 2)), metadata
                with patch("baseline_reuse.choose_day", side_effect=choose):
                    self.assertEqual(window_inputs_match({}, 0, np.zeros((34, 144, 2)), dates,
                                                         np.ones(144), main, 31, 32), not changed)

    def test_incomplete_or_different_main_settings_cannot_be_reused(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp)
            for value in ({"complete": False, "settings": {}}, {"complete": True, "settings": {"horizon": 3}}):
                atomic_json(run/"processed/main/run_status.json", value)
                self.assertFalse(reuse_main_baseline(run, "initial_6000", {}, 0, None, None, None, 6000))


if __name__ == "__main__":
    unittest.main()
