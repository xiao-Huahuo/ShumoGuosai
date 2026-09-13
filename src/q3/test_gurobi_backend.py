"""同矩阵 Gurobi 后端；未安装或许可证不可用时明确跳过。"""
import importlib.util
import unittest
import numpy as np
from .config import Config, CAP, TOL
from .fast_solver import build_matrix, build_matrix_v2_free, matrix_digest, matrix_error, seed_vector
from .gurobi_backend import license_probe, solve_gurobi_matrix
from .optimization import solve, objective
from .physics import Policy, replay
from .scenarios import Scenarios


PROBE=license_probe() if importlib.util.find_spec('gurobipy') else {'usable':False,'reason':'not_installed'}


@unittest.skipUnless(PROBE.get('usable'),f'Gurobi不可用：{PROBE}')
class GurobiBackendTests(unittest.TestCase):
    def _case(self,initial: float,terminal: float,reference: bool) -> None:
        rng=np.random.default_rng(int(initial+terminal*10))
        scenes=Scenarios(rng.uniform(300,9000,(3,5)),rng.uniform(0,6500,(3,5)),np.array([.2,.3,.5]),{})
        prices=rng.uniform(.4,1.4,5);ref=np.full(3,400.) if reference else None;today=3
        cfg=Config(gap=0.,seconds=15.,formulation='legacy')
        original=solve(scenes,prices,initial,cfg,reference=ref,today=today,terminal=terminal)
        matrix=build_matrix(scenes,prices,initial,reference=ref,today=today,terminal=terminal)
        f,b,integer,c,indices=matrix
        seed=seed_vector(original.policy,scenes,prices,initial,indices,len(f),ref)
        self.assertLessEqual(max(matrix_error(seed,b,integer,c)),TOL)
        before=matrix_digest(f,b,integer,c)
        vector,lower,meta=solve_gurobi_matrix(f,b,integer,c,seed_vector=seed,gap=0.,seconds=15.,threads=1,
            assess=lambda vector,bound:(None,None,{}))
        self.assertEqual(before,matrix_digest(f,b,integer,c))
        policy=Policy(*[np.maximum(vector[indices[key]],0) for key in ('g','cp','rp')])
        responses=[replay(policy,path,initial) for path in scenes.net]
        value=objective(policy,responses,scenes.weights,prices,ref,today,terminal)
        self.assertLessEqual(max(matrix_error(vector,b,integer,c)),1e-5)
        self.assertLessEqual(lower,value+1e-5)
        self.assertAlmostEqual(value,original.audit['objective'],places=5)
        self.assertEqual(meta['solver'],'Gurobi_same_matrix')

    def test_gap_zero_positive_terminal_adjustment_and_initial_states(self) -> None:
        for initial in (1200.,6000.,10800.):
            self._case(initial,.7,True)
        self._case(6000.,0.,False)

    def test_fixed_policy_uses_legacy_matrix_and_seed(self) -> None:
        scenes=Scenarios(np.array([[1000.,9000.],[5000.,3000.]]),np.array([[3000.,0.],[0.,4000.]]),np.array([.4,.6]),{})
        policy=Policy(np.array([200.,400.]),np.array([100.,120.]),np.array([150.,180.]))
        f,b,integer,c,indices=build_matrix(scenes,np.ones(2),6000.,fixed_policy=policy)
        self.assertFalse(indices['free_charge'])
        self.assertGreater(len(indices['cp']),0);self.assertGreater(sum(len(x.ravel()) for x in indices['lc']),0)
        seed=seed_vector(policy,scenes,np.ones(2),6000.,indices,len(f),None)
        self.assertLessEqual(max(matrix_error(seed,b,integer,c)),TOL)
        with self.assertRaises(TypeError):build_matrix_v2_free(scenes,np.ones(2),6000.,fixed_policy=policy)


if __name__=='__main__':unittest.main(verbosity=2)
