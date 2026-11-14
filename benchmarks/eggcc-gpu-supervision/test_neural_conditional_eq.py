import unittest
import numpy as np
import mlx.core as mx
from neural_conditional_eq import compile_cases,select
from neural_ordered_relations import projected


class ConditionalEqTests(unittest.TestCase):
    def fixture(self):
        eq=dict(kind='eq',name='E')
        def atom(name,*s):return dict(call=dict(table=name),args=[dict(slot=i) for i in s])
        rule=dict(slots=[dict(sort=eq,definition='query' if i<6 else 0) for i in range(8)],query=[atom('F',0,1,2),atom('F',3,4,5)],effects=[dict(kind='construct',call=dict(table='G'),args=[dict(slot=2)],dst=6),dict(kind='construct',call=dict(table='G'),args=[dict(slot=5)],dst=7)])
        return dict(tables=[dict(name=t,kind='constructor') for t in ('F','G')]),rule

    def test_conditional_multilevel_proof_and_partial_arguments(self):
        rec,rule=self.fixture();plan=compile_cases(rec,rule,8)
        inputs=np.array([projected(rule,[[10,11,12],[10,11,13]],2,5),projected(rule,[[10,11,12],[10,14,13]],2,5)])
        known,covered=select(plan,inputs,np);pairs=list(zip(*np.triu_indices(8,1)))
        self.assertTrue(covered.all());self.assertTrue(known[0,pairs.index((6,7))]);self.assertFalse(known[1,pairs.index((6,7))])
        device=dict(relation_width=plan['relation_width'],**{k:mx.array(v) for k,v in plan.items() if isinstance(v,np.ndarray)})
        got=mx.compile(lambda x:select(device,x,mx))(mx.array(inputs));mx.eval(got)
        np.testing.assert_array_equal(got[0],known);np.testing.assert_array_equal(got[1],covered)
        invalid=inputs.copy();invalid[:,plan['columns'][0]]=float('nan')
        self.assertFalse(select(plan,invalid,np)[1].any())

    def test_positive_proofs_against_independent_synthetic_execution(self):
        from neural_cell_samples import samples
        from neural_cell_chains import completed
        from neural_eq_readout import targets
        rec,rule=self.fixture();eq=rule['slots'][0]['sort']
        rec['rules']=[rule]
        for t in rec['tables']:t['schema']=[eq]*(3 if t['name']=='F' else 2)
        records=[];data=samples(rec,4,71,records,ordered=True)
        plan=compile_cases(rec,rule,8,fields=3);known,covered=select(plan,data['relations'],np)
        self.assertTrue(records)
        with self.assertRaisesRegex(ValueError,'layout mismatch'):select(compile_cases(rec,rule,8),data['relations'],np)
        for record in records:
            i=record['index'];ref=record['reference']
            truth=targets(rule,completed(rule,record['binding'],ref),ref,8)
            self.assertTrue(covered[i])
            self.assertFalse(np.any(known[i]&((truth['eq_target']==0)|~truth['eq_mask'])))

    def test_budget_and_mutability_do_not_manufacture_proofs(self):
        rec,rule=self.fixture();plan=compile_cases(rec,rule,8,limit=2)
        self.assertFalse(plan['supported']);self.assertEqual(len(plan['known']),0)
        x=np.array([projected(rule,[[1,2,3],[1,2,3]],2,5)])
        known,covered=select(plan,x,np);self.assertFalse(covered.any());np.testing.assert_array_equal(known[0],plan['base'])
        rec['tables'][0]['kind']='function';self.assertFalse(compile_cases(rec,rule,8)['supported'])


if __name__=='__main__':unittest.main()
