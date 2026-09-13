"""紧急修复的公式与失效路径回归测试；真实连续回放另由vertical_slice执行。"""
import argparse
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
import pandas as pd
from .config import Config, E_MIN, ROOT
from .data import Inputs
from .price import Forecasts
from .physics import DispatchPolicy, replay, scenario_costs
from .optimization import build_matrix, solve, solve_dual, LimitedSolve
from .scenarios import Scenarios, _reduce
from .rolling import run_period
from .run import settings
from .diagnostics import sanity_metrics, write_window_policy


class RescueTests(unittest.TestCase):
    def scenario(self, radius=0):
        return Scenarios(np.array([[100.,120,80,50],[130.,140,90,70]]),
                         np.ones((2,4)), np.array([.6,.4]), np.array([[0.,1.],[1.,0.]]), radius,{})

    def test_zero_integer_and_shared_storage_variables(self):
        obj, bounds, integer, con, ids, _ = build_matrix(self.scenario(), E_MIN)
        self.assertEqual(integer.sum(), 0)
        for key in ('g','c','r','E'):
            self.assertEqual(ids[key].shape,(4,))
        self.assertEqual(ids['x'].shape,(2,4))
        self.assertEqual(ids['alpha'].shape,(2,))

    def test_soc_roundoff_at_both_boundaries(self):
        for initial in (1200.-1e-10,10800.+1e-10):
            result=solve_dual(self.scenario(),initial,Config())
            self.assertTrue(result.audit['reliable'])
        for initial in (1200.-1e-3,10800.+1e-3):
            with self.assertRaises(ValueError):
                build_matrix(self.scenario(),initial)

    def test_infinite_bound_roundoff_reproducer(self):
        from .optimization import dual_bound
        from scipy.optimize import Bounds, LinearConstraint
        from scipy.sparse import csr_matrix
        saved=np.load(ROOT/'docs/4/rescue_lp/dual_roundoff_reproducer.npz')
        bounds=Bounds(saved['col_lower'],saved['col_upper'])
        con=LinearConstraint(csr_matrix((len(saved['row_lower']),len(saved['col_lower']))),saved['row_lower'],saved['row_upper'])
        value,error=dual_bound(saved['row_dual'],saved['col_dual'],con,bounds)
        self.assertAlmostEqual(value,10769.494225926748,places=6)
        self.assertLess(error,1e-8)
        changed=saved['row_dual'].copy();changed[5212]=1e-3
        _,invalid=dual_bound(changed,saved['col_dual'],con,bounds)
        self.assertGreater(invalid,1e-8)

    def test_failure_audit_remains_json_serializable(self):
        import json
        error=LimitedSolve({'status':'failed','lower_bound':-np.inf,'nested':[np.nan]})
        self.assertIsNone(error.audit['lower_bound'])
        json.dumps(error.audit,allow_nan=False)

    def test_four_slot_hand_balance(self):
        policy=DispatchPolicy(np.array([100.,100,100,0]), np.array([10.,0,0,0]),np.array([0.,20,0,0]))
        out=replay(policy,np.array([120.,50,-10,30]),6000)
        np.testing.assert_allclose(out['called'],[100,30,0,0])
        np.testing.assert_allclose(out['emergency'],[30,0,0,30])
        np.testing.assert_allclose(out['spill'],[0,0,10,0])
        np.testing.assert_allclose(out['soc'],6000+np.cumsum([9,-20/.9,0,0]))

    def test_rho_zero_equals_hand_expected_cost(self):
        # 恒价、初始下界，无跨时段套利：80%分位数逐时取高需求。
        scenario=self.scenario()
        solution=solve_dual(scenario,E_MIN,Config())
        self.assertAlmostEqual(solution.audit['objective'],430.,places=5)
        costs=scenario_costs(solution.policy,solution.responses,scenario.prices)
        self.assertAlmostEqual(solution.audit['objective'],float(scenario.weights@costs),places=6)

    def test_positive_radius_matches_two_point_hand_worst_case(self):
        scenario=self.scenario(.1)
        solution=solve_dual(scenario,E_MIN,Config())
        costs=np.asarray(solution.audit['scenario_costs'])
        empirical=float(scenario.weights@costs)
        expected=empirical+.1*abs(costs[1]-costs[0])
        self.assertAlmostEqual(solution.audit['objective'],expected,places=5)

    def test_adjustment_matrix_three_cases_and_continuation(self):
        # 强制g为指定增购/减购/不变，第四段跨日，手工结算350+40=390。
        scenario=Scenarios(np.zeros((1,4)),np.ones((1,4)),np.ones(1),np.zeros((1,1)),0,{})
        with patch('src.q4.optimization.build_matrix', wraps=build_matrix) as builder:
            original=build_matrix
            def fixed(*args,**kwargs):
                obj,bounds,integer,con,ids,offset=original(*args,**kwargs)
                bounds.lb[ids['g']]=[150,50,100,40];bounds.ub[ids['g']]=[150,50,100,40]
                return obj,bounds,integer,con,ids,offset
            builder.side_effect=fixed
            sol=solve_dual(scenario,6000,Config(),reference=np.full(3,100.),today=3)
        self.assertAlmostEqual(sol.audit['objective'],390.,places=5)

    def test_residual_origin_48h_and_midnight(self):
        actual=np.arange(365*144,dtype=float).reshape(365,144)
        forecasts=np.arange(365*288,dtype=float).reshape(365,288)*.3
        data=Inputs(None,actual,Forecasts(forecasts,np.zeros_like(actual),{}),{})
        for hour,length in ((0,288),(6,144),(12,144),(18,144)):
            start=20*144+hour*6
            expected=actual.ravel()[start:start+length]-forecasts[20,hour*6:hour*6+length]
            np.testing.assert_array_equal(data.price_residual_path(20,hour,length,cutoff=10000),expected)
            old=forecasts[21].copy();forecasts[21]+=99999
            np.testing.assert_array_equal(data.price_residual_path(20,hour,length,cutoff=10000),expected)
            forecasts[21]=old
        with self.assertRaises(ValueError):
            data.price_residual_path(20,0,288,cutoff=21*144)

    def test_tail_never_absorbs_ordinary_mass(self):
        net=np.tile(np.arange(20,dtype=float)[:,None],(1,4));price=net.copy()
        prior=np.arange(1,21,dtype=float);prior/=prior.sum()
        reps,labels,weights,_,audit=_reduce(net,price,prior,Config(scenarios=5))
        for tail in audit['tail_indices_in_pool']:
            column=list(reps).index(tail)
            self.assertAlmostEqual(weights[column],prior[tail])
            self.assertEqual(int((labels==column).sum()),1)
        self.assertAlmostEqual(weights.sum(),1)

    def test_formal_limited_forbidden_before_inputs_and_output(self):
        for mode in ('4-2','4-3'):
            with tempfile.TemporaryDirectory() as d, self.assertRaisesRegex(ValueError,'allow_limited'):
                run_period(None,mode,Config(allow_limited=True),Path(d))
        with self.assertRaisesRegex(ValueError,'allow-limited'):
            settings(argparse.Namespace(command='q42',allow_limited=True))

    def test_hard_timeout_has_no_fallback(self):
        with self.assertRaises(LimitedSolve) as context:
            solve(self.scenario(),6000,Config(hard_timeout=.001))
        self.assertEqual(context.exception.audit['status'],'hard_timeout')
        self.assertFalse(context.exception.audit['reliable'])

    def test_limited_solver_rejected_even_with_allow_flag(self):
        with self.assertRaises(LimitedSolve):
            solve_dual(self.scenario(),6000,Config(seconds=1e-9,allow_limited=True))

    def test_baseline_alarm_and_storage_alarm(self):
        frame=pd.DataFrame({key:[1.] for key in ('grid','called','unused','emergency','charge','discharge','spill')})
        frame['total_cost']=116.;frame['soc']=10800.
        metrics=sanity_metrics(frame,100.)
        self.assertFalse(metrics['economic_pass']);self.assertFalse(metrics['storage_pass'])
        frame['total_cost']=100;frame['soc']=6000
        self.assertTrue(sanity_metrics(frame,100.)['economic_pass'])

    def test_window_is_declared_preset(self):
        with tempfile.TemporaryDirectory() as d:
            audit=write_window_policy(Path(d))
        self.assertEqual(audit['selected_window'],56)
        self.assertFalse(audit['calibration_performed'])


if __name__=='__main__':
    unittest.main()
