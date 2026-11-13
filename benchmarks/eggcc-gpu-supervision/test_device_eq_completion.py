import unittest
import numpy as np
import mlx.core as mx
from device_eq_completion import merge_round,close,compile_unions,union_inputs,finish_unions
from device_witness_views import compile_view,project
from device_constructor_results import resolve


def fixture(xp):
    sort=dict(kind='eq',name='E')
    rule=dict(slots=[dict(sort=sort,definition='query') for _ in range(3)],
        query=[dict(call=dict(table='F'),args=[dict(slot=0),dict(slot=1)]),dict(call=dict(table='G'),args=[dict(slot=1),dict(slot=2)])],effects=[])
    recipe=dict(tables=[dict(name=n,kind='constructor') for n in ('F','G')],rules=[rule])
    plans=[{k:xp.array(v) if isinstance(v,np.ndarray) else v for k,v in compile_view(recipe,i,1).items()} for i in (0,1)]
    state=dict(keys=xp.array([[0,1,3,5],[0,2,4,6]],xp.int32),slots=xp.array([[1,3,5],[2,4,6]],xp.int32),
        slot_valid=xp.array([[True]*3]*2),present=xp.array([True,True]),active=xp.array([True,True]),
        visible=xp.array([True,True]),settled=xp.array([True,True]),effect_pc=xp.array([0,0],xp.int32))
    return state,plans


