import unittest
import numpy as np
import mlx.core as mx
from device_completion_states import compile_states, compile_tokens, tokens, partitions, project
from device_token_refresh import encode_batch
from device_semantic_template import template


def rule(n, effects=()):
    return dict(slots=[dict(sort=dict(kind='eq',name='Expr'),definition='query') for _ in range(n)],
                query=[],effects=list(effects))


class CompletionStates(unittest.TestCase):
    def test_all_partitions_and_static_quotient(self):
        self.assertEqual([len(list(partitions(n))) for n in range(6)],[1,1,2,5,15,52])
        r=rule(3,[dict(kind='union',args=[dict(slot=0),dict(slot=1)])])
        plan=compile_states(r)
        self.assertEqual(len(plan['states']),2)
        self.assertTrue(plan['full'][:,0].all())
        with self.assertRaises(ValueError):compile_states(rule(8),100)

    def test_typed_empty_and_scalar_states(self):
        r=rule(2);r['slots'][1]['sort']['name']='Context'
        self.assertEqual(compile_states(r)['states'].shape,(1,0))
        r['slots'][0]['sort']=dict(kind='scalar',name='f64')
        self.assertEqual(compile_states(r)['states'].shape,(1,0))

    def test_transitivity_required_edges_and_gpu(self):
        states=compile_states(rule(3))['states']
        scores=np.array([[.9,.1,.8],[.1,.1,.1],[.5,.5,.5]],np.float32)
        required=np.array([[False,False,False],[True,False,False],[False]*3])
        actual,idx=project(scores,states,required,np)
        self.assertTrue(actual[1,0]);self.assertFalse(actual[2].any())
        # Every output is a complete equivalence relation, including adversarial scores.
        self.assertFalse(any(row.sum()==2 for row in actual))
        gpu=mx.compile(lambda x,r:project(x,mx.array(states),r,mx))
        out,ids=gpu(mx.array(scores),mx.array(required));mx.eval(out,ids)
        np.testing.assert_array_equal(out,actual);np.testing.assert_array_equal(ids,idx)

    def test_full_tokens_retain_dynamic_scalars(self):
        r=rule(3);r['slots'].append(dict(sort=dict(kind='f64',name='f64'),definition='query'))
        plan=compile_states(r);compiled=compile_tokens(r,plan)
        codes=np.random.default_rng(8).normal(size=(len(plan['states']),1,64)).astype(np.float32)
        chosen=np.arange(len(codes),dtype=np.int32)
        result=tokens(chosen,codes,compiled,np)
        roles=template(r)[0];roots=[]
        for state in plan['full']:
            ids=list(range(4))
            for (a,b),yes in zip(plan['pairs'],state):
                if yes:
                    old=ids[b];ids=[ids[a] if v==old else v for v in ids]
            roots.append(ids)
        scalar_codes=np.zeros((len(codes),4,64),np.float32);scalar_codes[:,3:]=codes
        expected=encode_batch(np.array(roots),np.tile([0,0,0,-1],(len(codes),1)),
            np.tile([True,True,True,False],(len(codes),1)),np.ones((len(codes),4),bool),
            np.broadcast_to(roles,(len(codes),4,64)),scalar_codes,np)
        np.testing.assert_allclose(result,expected,atol=2e-7)
        device_plan={k:mx.array(v) for k,v in compiled.items()}
        out=mx.compile(lambda c:tokens(mx.array(chosen),c,device_plan,mx))(mx.array(codes));mx.eval(out)
        np.testing.assert_allclose(out,expected,atol=3e-7)
        self.assertGreater(np.max(abs(result-tokens(chosen,np.zeros_like(codes),compiled,np))),.01)

if __name__=='__main__':unittest.main()
