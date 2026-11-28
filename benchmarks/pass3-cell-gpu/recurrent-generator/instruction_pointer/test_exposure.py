"""Regression checks for exact-state forks, named identity and continuation cutoffs."""
import copy
import tempfile
import unittest
from pathlib import Path

from exposure_data import Fork
from exposure_eval import BUDGETS, Database, Trials
from exposure_policy import NamedPaths


class ExposureTest(unittest.TestCase):
    def test_fork_requires_identical_runtime_state(self):
        state = {"run": 3, "request_receipts": [("accepted", 4)]}
        replay = Fork([["prefix"]], 1, state, "one")
        self.assertEqual(replay.generate(None,{},None,1), ["prefix"])
        with self.assertRaises(ValueError):
            replay.generate(None,dict(state,run=4),None,1)
        blank = Fork([],0,state,None)
        self.assertEqual(blank.generate(None,copy.deepcopy(state),None,1), [])
        self.assertTrue(blank.hit)

    def test_continuation_starts_after_actual_success(self):
        captured = []
        class T(Trials):
            def trial(self, n):
                n = min(512,n if n is not None else 512)
                requests = [dict(ops=0 if i!=1 else 199, name=[1,[]], owner=i,
                                 complete=True,reply=[i,"accepted"]) for i in range(n)]
                r=dict(stats={},ops=sum(x["ops"] for x in requests),facts=[3] if n>=2 else [],
                       reference=3,coverage=1/3,wall=1,ept=199/n,eps=199,graph="g",receipts={})
                return dict(r=r,requests=requests)
            def effect(self, req):
                return dict(graph="g",facts=[3],ops=199)
        t=object.__new__(T)
        t.condition={}
        class Sink:
            def put(self, kind,key,rows):
                captured.extend(rows)
        t.db=Sink()
        t.run()
        follow=[r for r in captured if r["mode"]=="continuation"]
        self.assertEqual([r["paid_total"] for r in follow],[2+b for b in BUDGETS])
        self.assertTrue(all(r["ops"]==0 and r["continuation_ept"]==0 and r["new_facts"]==0 for r in follow))
        self.assertTrue(all(r["ops"]==199 for r in captured if r["mode"]=="total"))

    def test_evidence_database_resumes_by_full_key(self):
        with tempfile.TemporaryDirectory() as d:
            first=Database(Path(d)/"raw.db")
            first.put("curve","random",{"budget":16})
            second=Database(Path(d)/"raw.db")
            self.assertEqual(second.get("curve","random"),{"budget":16})
            self.assertIsNone(second.get("trial","random"))
