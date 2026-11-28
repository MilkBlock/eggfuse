"""Regression checks for exact-state forks, named identity and continuation cutoffs."""
import copy
import tempfile
import unittest
from pathlib import Path

from exposure_data import Fork
from exposure_eval import BUDGETS, Database, SourcePanic, Trials, is_source_panic
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

    def test_source_panic_has_no_score_and_other_caps_still_run(self):
        native_error = 'Error: "source panic (Run 21, rule 351, op 0, (panic ...))"'
        self.assertTrue(is_source_panic(native_error))
        self.assertFalse(is_source_panic("native run incomplete"))
        self.assertFalse(is_source_panic("No space left on device"))
        class T(Trials):
            def trial(self, n):
                if n is None or n > 32:
                    raise SourcePanic(dict(stderr=native_error, observed_replies=[]))
                req = [dict(ops=int(i == 0), name=[1, []], owner=i, complete=True,
                            reply=[i, "accepted"]) for i in range(n)]
                return dict(requests=req, r=dict(stats={}, ops=1, facts=[1], reference=1,
                            coverage=1, wall=1, ept=1/n, eps=1, graph="g", receipts={}))
            def effect(self, req):
                return dict(facts=[1], graph="g", ops=1)
        t = object.__new__(T)
        with tempfile.TemporaryDirectory() as directory:
            t.db = Database(Path(directory) / "evidence.db")
            t.condition = {"model": "test"}
            t.run()
            counts = dict(t.db.db.execute("select kind,count(*) from evidence group by kind"))
            self.assertEqual(counts, {"curve": 1, "failed_budget": 7})
            from int_parameters import digest
            curve = t.db.get("curve", digest(t.condition))
            self.assertEqual([(r["mode"], r["budget"]) for r in curve],
                             [("total", 16), ("continuation", 16), ("total", 32)])

    def test_evidence_database_resumes_by_full_key(self):
        with tempfile.TemporaryDirectory() as d:
            first=Database(Path(d)/"raw.db")
            first.put("curve","random",{"budget":16})
            second=Database(Path(d)/"raw.db")
            self.assertEqual(second.get("curve","random"),{"budget":16})
            self.assertIsNone(second.get("trial","random"))
