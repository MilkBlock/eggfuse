import unittest
import numpy as np
import mlx.core as mx
from chain_completion_audit import candidates,pack,decode,audit
from boundary_cell_ridge import state,D,B
from dominator_completion import compose
from test_cell_token_successors import rule,atom,make,TABLES


class ChainAudit(unittest.TestCase):
    def test_catalog_contains_alternative_rules_and_identity(self):
        a,b=('input',0),('input',1);source=[('F',(a,b),True)]
        first=rule([atom('F',0,1)],[make('G',2,1)],2)
        other=rule([atom('F',0,1)],[make('Pair',2,0,1)],2)
        expected,reason=compose(source,first,[(0,a),(1,b)],TABLES)
        self.assertIsNone(reason)
        values,index,limits=candidates(source,[first,other],TABLES,expected,[a,b],[(a,a),(b,b)],state,2)
        self.assertEqual(len(values),3);self.assertNotEqual(index,0)
        np.testing.assert_allclose(values[index,:D],state(expected['facts'],[a,b],2,expected['source_map'])[:D])
        self.assertEqual(limits['exhausted_rule_enumerations'],0)

    def test_equal_codes_are_ambiguous_not_accepted(self):
        values=np.array([[1.,2.],[1.,2.]],np.float32)
        prototypes,valid,scale=pack([(values,0,1)],1)
        query=values[:1];choice,_=decode(mx.array(query),mx.array(prototypes),mx.array(valid),mx.array(scale));mx.eval(choice)
        result=audit(query,np.array(choice),np.array([True]),prototypes,valid,scale,[0])
        self.assertEqual(result['exact_target'],0);self.assertEqual(result['ambiguous'],1)

    def test_wrong_and_missing_are_separate(self):
        prototypes,valid,scale=pack([(np.array([[0.,0.],[1.,1.]],np.float32),1,1)]*2,1)
        query=np.zeros((2,2),np.float32)
        choice,_=decode(mx.array(query),mx.array(prototypes),mx.array(valid),mx.array(scale));mx.eval(choice)
        result=audit(query,np.array(choice),np.array([True,False]),prototypes,valid,scale,[1,1])
        self.assertEqual(result['wrong_target'],1);self.assertEqual(result['not_emitted'],1)

    def test_padded_candidate_is_never_selected(self):
        prototypes,valid,scale=pack([(np.array([[4.,4.]],np.float32),0,1),(np.array([[0.,0.],[1.,1.]],np.float32),0,1)],1)
        choice,_=decode(mx.zeros((2,2)),mx.array(prototypes),mx.array(valid),mx.array(scale));mx.eval(choice)
        self.assertEqual(int(np.array(choice)[0]),0)


if __name__=='__main__':unittest.main()
