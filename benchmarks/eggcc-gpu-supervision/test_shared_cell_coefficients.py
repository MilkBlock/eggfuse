import unittest
import numpy as np
from packed_cell_replay import prepare,prepare_shared,prepare_broadcast,costs,executor
from test_packed_cell_replay import fixture
from multi_entry_ridge import WIDTH

class SharedCoefficients(unittest.TestCase):
    def make_nodes(self):
        nodes,w,coef=fixture();nodes=nodes[:18]
        for i in range(10):
            nodes.append(dict(seed=np.zeros(WIDTH,np.float32),q=np.zeros(64,np.float32),
                target=np.zeros(WIDTH,np.float32),valid=True,depth=1,
                edges=[(i,np.ones(WIDTH,np.float32))]))
        return nodes,w,coef

    def test_share_constants_not_instance_sources(self):
        nodes,w,coef=self.make_nodes();base=prepare(nodes,'two');shared=prepare_shared(nodes)
        self.assertEqual(costs(shared)['shared_rows'],10)
        self.assertLess(costs(shared)['unique_coefficient_bytes'],costs(base)['unique_coefficient_bytes'])
        group=shared[1]['groups'][0]
        self.assertEqual(group['base'].shape,(1,1,WIDTH))
        self.assertEqual(group['sources'].reshape(-1).tolist(),list(range(10)))
        np.testing.assert_allclose(executor(nodes,w,coef,shared,False)(),executor(nodes,w,coef,base,False)(),atol=1e-6,rtol=1e-6)

    def test_broadcast_keeps_group_count_and_does_not_retain_expansion(self):
        nodes,w,coef=self.make_nodes();base=prepare(nodes,'two');shared=prepare_broadcast(nodes)
        self.assertEqual(costs(shared)['aggregation_groups'],costs(base)['aggregation_groups'])
        self.assertLess(costs(shared)['unique_coefficient_bytes'],costs(base)['unique_coefficient_bytes'])
        group=shared[1]['groups'][0]
        self.assertTrue(group['base'].flags['OWNDATA'])
        np.testing.assert_allclose(executor(nodes,w,coef,shared,False)(),executor(nodes,w,coef,base,False)(),atol=1e-6,rtol=1e-6)

    def test_different_weights_are_not_shared_by_shape(self):
        nodes,_,_=self.make_nodes()
        for i,n in enumerate(nodes[18:]):n['edges'][0]=(i,np.full(WIDTH,i+1,np.float32))
        self.assertEqual(costs(prepare_shared(nodes))['shared_groups'],0)

    def test_exact_constants_reused_across_layers(self):
        nodes,_,_=self.make_nodes()
        for i in range(10):
            nodes.append(dict(seed=np.zeros(WIDTH),q=np.zeros(64),target=np.zeros(WIDTH),
                valid=True,depth=2,edges=[(18+i,np.ones(WIDTH,np.float32))]))
        plan=prepare_shared(nodes)
        self.assertIs(plan[1]['groups'][0]['base'],plan[2]['groups'][0]['base'])
        self.assertLess(costs(plan)['unique_coefficient_bytes'],costs(plan)['coefficient_bytes'])

if __name__=='__main__':unittest.main()
