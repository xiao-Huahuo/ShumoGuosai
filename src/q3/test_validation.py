"""最终检验方案范围、优先级、真实反事实及原始主结果只读核验。"""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import numpy as np
import pandas as pd
from .config import ROOT, Config, write_json, write_csv
from .data import read_inputs
from .rolling import run_day, date_of
from .terminal import TerminalValues
from .validation import variant_configs, plan_jobs, base_fiv_job, rollout_job, metric_tables, audit_main


class ValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.data=read_inputs(ROOT/'outputs/q2/dispatch_runs/20260911_224501')

    def test_six_core_settings_and_three_assumptions(self) -> None:
        variants=variant_configs(Config(gap=.03))
        self.assertEqual(set(variants),{'M1','S10','S30','tail0','tail4','terminal08','terminal12','pchip','lag','sequential'})
        self.assertEqual(variants['sequential'].settlement,'sequential')
        self.assertEqual(variants['lag'].feedback,'lag')
        self.assertTrue(all(cfg.gap==.03 for cfg in variants.values()))

    def test_queue_reuses_M1_and_prioritizes_information(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);main=root/'main';date='2025-02-01'
            write_csv(main/f'days/{date}.csv',pd.DataFrame({'initial_soc':[6000.]}))
            jobs=plan_jobs(self.data,Config(gap=.03),main,root/'validation',[date],'sampled')
            self.assertEqual(len(jobs),40)
            self.assertEqual([job[2].parts[-2:] for job in jobs[:4]], [('M1','K0'),('M1','K06'),('M1','K0612'),('M0','K061218')])
            self.assertEqual({job[2].parts[-2] for job in jobs[4:28]}, {'S10','S30','tail0','tail4','terminal08','terminal12'})
            self.assertEqual({job[2].parts[-2] for job in jobs[28:]}, {'pchip','lag','sequential'})
            self.assertFalse(any(job[2].parts[-2:]==('M1','K061218') for job in jobs))

    def test_real_single_date_information_and_comparison_tables(self) -> None:
        cfg=Config(gap=.03,deterministic=True,seconds=15.)
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); main=root/'main'; output=root/'validation'; date='2025-02-01'; d=31
            frame,audit,_=run_day(self.data,TerminalValues(self.data,cfg),d,6000.,cfg)
            write_csv(main/'dispatch.csv',frame);write_csv(main/f'days/{date}.csv',frame);write_json(main/f'audit/{date}.json',audit)
            before=hashlib.sha256((main/'dispatch.csv').read_bytes()).hexdigest()
            for job in plan_jobs(self.data,cfg,main,output,[date],'sampled')[:4]:rollout_job(job)
            base_fiv_job((self.data,cfg,main,output/'base_fiv',[date],'sampled'))
            errors=pd.read_csv(ROOT/'outputs/q3/raw/timing_final_20260912/diagnostics/forecast_revision_pairs.csv')
            write_csv(output/'forecast/forecast_revision_pairs.csv',errors)
            metric_tables(self.data,main,output,{'M1':cfg},[date],'sampled')
            table=pd.read_csv(output/'information_value.csv')
            self.assertEqual(len(table),3);self.assertTrue((table.scope=='sampled').all())
            self.assertTrue((table.days==1).all());self.assertTrue(table.FIV18_cont.iloc[2]==table.FIV18_cont.iloc[2])
            self.assertEqual(len(pd.read_csv(output/'M0_M1_comparison.csv')),2)
            self.assertEqual(before,hashlib.sha256((main/'dispatch.csv').read_bytes()).hexdigest())

    def test_empty_formal_prefix_does_not_claim_pass(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);write_json(root/'main/state.json',{'days':[]})
            result=audit_main(self.data,root,root/'validation')
            self.assertTrue(result.value.isna().all())
            self.assertTrue((result.status=='待正式数据').all())


if __name__=='__main__':unittest.main(verbosity=2)
