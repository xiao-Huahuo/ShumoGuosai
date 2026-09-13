import unittest,json
import numpy as np
from dataclasses import replace
from .common import RUN,comparison,digest
from .q3 import base_config,scenarios_for
from .run import design

class Tests(unittest.TestCase):
    def test_core_design_and_no_baseline_resolve(self):
        jobs=design();self.assertEqual(len(jobs),32);self.assertEqual(len({j['id'] for j in jobs}),32)
        self.assertEqual({j['value'] for j in jobs if j['parameter']=='S'},{10,28})
        self.assertFalse(any(j['value']==1 for j in jobs if j['parameter'] in ('beta_R','lambda_E')))
    def test_zero_emergency_baseline_is_not_percent(self):
        r=comparison({'total_cost':105,'emergency_kwh':2},{'total_cost':100,'emergency_kwh':0})
        self.assertEqual(r['delta_cost_pct'],5);self.assertIsNone(r['delta_emergency_pct']);self.assertEqual(r['delta_emergency_kwh'],2)
    def test_representatives_are_four_unique_and_frozen(self):
        r=json.loads((RUN/'representatives.json').read_text())
        for q in ('q2','q3'):self.assertEqual(len({x['date'] for x in r[q]}),4)
        self.assertTrue(r['rules_frozen_before_experiments'])
    def test_q2_scaling_and_tail_fixed_reserve(self):
        from .q2 import construct
        for folder in (RUN/'inputs/q2').iterdir():
            a=np.load(folder/'frozen.npz');m=json.loads((folder/'metadata.json').read_text())
            for b in [.8,1.2]:
                r=a['reserve']*b;np.testing.assert_array_equal(r[144:],a['reserve'][144:]);self.assertTrue((r<9600).all())
            for frac in [.1,.3]:
                net,w,meta=construct(a['point'],a['blocks'],a['prices'],m['S'],origins=a['origins'],all_blocks=a['all_blocks'],all_origins=a['all_origins'],tail_fraction=frac)
                self.assertEqual(len(net),26);self.assertEqual(meta['S_body']+meta['S_tail'],26);self.assertAlmostEqual(w.sum(),1)
    def test_q3_scenario_size_does_not_change_pool(self):
        config=base_config()
        for folder in (RUN/'inputs/q3').iterdir():
            for h in (0,6,12,18):
                a=np.load(folder/f'{h:02d}.npz');before=digest(a['history_days'],a['load_errors'],a['pv_errors'])
                for n in (10,20,28):
                    scenes=scenarios_for(a,replace(config,scenarios=n));self.assertEqual(len(scenes.weights),n)
                    self.assertTrue(set(scenes.audit['history_days']).issubset(set(a['history_days'])))
                    self.assertAlmostEqual(scenes.weights.sum(),1)
                self.assertEqual(before,digest(a['history_days'],a['load_errors'],a['pv_errors']))
    def test_terminal_only_perturbation_leaves_scenarios_unchanged(self):
        config=base_config()
        folder=next((RUN/'inputs/q3').iterdir());a=np.load(folder/'06.npz')
        original=scenarios_for(a,config)
        for scale in [.8,1.2]:
            scenes=scenarios_for(a,replace(config,terminal_scale=scale))
            for key in ['load','pv','weights']:np.testing.assert_array_equal(getattr(original,key),getattr(scenes,key))

if __name__=='__main__':unittest.main()
