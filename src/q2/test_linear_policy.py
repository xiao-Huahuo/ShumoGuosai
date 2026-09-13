"""有界线性MILP与原生indicator模型及原始min/max映射的独立等价验收。"""

import unittest

import numpy as np

from linear_policy import build_linear_policy, linear_seed, solve_linear_policy
from optimization import solve_policy
from policy import CAP, E_MIN, E_MAX, ETA_C, ETA_D, Policy, replay


class LinearPolicyTests(unittest.TestCase):
    def test_undercharging_matrix_paths_project_to_original_feedback_without_cost_increase(self):
        rng = np.random.default_rng(2719)
        difference = 0.
        for soc in (E_MIN, 1538.0615848778116, 6000., E_MAX):
            for _ in range(8):
                net, prices = rng.uniform(-2200, 2500, (3, 144)), rng.uniform(.2, 1.2, 144)
                policy = Policy(rng.uniform(0, CAP, 144), np.full(144, CAP), rng.uniform(0, CAP, 144))
                objective, bounds, integer, constraints, indices = build_linear_policy(
                    net, prices, np.full(3, 1/3), soc)
                vector = np.zeros(len(objective))
                for key, values in (("g", policy.grid), ("cp", policy.charge_cap), ("rp", policy.discharge_cap)):
                    vector[indices[key]] = values
                for j, path in enumerate(net):
                    previous, raw = soc, []
                    for i, n in enumerate(path):
                        x = n-policy.grid[i]
                        vector[indices["reserve_active"][j, i]] = int(previous >= E_MIN+policy.reserve[i])
                        if x >= 0:
                            terms = [policy.discharge_cap[i], x, ETA_D*(previous-E_MIN)]
                            c, r = 0., min(terms)
                            q, w = x-r, 0.
                            vector[indices["z"][j, i]] = 1
                            vector[indices["lr"][int(np.argmin(terms))][j, i]] = 1
                        else:
                            c = rng.uniform(0, 1)*min(policy.charge_cap[i], -x, (E_MAX-previous)/ETA_C)
                            r, q, w = 0., 0., -x-c
                        previous += ETA_C*c-r/ETA_D
                        raw.append([c, r, q, w, previous])
                    raw = np.asarray(raw)
                    for columns, values in zip(indices["responses"], raw.T):
                        vector[columns[j]] = values
                    exact = replay(policy, path, soc)
                    self.assertTrue(np.all(exact["soc"] >= raw[:, 4]-1e-5))
                    self.assertTrue(np.all(exact["emergency"] <= raw[:, 2]+1e-5))
                    self.assertLessEqual(prices@exact["emergency"], prices@raw[:, 2]+1e-5)
                    difference = max(difference, float(np.max(np.abs(exact["soc"]-raw[:, 4]))))
                activity = constraints.A@vector
                self.assertTrue(np.all(activity <= constraints.ub+1e-5))
                self.assertTrue(np.all(activity >= constraints.lb-1e-5))
                self.assertTrue(np.all(vector >= bounds.lb-1e-5))
                self.assertTrue(np.all(vector <= bounds.ub+1e-5))
                np.testing.assert_array_equal(vector[integer == 1], np.rint(vector[integer == 1]))
        self.assertGreater(difference, 1.)

    def test_dynamic_reserve_linear_native_and_replay_are_equivalent(self):
        net = np.array([[500., 300., 900., -200.], [700., 100., 600., -300.]])
        prices, weights = np.array([.4, .9, .7, .3]), np.array([.4, .6])
        reserve = np.array([300., 200., 100., 0.])
        initial = E_MIN+250
        linear_policy, linear_responses, linear = solve_linear_policy(
            net, prices, weights, initial, reserve=reserve, gap=1e-7, time_limit=15)
        native_policy, native_responses, native = solve_policy(
            net, prices, weights, initial, reserve=reserve, gap=1e-7, time_limit=15)
        self.assertTrue(linear["reliable"] and native["reliable"])
        np.testing.assert_allclose(linear["objective"], native["objective"], atol=1e-4, rtol=1e-7)
        np.testing.assert_array_equal(linear_policy.reserve, reserve)
        np.testing.assert_array_equal(native_policy.reserve, reserve)
        for policy, responses in ((linear_policy, linear_responses), (native_policy, native_responses)):
            for path, response in zip(net, responses):
                expected = replay(policy, path, initial)
                for key in expected:
                    np.testing.assert_allclose(response[key], expected[key], atol=1e-5)

    def test_monotone_certificate_is_distinct_from_fixed_policy_exact_mapping(self):
        net = np.array([[-600., 900., 400.], [-300., 1100., 200.]])
        prices, weights = np.array([.3, .9, .7]), np.array([.4, .6])
        policy, _, free = solve_linear_policy(net, prices, weights, E_MIN, time_limit=15)
        self.assertTrue(free["reliable"] and free["mapped_policy_cost_not_above_raw_objective"])
        self.assertTrue(free["monotone_charge_bound"])
        self.assertIsNone(free["mapping_error_kwh"])
        for key in ("monotone_projection_error_kwh", "linear_feasibility_error", "integrality_error"):
            self.assertLessEqual(free[key], 1e-5)
        _, _, fixed = solve_linear_policy(net, prices, weights, E_MIN, fixed_policy=policy, time_limit=15)
        self.assertTrue(fixed["reliable"])
        self.assertFalse(fixed["monotone_charge_bound"])
        self.assertIsNone(fixed["monotone_projection_error_kwh"])
        self.assertLessEqual(fixed["mapping_error_kwh"], 1e-5)

    def test_branch_cuts_preserve_complete_fixed_policy_trajectories(self):
        rng = np.random.default_rng(7216)
        for soc in (E_MIN, 1538.0615848778116, 6000., E_MAX):
            for _ in range(8):
                net = rng.uniform(-2200, 2500, (3, 144))
                policy = Policy(*[rng.uniform(0, CAP, 144) for _ in range(3)])
                objective, bounds, _, constraints, indices = build_linear_policy(
                    net, np.ones(144), np.full(3, 1/3), soc, fixed_policy=policy)
                vector = linear_seed(policy, net, soc, indices, len(objective))
                activity = constraints.A@vector
                self.assertTrue(np.all(activity <= constraints.ub+1e-5))
                self.assertTrue(np.all(activity >= constraints.lb-1e-5))
                self.assertTrue(np.all(vector >= bounds.lb-1e-5))
                self.assertTrue(np.all(vector <= bounds.ub+1e-5))

    def test_maximum_charge_cap_dominates_for_each_realized_step(self):
        rng = np.random.default_rng(20260912)
        for soc in (E_MIN, 1462.9246853535594, 6000., E_MAX):
            for _ in range(8):
                net, grid = rng.uniform(-2000, 2500, 144), rng.uniform(0, 1200, 144)
                original = Policy(grid, rng.uniform(0, CAP, 144), rng.uniform(0, CAP, 144))
                raised = Policy(grid, np.full(144, CAP), original.discharge_cap)
                before, after = replay(original, net, soc), replay(raised, net, soc)
                self.assertTrue(np.all(after["soc"] >= before["soc"]-1e-5))
                self.assertTrue(np.all(after["emergency"] <= before["emergency"]+1e-5))

    def test_dominance_presolve_transforms_seed_but_preserves_fixed_policy(self):
        net = np.array([[-600., 900., 400.], [-300., 1100., 200.]])
        prices, weights = np.array([.3, .9, .7]), np.array([.4, .6])
        seed = Policy(np.zeros(3), np.zeros(3), np.full(3, CAP))
        optimized, _, info = solve_linear_policy(net, prices, weights, E_MIN,
                                                 seed_policy=seed, time_limit=15)
        self.assertTrue(info["reliable"] and info["maximum_charge_cap_dominance_presolve"])
        np.testing.assert_array_equal(optimized.charge_cap, np.full(3, CAP))
        fixed, responses, fixed_info = solve_linear_policy(net, prices, weights, E_MIN,
                                                           fixed_policy=seed, seed_policy=seed, time_limit=15)
        self.assertTrue(fixed_info["reliable"])
        self.assertFalse(fixed_info["maximum_charge_cap_dominance_presolve"])
        np.testing.assert_array_equal(fixed.charge_cap, seed.charge_cap)
        for path, response in zip(net, responses):
            np.testing.assert_allclose(response["emergency"], replay(seed, path, E_MIN)["emergency"], atol=1e-5)

    def test_optima_match_indicator_model_at_three_initial_states(self):
        rng = np.random.default_rng(31)
        prices, weights = np.array([.3, .9, .8, .2, .7, .4]), np.array([.2, .3, .5])
        for soc in (E_MIN, 6000., E_MAX):
            with self.subTest(initial_soc=soc):
                net = rng.uniform(-900, 1500, (3, 6))
                _, _, linear = solve_linear_policy(net, prices, weights, soc, gap=1e-7, time_limit=15)
                _, _, native = solve_policy(net, prices, weights, soc, gap=1e-7, time_limit=15)
                self.assertTrue(linear["reliable"] and native["reliable"])
                np.testing.assert_allclose(linear["objective"], native["objective"], atol=1e-4, rtol=1e-7)

    def test_complete_causal_seed_satisfies_every_linear_row(self):
        net = np.array([[-600., 900., 0., 1200.], [400., -300., -900., 500.]])
        seed = Policy(np.array([50., 100., 0., 200.]), np.full(4, 400.), np.full(4, 700.))
        _, _, info = solve_linear_policy(net, np.array([.3, .9, .2, .7]), np.array([.4, .6]), E_MAX,
                                         seed_policy=seed, time_limit=15)
        self.assertTrue(info["seed_verified"] and info["reliable"])
        self.assertEqual(info["solver_version"], "1.8.0")
        _, _, native = solve_policy(net, np.array([.3, .9, .2, .7]), np.array([.4, .6]), E_MAX, time_limit=15)
        np.testing.assert_allclose(info["objective"], native["objective"], atol=1e-5, rtol=0)

    def test_fixed_policy_exactly_matches_clipping_and_has_no_emergency_charging(self):
        net = np.array([[-600., -100., 400., 1100., 200., -900.], [200., 400., -300., 700., -1200., 0.]])
        policy = Policy(np.array([50., 70., 200., 300., 50., 200.]),
                        np.array([200., 0., 400., 200., 800., 600.]), np.array([150., 300., 700., 150., 0., 700.]))
        for soc in (E_MIN, E_MAX):
            _, responses, info = solve_linear_policy(net, np.ones(6), np.array([.5, .5]), soc,
                                                      fixed_policy=policy, gap=1e-7, time_limit=15)
            self.assertTrue(info["reliable"])
            for path, response in zip(net, responses):
                expected = replay(policy, path, soc)
                for key in expected:
                    np.testing.assert_allclose(response[key], expected[key], atol=1e-5, rtol=0)
                self.assertFalse(((response["emergency"] > 1e-5)&(response["charge"] > 1e-5)).any())
            self.assertLess(info["mapping_error_kwh"], 1e-5)

    def test_fixed_policy_cannot_invalidate_derived_activation_bounds(self):
        policy = Policy(np.full(2, 10000.), np.zeros(2), np.zeros(2))
        with self.assertRaisesRegex(ValueError, "物理上界"):
            solve_linear_policy(np.zeros((1, 2)), np.ones(2), np.ones(1), 6000., fixed_policy=policy)


if __name__ == "__main__":
    unittest.main()
