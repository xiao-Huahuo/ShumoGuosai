"""需求导向核验：物理恒等式、精确min、未来哨兵、结算、树非前瞻、模板。"""
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest
import numpy as np
import pandas as pd
from .config import Config, ROOT, CAP, E_MIN, E_MAX, E_INITIAL
from .data import read_inputs
from .physics import Policy, replay, adjustment, no_storage_decision
from .scenarios import Scenarios, construct, medoids, reduce_errors, pool_indices
from .optimization import solve, LimitedSolve
from .terminal import TerminalValues
from .rolling import run_day, run_period, fiv, validate_frame, previous_net
from .multistage import conditional_tree, solve_tree, tree_inputs
from .export import export_workbook, summaries, emergency_events


class MathTests(unittest.TestCase):
    def test_incumbent_gradient_matches_finite_difference(self) -> None:
        from .incumbent import value_gradient
        rng = np.random.default_rng(2)
        net = rng.uniform(-500, 1500, (4, 8)); prices = rng.uniform(.4, 1., 8); weights = np.full(4, .25)
        vector = rng.uniform(20, 700, 24); reference = rng.uniform(200, 500, 4)
        value, gradient = value_gradient(vector, net, prices, weights, 6000., reference, 4, .6)
        for i in range(24):
            positive = vector.copy(); positive[i] += 1e-4
            negative = vector.copy(); negative[i] -= 1e-4
            numerical = (value_gradient(positive, net, prices, weights, 6000., reference, 4, .6)[0]-value_gradient(negative, net, prices, weights, 6000., reference, 4, .6)[0])/2e-4
            self.assertAlmostEqual(gradient[i], numerical, places=5)

    def test_energy_balance_saturation(self) -> None:
        rng = np.random.default_rng(87)
        for initial in (E_MIN, E_INITIAL, E_MAX):
            for mode in ('aggregate', 'lag'):
                policy = Policy(rng.uniform(0, 1500, 144), rng.uniform(0, CAP, 144), rng.uniform(0, CAP, 144))
                result = replay(policy, rng.uniform(-1000, 2000, 144), initial, mode=mode, previous_net=10.)
                self.assertTrue(np.all(np.minimum(result['charge'], result['discharge']) == 0))

    def test_lag_does_not_observe_current(self) -> None:
        policy = Policy(np.array([0., 0.]), np.full(2, CAP), np.full(2, CAP))
        a = replay(policy, np.array([200., -200.]), 6000., mode='lag', previous_net=-100.)
        b = replay(policy, np.array([500., -900.]), 6000., mode='lag', previous_net=-100.)
        self.assertEqual(a['charge'][0], b['charge'][0])
        self.assertEqual(a['discharge'][0], 0)
        self.assertGreater(a['emergency'][0], 200)  # 上一负荷触发充电，当期缺口由紧急购电同时平衡。

    def test_settlement_cancellation_and_repeated_proxy(self) -> None:
        g0 = np.array([100., 100., 100.]); p = np.ones(3)
        effective = np.array([80., 100., 140.])
        np.testing.assert_allclose(adjustment(effective, g0, p), [-10., 0., 60.])
        old = np.array([200., 50., 100.])
        final = adjustment(effective, g0, p)
        sequential = adjustment(old, g0, p)+adjustment(effective, old, p)
        self.assertFalse(np.allclose(final, sequential))

    def test_no_storage_deadband(self) -> None:
        demand, weights = np.arange(1., 101.), np.full(100, .01)
        self.assertEqual(no_storage_decision(demand, 80., weights), 80.)
        self.assertIn(no_storage_decision(demand, 1., weights), (70., 71.))
        self.assertIn(no_storage_decision(demand, 100., weights), (90., 91.))

    def test_reduction_probability_tail_original_support(self) -> None:
        errors = np.random.default_rng(1).normal(size=(30, 12))
        errors[29] += 40; errors[28] += 20
        indices, weights, audit = reduce_errors(errors, np.ones(12), Config(scenarios=10, tail=2))
        self.assertTrue({28, 29}.issubset(indices)); self.assertEqual(len(indices), 10)
        self.assertEqual(len(np.unique(indices)), 10)
        self.assertAlmostEqual(weights.sum(), 1.)
        self.assertTrue((weights > 0).all())
        self.assertEqual(sum(audit['represented_counts']), 30)

    def test_no_artificial_samples(self) -> None:
        indices, weights, _ = reduce_errors(np.ones((3, 12)), np.ones(12), Config())
        np.testing.assert_array_equal(indices, [0, 1, 2]); np.testing.assert_allclose(weights, [1/3]*3)

    def test_recent_then_expand_and_condition(self) -> None:
        days = np.arange(80)
        indices, audit = pool_indices(days, np.arange(80.), 100, 79., Config())
        self.assertEqual(audit['window'], 56)
        self.assertTrue((days[indices] >= 44).all())
        self.assertGreaterEqual(len(indices), 20)

    def test_exact_milp_matches_fixed_min(self) -> None:
        # 同时覆盖不同净缺口符号、SOC容量约束和每种响应上限；不可用自由场景recourse蒙混。
        load = np.array([[0., 12000., 400., 10000.], [6000., 300., 10000., 200.]])
        pv = np.array([[3000., 0., 5000., 0.], [0., 6000., 0., 800.]])
        scene = Scenarios(load, pv, np.array([.4, .6]), {})
        fixed = Policy(np.array([200., 400., 200., 100.]), np.array([100., 500., 300., 700.]), np.array([700., 200., 800., 50.]))
        for mode in ('aggregate', 'lag'):
            solved = solve(scene, np.array([.5, .8, 1., .3]), 1250., Config(seconds=15, feedback=mode),
                           fixed=fixed, reference=np.full(4, 300.), today=2, terminal=.2, previous_net=-100.)
            self.assertLessEqual(solved.audit['mapping_error'], 1e-5)
            self.assertTrue(solved.audit['reliable'])

    def test_solution_objective_uses_residual_not_real_cost(self) -> None:
        scene = Scenarios(np.full((1, 8), 1000.), np.zeros((1, 8)), np.ones(1), {})
        result = solve(scene, np.ones(8), E_INITIAL, Config(seconds=5), terminal=.5)
        real_cost = np.sum(result.policy.grid+5*result.responses[0]['emergency'])
        self.assertAlmostEqual(result.audit['objective'], real_cost-.5*result.responses[0]['soc'][-1], places=5)

    def test_tree_conditioning_and_uncertainty(self) -> None:
        revisions = np.random.default_rng(4).normal(size=(24, 3, 18))
        labels, nodes = conditional_tree(revisions)
        self.assertTrue((labels[:, 0] == 0).all())
        for node in nodes[1:]:
            parent = nodes[node['parent']]
            self.assertTrue(set(node['members']).issubset(parent['members']))
            self.assertGreaterEqual(len(node['members']), 2)
            self.assertLessEqual(len([x for x in nodes if x['parent'] == node['parent']]), 2)
        for stage in range(4):
            self.assertAlmostEqual(sum(node['probability'] for node in nodes if node['stage'] == stage), 1.)

    def test_actual_small_multistage_solve(self) -> None:
        revisions = np.random.default_rng(3).normal(size=(8, 3, 3))
        labels, nodes = conditional_tree(revisions)
        net = np.random.default_rng(5).uniform(10, 100, size=(8, 8))
        result = solve_tree(net, labels, nodes, net.max(0)+CAP, np.ones(8), 6000., .8, Config(seconds=20))
        self.assertTrue(result['audit']['reliable'])
        self.assertLessEqual(result['audit']['mapping_error'], 1e-5)


class RealDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.data = read_inputs(ROOT/'outputs/q2/dispatch_runs/20260911_224501')

    def test_origin_alignment_and_nodes(self) -> None:
        for hour in (0, 6, 12, 18):
            p = self.data.pv(31, hour)
            np.testing.assert_allclose(p[5::6], self.data.hourly[31, hour//6])
            self.assertAlmostEqual(p[0], 5/6*self.data.observation(31, hour)+self.data.hourly[31, hour//6, 0]/6)
        with self.assertRaises(ValueError):
            self.data.observation(0, 0)

    def test_48h_predictor_identity_frozen(self) -> None:
        before = self.data.load(31)
        for hour in (0, 6, 12, 18):
            scenes = construct(self.data, 31, hour, Config())
            self.assertEqual(scenes.audit['predictor'], self.data.selected[31])
        np.testing.assert_array_equal(self.data.load(31), before)
        self.assertEqual(len(before), 288)

    def test_future_poison_not_used_by_node(self) -> None:
        original = self.data.actual.copy()
        before = construct(self.data, 70, 12, Config())
        try:
            self.data.actual.reshape(-1, 2)[70*144+72:] = 1e10
            after = construct(self.data, 70, 12, Config())
            np.testing.assert_array_equal(before.net, after.net)
            self.assertEqual(before.audit, after.audit)
        finally:
            self.data.actual[:] = original

    def test_completed_trajectory_horizon(self) -> None:
        for hour in (0, 6, 12, 18):
            scenes = construct(self.data, 31, hour, Config())
            for j in scenes.audit['history_days']:
                self.assertLess(j, 31)
                self.assertLessEqual(j*144+hour*6+144, 31*144+hour*6)
            self.assertLessEqual(len(scenes.weights), 20)

    def test_pchip_preserves_hourly_knots(self) -> None:
        np.testing.assert_allclose(self.data.pv(171, 6, 'pchip')[5::6], self.data.hourly[171, 1])
        self.assertTrue((self.data.pv(171, 6, 'pchip') >= 0).all())

    def test_terminal_causal_and_delta_stability(self) -> None:
        value = TerminalValues(self.data, Config(seconds=10))
        coefficient, audit = value.value(8, 0)
        self.assertGreater(coefficient, 0)
        self.assertTrue(all(row['complete_at_slot'] <= 8*144 for row in value.cache.values()))
        rows = value.stability(6, 0)
        self.assertTrue(all(row['value'] >= 0 for row in rows))

    def test_real_day_rollout_and_template(self) -> None:
        config = Config(seconds=15, deterministic=True)
        terminal = TerminalValues(self.data, config)
        first, audit, _ = run_day(self.data, terminal, 7, E_INITIAL, config)
        second, _, _ = run_day(self.data, terminal, 8, float(first.soc.iloc[-1]), config)
        frame = pd.concat([first, second], ignore_index=True)
        validate_frame(frame, config)
        self.assertEqual([node['hour'] for node in audit['nodes']], [0, 6, 12, 18])
        self.assertTrue(all(len(node['grid']) == 144 for node in audit['nodes']))
        with tempfile.TemporaryDirectory() as folder:
            result = export_workbook(frame, Path(folder), config, smoke=True)
            self.assertTrue(result['roundtrip_all_sheets'])
            with self.assertRaises(ValueError):
                export_workbook(frame, Path(folder), config)
            # 零紧急事件是合法结果，空事件表仍须可回填与回读。
            net = first.net_kwh.to_numpy()
            first['grid'] = first['g0'] = np.maximum(net, 0)
            first['charge_cap'] = first['discharge_cap'] = 0.
            recovered = replay(Policy(first.grid.to_numpy(), np.zeros(144), np.zeros(144)), net, E_INITIAL)
            for key, values in recovered.items():
                first[key] = values
            first['planned_cost'] = first.price*first.g0
            first['adjustment_cost'] = first['emergency_cost'] = 0.
            first['total_cost'] = first.planned_cost
            self.assertEqual(len(emergency_events(first)), 0)
            self.assertTrue(export_workbook(first, Path(folder), config, smoke=True)['roundtrip_all_sheets'])

    def test_cold_start_no_future_or_soc_reset(self) -> None:
        config = Config()
        terminal = TerminalValues(self.data, config)
        frame, audit, _ = run_day(self.data, terminal, 0, E_INITIAL, config)
        self.assertTrue(audit['cold_start'])
        np.testing.assert_array_equal(frame.soc, np.full(144, E_INITIAL))
        self.assertEqual(frame.charge.sum()+frame.discharge.sum()+frame.g0.sum(), 0.)

    def test_fiv_common_support_and_state_independence(self) -> None:
        config = Config(seconds=15, deterministic=True)
        terminal = TerminalValues(self.data, config)
        reference = np.ones(108)*500
        row, records = fiv(self.data, terminal, 31, 6, 6000., reference, config)
        self.assertEqual(row['audits'][0]['scenarios']['length'], 108)
        self.assertEqual(row['audits'][1]['scenarios']['length'], 108)
        self.assertEqual(row['initial_soc'], 6000.)
        self.assertAlmostEqual(row['FIV_block'], sum(records[0]['real_cost'][:36])-sum(records[1]['real_cost'][:36]))
        np.testing.assert_array_equal(reference, np.ones(108)*500)

    def test_resume_keeps_prefix_and_rejects_tamper(self) -> None:
        config = Config(seconds=15, deterministic=True)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            run_period(self.data, config, root, end=9, with_fiv=False)
            before = (root/'days/2025-01-08.csv').read_bytes()
            run_period(self.data, config, root, end=9, with_fiv=False)
            self.assertEqual(before, (root/'days/2025-01-08.csv').read_bytes())
            (root/'audit/2025-01-08.json').write_text('{}', encoding='utf-8')
            with self.assertRaises(ValueError):
                run_period(self.data, config, root, end=9, with_fiv=False)

    def test_sequential_reoptimization_and_ouv_sets(self) -> None:
        for settlement in ('final', 'sequential'):
            for nodes in ((0,), (0, 6), (0, 6, 12), (0, 6, 12, 18)):
                config = Config(seconds=15, deterministic=True, nodes=nodes, settlement=settlement)
                frame, audit, _ = run_day(self.data, TerminalValues(self.data, config), 8, 6000., config)
                self.assertEqual(len(audit['nodes']), len(nodes))
                self.assertEqual(sum(node['committed_slots'] for node in audit['nodes']), 144)
                validate_frame(frame, config)
                if settlement == 'sequential':
                    version = frame.g0.to_numpy().copy(); cost = np.zeros(144)
                    for node in audit['nodes'][1:]:
                        start = node['hour']*6; current = np.array(node['grid'][:144-start])
                        cost[start:] += adjustment(current, version[start:], self.data.prices[start:])
                        version[start:] = current
                    np.testing.assert_allclose(frame.adjustment_cost, cost, atol=1e-5)


if __name__ == '__main__':
    unittest.main(verbosity=2)
