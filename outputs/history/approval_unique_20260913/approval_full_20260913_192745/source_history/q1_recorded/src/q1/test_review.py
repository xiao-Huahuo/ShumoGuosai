"""CR-01–13回归：新鲜实算、解析解、文件篡改与故障注入。"""

import copy
import hashlib
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from analysis import active_sets, bottlenecks, local_marginals
from export import check_csv_output, export_csv_output
from model import (ARTIFACT_ROOT, ROOT, DT, PHYS_TOL_KWH, COST_TOL_YUAN, BINARY_TOL,
                   ECONOMIC_VALUE_TOL, arrays, build_problem, check_solution, read_inputs, solve, solve_milp)
from pipeline import ALIASES, publish_generation, render_figures
import run


class ReviewAcceptance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = ROOT / 'docs/CUMCM2026Problems/C题/附件/附件1.xlsx'
        cls.data = read_inputs(cls.source)
        cls.solution = solve(cls.data, .9)

    def test_official_attachment_fresh_solve_golden_and_csv(self):
        golden = json.loads((ROOT / 'src/q1/golden_main.json').read_text(encoding='utf-8'))
        self.assertEqual(hashlib.sha256(self.source.read_bytes()).hexdigest(), golden['source_sha256'])
        self.assertTrue(check_solution(self.data, self.solution)['passed'])
        self.assertAlmostEqual(self.solution['solver']['objective_yuan'], golden['objective_yuan'], delta=COST_TOL_YUAN)
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            check = export_csv_output(directory, self.data, self.solution)
            self.assertTrue(check['passed'])
            self.assertFalse(list(directory.glob('*.xlsx')))
            self.assertAlmostEqual(check['reread_cost_yuan'], golden['objective_yuan'], delta=COST_TOL_YUAN)

    def test_independent_efficiencies_analytical_case(self):
        data = [{'price_yuan_per_kwh': .1, 'load_kwh': 0., 'pv_kwh': 0., 'interval': 'first'},
                {'price_yuan_per_kwh': 1., 'load_kwh': 100., 'pv_kwh': 0., 'interval': 'last'}]
        solution = solve(data, eta_c=.8, eta_d=.95)
        self.assertTrue(check_solution(data, solution)['passed'])
        self.assertAlmostEqual(solution['solver']['objective_yuan'], 10 / (.8 * .95), delta=COST_TOL_YUAN)
        self.assertAlmostEqual(sum(solution['C']), 100 / (.8 * .95), delta=PHYS_TOL_KWH)
        rows, _, _, _ = local_marginals(data, solution, 'asymmetric')
        for row in rows:
            self.assertAlmostEqual(row['charge_threshold'], .8 * row['lambda_yuan_per_kwh'], delta=ECONOMIC_VALUE_TOL)
            self.assertAlmostEqual(row['discharge_threshold'], row['lambda_yuan_per_kwh'] / .95, delta=ECONOMIC_VALUE_TOL)
        for kwargs in ({'eta_c': 0}, {'eta_c': .9, 'eta_d': 1.01}, {'eta_c': .9, 'e_min': 6001}):
            with self.assertRaises(ValueError):
                build_problem(data, **kwargs)

    def test_active_sets_use_current_limits_and_lower_space(self):
        solution = solve(self.data, .9, e_min=5900, e_max=6100, charge_kw=100, discharge_kw=150)
        active = active_sets(solution)
        for key, variable, limit in [('E_min', 'E', 5900), ('E_max', 'E', 6100),
                                     ('charge', 'C', 100 * DT), ('discharge', 'D', 150 * DT)]:
            expected = [i + 1 for i, value in enumerate(solution[variable]) if abs(value - limit) <= PHYS_TOL_KWH]
            self.assertEqual(active[key], expected)
        rows, raw = bottlenecks(self.data, solution, 'custom', [1., 10., 100.])
        self.assertEqual(len(rows), 12)
        for row in rows:
            self.assertIsNone(row['economic_bottleneck'])
            if row['resource'] == 'storage_lower':
                self.assertEqual(row['parameter_change'], -row['increment'])
                changed = raw[f"storage_lower_{row['increment']:g}"]['solution']
                self.assertEqual(changed['settings']['e_min'], 5900 - row['increment'])
                self.assertEqual(changed['settings']['e_max'], 6100)

    def test_pv_only_source_with_zero_price_and_surplus(self):
        data = [{'price_yuan_per_kwh': 0., 'load_kwh': 50., 'pv_kwh': 200.},
                {'price_yuan_per_kwh': 1., 'load_kwh': 100., 'pv_kwh': 0.}]
        for baseline in ('pv_only', 'no_ess'):
            solution = solve(data, .9, baseline=baseline)
            self.assertTrue(check_solution(data, solution)['passed'])
            self.assertAlmostEqual(solution['G'][0], 0., delta=PHYS_TOL_KWH)
            problem = build_problem(data, .9, baseline=baseline)
            self.assertEqual(problem['upper'][problem['index']['G'][0]], 0)
            # 强迫富余光伏时外网购电应不可行，不能仅依赖正电价抑制它。
            problem['lower'][problem['index']['G'][0]] = 1
            self.assertEqual(solve_milp(problem).status, 2)

    def test_binary_tolerance_is_independent_of_physical(self):
        solution = copy.deepcopy(self.solution)
        idle = next(i for i in range(144) if max(solution['C'][i], solution['D'][i]) <= PHYS_TOL_KWH)
        solution['u'][idle] = 20 * BINARY_TOL
        with self.assertRaises(ValueError):
            check_solution(self.data, solution)

    def test_original_milp_rhs_all_576_results(self):
        raw = json.loads((ARTIFACT_ROOT / 'raw/analysis_solutions.json').read_text(encoding='utf-8'))
        checks = json.loads((ARTIFACT_ROOT / 'raw/analysis_validation.json').read_text(encoding='utf-8'))['milp_rhs_checks']
        problem = build_problem(self.data, .9)
        self.assertEqual(len(raw['milp_rhs_solutions']), 576)
        self.assertEqual(len(checks), 288)
        for record in raw['milp_rhs_solutions']:
            index = record['row']
            if record['status'] == 2:
                self.assertEqual(checks[index][record['side'] + '_status'], 2)
                continue
            x = np.concatenate([record['variables'][key] for key in problem['index']])
            expected = problem['ub'][:288].copy()
            step = -.01 if record['side'] == 'minus' else .01
            expected[index] += step
            np.testing.assert_allclose(problem['a'][:288] @ x, expected, atol=PHYS_TOL_KWH, rtol=0)
            self.assertTrue(np.all(problem['a'][288:] @ x <= problem['ub'][288:] + PHYS_TOL_KWH))
            self.assertTrue(np.all(x >= problem['lower'] - PHYS_TOL_KWH))
            self.assertTrue(np.all(x <= problem['upper'] + PHYS_TOL_KWH))
            u = np.array(record['variables']['u'])
            np.testing.assert_allclose(u, np.rint(u), atol=BINARY_TOL, rtol=0)
            objective = arrays(self.data)[0] @ record['variables']['G']
            self.assertAlmostEqual(objective, record['dual_bound_yuan'], delta=COST_TOL_YUAN)
            slope = (objective - self.solution['solver']['objective_yuan']) / step
            self.assertAlmostEqual(slope, checks[index][record['side'] + '_slope'], delta=ECONOMIC_VALUE_TOL)
        self.assertTrue(any(r['base_action'] == 'idle' for r in checks))


