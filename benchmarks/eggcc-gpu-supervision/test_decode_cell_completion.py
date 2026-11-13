import unittest
import numpy as np
import mlx.core as mx
from decode_cell_completion import retention, gpu_decode, representation
from whole_cell_ridge import encode, request
from dominator_completion import compose
from test_cell_token_successors import rule, atom, make, TABLES


class Decode(unittest.TestCase):
    def test_retention_requires_every_source_fact_and_port(self):
        a,b,c=('input',0),('input',1),('input',2)
        source=[('F',(a,b)),('G',(b,c))]
        self.assertFalse(retention(source,source,[(a,a),(b,b)]))
        self.assertFalse(retention(source,source[:1],[(a,a),(b,b),(c,c)]))
        self.assertTrue(retention(source,source,[(a,a),(b,b),(c,c)]))

    def test_quotient_preserves_facts(self):
        a,b,c=('input',0),('input',1),('input',2)
        self.assertTrue(retention([('F',(a,b)),('F',(a,c))],
                                  [('F',(a,b))],[(a,a),(b,b),(c,b)]))

    def test_conflicting_source_mapping_is_rejected(self):
        a,b=('input',0),('input',1)
        self.assertFalse(retention([('F',(a,b))],[('F',(a,b))],
                                   [(a,b),(a,a),(b,b)]))

    def test_gpu_masks_unrelated_producer_and_exposes_ties(self):
        values=mx.array([[0.,0.],[1.,1.]])
        prototypes=mx.array([[0.,0.],[1.,1.],[1.,1.]])
        selected,_,margin=gpu_decode(values,prototypes,mx.array([1,1]),mx.array([0,1,1]))
        mx.eval(selected,margin)
        self.assertTrue(np.all(np.array(selected)!=0))
        np.testing.assert_array_equal(np.array(margin),[0.,0.])

    def test_same_body_different_boundary_map_remains_distinct(self):
        a,b=('input',0),('input',1)
        facts=[('F',(a,b))]
        self.assertNotEqual(representation(facts,[(a,a),(b,b)]),
                            representation(facts,[(a,b),(b,a)]))

    def test_current_request_loses_attachment_to_source(self):
        # Diagnostic: exactly identical model inputs require different targets.
        # This cannot be repaired by more ridge training or a larger hidden layer.
        a,b,c,d,e=[('input',i) for i in range(5)]
        source=[('F',(a,b)),('F',(c,d)),('G',(a,e))]
        consumer=rule([atom('F',0,1)],[make('G',2,1)],2)
        left=[(0,a),(1,b)];right=[(0,c),(1,d)]
        np.testing.assert_array_equal(request(consumer,left),request(consumer,right))
        first,err1=compose(source,consumer,left,TABLES)
        second,err2=compose(source,consumer,right,TABLES)
        self.assertIsNone(err1);self.assertIsNone(err2)
        self.assertFalse(np.allclose(encode(first['facts']),encode(second['facts'])))


if __name__=='__main__':unittest.main()
