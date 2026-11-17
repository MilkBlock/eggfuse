import unittest
import numpy as np
import mlx.core as mx
from task import generate,KEYS
from test_direction import literal_output
from checked_forward import check

class CheckedForward(unittest.TestCase):
    def test_binds_values_to_latent_without_fixing_advertised_values(self):
        d=generate(2,3,3,55,'functional');out=literal_output(d)
        width=out['field_logits'].shape[-1]
        out['latent']=mx.concatenate((out['field_logits'],mx.zeros(out['field_logits'].shape[:-1]+(64-width,))),-1)
        weight=mx.eye(width,64);bias=mx.zeros((width,))
        args=(mx.array(d['a']),mx.array(d['b']))
        coords=(mx.array(d['coords_b']),mx.array(d['coords_pair']))
        good=check(*args,out,*coords,weight,bias);mx.eval(good)
        self.assertTrue(bool(mx.all(good['whole_graph'])))
        bad=dict(out);bad['field_logits']=mx.array(out['field_logits'])
        wrong=(int(d['fields'][0,0,0,0])+1)%KEYS
        bad['field_logits'][0,0,0,:KEYS]=mx.eye(KEYS)[wrong]*20-10
        v=check(*args,bad,*coords,weight,bias);mx.eval(v)
        self.assertFalse(bool(v['whole_graph'][0]));self.assertFalse(bool(v['latent_bound'][0,0,0]))
        np.testing.assert_array_equal(out['latent'],bad['latent'])

if __name__=='__main__':unittest.main()