class EqCompletion(unittest.TestCase):
    def test_transitive_union_and_type_rejection(self):
        roots=np.arange(8,dtype=np.int32);sorts=np.zeros(8,np.int32)
        pairs=np.array([[5,4],[4,3],[3,1]],np.int32)
        for _ in range(4):roots,bad=merge_round(roots,sorts,pairs,np.ones(3,bool),np)
        np.testing.assert_array_equal(roots[[1,3,4,5]],[1]*4);self.assertFalse(bad)
        sorts[6]=1
        out,bad=merge_round(roots,sorts,np.array([[1,6],[-1,2]],np.int32),np.array([True,True]),np)
        self.assertTrue(bad);np.testing.assert_array_equal(out,roots)

    def test_multi_argument_constructor_waits_for_every_equality(self):
        sort=dict(kind='eq',name='E')
        recipe=dict(tables=[dict(name='Pair',kind='constructor')],rules=[dict(slots=[dict(sort=sort)]*3,
            query=[dict(call=dict(table='Pair'),args=[dict(slot=i) for i in range(3)])],effects=[])])
        s,_=fixture(np);s['slots']=np.array([[1,3,5],[2,4,6]],np.int32)
        plan=compile_view(recipe,0,2)
        for pairs,should_merge in [([[1,2]],False),([[1,2],[3,4]],True)]:
            out,roots,m=close(s,np.arange(8,dtype=np.int32),np.zeros(8,np.int32),np.ones((2,3),bool),np.array(pairs,np.int32),np.ones(len(pairs),bool),[plan],True,6,np)
            self.assertTrue(m['settled']);self.assertEqual(bool(roots[5]==roots[6]),should_merge)

    def test_partition_matches_independent_union_reference(self):
        rng=np.random.default_rng(21)
        for _ in range(10):
            n=17;pairs=rng.integers(0,n,(12,2),dtype=np.int32);parent=list(range(n))
            def find(i):
                while parent[i]!=i:i=parent[i]
                return i
            for a,b in pairs:
                x,y=find(int(a)),find(int(b));parent[max(x,y)]=min(x,y)
            roots=np.arange(n,dtype=np.int32)
            for _ in range(n+1):roots,bad=merge_round(roots,np.zeros(n,np.int32),pairs,np.ones(len(pairs),bool),np)
            np.testing.assert_array_equal(roots,[find(i) for i in range(n)])
            self.assertFalse(bad)

    def test_round_budget_cannot_authorize_closure(self):
        s,plans=fixture(np)
        out,roots,m=close(s,np.arange(8,dtype=np.int32),np.zeros(8,np.int32),np.ones((2,3),bool),np.array([[1,2]],np.int32),np.array([True]),plans,np.array(True),1,np)
        self.assertFalse(m['settled']);self.assertTrue(m['budget_pending'])
        np.testing.assert_array_equal(out['slots'],s['slots'])

    def test_gpu_congruence_then_existing_result_reuse(self):
        if not mx.metal.is_available():self.skipTest('Metal required')
        mx.set_default_device(mx.gpu);s,plans=fixture(mx)
        def flow(state):
            out,roots,m=close(state,mx.arange(8,dtype=mx.int32),mx.zeros(8,mx.int32),mx.ones((2,3),mx.bool_),
                mx.array([[1,2]],mx.int32),mx.array([True]),plans,mx.array(True),5,mx)
            witness=project(out,plans[1],mx.array(True),m['settled'],mx)
            result=resolve(mx.array([[1,3]],mx.int32),mx.array([True])&witness['complete'],witness['keys'],witness['ids'],witness['roots'],witness['live'],mx.array(8),mx.array(16),mx.array(8),mx)
            return out,roots,m,result
        out,roots,m,r=mx.compile(flow)(s);mx.eval(out,roots,m,r)
        self.assertTrue(bool(np.array(m['settled'])))
        np.testing.assert_array_equal(np.array(out['slots']),[[1,3,5],[2,4,6]])
        np.testing.assert_array_equal(np.array(out['slot_roots']),[[1,3,5],[1,3,5]])
        self.assertEqual(int(np.array(r['result'])[0]),5);self.assertEqual(int(np.array(r['next_id'])),8)

    def test_device_collects_source_union_and_advances_only_after_closure(self):
        if not mx.metal.is_available():self.skipTest('Metal required')
        mx.set_default_device(mx.gpu)
        sort=dict(kind='eq',name='E')
        recipe=dict(rules=[dict(slots=[dict(sort=sort)]*2,effects=[dict(kind='union',args=[dict(slot=0),dict(slot=1)])])])
        raw,marks=compile_unions(recipe);self.assertFalse(marks)
        plan={k:mx.array(v) for k,v in raw.items()}
        s=dict(keys=mx.array([[0,1,2]],mx.int32),slots=mx.array([[1,2]],mx.int32),slot_valid=mx.array([[True,True]]),
            present=mx.array([True]),active=mx.array([True]),visible=mx.array([True]),settled=mx.array([False]),effect_pc=mx.array([0],mx.int32))
        def run(state,budget):
            pairs,active,missing=union_inputs(state,plan,mx)
            state,roots,m=close(state,mx.arange(4,dtype=mx.int32),mx.zeros(4,mx.int32),mx.ones((1,2),mx.bool_),pairs,active,[],mx.array(True),budget,mx)
            state,advanced=finish_unions(state,plan,active,m,mx)
            return state,m,advanced
        out,m,a=mx.compile(lambda state:run(state,3))(s);mx.eval(out,m,a)
        self.assertTrue(np.array(out['settled'])[0]);self.assertEqual(np.array(out['effect_pc'])[0],1)
        self.assertTrue(np.array(out['token_dirty'])[0]);self.assertTrue(bool(np.array(m['token_refresh_required'])))
        out,m,a=mx.compile(lambda state:run(state,1))(s);mx.eval(out,m,a)
        self.assertFalse(np.array(out['settled'])[0]);self.assertEqual(np.array(out['effect_pc'])[0],0)

    def test_missing_visibility_coverage_and_bad_slot_block_settlement(self):
        s,plans=fixture(np)
        for external,bad_slot in [(False,False),(True,True)]:
            current=dict(s);current['slots']=s['slots'].copy()
            if bad_slot:current['slots'][0,0]=100
            _,_,m=close(current,np.arange(8,dtype=np.int32),np.zeros(8,np.int32),np.ones((2,3),bool),np.array([[1,2]],np.int32),np.array([True]),plans,np.array(external),5,np)
            self.assertFalse(m['settled']);self.assertTrue(m['needs_attention'])


if __name__=='__main__':unittest.main()
