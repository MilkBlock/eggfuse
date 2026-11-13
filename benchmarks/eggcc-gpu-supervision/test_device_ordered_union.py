import unittest
import numpy as np
import mlx.core as mx
from device_constructor_completion import compile_completion,complete
import test_device_constructor_completion as helper


def fixture():
    sort=dict(kind='eq',name='E')
    def slots(n,q):return [dict(sort=sort,definition='query' if i<q else 'effect') for i in range(n)]
    def atom(t,args):return dict(call=dict(table=t),args=[dict(slot=i) for i in args])
    recipe=dict(tables=[dict(name=t,kind='constructor') for t in ('F','G')],rules=[
        dict(metadata=dict(source_set='s'),slots=slots(5,4),query=[atom('F',[0,2]),atom('F',[1,3])],effects=[dict(kind='union',args=[dict(slot=0),dict(slot=1)]),dict(kind='construct',call=dict(table='G'),args=[dict(slot=2)],dst=4)]),
        dict(metadata=dict(source_set='s'),slots=slots(2,2),query=[atom('G',[0,1])],effects=[])])
    state=dict(keys=np.array([[0,1,2,3,4],[1,4,5,-1,-1]],np.int32),slots=np.array([[1,2,3,4,-1],[4,5,-1,-1,-1]],np.int32),
        slot_roots=np.array([[1,2,3,4,-1],[4,5,-1,-1,-1]],np.int32),slot_valid=np.array([[True]*4+[False],[True,True,False,False,False]]),
        tokens=np.zeros((2,128),np.float32),effect_pc=np.zeros(2,np.int32),present=np.ones(2,bool),visible=np.ones(2,bool),active=np.array([True,False]),
        settled=np.array([False,True]),token_dirty=np.zeros(2,bool))
    context=dict(roots=np.arange(16,dtype=np.int32),sorts=np.zeros(16,np.int32))
    return state,compile_completion(recipe,5,include_unions=True),context


def device_plan(plan):
    p=helper.device_plan(plan)
    p['eq_types']=mx.array(plan['eq_types'])
    p['closure_views']=[{k:mx.array(v) if isinstance(v,np.ndarray) else v for k,v in view.items()} for view in plan['closure_views']]
    p['operations']=[(kind,dict(site,plan={k:mx.array(v) for k,v in site['plan'].items()}) if kind=='union' else site) for kind,site in plan['operations']]
    return p


class OrderedUnion(unittest.TestCase):
    def test_union_congruence_then_constructor_reuse_and_shared_reader_refresh(self):
        if not mx.metal.is_available():self.skipTest('Metal required')
        state,plan,ctx=fixture();dp=device_plan(plan);dev=lambda d:{k:mx.array(v) for k,v in d.items()}
        dc=dev(ctx)
        out,n,marks=mx.compile(lambda s:complete(s,dp,mx.array(10),mx.array(16),mx.array(6),mx.array(True),mx.array(True),mx,dc,4))(dev(state));mx.eval(out,n,marks)
        self.assertEqual(int(n),10);self.assertEqual(int(marks['executed']),2)
        np.testing.assert_array_equal(np.array(out['slots'])[0],[1,2,3,4,5])
        np.testing.assert_array_equal(np.array(out['slot_roots'])[0],[1,1,3,3,5])
        self.assertEqual(np.array(out['slot_roots'])[1,0],3)
        self.assertFalse(np.array(out['token_dirty']).any());self.assertEqual(int(marks['refreshed']),2)
        self.assertTrue(bool(marks['eq_settled']));self.assertTrue(np.array(out['settled']).all())

    def test_budget_or_missing_boundary_keeps_effect_pc_pending(self):
        for rounds,external in ((1,True),(4,False)):
            s,p,c=fixture();out,n,m=complete(s,p,np.array(10),np.array(16),np.array(6),np.array(external),np.array(True),np,c,rounds)
            self.assertEqual(out['effect_pc'][0],0);self.assertEqual(n,10);self.assertTrue(m['needs_attention'])
            self.assertFalse(m['eq_settled']);self.assertFalse(out['settled'][0])

    def test_wrong_typed_slot_cannot_merge_even_when_both_roots_share_a_sort(self):
        s,p,c=fixture();c['sorts'][:]=1
        out,n,m=complete(s,p,np.array(10),np.array(16),np.array(6),np.array(True),np.array(True),np,c,4)
        self.assertEqual(out['effect_pc'][0],0);self.assertEqual(n,10);self.assertTrue(m['needs_attention'])
        np.testing.assert_array_equal(m['eq_context']['roots'],c['roots'])

    def test_allocated_constructor_gets_typed_registry_entry(self):
        s,p,c=fixture();s['present'][1]=False
        c['sorts'][10:]=-1
        out,n,m=complete(s,p,np.array(10),np.array(16),np.array(6),np.array(True),np.array(True),np,c,4)
        self.assertEqual(n,11);self.assertEqual(out['slots'][0,4],10)
        self.assertEqual(m['eq_context']['roots'][10],10);self.assertEqual(m['eq_context']['sorts'][10],0)
        with self.assertRaisesRegex(ValueError,'registry'):complete(s,p,np.array(10),np.array(16),np.array(6),True,True,np)


if __name__=='__main__':unittest.main()
