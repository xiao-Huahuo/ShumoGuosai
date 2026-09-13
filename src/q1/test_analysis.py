"""新版分析验收：解析边际量、真实情景、独立重算和反向篡改。"""

import copy
import itertools
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from analysis import (active_sets, checked_analysis_csv, local_marginals,
                      rhs_validation, scaled_data, verify_lp)
from export import read_csv
from model import (DT, PHYS_TOL_KWH, COST_TOL_YUAN, ARTIFACT_ROOT, E_MAX, ROOT, SCENARIOS, arrays, build_problem,
                   check_solution, read_inputs, solve, solve_lp, summary)


class MarginalAcceptance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = read_inputs(ARTIFACT_ROOT / 'inputs/raw/attachment1.xlsx')
        cls.raw = json.loads((ARTIFACT_ROOT / 'raw/analysis_solutions.json').read_text(encoding='utf-8'))
        cls.a = json.loads((ARTIFACT_ROOT / 'processed/analysis_summary.json').read_text(encoding='utf-8'))

    def test_all_36_scenarios_and_432_relaxations(self):
        expected = set(itertools.product(SCENARIOS, [-.05,0,.05], [-.05,0,.05]))
        actual = {(r['efficiency_name'],r['load_delta'],r['pv_delta']) for r in self.a['scenarios']}
        self.assertEqual(actual, expected)
        count = 0
        for row in self.a['scenarios']:
            sraw = self.raw['scenarios'][row['scenario']]
            data = scaled_data(self.data,row['load_delta'],row['pv_delta'])
            s = sraw['solution']
            self.assertTrue(check_solution(data,s)['passed'])
            self.assertEqual(active_sets(s), sraw['active_sets'])
            for key,value in summary(data,s).items():
                self.assertAlmostEqual(row[key], value, delta=COST_TOL_YUAN if key == "cost_yuan" else PHYS_TOL_KWH)
            for name,record in sraw['perturbations'].items():
                changed = record['solution']
                self.assertTrue(check_solution(data,changed)['passed'])
                original = s['settings']
                settings = changed['settings']
                changed_keys = [k for k in original if settings[k] != original[k]]
                self.assertEqual(len(changed_keys),1)
                parameter = changed_keys[0]
                self.assertIn(parameter,['e_min','e_max','charge_kw','discharge_kw'])
                step = abs(settings[parameter] - original[parameter])
                values = next(v for v in self.a['bottlenecks'] if v['scenario']==row['scenario']
                              and v['resource']==name.rsplit('_',1)[0] and v['increment']==step)
                saving = s['solver']['objective_yuan'] - changed['solver']['objective_yuan']
                self.assertAlmostEqual(values['value_per_unit_day'],saving/step,delta=PHYS_TOL_KWH)
                self.assertGreaterEqual(saving,-PHYS_TOL_KWH)
                self.assertAlmostEqual(values['increment_period_kwh'],step if parameter in ('e_min','e_max') else step/6,delta=PHYS_TOL_KWH)
                count += 1
        self.assertEqual(count,432)

    def test_nested_baselines_and_analytic_no_ess(self):
        p, load, pv = arrays(self.data)
        s0, spv, sfull = (self.raw[k] for k in ('no_ess','pv_only','full'))
        for s in (s0,spv,sfull):
            self.assertTrue(check_solution(self.data,s)['passed'])
        self.assertAlmostEqual(s0['solver']['objective_yuan'],p @ np.maximum(load-pv,0),delta=PHYS_TOL_KWH)
        self.assertTrue(np.all(np.array(spv['C'])<=np.maximum(pv-load,0)+PHYS_TOL_KWH))
        self.assertTrue(np.all(np.array(spv['D'])<=np.maximum(load-pv,0)+PHYS_TOL_KWH))
        self.assertLessEqual(sfull['solver']['objective_yuan'],spv['solver']['objective_yuan']+PHYS_TOL_KWH)
        b=self.a['benefits']
        self.assertAlmostEqual(b['pv_increment_yuan']+b['flex_increment_yuan'],b['total_saving_yuan'],delta=PHYS_TOL_KWH)

    def test_lp_relaxation_keeps_big_m_coupling(self):
        problem=build_problem(self.data,.9)
        s=self.raw['lp_relaxation']
        x=np.concatenate([s['variables'][v] for v in problem['index']])
        lhs=problem['a']@x
        self.assertTrue(np.all(lhs>=problem['lb']-PHYS_TOL_KWH))
        self.assertTrue(np.all(lhs<=problem['ub']+PHYS_TOL_KWH))
        self.assertTrue(np.all(x>=problem['lower']-PHYS_TOL_KWH))
        self.assertTrue(np.all(x<=problem['upper']+PHYS_TOL_KWH))
        self.assertAlmostEqual(problem['objective']@x,s['objective_yuan'],delta=PHYS_TOL_KWH)
        u=np.array(s['variables']['u']); c=np.array(s['variables']['C']); d=np.array(s['variables']['D'])
        self.assertEqual(self.a['lp_diagnosis']['fractional_modes'],np.sum((u>PHYS_TOL_KWH)&(u<1-PHYS_TOL_KWH)))
        self.assertEqual(self.a['lp_diagnosis']['simultaneous_periods'],np.sum((c>PHYS_TOL_KWH)&(d>PHYS_TOL_KWH)))
        self.assertLessEqual(s['objective_yuan'],self.a['lp_diagnosis']['milp_cost_yuan']+PHYS_TOL_KWH)

    def test_analytic_shadow_sign_and_price_threshold(self):
        # 两时段、首段低价、末段100kWh负荷。初末均6000，充放边界不活跃。
        data=[{'price_yuan_per_kwh':.1,'load_kwh':0.,'pv_kwh':0.,'interval':'00:00-00:10'},
              {'price_yuan_per_kwh':1.,'load_kwh':100.,'pv_kwh':0.,'interval':'00:10-00:20'}]
        s=solve(data,.9)
        rows,problem,result,checks=local_marginals(data,s,'analytic')
        self.assertAlmostEqual(result.fun,100*.1/.81,delta=PHYS_TOL_KWH)
        self.assertAlmostEqual(rows[0]['mu_yuan_per_kwh'],.1,delta=PHYS_TOL_KWH)
        self.assertAlmostEqual(rows[1]['mu_yuan_per_kwh'],.1/.81,delta=PHYS_TOL_KWH)
        self.assertAlmostEqual(rows[0]['lambda_yuan_per_kwh'],.1/.9,delta=PHYS_TOL_KWH)
        self.assertAlmostEqual(rows[1]['lambda_yuan_per_kwh'],.1/.9,delta=PHYS_TOL_KWH)
        self.assertEqual(len(rhs_validation(problem,result)),4)
        bad=copy.deepcopy(result)
        bad.eqlin.marginals *= -1
        with self.assertRaises(ValueError):
            verify_lp(problem,bad)
        # 无效率套利收益时不能强行充放：0.9*.81小于当前价1。
        data[0]['price_yuan_per_kwh']=1.; data[1]['price_yuan_per_kwh']=.9
        no_gain=solve(data,.9)
        self.assertAlmostEqual(sum(no_gain['C']),0,delta=PHYS_TOL_KWH)
        self.assertAlmostEqual(sum(no_gain['D']),0,delta=PHYS_TOL_KWH)

    def test_actual_rhs_slopes_and_local_thresholds(self):
        rows=read_csv(ARTIFACT_ROOT/'processed/marginal_rhs_validation.csv')
        self.assertEqual(len(rows),288)
        self.assertEqual({(r['kind'],int(r['t'])) for r in rows},set(itertools.product(['bus_demand','internal_injection'],range(1,145))))
        for r in rows:
            shadow=float(r['shadow_dJ_db'])
            if r['minus_slope']:
                self.assertLessEqual(float(r['minus_slope']),shadow+PHYS_TOL_KWH)
            if r['plus_slope']:
                self.assertLessEqual(shadow,float(r['plus_slope'])+PHYS_TOL_KWH)
        local=read_csv(ARTIFACT_ROOT/'processed/marginal_values.csv')
        self.assertEqual(len(local),36*144)
        by_key={r['scenario']:r for r in self.a['scenarios']}
        for r in local:
            eta=by_key[r['scenario']]['eta_c']
            self.assertAlmostEqual(float(r['charge_threshold']),eta*float(r['lambda_yuan_per_kwh']),delta=PHYS_TOL_KWH)
            self.assertAlmostEqual(float(r['discharge_threshold']),float(r['lambda_yuan_per_kwh'])/eta,delta=PHYS_TOL_KWH)
            if r['actual_action']=='charge':
                self.assertGreaterEqual(float(r['charge_gain']),-PHYS_TOL_KWH)
            if r['actual_action']=='discharge':
                self.assertGreaterEqual(float(r['discharge_gain']),-PHYS_TOL_KWH)

    def test_full_input_output_csv_and_normalized_sensitivity(self):
        rows=read_csv(ARTIFACT_ROOT/'raw/analysis_schedules.csv')
        self.assertEqual(len(rows),36*144)
        grouped={key:[] for key in self.raw['scenarios']}
        for row in rows:
            grouped[row['scenario']].append(row)
        for case in self.a['scenarios']:
            data=scaled_data(self.data,case['load_delta'],case['pv_delta'])
            s=self.raw['scenarios'][case['scenario']]['solution']
            for i,r in enumerate(grouped[case['scenario']]):
                for k in data[i]:
                    self.assertEqual(r[k],str(data[i][k]))
                for k in ('G','C','D','E','W','u'):
                    self.assertAlmostEqual(float(r[k]), s[k][i], delta=PHYS_TOL_KWH)
        for r in self.a['normalized_sensitivity']:
            self.assertAlmostEqual(r['normalized_sensitivity'],
                                   (r['plus_cost_yuan']-r['minus_cost_yuan'])/(.1*r['base_cost_yuan']),delta=PHYS_TOL_KWH)

    def test_independent_power_limits_and_csv_nonfinite_rejected(self):
        a=build_problem(self.data,.9,charge_kw=5001)
        b=build_problem(self.data,.9,discharge_kw=5001)
        n=len(self.data); u=a['index']['u'][0]
        self.assertAlmostEqual(a['a'][2*n,u],-5001/6,delta=PHYS_TOL_KWH)
        self.assertAlmostEqual(a['a'][3*n,u],5000/6,delta=PHYS_TOL_KWH)
        self.assertAlmostEqual(b['a'][2*n,u],-5000/6,delta=PHYS_TOL_KWH)
        self.assertAlmostEqual(b['a'][3*n,u],5001/6,delta=PHYS_TOL_KWH)
        with tempfile.TemporaryDirectory() as tmp:
            for value in (float('nan'),float('inf')):
                with self.assertRaises(ValueError):
                    checked_analysis_csv(Path(tmp)/'bad.csv',[{'value':value}])


if __name__ == "__main__":
    unittest.main(verbosity=2)
