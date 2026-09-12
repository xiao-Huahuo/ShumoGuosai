"""最终方案核心验收：手算、未来扰动、MILP精确映射、经验概率和信息边界。"""

import unittest

import numpy as np

from optimization import build_model, solve_policy
from policy import CAP, E_MIN, E_MAX, Policy, replay, respond
from scenarios import (construct, eligible_origins, history_window, joint_blocks,
                       medoids, weighted_quantile)


class PolicyTests(unittest.TestCase):
    def test_load_priority_and_soc_clipping(self):
        c, r, q, w, e = respond(1000, E_MIN+100, 0, CAP, CAP)
        np.testing.assert_allclose((c, r, q, w, e), (0, 90, 910, 0, E_MIN))
        np.testing.assert_allclose(respond(-1000, E_MAX-90, 0, CAP, CAP), (100, 0, 0, 900, E_MAX))
        np.testing.assert_allclose(respond(200, 6000, 200, CAP, CAP), (0, 0, 0, 0, 6000))

    def test_frozen_parameters_and_causal_prefix(self):
        policy = Policy([0, 20, 40, 0], [CAP]*4, [CAP]*4)
        with self.assertRaises(ValueError):
            policy.grid[0] = 500
        first = replay(policy, [500, -200, 600, 800], 6000)
        changed = replay(policy, [500, -200, -10000, -10000], 6000)
        for key in first:
            np.testing.assert_array_equal(first[key][:2], changed[key][:2])

    def test_soc_piecewise_execution_boundary(self):
        cp = np.array([[0, 100, 200]])
        policy = Policy([0], cp, cp)
        self.assertEqual(replay(policy, [-300], 4400)["charge"][0], 100)
        self.assertEqual(replay(policy, [-300], 7600)["charge"][0], 200)

    def test_exact_indicator_mapping_fixed_random_paths(self):
        random = np.random.default_rng(23)
        net = random.uniform(-700, 1400, (3, 12))
        policy = Policy(random.uniform(0, 400, 12), random.uniform(0, CAP, 12), random.uniform(0, CAP, 12))
        for soc in (E_MIN, 6000, E_MAX):
            solved, responses, info = solve_policy(net, np.ones(12), np.ones(3)/3, soc,
                                                   fixed_policy=policy, gap=1e-8, time_limit=15)
            self.assertTrue(info["reliable"], info)
            self.assertLess(info["mapping_error_kwh"], 1e-5)
            for path, actual in zip(net, responses):
                expected = replay(policy, path, soc)
                for key in expected:
                    np.testing.assert_allclose(actual[key], expected[key], atol=1e-5)

    def test_no_storage_optimizer_is_eighty_percent_quantile(self):
        net = np.array([[0.], [10.], [30.], [100.], [300.]])
        weights = np.array([.1, .3, .3, .2, .1])
        model, variables = build_model(net, [1.], weights)
        model.addCons(variables["cp"][0] == 0)
        model.addCons(variables["rp"][0] == 0)
        model.optimize()
        self.assertEqual(str(model.getStatus()), "optimal")
        grid = model.getVal(variables["g"][0])
        self.assertAlmostEqual(grid, 100)
        self.assertAlmostEqual(model.getObjVal(), 200)
        model.freeProb()

    def test_unfixed_policy_replay_matches_solver(self):
        n = np.array([[100, 1000, -500, 300], [150, 500, -100, 400.]])
        _, _, info = solve_policy(n, [.4, 1, .4, 1], [.5, .5], time_limit=15, gap=1e-8)
        self.assertTrue(info["reliable"])
        self.assertAlmostEqual(info["objective"], 1000-CAP)
        self.assertAlmostEqual(info["objective"], info["optimizer_objective"])


class ScenarioTests(unittest.TestCase):
    def test_no_bootstrap_below_forty_and_physical_projection(self):
        blocks = np.zeros((14, 2, 144, 2))
        blocks[:, :, :, 0] = np.arange(14)[:, None, None]-20
        blocks[:, :, :, 1] = 60
        net, weights, meta = construct(np.zeros((2, 144, 2)), blocks, np.ones(288), count=10)
        self.assertEqual(meta["S"], 14)
        self.assertFalse(meta["reduced"])
        np.testing.assert_allclose(weights, np.ones(14)/14)
        np.testing.assert_allclose(net, -10)

    def test_weighted_quantile_uses_discrete_probability(self):
        self.assertEqual(weighted_quantile(np.array([0., 10, 20]), [.1, .6, .3], .8), 20)

    def test_tail_protection_and_cluster_probability(self):
        random = np.random.default_rng(19)
        blocks = random.normal(size=(45, 1, 144, 2))
        blocks[-1, :, :, 0] = 1000
        indices, weights, meta = medoids(blocks, np.ones(144), 10)
        self.assertIn(44, indices)
        self.assertEqual(len(set(indices)), 10)
        np.testing.assert_allclose(weights*45, np.bincount(meta["cluster_assignment"]), atol=1e-12, rtol=0)
        self.assertAlmostEqual(weights.sum(), 1)

    def test_complete_origin_horizon_and_window_fallback(self):
        shadows = np.full((80, 3, 144, 2), np.nan)
        shadows[14:45] = 0
        origins, window = history_window(shadows, 65, 3)
        self.assertEqual(window, 56)
        self.assertTrue(np.all(origins+3 <= 65))
        self.assertEqual(eligible_origins(shadows, 31, 3).tolist(), list(range(14, 29)))
        history = np.broadcast_to(np.arange(80)[:, None, None], (80, 144, 2)).copy()
        blocks = joint_blocks(history, shadows, [14, 15], 3)
        np.testing.assert_array_equal(blocks[0, :, 0, 0], [14, 15, 16])


if __name__ == "__main__":
    unittest.main()