class PipelineAcceptance(unittest.TestCase):
    def test_atomic_pointer_and_failed_commit_preserve_old_generation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for relative in ALIASES:
                alias = root / relative
                if relative.endswith(('.md', '.csv')):
                    alias.parent.mkdir(parents=True, exist_ok=True)
                    alias.write_text('old', encoding='utf-8')
                else:
                    alias.mkdir(parents=True, exist_ok=True)
                    (alias / 'version.txt').write_text('old', encoding='utf-8')
            def generation(name):
                directory = root / 'outputs/.q1-runs' / name
                for target in ALIASES.values():
                    path = directory / target
                    if target.endswith(('.md', '.csv')):
                        path.parent.mkdir(parents=True, exist_ok=True)
                        path.write_text(name, encoding='utf-8')
                    else:
                        path.mkdir(parents=True, exist_ok=True)
                        (path / 'version.txt').write_text(name, encoding='utf-8')
                return directory
            first, second = generation('first'), generation('second')
            publish_generation(first, root)
            before = os.readlink(root / 'outputs/q1_current')
            with patch('pipeline.os.replace', side_effect=OSError('injected commit failure')):
                with self.assertRaises(OSError):
                    publish_generation(second, root)
            self.assertEqual(os.readlink(root / 'outputs/q1_current'), before)
            for relative in ALIASES:
                path = root / relative
                actual = path if relative.endswith(('.md', '.csv')) else path / 'version.txt'
                self.assertEqual(actual.read_text(encoding='utf-8'), 'first')
            publish_generation(second, root)
            self.assertEqual((root / 'outputs/q1_current').resolve(), second.resolve())

    def test_missing_font_does_not_leave_partial_figures(self):
        with tempfile.TemporaryDirectory() as temporary:
            staging = Path(temporary)
            (staging / 'processed').mkdir()
            def broken(*args):
                (args[-1] / 'partial.png').write_bytes(b'partial')
                raise RuntimeError('没有可用中文字体')
            with patch('report.create_figures', side_effect=broken):
                status = render_figures(None, None, None, None, staging)
            self.assertEqual(status['status'], 'failed')
            self.assertIn('中文字体', status['message'])
            self.assertEqual(list((staging / 'processed').iterdir()), [])

    def test_pipeline_analysis_and_test_failure_do_not_publish(self):
        # 真实读取/求解/导出；只在分析入口或测试门槛注入错误。
        for target in ('run.run_analysis', 'run.run_tests'):
            with self.subTest(stage=target), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                source = root / 'docs/CUMCM2026Problems/C题/附件'
                source.mkdir(parents=True)
                shutil.copy2(ROOT / 'docs/CUMCM2026Problems/C题/附件/附件1.xlsx', source / '附件1.xlsx')
                old = root / 'outputs/processed/q1'
                old.mkdir(parents=True)
                (old / 'sentinel.txt').write_text('previous', encoding='utf-8')
                with patch(target, side_effect=RuntimeError('injected numerical gate failure')):
                    with self.assertRaisesRegex(RuntimeError, 'injected numerical gate'):
                        run.run_pipeline(root, plots=False)
                self.assertEqual((old / 'sentinel.txt').read_text(encoding='utf-8'), 'previous')
                self.assertFalse((root / 'outputs/q1_current').is_symlink())
                self.assertEqual(list((root / 'outputs/.q1-runs').iterdir()), [])

    def test_font_failure_still_publishes_valid_csv_and_visible_status(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / 'docs/CUMCM2026Problems/C题/附件'
            source.mkdir(parents=True)
            for rel in ('附件1.xlsx',):
                shutil.copy2(ROOT / 'docs/CUMCM2026Problems/C题/附件' / rel, source / rel)
            model = root / 'docs/1/final/第一问_MILP_边际价值强化版.md'
            model.parent.mkdir(parents=True)
            shutil.copy2(ROOT / 'docs/1/final/第一问_MILP_边际价值强化版.md', model)
            # 外层正在执行真实测试套件；嵌套流水线不递归调用同一套件。
            def nested_test_gate(staging):
                self.assertTrue((staging / 'processed/result1.csv').is_file())
            with patch('report.create_figures', side_effect=RuntimeError('没有可用中文字体')), \
                    patch('run.run_tests', side_effect=nested_test_gate):
                generation = run.run_pipeline(root)
            data = read_inputs(source / '附件1.xlsx')
            solution = json.loads((generation / 'raw/solution_main.json').read_text(encoding='utf-8'))
            self.assertTrue(check_csv_output(generation / 'processed', data, solution)['passed'])
            self.assertFalse(list((generation / 'processed').glob('*.xlsx')))
            self.assertEqual((root / 'outputs/q1_current').resolve(), generation)
            for name in ('report.html', 'marginal_report.html'):
                page = (generation / 'processed' / name).read_text(encoding='utf-8')
                self.assertIn('没有可用中文字体', page)
                self.assertNotIn('<img', page)
            self.assertEqual(list((generation / 'processed').glob('*.png')), [])
