import unittest
import numpy as np
from packed_cell_replay import prepare,costs,executor
from multi_entry_ridge import replay,WIDTH


def fixture():
    def node(seed,edges,depth):
        return dict(seed=np.full(WIDTH,seed,np.float32),q=np.zeros(64,np.float32),
            target=np.zeros(WIDTH,np.float32),valid=True,depth=depth,
            edges=[(i,np.ones(WIDTH,np.float32)) for i in edges])
    nodes=[node(i/18,[],0) for i in range(18)]
    nodes.extend([node(0,[0],1),node(0,list(range(17)),1),node(0,[4,5,6],1),node(0,[18,19,20],2)])
    w=np.zeros((448,1),np.float32);coef=np.zeros((450,WIDTH),np.float32)
    for i in range(WIDTH):coef[1+i,i]=.2;coef[1+WIDTH+64+i,i]=.1
    return nodes,w,coef


class PackedReplay(unittest.TestCase):
    def test_grouping_preserves_all_destinations_and_one_readout_per_layer(self):
        nodes,_,_=fixture();flat=prepare(nodes,False);packed=prepare(nodes,True)
        self.assertEqual(costs(flat)['readouts'],costs(packed)['readouts'])
        self.assertLess(costs(packed)['padded_edges'],costs(flat)['padded_edges'])
        self.assertEqual(sorted(i for l in packed for i in l['ids']),list(range(len(nodes))))
        self.assertTrue(all(g['sources'].size==0 for g in packed[0]['groups']))
        two=prepare(nodes,'two')
        self.assertTrue(all(sum(g['sources'].shape[1]>0 for g in layer['groups'])<=2 for layer in two))

    def test_numerics_and_reused_plan_match_original(self):
        nodes,w,coef=fixture();expected=replay(nodes,w,coef,False)
        for packed in (False,True,"two"):
            run=executor(nodes,w,coef,prepare(nodes,packed),False)
            np.testing.assert_allclose(run(),expected,atol=1e-6,rtol=1e-6)
            np.testing.assert_array_equal(run(),run())

    def test_rejects_same_layer_dependency(self):
        nodes,_,_=fixture();nodes[0]['edges']=[(1,np.ones(WIDTH))]
        with self.assertRaisesRegex(ValueError,'independence'):prepare(nodes,True)

if __name__=='__main__':unittest.main()
