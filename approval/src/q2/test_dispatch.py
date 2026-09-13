"""最终方案核心验收：手算、未来扰动、MILP精确映射、经验概率和信息边界。"""

import unittest

import numpy as np

from optimization import build_model, solve_policy
from policy import CAP, E_MIN, E_MAX, Policy, replay, respond
from scenarios import (construct, cumulative_pressure, dynamic_reserve, eligible_origins,
                       history_window, joint_blocks, medoids, weighted_quantile)


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

    def test_dynamic_reserve_only_blocks_discharge_and_never_recharges(self):
        reserve = 200.
        actual = respond(500, E_MIN+100, 0, CAP, CAP, reserve)
        np.testing.assert_allclose(actual, (0, 0, 500, 0, E_MIN+100))
        policy = Policy([0], [CAP], [CAP], [reserve])
        replayed = replay(policy, [500], E_MIN+100)
        self.assertEqual(replayed["charge"][0], 0)
        self.assertEqual(replayed["discharge"][0], 0)
        self.assertEqual(replayed["emergency"][0], 500)

    def test_indicator_model_and_replay_share_dynamic_reserve(self):
        policy = Policy([0., 0.], [0., 0.], [CAP, CAP], [200., 0.])
        net = np.array([[500., 500.]])
        _, responses, info = solve_policy(
            net, np.ones(2), np.ones(1), E_MIN+100,
            fixed_policy=policy, gap=1e-8, time_limit=15)
        self.assertTrue(info["reliable"], info)
        expected = replay(policy, net[0], E_MIN+100)
        for key in expected:
            np.testing.assert_allclose(responses[0][key], expected[key], atol=1e-5)
        np.testing.assert_allclose(responses[0]["emergency"], [500., 410.])

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
    def test_cumulative_pressure_and_dynamic_reserve_use_kwh_paths(self):
        blocks = np.zeros((5, 1, 144, 2))
        blocks[:, 0, 0, 0] = 6*np.arange(5)
        np.testing.assert_allclose(cumulative_pressure(blocks), np.arange(5))
        reserve, meta = dynamic_reserve(blocks, .8)
        self.assertAlmostEqual(reserve[0], 3/.9)
        np.testing.assert_array_equal(reserve[1:], np.zeros(143))
        self.assertEqual(meta["historical_blocks"], 5)

    def test_tail_strata_preserve_count_origins_and_probability_mass(self):
        local = np.zeros((5, 1, 144, 2))
        all_blocks = np.zeros((10, 1, 144, 2))
        all_blocks[:, 0, 0, 0] = 6*np.arange(10)
        net, weights, meta = construct(
            np.zeros((1, 144, 2)), local, np.ones(144),
            origins=np.arange(100, 105), all_blocks=all_blocks,
            all_origins=np.arange(100, 110))
        self.assertEqual((len(net), meta["S_body"], meta["S_tail"]), (5, 4, 1))
        self.assertEqual(meta["tail_origin_indices"], [109])
        self.assertAlmostEqual(weights[-1], .2)
        self.assertAlmostEqual(weights[:-1].sum(), .8)
        self.assertAlmostEqual(weights.sum(), 1)

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

    def test_tail_stratification_does_not_increase_reduced_scenario_count(self):
        rng = np.random.default_rng(20260912)
        blocks = rng.normal(size=(45, 1, 144, 2))
        net, weights, meta = construct(np.zeros((1, 144, 2)), blocks, np.ones(144), count=10)
        self.assertEqual((len(net), len(weights), meta["S"]), (10, 10, 10))
        self.assertEqual((meta["S_body"], meta["S_tail"]), (8, 2))

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
