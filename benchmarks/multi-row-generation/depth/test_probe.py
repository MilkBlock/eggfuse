import sys,unittest
from pathlib import Path
import numpy as np
import mlx.core as mx
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from task import generate
from network import Generator
from probe import reference,rollout

class DepthTests(unittest.TestCase):
    def test_source_composition_doubles_path_length(self):
        d=generate(2,3,3,2,'long_cycle');p,f=reference(d['a'],d['b'],5)
        np.testing.assert_array_equal(p[:2],d['targets']);np.testing.assert_array_equal(f[:2],d['fields'])
        # Compare against following original source edges, independently of squaring.
        for g in range(3):
            edges={int(row[0]):int(row[1]) for row in d['b'][g]}
            for step in range(5):
                for i,key in enumerate(d['a'][g,:,0]):
                    at=int(key)
                    for _ in range(2**step):at=edges[at]
                    self.assertEqual(f[step,g,i,1],at)

    def test_first_two_neural_rounds_unchanged(self):
        if not mx.metal.is_available():self.fail('Metal required')
        mx.set_default_device(mx.gpu);d=generate(2,3,2,9);m=Generator()
        args=[mx.array(d[k]) for k in ('x_a','x_b','coords_a','coords_b','coords_pair')]
        old=m.forward(*args);new=rollout(m,*args,3,4);mx.eval(old,new)
        for k in old:np.testing.assert_array_equal(old[k],new[k][:2])

if __name__=='__main__':unittest.main()
