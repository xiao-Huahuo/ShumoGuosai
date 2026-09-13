"""v2 精确列消元、可达界和矩阵摘要回归。"""
import unittest
import numpy as np
from .config import Config, CAP, E_MIN, E_MAX, TOL
from .fast_solver import (build_matrix,build_matrix_v2_free,build_matrix_v2_2bit,matrix_digest,matrix_error,
                          reachable_bounds,seed_vector,solve_fast)
from .optimization import solve
from .physics import Policy,replay
from .scenarios import Scenarios


class SolverAccelerationTests(unittest.TestCase):
    def test_v2_gap_zero_matches_legacy_on_random_cases(self) -> None:
        rng=np.random.default_rng(9301)
        for case in range(36):
            s=2+case%3;t=3+case%4
            scenes=Scenarios(rng.uniform(0,11000,(s,t)),rng.uniform(0,8000,(s,t)),np.full(s,1/s),{})
            prices=rng.uniform(.35,1.5,t);initial=(E_MIN,6000.,E_MAX)[case%3]
            today=max(1,t-2);reference=rng.uniform(0,800,today);terminal=float(rng.uniform(0,1.4))
            cfg=Config(gap=0.,seconds=20.)
            _,_,legacy=solve_fast(scenes,prices,initial,cfg,reference=reference,today=today,
                                  terminal=terminal,formulation='legacy')
            _,_,v2=solve_fast(scenes,prices,initial,cfg,reference=reference,today=today,
                              terminal=terminal,formulation='v2_free')
            self.assertTrue(legacy['reliable']);self.assertTrue(v2['reliable'])
            self.assertAlmostEqual(legacy['objective'],v2['objective'],places=5)

    def test_v2_removes_only_fixed_columns_and_keeps_binary_count(self) -> None:
        rng=np.random.default_rng(44);s,t=5,12
        scenes=Scenarios(rng.uniform(0,10000,(s,t)),rng.uniform(0,7000,(s,t)),np.full(s,1/s),{})
        old=build_matrix(scenes,np.ones(t),6000.);new=build_matrix_v2_free(scenes,np.ones(t),6000.)
        self.assertEqual(len(old[0])-len(new[0]),t+4*s*t)
        self.assertEqual(int(old[2].sum()),int(new[2].sum()))
        # 删除 c<=cp 的 ST 行；z 等式由 selector 上界行机械替代，故其行数净变化为0。
        self.assertEqual(old[3].A.shape[0]-new[3].A.shape[0],s*t)
        self.assertEqual(len(new[4]['cp']),0);self.assertEqual(len(new[4]['z']),0);self.assertEqual(new[4]['lc'],())

    def test_reachable_bounds_contain_many_original_replays(self) -> None:
        rng=np.random.default_rng(208);checked=0
        for initial in (E_MIN,6000.,E_MAX):
            for _ in range(80):
                net=rng.uniform(-1200,1800,(4,144));upper=np.maximum(net.max(0),0)+CAP
                lo,hi,cu,ru=reachable_bounds(net,upper,initial)
                for _ in range(4):
                    policy=Policy(rng.uniform(0,1,144)*upper,np.full(144,CAP),rng.uniform(0,CAP,144))
                    for j,path in enumerate(net):
                        result=replay(policy,path,initial)
                        self.assertTrue((result['soc']>=lo[j]-TOL).all());self.assertTrue((result['soc']<=hi[j]+TOL).all())
                        self.assertTrue((result['charge']<=cu[j]+TOL).all());self.assertTrue((result['discharge']<=ru[j]+TOL).all())
                        checked+=144
        self.assertEqual(checked,552960)

    def test_seed_and_digest_are_stable_for_edge_cases(self) -> None:
        net=np.array([[0.,100.,-100.,CAP],[CAP,0.,-CAP,100.]])
        load=np.maximum(net,0)*6;pv=np.maximum(-net,0)*6;scenes=Scenarios(load,pv,np.array([.4,.6]),{})
        for initial in (E_MIN,E_MAX):
            matrix=build_matrix_v2_free(scenes,np.ones(4),initial)
            f,b,integer,c,indices=matrix;upper=np.maximum(net.max(0),0)+CAP
            policy=Policy(upper.copy(),np.full(4,CAP),np.full(4,CAP))
            vector=seed_vector(policy,scenes,np.ones(4),initial,indices,len(f),None)
            self.assertLessEqual(max(matrix_error(vector,b,integer,c)),TOL)
            self.assertEqual(matrix_digest(*matrix[:4]),matrix_digest(*matrix[:4]))

    def test_original_exact_small_problem_matches_v2(self) -> None:
        rng=np.random.default_rng(99);scenes=Scenarios(rng.uniform(0,9000,(3,5)),rng.uniform(0,6000,(3,5)),np.array([.2,.3,.5]),{})
        prices=rng.uniform(.4,1.3,5);reference=np.full(3,400.);cfg=Config(gap=0.,seconds=20.)
        exact=solve(scenes,prices,6000.,cfg,reference=reference,today=3,terminal=.5)
        _,_,v2=solve_fast(scenes,prices,6000.,cfg,reference=reference,today=3,terminal=.5,formulation='v2_free')
        self.assertAlmostEqual(exact.audit['objective'],v2['objective'],places=5)

    def test_two_bit_gap_zero_matches_three_selector_v2(self) -> None:
        rng=np.random.default_rng(772)
        for case in range(36):
            s=2+case%3;t=3+case%4
            scenes=Scenarios(rng.uniform(0,10500,(s,t)),rng.uniform(0,7500,(s,t)),np.full(s,1/s),{})
            prices=rng.uniform(.35,1.45,t);initial=(E_MIN,6000.,E_MAX)[case%3]
            today=max(1,t-2);reference=rng.uniform(0,700,today);terminal=float(rng.uniform(0,1.3));cfg=Config(gap=0.,seconds=20.)
            _,_,three=solve_fast(scenes,prices,initial,cfg,reference=reference,today=today,
                                  terminal=terminal,formulation='v2_free')
            _,_,two=solve_fast(scenes,prices,initial,cfg,reference=reference,today=today,
                                terminal=terminal,formulation='v2_2bit')
            self.assertTrue(three['reliable']);self.assertTrue(two['reliable'])
            self.assertAlmostEqual(three['objective'],two['objective'],places=5)

    def test_two_bit_reduces_binary_count_and_accepts_exact_seed(self) -> None:
        rng=np.random.default_rng(663);s,t=5,12
        scenes=Scenarios(rng.uniform(0,10000,(s,t)),rng.uniform(0,7000,(s,t)),np.full(s,1/s),{})
        three=build_matrix_v2_free(scenes,np.ones(t),6000.);two=build_matrix_v2_2bit(scenes,np.ones(t),6000.)
        self.assertEqual(int(three[2].sum())-int(two[2].sum()),s*t)
        self.assertEqual(len(three[0])-len(two[0]),s*t)
        upper=np.maximum(scenes.net.max(0),0)+CAP
        policy=Policy(rng.uniform(0,1,t)*upper,np.full(t,CAP),rng.uniform(0,CAP,t))
        vector=seed_vector(policy,scenes,np.ones(t),6000.,two[4],len(two[0]),None)
        self.assertLessEqual(max(matrix_error(vector,*two[1:4])),TOL)


if __name__=='__main__':unittest.main(verbosity=2)
