"""延迟K1必须保留全部可选结果下的旧选择规则与失败隔离。"""

import itertools
import unittest
from unittest.mock import patch

import numpy as np

from policy import Policy
from rolling import ComputationalLimit, make_day


class HorizonExecutionTests(unittest.TestCase):
    def test_every_candidate_availability_and_stability_case(self):
        for flags in itertools.product((False, True), repeat=3):
            for stable in (False, True):
                available = {k for k, reliable in enumerate(flags, 1) if reliable}
                called = []
                policies = {k: Policy(np.full(k*144, 1. if k != 2 or stable else 2.),
                                      np.zeros(k*144), np.zeros(k*144)) for k in (1, 2, 3)}

                def choose(store, frozen, history, day, k, prices, **settings):
                    return np.zeros((k, 144, 2)), None, {"common_scored_origins": []}

                def solve(point, blocks, prices, soc, **settings):
                    k = len(point); called.append(k)
                    if k not in available:
                        raise ComputationalLimit({"K": k})
                    return policies[k], [{"emergency": np.zeros(k*144)}], np.ones(1), np.zeros((1, k*144)), {
                        "M": 14, "selected_solver": {"reliable": True}, "computational_limited": False}

                with self.subTest(available=available, stable=stable), \
                        patch("rolling.choose_day", side_effect=choose), \
                        patch("rolling.select_resolution", side_effect=solve):
                    if not available:
                        with self.assertRaises(ComputationalLimit):
                            make_day({}, 0, None, 31, np.ones(144), 6000)
                    else:
                        policy, _, _, _, audit = make_day({}, 0, None, 31, np.ones(144), 6000)
                        expected = 2 if {2, 3}.issubset(available) and stable else max(available)
                        self.assertIs(policy, policies[expected])
                        self.assertEqual(audit["selected_K"], expected)
                        self.assertEqual(audit["computational_limited"], not {2, 3}.issubset(available))
                        self.assertEqual("skipped_K1" in audit, bool(available.intersection({2, 3})))
                    self.assertEqual(called, [2, 3] if available.intersection({2, 3}) else [2, 3, 1])

    def test_fixed_K1_is_still_executed_for_sensitivity(self):
        policy = Policy(np.ones(144), np.zeros(144), np.zeros(144))
        with patch("rolling.choose_day", return_value=(np.zeros((1, 144, 2)), None, {"common_scored_origins": []})) as choose, \
                patch("rolling.select_resolution", return_value=(policy, [{"emergency": np.zeros(144)}],
                      np.ones(1), np.zeros((1, 144)), {"M": 14, "selected_solver": {"reliable": True}})):
            result = make_day({}, 0, None, 31, np.ones(144), 6000, horizon=1)
        self.assertEqual(choose.call_args.args[4], 1)
        self.assertIs(result[0], policy)
        self.assertNotIn("skipped_K1", result[-1])


if __name__ == "__main__":
    unittest.main()
