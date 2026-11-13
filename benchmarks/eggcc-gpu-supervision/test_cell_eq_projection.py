import unittest
import numpy as np
import mlx.core as mx
from cell_eq_projection import groups,compile_projection,project
from boundary_cell_ridge import D,B


class EqProjection(unittest.TestCase):
    def test_transitive_groups_and_disjoint_padding(self):
        self.assertEqual(groups([(0,1),(2,3),(1,2),(4,4)]),[[0,1,2,3]])
        plans=[(None,[(0,1),(1,2)]),(None,[])];w=compile_projection(plans,5)
        self.assertEqual(len(set(w[0][1])),len(w[0][1]))
        v=np.random.default_rng(3).normal(size=(2,D+5*B)).astype(np.float32)
        out=project(v,w,np);ch=out[:,D:].reshape(2,5,B)
        np.testing.assert_allclose(ch[0,0],ch[0,1]);np.testing.assert_allclose(ch[0,1],ch[0,2])
        np.testing.assert_array_equal(out[1],v[1]);np.testing.assert_array_equal(out[:,:D],v[:,:D])
        np.testing.assert_allclose(project(out,w,np),out,atol=1e-6)
        np.testing.assert_allclose(np.array(project(mx.array(v),[mx.array(x) for x in w],mx)),out,atol=1e-6)

if __name__=='__main__':unittest.main()
