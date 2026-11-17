"""ABI/reference and permutation tests; synthetic oracle states stay in tests only."""
import unittest
import numpy as np
import mlx.core as mx
from abi import *
from shared_net import SharedNet,parts,pack,rotate
from cpu_contract import cpu_scores
from semantics import checker_eq,expected,decode
from spec import seed_inputs,sample,positions,SHAPES,shape_key
from fresh import freeze

class ContractTests(unittest.TestCase):
    def test_fresh_shape_disjointness(self):
        f=freeze();keys={shape_key(s) for s in f['shapes']}
        self.assertEqual(len(keys),16)
        self.assertFalse(keys&{shape_key(s) for s in SHAPES[:10]})
        for s in f['shapes']:
            for dst,(op,a,b) in enumerate(s,4):
                self.assertLess(a,dst)
                self.assertTrue(b==9 if op==0 else b<dst)

    def test_reference_frames_decode_without_repair(self):
        rng=np.random.default_rng(42)
        for c in sample('joint',6,rng):
            seed=mx.array(seed_inputs([c]));pos=mx.array(positions(1,rng))
            for s in (1,2,3):
                want=expected(c,s);eq=mx.array(checker_eq(c,s)[None].astype(np.float32))
                ptr=mx.array(np.eye(9)[np.array(want['alias'])][None].astype(np.float32))
                phase=mx.eye(3)[s-1][None];gate=mx.array([want['retired']],mx.float32)
                h=pack(eq,ptr,seed,phase,gate);at=pos[:,want['owner'][0]]
                token=rotate(h,at,'cell');mx.eval(token)
                decoded=decode(cpu_scores(np.array(token),np.array(at)))
                for k in SPECS:self.assertEqual(decoded[k][0].tolist(),want[k],k)

    def test_relation_features_are_leaf_permutation_equivariant(self):
        rng=np.random.default_rng(22);m=SharedNet();seed=mx.array(seed_inputs(sample('seen',3,rng)));d=parts(seed)
        eq=mx.array(rng.random((3,8,8)).astype(np.float32));perm=mx.array([1,0,2,3,4,5,6,7])
        before=m.relation_features(eq,d,1.)
        after_d=dict(d)
        args=d['args'];after_d['args']=mx.concatenate((args[:,:,:,perm],args[:,:,:,8:]),-1)
        after_d['union']=d['union'][:,:,perm]
        after=m.relation_features(eq[:,perm][:,:,perm],after_d,1.)
        mx.eval(before,after)
        np.testing.assert_allclose(after,before[:,perm][:,:,perm],atol=1e-6)

if __name__=='__main__':unittest.main()
