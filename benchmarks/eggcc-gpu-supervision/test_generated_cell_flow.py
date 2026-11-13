import unittest
import numpy as np
import mlx.core as mx
from cell_token_successors import compile_catalog
from generated_cell_flow import bootstrap,layout,initial_states,execute


def program():
    sort=dict(name='E',kind='eq')
    def rule(table,out):
        return dict(metadata=dict(source_set='region'),slots=[dict(sort=sort,definition='query'),dict(sort=sort,definition='query'),dict(sort=sort,definition=0)],query=[dict(call=dict(table=table),args=[dict(slot=0),dict(slot=1)])],effects=[dict(kind='construct',call=dict(table=out),dst=2,args=[dict(slot=1)])])
    return dict(recipe=dict(tables=[dict(name=n,kind='constructor',schema=[sort,sort]) for n in ['Seed','G','H','K']],rules=[rule('Seed','G'),rule('G','H'),rule('H','K')]),initial=[dict(table='Seed',values=[dict(eq='first',sort='E'),dict(eq='second',sort='E')],subsumed=False)])


class Flow(unittest.TestCase):
    def test_empty_query_bootstraps_once_without_a_trace(self):
        p=program();p['recipe']['rules'][0]['query']=[]
        p['recipe']['rules'][0]['slots']=[];p['recipe']['rules'][0]['effects']=[]
        c=compile_catalog(p['recipe']);seeds,_=bootstrap(p,c)
        self.assertEqual(len(seeds),1);self.assertEqual(seeds[0]['entries'][0]['inputs'],())

    def test_capacity_is_marked_not_saturation(self):
        p=program();c=compile_catalog(p['recipe']);seeds,_=bootstrap(p,c)
        plan=layout(p,c,seeds,max_tokens=2)
        self.assertEqual(plan['tokens'],2)
        self.assertTrue(any(m['reason']=='token capacity' for m in plan['marks']))

    @unittest.skipUnless(mx.metal.is_available(),'Metal required')
    def test_grandchild_consumes_generated_state_and_input_changes_propagate(self):
        p=program();c=compile_catalog(p['recipe']);seeds,_=bootstrap(p,c);plan=layout(p,c,seeds)
        self.assertEqual([len(v) for v in plan['levels']],[1,1,1])
        inputs=initial_states(p,plan);mx.set_default_device(mx.gpu)
        kernel=mx.compile(lambda x:execute(p,plan,x,mx))
        actual=kernel({k:mx.array(v) for k,v in inputs.items()});mx.eval(actual)
        reference=execute(p,plan,inputs,np)
        for a,b in zip(actual,reference):np.testing.assert_allclose(np.array(a),b,atol=2e-5,rtol=2e-4)
        # No second/third-stage state or recorded binding is supplied as input.
        changed={k:v.copy() for k,v in inputs.items()};changed[0][:,1,:]+=.25
        other=kernel({k:mx.array(v) for k,v in changed.items()});mx.eval(other)
        self.assertFalse(np.allclose(np.array(actual[-1]),np.array(other[-1])))
        # The next Cell's slot is exactly the preceding GPU-produced result.
        np.testing.assert_array_equal(np.array(actual[0][:,2,:]),np.array(actual[1][:,1,:]))
        np.testing.assert_array_equal(np.array(actual[1][:,2,:]),np.array(actual[2][:,1,:]))

if __name__=='__main__':unittest.main()
