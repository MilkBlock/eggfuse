import unittest
import numpy as np
import mlx.core as mx
from compile_constructor_sites import compile_sites
from cell_token_successors import compile_catalog
from lower_device_entries import lower,tensors
from device_entry_transition import compile_features
from device_entry_round import run_round
from device_constructor_completion import compile_completion,complete


def recipe():
    eq=dict(kind='eq',name='E')
    def slots(n,q):return [dict(sort=eq,definition='query' if i<q else 'effect') for i in range(n)]
    def query(t,args):return dict(call=dict(table=t),args=[dict(slot=i) for i in args])
    def op(t,a,d):return dict(kind='construct',call=dict(table=t),args=[dict(slot=a)],dst=d)
    return dict(tables=[dict(name=t,kind='constructor') for t in ('Input','F','G')],rules=[
        dict(metadata=dict(source_set='s'),slots=slots(2,1),query=[query('Input',[0])],effects=[op('F',0,1)]),
        dict(metadata=dict(source_set='s'),slots=slots(3,2),query=[query('F',[0,1])],effects=[op('G',1,2)]),
        dict(metadata=dict(source_set='s'),slots=slots(2,2),query=[query('G',[0,1])],effects=[])])


def state():
    s=dict(keys=np.array([[0,7,-1],[-1,-1,-1],[-1,-1,-1]],np.int32),slots=np.array([[7,-1,-1],[-1,-1,-1],[-1,-1,-1]],np.int32),
        slot_roots=np.array([[7,-1,-1],[-1,-1,-1],[-1,-1,-1]],np.int32),slot_valid=np.array([[True,False,False],[False]*3,[False]*3]),
        tokens=np.zeros((3,128),np.float32),generation=np.array([1,0,0],np.int32),effect_pc=np.zeros(3,np.int32))
    for k in ('present','active','visible'):s[k]=np.array([True,False,False])
    for k in ('settled','readers','token_dirty'):s[k]=np.zeros(3,bool)
    return s


def device_plan(plan):
    p=dict(plan);p['views']={key:{k:mx.array(v) if isinstance(v,np.ndarray) else v for k,v in view.items()} for key,view in p['views'].items()}
    p['layouts']=[(rid,{k:mx.array(v) for k,v in layout.items()}) for rid,layout in p['layouts']]
    return p


class ConstructorCompletion(unittest.TestCase):
    def test_generated_cell_effects_refresh_then_generate_next_cell_on_gpu(self):
        if not mx.metal.is_available():self.skipTest('Metal required')
        r=recipe();lowered=lower(r,compile_catalog(r),source_slots=True);blocks=[]
        dev=lambda d:{k:mx.array(v) for k,v in d.items()}
        for entry in lowered['entries']:
            p=tensors(dict(lowered,entries=[entry]),np.zeros((1,128,128)),np.zeros((1,128)));p.pop('weights');p.pop('bias')
            il,cl=compile_features(r,entry);blocks.append(tuple(map(dev,(p,il,cl))))
        cp=device_plan(compile_completion(r,3));rng=np.random.default_rng(12)
        model=dev(dict(w=rng.normal(0,.01,(1408,16)).astype(np.float32),coef=rng.normal(0,.01,(1425,128)).astype(np.float32)))
        def run(s):
            s,next_id,initial=complete(s,cp,mx.array(100),mx.array(200),mx.array(100),mx.array(True),mx.array(True),mx)
            counts=[];effects=[]
            for _ in range(3):
                s,admission=run_round(s,blocks,model,mx.array(0),mx)
                s,next_id,completion=complete(s,cp,next_id,mx.array(200),mx.array(100),mx.array(True),mx.array(True),mx)
                counts.append(admission['new_tokens']);effects.append(completion['executed'])
            return s,next_id,mx.stack(counts),mx.stack(effects)
        out,n,counts,effects=mx.compile(run)(dev(state()));mx.eval(out,n,counts,effects)
        self.assertEqual(np.array(counts).tolist(),[1,1,0]);self.assertEqual(np.array(effects).tolist(),[1,0,0])
        self.assertEqual(int(n),102);self.assertTrue(np.array(out['settled']).all());self.assertFalse(np.array(out['token_dirty']).any())
        np.testing.assert_array_equal(np.array(out['slots'])[1],[7,100,101])
        np.testing.assert_array_equal(np.array(out['keys'])[2],[2,100,101])

    def test_unknown_external_witnesses_block_allocation_and_refresh(self):
        s=state();cp=compile_completion(recipe(),3)
        out,n,marks=complete(s,cp,np.array(100),np.array(200),np.array(100),np.array(False),np.array(True),np)
        self.assertEqual(n,100);self.assertEqual(marks['executed'],0);self.assertTrue(marks['needs_attention'])
        self.assertFalse(out['settled'][0])

    def test_unsupported_effect_does_not_advance_to_later_constructor(self):
        r=recipe();r['rules'][0]['effects'].insert(0,dict(kind='union',args=[dict(slot=0),dict(slot=0)]))
        out,n,marks=complete(state(),compile_completion(r,3),np.array(100),np.array(200),np.array(100),np.array(True),np.array(True),np)
        self.assertEqual(n,100);self.assertEqual(out['effect_pc'][0],0);self.assertTrue(marks['needs_attention'])


if __name__=='__main__':unittest.main()
