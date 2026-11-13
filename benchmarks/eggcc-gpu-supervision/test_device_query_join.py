import unittest
import numpy as np
import mlx.core as mx
from device_query_join import compile_query,match,match_inputs


def fixture():
    eq=dict(kind='eq',name='E')
    def atom(t,slots):return dict(call=dict(table=t),args=[dict(slot=i) for i in slots])
    def rule(n,atoms):return dict(metadata=dict(source_set='s'),slots=[dict(sort=eq,definition='query') for _ in range(n)],query=atoms,effects=[])
    recipe=dict(tables=[dict(name=t,kind='constructor') for t in ('F','G')],rules=[rule(2,[atom('F',[0,1])]),rule(2,[atom('G',[0,1])]),rule(3,[atom('F',[0,1]),atom('G',[1,2])])])
    s=dict(keys=np.array([[0],[1]],np.int32),slots=np.array([[7,100,-1],[99,200,-1]],np.int32),slot_roots=np.array([[7,10,-1],[10,20,-1]],np.int32),
           slot_valid=np.array([[True,True,False]]*2),present=np.ones(2,bool),visible=np.ones(2,bool),settled=np.ones(2,bool),effect_pc=np.zeros(2,np.int32),generation=np.array([4,9],np.int32))
    return recipe,s


def device_plan(plan):
    p=dict(plan);p['atoms']=[dict(a,view={k:mx.array(v) if isinstance(v,np.ndarray) else v for k,v in a['view'].items()}) for a in p['atoms']]
    return p


class QueryJoin(unittest.TestCase):
    def test_two_sources_join_by_eq_but_return_actual_ids_and_witnesses(self):
        if not mx.metal.is_available():self.skipTest('Metal required')
        r,s=fixture();p=device_plan(compile_query(r,2));ds={k:mx.array(v) for k,v in s.items()}
        out=mx.compile(lambda state:match(state,p,4,mx.array(True),mx.array(True),mx))(ds);mx.eval(out)
        self.assertTrue(bool(out['complete']));self.assertEqual(np.array(out['live']).sum(),1)
        np.testing.assert_array_equal(np.array(out['slots'])[0],[7,100,200])
        np.testing.assert_array_equal(np.array(out['slot_roots'])[0],[7,10,20])
        np.testing.assert_array_equal(np.array(out['witness_rows'])[0],[0,1])
        np.testing.assert_array_equal(np.array(out['witness_generations'])[0],[4,9])

    def test_device_join_directly_encodes_inputs_without_cpu_binding(self):
        if not mx.metal.is_available():self.skipTest('Metal required')
        from device_input_features import compile_inputs
        r,s=fixture();p=device_plan(compile_query(r,2));layout={k:mx.array(v) for k,v in compile_inputs(r['rules'][2]).items()}
        ds={k:mx.array(v) for k,v in s.items()}
        bindings,features,marks=mx.compile(lambda state:match_inputs(state,p,layout,4,mx.array(True),mx.array(True),mx))(ds)
        mx.eval(bindings,features,marks)
        self.assertEqual(np.array(features['input_ready']).sum(),1)
        self.assertGreater(float(np.linalg.norm(np.array(features['seed'])[0])),.01)
        self.assertEqual(features['q'].shape,(4,256))

    def test_mismatch_hidden_or_missing_boundary(self):
        r,s=fixture();p=compile_query(r,2)
        s['slot_roots'][1,0]=11
        out=match(s,p,4,True,True,np);self.assertFalse(out['live'].any());self.assertTrue(out['complete'])
        s['slot_roots'][1,0]=10;s['visible'][1]=False
        self.assertFalse(match(s,p,4,True,True,np)['live'].any())
        s['visible'][1]=True
        out=match(s,p,4,False,True,np);self.assertTrue(out['live'].any());self.assertFalse(out['complete'])

    def test_repeated_variable_and_capacity(self):
        r,s=fixture();r['rules'][2]['query']=[dict(call=dict(table='F'),args=[dict(slot=0),dict(slot=0)])];r['rules'][2]['slots']=r['rules'][2]['slots'][:1]
        p=compile_query(r,2);self.assertFalse(match(s,p,4,True,True,np)['live'].any())
        s['slot_roots'][0,1]=7
        self.assertEqual(match(s,p,4,True,True,np)['live'].sum(),1)
        r,s=fixture();r['rules'][2]['query'][1]['args'][0]['slot']=0 # F(x,y), G(x,z)
        s['keys'][1,0]=0;s['slots'][1]=[8,101,-1];s['slot_roots'][1]=[8,11,-1]
        p=compile_query(r,0);out=match(s,p,1,True,True,np)
        self.assertTrue(out['overflow']);self.assertFalse(out['complete'])

    def test_unsupported_guards_cannot_be_silently_dropped(self):
        r,s=fixture();r['rules'][2]['query'].append(dict(call=dict(primitive='='),args=[dict(slot=0),dict(slot=1)]))
        p=compile_query(r,2);self.assertFalse(p['covered'])
        with self.assertRaises(ValueError):match(s,p,4,True,True,np)


if __name__=='__main__':unittest.main()
