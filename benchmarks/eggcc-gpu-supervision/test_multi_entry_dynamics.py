import unittest
import numpy as np
from audit_multi_entry_dynamics import train_catalog,evaluate
from multi_entry_ridge import template_identity


def node(family,key,value):
    return dict(family=family,state_key=key,target=np.full(128,value,np.float32),
                seed=np.zeros(128),q=np.zeros(64),valid=True)


class Dynamics(unittest.TestCase):
    def test_unknown_states_do_not_enter_training_dictionary(self):
        catalog=train_catalog([node('f','a',0),node('f','b',1)])
        test=[node('f','c',.7),node('new','z',2),node('f','a',0)]
        r=evaluate(test,{'prediction':np.array([n['target'] for n in test])},catalog)
        self.assertEqual(r['train_dictionary_decode']['prediction']['covered_cases'],1)
        self.assertEqual(r['train_dictionary_decode']['prediction']['correct'],1)
        self.assertEqual(r['train_dictionary_decode']['prediction']['unseen_target'],1)
        self.assertEqual(r['train_dictionary_decode']['prediction']['unknown_template'],1)
        self.assertEqual(catalog['f']['keys'],['a','b'])
        np.testing.assert_array_equal(catalog['f']['mean'],.5)

    def test_template_mean_is_not_treated_as_exact_state_when_tied(self):
        c=train_catalog([node('f','a',0),node('f','b',1)])
        r=evaluate([node('f','a',0)],{'prediction':np.full((1,128),.5)},c)
        self.assertEqual(r['train_dictionary_decode']['prediction']['ambiguous'],1)
        self.assertEqual(r['train_dictionary_decode']['prediction']['correct'],0)

    def test_template_key_includes_literals_not_names(self):
        a=dict(query=[],effects=[dict(kind='construct',args=[dict(literal=0)])],slots=[],metadata=dict(name='a'))
        b={**a,'metadata':dict(name='b')}
        self.assertEqual(template_identity(a),template_identity(b))
        b={**b,'effects':[dict(kind='construct',args=[dict(literal=1)])]}
        self.assertNotEqual(template_identity(a),template_identity(b))

if __name__=='__main__':unittest.main()
