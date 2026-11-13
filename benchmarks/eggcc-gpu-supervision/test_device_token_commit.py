import unittest
import numpy as np
import mlx.core as mx
from device_token_commit import commit, closed_entry_proposals


def seed(capacity=5):
    state=dict(keys=np.full((capacity,2),-1,np.int32),tokens=np.zeros((capacity,3),np.float32))
    for k in ('present','active','visible','settled','readers'):state[k]=np.zeros(capacity,bool)
    state['generation']=np.zeros(capacity,np.int32)
    state['keys'][0]=[0,17];state['tokens'][0]=[.2,-.3,.7]
    for k in ('present','active','visible','settled'):state[k][0]=True
    state['generation'][0]=1
    return state


def proposals(keys, source=None):
    n=len(keys)
    return dict(keys=np.array(keys,np.int32),tokens=np.ones((n,3),np.float32),
        source=np.zeros(n,np.int32) if source is None else np.array(source,np.int32),
        generation=np.ones(n,np.int32),matched=np.ones(n,bool),
        transfer_covered=np.ones(n,bool),completed=np.ones(n,bool))


class TokenCommit(unittest.TestCase):
    def test_duplicate_keeps_one_and_preserves_source_on_competition(self):
        out,m=commit(seed(),proposals([[1,17],[1,17]]),np)
        self.assertEqual(m['accepted'].tolist(),[True,False])
        self.assertEqual(m['transferred'].tolist(),[False,False])
        self.assertTrue(out['active'][0]);self.assertEqual(out['present'].sum(),2)
        again,m=commit(out,proposals([[1,17]]),np)
        np.testing.assert_array_equal(again['tokens'],out['tokens'])
        self.assertTrue(m['no_new_admission'])

    def test_transfer_requires_settlement_readers_and_coverage(self):
        for field in ('settled','readers','transfer_covered'):
            state=seed();p=proposals([[1,17]])
            if field=='transfer_covered':p[field][0]=False
            else:state[field][0]=(field=='readers')
            out,m=commit(state,p,np)
            self.assertTrue(out['active'][0]);self.assertEqual(bool(m['accepted'][0]),field!='settled')
        out,m=commit(seed(),proposals([[1,17]]),np)
        self.assertFalse(out['active'][0]);self.assertTrue(out['active'][1])
        self.assertTrue(out['present'][0]);self.assertTrue(m['transferred'][0])

    def test_stale_hidden_nonfinite_and_capacity_are_not_closure(self):
        p=proposals([[1,17],[2,17],[3,17]],[-1,0,0]);p['generation'][1]=9;p['tokens'][2,0]=np.nan
        out,m=commit(seed(),p,np)
        self.assertFalse(m['accepted'].any());self.assertEqual(m['stale_source'].sum(),2)
        self.assertTrue(m['nonfinite'][2]);self.assertTrue(m['no_new_admission'])
        out,m=commit(seed(1),proposals([[1,17]]),np)
        self.assertTrue(m['capacity'][0]);self.assertFalse(m['transferred'][0]);self.assertTrue(out['active'][0])
        s=seed();s['visible'][0]=False
        self.assertTrue(commit(s,proposals([[1,17]]),np)[1]['stale_source'][0])

    def test_device_matches_dynamic_sources_and_stops_repeated_derivations(self):
        if not mx.metal.is_available():self.skipTest('Metal required')
        plan=dict(producer=np.array([0,1],np.int32),consumer=np.array([1,2],np.int32),
            stage=np.array([0,0],np.int32),projection=np.array([[1],[1]],np.int32),
            query_covered=np.array([True,True]),transfer_covered=np.array([True,True]),
            completed=np.array([True,True]),weights=np.stack([np.eye(3,dtype=np.float32)*.7]*2),
            bias=np.full((2,3),.1,np.float32))
        device_plan={k:mx.array(v) for k,v in plan.items()}
        def flow(state):
            marks=[]
            for _ in range(4):
                state,m=commit(state,closed_entry_proposals(state,device_plan,mx.array(0),mx),mx)
                marks.append(m)
            return state,marks
        out,marks=mx.compile(flow)({k:mx.array(v) for k,v in seed().items()});mx.eval(out,marks)
        self.assertEqual(np.array(out['keys'])[:3].tolist(),[[0,17],[1,17],[2,17]])
        self.assertEqual([int(np.array(m['accepted']).sum()) for m in marks],[1,1,0,0])
        self.assertFalse(any(bool(np.array(m['needs_attention'])) for m in marks))
        wrong_stage=closed_entry_proposals(seed(),plan,np.array(1),np)
        self.assertFalse(wrong_stage['matched'].any())
        changed=seed();changed['keys'][0,0]=1
        other,_=mx.compile(flow)({k:mx.array(v) for k,v in changed.items()});mx.eval(other)
        self.assertEqual(np.array(other['present']).sum(),2)
        self.assertEqual(np.array(other['keys'])[1].tolist(),[2,17])

    def test_device_rounds_consume_previous_float_state_without_host_reads(self):
        if not mx.metal.is_available():self.skipTest('Metal required')
        mx.set_default_device(mx.gpu)
        initial=seed();weight=np.array([[.3,-.7,.2],[.8,.4,-.6],[-.2,.9,.5]],np.float32)
        def flow(state,xp):
            outputs=[]
            # Static unroll of two kernel rounds, not a host read of success.
            for src in (0,1):
                p={k:xp.array(v) for k,v in proposals([[src+1,17]],[src]).items()}
                p['tokens']=xp.tanh(state['tokens'][src:src+1]@xp.array(weight))
                state,marks=commit(state,p,xp);outputs.append(marks)
            return state,outputs
        reference,_=flow(initial,np)
        result,marks=mx.compile(lambda s:flow(s,mx))({k:mx.array(v) for k,v in initial.items()})
        mx.eval(result,marks)
        for key,value in result.items():np.testing.assert_allclose(np.array(value),reference[key],atol=2e-6)
        self.assertEqual(np.array(result['active']).tolist(),[False,False,True,False,False])
        changed=seed();changed['tokens'][0]*=2
        other,_=flow({k:mx.array(v) for k,v in changed.items()},mx);mx.eval(other)
        self.assertFalse(np.allclose(np.array(result['tokens'])[2],np.array(other['tokens'])[2]))


if __name__=='__main__':unittest.main()
