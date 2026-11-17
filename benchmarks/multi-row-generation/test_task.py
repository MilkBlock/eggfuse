import unittest
import numpy as np
import mlx.core as mx
import mlx.nn as nn
from task import generate,audit,fingerprints,KEYS,VALUES
from network import Generator,loss

class GenerationTests(unittest.TestCase):
    def test_offline_labels_are_complete_relational_results(self):
        d=generate(2,3,12,99,'long_cycle')
        addr=np.stack((d['coords_b'][d['targets'][0]],d['coords_pair'][d['targets'][1]]))
        r=audit(d,d['targets'],d['fields'],addr)
        self.assertEqual(r['whole_graph_passed'],12)
        self.assertGreater(r['cross_row_successor_obligations'],0)
        self.assertTrue(all(c==(6,) for c in d['cycle_keys']))

    def test_duplicate_wrong_binding_is_rejected(self):
        d=generate(2,3,2,5);p=d['targets'].copy();p[0,:,1]=p[0,:,0]
        addr=np.stack((d['coords_b'][p[0]],d['coords_pair'][p[1]]))
        r=audit(d,p,d['fields'],addr)
        self.assertEqual(r['whole_graph_passed'],0)
        self.assertGreater(r['repeated_first_stage_partner_count'],0)

    def test_distinct_inputs_and_held_cycle_shapes(self):
        train=generate(2,3,80,1);test=generate(2,3,80,2,'long_cycle')
        self.assertFalse(set(fingerprints(train))&set(fingerprints(test)))
        self.assertTrue(all(max(c)<=2 for c in train['cycle_keys']))
        self.assertFalse(set(train['cycle_keys'])&set(test['cycle_keys']))

    def test_neural_recurrence_gradients_and_cached_query_serialization(self):
        if not mx.metal.is_available():self.fail('Metal required')
        mx.set_default_device(mx.gpu);mx.random.seed(12)
        d=generate(2,3,2,8);m=Generator('joint')
        args=[mx.array(d[k]) for k in ('x_a','x_b','coords_a','coords_b','coords_pair')]
        out=m.forward(*args);mx.eval(out)
        _,h2,f2=m.emit(m.prepare(out['latent'][0],out['latent'][0],args[-1],args[-1],1));mx.eval(h2,f2)
        np.testing.assert_array_equal(h2,out['latent'][1])
        value,g=nn.value_and_grad(m,loss)(m,*args,mx.array(d['targets']),mx.array(d['fields']));mx.eval(value,g)
        self.assertTrue(np.isfinite(float(value)))
        self.assertGreater(float(mx.max(mx.abs(g['encoder']['layers'][0]['weight']))),0)
        serial=m.serial_same_queries(*args);mx.eval(serial)
        np.testing.assert_allclose(serial['field_logits'],out['field_logits'],atol=1e-4)
        np.testing.assert_array_equal(serial['pointers'],out['pointers'])

if __name__=='__main__':unittest.main()
