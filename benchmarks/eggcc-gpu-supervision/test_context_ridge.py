import copy
import unittest
import numpy as np
from context_ridge import prepare, metrics


def sample():
    ports=[dict(slot=0,sort='Expr',before=100,after=100),dict(slot=1,sort='Expr',before=101,after=100)]
    binding=dict(rule=0,eq_ports=ports,values=[dict(slot=2,value={'sort':'i64','value':10**16})])
    return dict(recipe={'rules':[{'slots':[{}, {}, {}]}]},runs=[dict(ordinal=1,audit={'bindings':[binding]})])


class ContextEncoding(unittest.TestCase):
    def test_post_run_labels_do_not_enter_features(self):
        trace=sample();a,_,_,_=prepare(trace)
        trace['runs'][0]['audit']['bindings'][0]['eq_ports'][1]['after']=101
        b,_,_,_=prepare(trace)
        for key in a:
            if key!='labels':np.testing.assert_array_equal(a[key],b[key])
        self.assertEqual(a['labels'].tolist(),[1])
        self.assertEqual(b['labels'].tolist(),[0])

    def test_root_routes_do_not_cross_runs(self):
        trace=sample();other=copy.deepcopy(trace['runs'][0]);other['ordinal']=2;trace['runs'].append(other)
        a,_,nroots,_=prepare(trace)
        self.assertEqual(nroots,4)
        self.assertEqual(a['roots'].tolist(),[0,1,2,3])

    def test_large_integer_low_bits_survive_input_features(self):
        trace=sample();a,_,_,_=prepare(trace)
        trace['runs'][0]['audit']['bindings'][0]['values'][0]['value']['value']+=1
        b,_,_,_=prepare(trace)
        self.assertFalse(a['unsupported'].any())
        self.assertFalse(np.array_equal(a['scalars'],b['scalars']))

    def test_no_positive_cases_does_not_report_perfect_recall(self):
        self.assertIsNone(metrics(np.array([0.]),np.array([0.]),.5)['recall'])


if __name__=='__main__':unittest.main()
