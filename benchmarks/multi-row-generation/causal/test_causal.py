import sys,unittest
from pathlib import Path
import numpy as np
import mlx.core as mx
from causal_model import CausalGenerator
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from task import generate
from network import Generator

class CausalTests(unittest.TestCase):
    def setUp(self):
        if not mx.metal.is_available():self.fail('Metal required')
        mx.set_default_device(mx.gpu);mx.random.seed(901)

    def test_block_is_same_neural_function_as_joint_generator(self):
        d=generate(2,3,2,8);m=CausalGenerator();old=Generator('joint');old.update(m.parameters())
        args=[mx.array(d[k]) for k in ('x_a','x_b','coords_a','coords_b','coords_pair')]
        baseline=old.forward(*args);block=m.forward_grouped(*args[:4],3,2,2,'block');mx.eval(baseline,block)
        for k in baseline:np.testing.assert_array_equal(baseline[k],block[k])

    def test_full_source_visible_and_generated_prefix_causal(self):
        m=CausalGenerator();d=generate(2,3,1,18)
        source=m.encoder(mx.array(d['x_a']));memory=m.encoder(mx.array(d['x_b']))
        pa,pb,pp=[mx.array(d[k]) for k in ('coords_a','coords_b','coords_pair')]
        changed=mx.concatenate((source[:,:3],mx.zeros_like(source[:,3:])),axis=1)
        first=m.stage(source,memory,pa,pb,pp,0,2,3,'serial')
        second=m.stage(changed,memory,pa,pb,pp,0,2,3,'serial');mx.eval(first,second)
        self.assertFalse(np.allclose(first[1][:,:3],second[1][:,:3]))
        future_erased=m.stage(source,memory,pa,pb,pp,0,2,3,'serial',erase_after=3);mx.eval(future_erased)
        np.testing.assert_array_equal(first[1][:,:4],future_erased[1][:,:4])
        self.assertFalse(np.allclose(first[1][:,4:],future_erased[1][:,4:]))
        erased=m.stage(source,memory,pa,pb,pp,0,2,3,'serial',True);mx.eval(erased)
        np.testing.assert_array_equal(first[1][:,:1],erased[1][:,:1])
        self.assertFalse(np.allclose(first[1][:,1:],erased[1][:,1:]))

if __name__=='__main__':unittest.main()
