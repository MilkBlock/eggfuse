import unittest
import numpy as np
import mlx.core as mx
from device_snapshot_import import identity
from device_literal_namespace import bind_effect_literals
from compile_constructor_sites import compile_sites
from device_witness_views import compile_view,project
from device_constructor_results import execute_site
from reference_cell_closure import facts_from_cells


class LiteralConstructors(unittest.TestCase):
    def fixture(self):
        eq=dict(kind='eq',name='Expr');integer=dict(kind='i64',name='i64')
        literals=[dict(literal=n,sort=integer) for n in ((1<<60)+7,(1<<60)+8)]
        rules=[dict(slots=[dict(sort=eq,definition='effect')],query=[],effects=[dict(kind='construct',call=dict(table='Int'),args=[arg],dst=0)]) for arg in literals]
        recipe=dict(tables=[dict(name='Int',kind='constructor',schema=[integer,eq])],rules=rules)
        bound,ids=bind_effect_literals(recipe,{})
        state=dict(keys=np.array([[0],[1]],np.int32),slots=np.full((2,1),-1,np.int32),slot_roots=np.full((2,1),-1,np.int32),slot_valid=np.zeros((2,1),bool),effect_pc=np.zeros(2,np.int32),settled=np.zeros(2,bool),token_dirty=np.zeros(2,bool))
        for k in ('present','active','visible'):state[k]=np.ones(2,bool)
        return recipe,bound,ids,state

    def test_gpu_exact_constants_allocate_distinct_results_and_reuse_views(self):
        original,recipe,ids,host=self.fixture();self.assertEqual(len(compile_sites(original)['marks']),2)
        sites=compile_sites(recipe);self.assertFalse(sites['marks'])
        dev=lambda d:{k:mx.array(v) if isinstance(v,np.ndarray) else v for k,v in d.items()}
        plan=dev(compile_view(recipe,0,1))
        def execute(s):
            next_id=mx.array(len(ids));allocated=mx.array(0)
            for site in sites['sites']:
                view=project(s,plan,mx.array(True),mx.array(True),mx)
                s,marks=execute_site(s,site,view,next_id,mx.array(10),mx.array(10),mx)
                next_id=marks['next_id'];allocated+=mx.sum(marks['new_owner'])
            return s,next_id,allocated,project(s,plan,mx.array(True),mx.array(True),mx,include_fields=True)
        out,last,count,view=mx.compile(execute)(dev(host));mx.eval(out,last,count,view)
        self.assertEqual(int(count),2);self.assertEqual(int(last),4);np.testing.assert_array_equal(out['slots'],[[2],[3]])
        live=np.array(view['live']);self.assertEqual(set(np.array(view['keys'])[live,1]),{0,1})
        np.testing.assert_array_equal(np.array(view['source_slots'])[live,0],[-1,-1])
        facts,covered=facts_from_cells(recipe,{k:np.array(v) for k,v in out.items()});self.assertTrue(covered)
        self.assertEqual(set(facts),{('Int',(0,),2),('Int',(1,),3)})
        # Re-execution reuses the real earlier result, not an invented producer address.
        again=dict(out,settled=mx.zeros(2,mx.bool_),effect_pc=mx.zeros(2,mx.int32))
        _,marks=execute_site(again,sites['sites'][0],view,last,mx.array(10),mx.array(10),mx)
        self.assertTrue(bool(marks['reused'][0]));self.assertEqual(int(marks['result'][0]),2)
        self.assertEqual(len(ids),2)

    def test_namespace_and_unbound_literals_cannot_commit(self):
        original,recipe,ids,s=self.fixture();site=compile_sites(recipe)['sites'][0]
        view=project(s,compile_view(recipe,0,1),True,True,np)
        out,marks=execute_site(s,site,view,np.array(0),np.array(10),np.array(10),np)
        self.assertTrue(marks['needs_attention']);np.testing.assert_array_equal(out['slots'],s['slots'])
        self.assertFalse(compile_view(original,0,1)['supported'].any())
        with self.assertRaises(ValueError):bind_effect_literals(original,{'bad':3})


if __name__=='__main__':unittest.main()
