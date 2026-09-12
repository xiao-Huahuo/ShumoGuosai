"""Q3单调等价模型：终端值/调整成本、原反馈投影、原模型最优值对照。"""
import unittest
import numpy as np
from .config import Config,CAP,E_MIN,E_MAX,ETA
from .physics import Policy,replay,adjustment
from .scenarios import Scenarios
from .optimization import solve,objective
from .fast_solver import solve_fast,build_matrix,seed_vector,matrix_error


class FastSolverTests(unittest.TestCase):
    def test_positive_terminal_preserves_monotone_projection(self) -> None:
        rng=np.random.default_rng(48)
        for initial in (E_MIN,6000.,E_MAX):
            for _ in range(24):
                net=rng.uniform(-900,1900,(3,24));prices=rng.uniform(.4,1.4,24);weights=np.full(3,1/3)
                p=Policy(rng.uniform(0,1400,24),np.full(24,CAP),rng.uniform(0,CAP,24))
                reference=rng.uniform(0,1400,18);terminal=float(rng.uniform(.2,1.5))
                raw=[]
                for path in net:
                    e=initial;row={k:[] for k in ('charge','discharge','emergency','spill','soc')}
                    for i,n in enumerate(path):
                        x=n-p.grid[i]
                        r=min(p.discharge_cap[i],max(x,0),ETA*(e-E_MIN))
                        c=rng.uniform(0,1)*min(CAP,max(-x,0),(E_MAX-e)/ETA)
                        e+=ETA*c-r/ETA
                        for k,v in zip(row,(c,r,max(x-r,0),max(-x-c,0),e)):row[k].append(v)
                    raw.append({k:np.array(v) for k,v in row.items()})
                exact=[replay(p,n,initial) for n in net]
                for a,b in zip(raw,exact):
                    self.assertTrue((b['soc']>=a['soc']-1e-8).all())
                    self.assertTrue((b['emergency']<=a['emergency']+1e-8).all())
                self.assertLessEqual(objective(p,exact,weights,prices,reference,18,terminal),
                                     objective(p,raw,weights,prices,reference,18,terminal)+1e-7)

    def test_exact_original_and_compact_optimal_values(self) -> None:
        rng=np.random.default_rng(512)
        for initial in (1200.,6000.,10800.):
            load=rng.uniform(0,11000,(3,5));pv=rng.uniform(0,7000,(3,5));prices=rng.uniform(.4,1.4,5)
            scenes=Scenarios(load,pv,np.array([.2,.3,.5]),{});reference=np.full(3,500.)
            cfg=Config(gap=0.,seconds=20.)
            original=solve(scenes,prices,initial,cfg,reference=reference,today=3,terminal=.6)
            _,_,fast=solve_fast(scenes,prices,initial,cfg,reference=reference,today=3,terminal=.6)
            self.assertTrue(fast['reliable']);self.assertAlmostEqual(original.audit['objective'],fast['objective'],places=5)

    def test_fixed_policy_still_matches_exact_response(self) -> None:
        scenes=Scenarios(np.array([[0.,12000.,400.,10000.],[6000.,300.,10000.,200.]]),
            np.array([[3000.,0.,5000.,0.],[0.,6000.,0.,800.]]),np.array([.4,.6]),{})
        p=Policy(np.array([200.,400.,200.,100.]),np.full(4,100.),np.full(4,200.))
        _,_,info=solve_fast(scenes,np.ones(4),1250.,Config(gap=0,seconds=15),fixed_policy=p,reference=np.full(4,300.),today=2,terminal=.6)
        self.assertTrue(info['reliable']);self.assertLess(info['raw_response_difference'],1e-5)

    def test_full_matrix_accepts_exact_feedback_and_prefix_orders(self) -> None:
        rng=np.random.default_rng(20)
        load=rng.uniform(100,8000,(1,24))+np.arange(5)[:,None]*100
        pv=np.broadcast_to(rng.uniform(0,6000,(1,24)),load.shape).copy()
        scenes=Scenarios(load,pv,np.full(5,.2),{});prices=np.ones(24);ref=np.full(18,500.)
        f,b,integer,c,idx=build_matrix(scenes,prices,6000.,reference=ref,today=18,terminal=.8)
        upper=np.maximum(scenes.net.max(0),0)+CAP
        p=Policy(rng.uniform(0,1,24)*upper,np.full(24,CAP),rng.uniform(0,CAP,24))
        x=seed_vector(p,scenes,prices,6000.,idx,len(f),ref)
        feasibility,integrality=matrix_error(x,b,integer,c)
        self.assertLess(feasibility,1e-5);self.assertEqual(integrality,0.)

    def test_grid_dominance_does_not_change_scenario_soc(self) -> None:
        rng=np.random.default_rng(5);net=rng.uniform(-600,1500,(4,24))
        safe=np.maximum(net.max(0),0)+CAP
        p=Policy(safe+rng.uniform(0,1000,24),rng.uniform(0,CAP,24),rng.uniform(0,CAP,24))
        clipped=Policy(safe,p.charge_cap,p.discharge_cap)
        for path in net:
            old,new=replay(p,path,6000.),replay(clipped,path,6000.)
            np.testing.assert_allclose(old['soc'],new['soc'],atol=1e-8)
            np.testing.assert_allclose(old['emergency'],new['emergency'],atol=1e-8)

    def test_parallel_solver_callback_preserves_negative_objective_certificate(self) -> None:
        rng=np.random.default_rng(421)
        scenes=Scenarios(rng.uniform(500,11000,(5,16)),rng.uniform(0,7000,(5,16)),np.full(5,.2),{})
        prices=rng.uniform(.4,1.4,16);ref=np.full(12,500.);observed=[]
        policy,_,audit=solve_fast(scenes,prices,6000.,Config(gap=.03,seconds=5,solver_threads=4),
            reference=ref,today=12,terminal=1.4,progress=lambda p,r,a:observed.append(a.copy()))
        self.assertIsNotNone(policy);self.assertTrue(observed)
        self.assertEqual(audit['solver_version'],'1.15.1');self.assertEqual(audit['solver_threads'],4)
        self.assertLess(audit['objective'],0.)
        self.assertLessEqual(audit['lower_bound'],audit['objective']+1e-5)
        self.assertLessEqual(audit['linear_feasibility_error'],1e-5)
        self.assertTrue(audit['reliable'])

    def test_invalid_candidate_bounds_rejected_before_matrix_product(self) -> None:
        scenes=Scenarios(np.full((1,3),1000.),np.zeros((1,3)),np.ones(1),{})
        f,b,i,c,_=build_matrix(scenes,np.ones(3),6000.)
        for value in (np.inf,np.nan,1e308):
            errors=matrix_error(np.full(len(f),value),b,i,c)
            self.assertGreater(errors[0],1e-5)


if __name__=='__main__':unittest.main(verbosity=2)
