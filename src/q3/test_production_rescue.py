"""七小时生产救援：节点硬墙、可行门禁、预算映射和恢复。"""
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from dataclasses import replace
from .config import Config,CAP,validate_production_rescue
from .data import Inputs
from .optimization import Solution,LimitedSolve,accept_feasible_incumbent,objective,reached_hard_limit,solve
from .checkpoint import request_digest,save_snapshot
from .physics import Policy,replay
from .rolling import run_day
from .scenarios import Scenarios


def small_case() -> tuple[Scenarios,np.ndarray,Policy]:
    load=np.array([[6000.,8000.,3000.,9000.],[7000.,4000.,8500.,2000.]])
    pv=np.array([[1000.,0.,4000.,0.],[0.,3000.,0.,3500.]])
    scenes=Scenarios(load,pv,np.array([.4,.6]),{})
    policy=Policy(np.array([500.,600.,300.,700.]),np.full(4,CAP),np.full(4,CAP))
    return scenes,np.array([.5,.8,1.1,.6]),policy


class ProductionRescueTests(unittest.TestCase):
    def test_valid_incumbent_accepted_without_faking_certificate(self) -> None:
        scenes,prices,policy=small_case();responses=[replay(policy,path,6000.) for path in scenes.net]
        value=objective(policy,responses,scenes.weights,prices,None,4,.6)
        result=accept_feasible_incumbent(policy,scenes,prices,6000.,Config(production_rescue=True,formulation='legacy'),
            reference=None,today=4,terminal=.6,previous_net=0.,audit={'objective':value,'lower_bound':value-100.,'gap':1.},
            hard_seconds=8.,source='test')
        self.assertTrue(result.audit['accepted']);self.assertFalse(result.audit['reliable'])
        self.assertFalse(result.audit['certificate_met']);self.assertEqual(result.audit['accepted_by'],'hard_limit_feasible')
        self.assertAlmostEqual(result.audit['gap'],100/abs(value))

    def test_invalid_or_missing_incumbent_is_rejected(self) -> None:
        scenes,prices,policy=small_case();config=Config(production_rescue=True,formulation='legacy')
        with self.assertRaises(LimitedSolve):
            accept_feasible_incumbent(None,scenes,prices,6000.,config,reference=None,today=4,terminal=.6,
                                      previous_net=0.,audit={},hard_seconds=8.,source='test')
        with self.assertRaises(LimitedSolve):
            accept_feasible_incumbent(policy,scenes,prices,6000.,config,reference=None,today=4,terminal=.6,
                                      previous_net=0.,audit={'objective':0.,'lower_bound':None},hard_seconds=8.,source='test')
        bad=Policy(policy.grid.copy(),policy.charge_cap.copy(),policy.discharge_cap.copy());bad.grid[0]=-1.
        with self.assertRaises(LimitedSolve):
            accept_feasible_incumbent(bad,scenes,prices,6000.,config,reference=None,today=4,terminal=.6,
                                      previous_net=0.,audit={'objective':0.},hard_seconds=8.,source='test')

    def test_actual_hard_wall_returns_valid_policy(self) -> None:
        scenes,prices,_=small_case();config=Config(production_rescue=True,formulation='legacy',
            gap=1e-9,solver_threads=1,hard_06_seconds=.3,hard_other_seconds=.2)
        started=time.perf_counter();result=solve(scenes,prices,6000.,config,terminal=.6,hard_seconds=.3)
        self.assertTrue(result.audit['accepted']);self.assertIn(result.audit['accepted_by'],('certified_3pct','hard_limit_feasible'))
        self.assertLess(time.perf_counter()-started,3.)
        if 'solver_time_limit' in result.audit:self.assertLessEqual(result.audit['solver_time_limit'],.3)
        for response in result.responses:self.assertEqual(len(response['soc']),4)

    def test_restored_hard_limit_node_skips_optimizer(self) -> None:
        scenes,prices,_=small_case();config=Config(production_rescue=True,formulation='legacy',gap=1e-9,
                                                   hard_06_seconds=.2,hard_other_seconds=.2)
        with tempfile.TemporaryDirectory() as folder:
            checkpoint=Path(folder);policy=small_case()[2]
            responses=[replay(policy,path,6000.) for path in scenes.net]
            value=objective(policy,responses,scenes.weights,prices,None,4,.6)
            accepted=accept_feasible_incumbent(policy,scenes,prices,6000.,config,reference=None,today=4,
                terminal=.6,previous_net=0.,audit={'objective':value,'lower_bound':value-100.},
                hard_seconds=.2,source='initial_test')
            signature=request_digest(config,scenes.load,scenes.pv,scenes.weights,prices,6000.,None,4,.6,0.,None,None,None)
            save_snapshot(checkpoint/'latest.json',signature,accepted.policy,accepted.audit)
            with patch('src.q3.optimization.make_model',side_effect=AssertionError('不得重新求解已接受节点')):
                second=solve(scenes,prices,6000.,config,terminal=.6,hard_seconds=.2,
                             checkpoint=checkpoint,max_slices=None)
            self.assertTrue(second.audit['accepted']);self.assertEqual(second.audit['acceptance_source'],'restored_rescue_checkpoint')

    def test_run_day_maps_35_and_8_second_limits(self) -> None:
        actual=np.zeros((365,144,2));prices=np.ones(144)
        data=Inputs(actual,np.zeros((365,4,24)),prices,{},[],{})
        scenes=Scenarios(np.zeros((1,144)),np.zeros((1,144)),np.ones(1),{})
        calls=[]
        def fake_solve(*args,**kwargs):
            calls.append(kwargs['hard_seconds']);policy=Policy(np.zeros(144),np.zeros(144),np.zeros(144))
            return Solution(policy,[replay(policy,np.zeros(144),args[2])],
                            {'accepted':True,'reliable':False,'accepted_by':'hard_limit_feasible','gap':None})
        terminal=type('Terminal',(),{'value':lambda self,day,hour:(.5,{})})()
        config=Config(production_rescue=True,formulation='legacy',hard_06_seconds=35.,hard_other_seconds=8.)
        with patch('src.q3.rolling.construct',return_value=scenes),patch('src.q3.rolling.solve',side_effect=fake_solve):
            frame,audit,_=run_day(data,terminal,7,6000.,config)
        self.assertEqual(calls,[8.,35.,8.,8.]);self.assertEqual(len(frame),144);self.assertEqual(len(audit['nodes']),4)

    def test_rescue_config_freezes_model_invariants(self) -> None:
        config=Config(production_rescue=True,formulation='legacy',solver_threads=4,gap=.03,
                      hard_06_seconds=35.,hard_other_seconds=8.)
        validate_production_rescue(config)
        self.assertEqual((config.scenarios,config.tail,config.nodes),(20,2,(0,6,12,18)))
        self.assertEqual(config.gap,.03);self.assertEqual(config.formulation,'legacy')
        with self.assertRaises(ValueError):validate_production_rescue(replace(config,scenarios=10))

    def test_only_real_timeout_can_accept_uncertified_policy(self) -> None:
        self.assertTrue(reached_hard_limit({'status':'Time limit reached'},.2,35.))
        self.assertTrue(reached_hard_limit({'status':'searching'},34.96,35.))
        self.assertFalse(reached_hard_limit({'status':'searching'},34.4,35.))
        self.assertFalse(reached_hard_limit({'status':'Interrupted by error'},2.,35.))


if __name__=='__main__':unittest.main(verbosity=2)
