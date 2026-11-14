import unittest
from types import SimpleNamespace
import numpy as np
from audit_neural_run import audit_query_sets


class QueryAudit(unittest.TestCase):
    def check(self,keys):
        rule=dict(slots=[dict(definition='query')]*2)
        ref=SimpleNamespace(root=lambda x:x,matches=lambda r:[{0:1,1:2},{0:2,1:3}])
        event=dict(query_keys=np.array(keys),query_live=np.ones(len(keys),bool))
        return audit_query_sets(dict(rules=[rule]),ref,dict(trace=[(0,event)]),{1:1,2:2,3:3})

    def test_exact_and_missing(self):
        self.assertTrue(self.check([[0,1,2],[0,2,3]])['passed'])
        result=self.check([[0,1,2]])
        self.assertFalse(result['passed']);self.assertEqual(result['rules'][0]['missed'],1)

    def test_extra_and_unknown(self):
        result=self.check([[0,1,3],[0,1,99]])
        self.assertFalse(result['passed']);self.assertEqual(result['rules'][0]['extra'],1)
        self.assertEqual(result['rules'][0]['unknown'],1)


if __name__=='__main__':unittest.main()
