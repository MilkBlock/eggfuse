import unittest
import numpy as np
from boundary_cell_ridge import B,D,state,symbols,projection,features,step
from whole_cell_ridge import request
from test_cell_token_successors import rule,atom,make


class Boundary(unittest.TestCase):
    def setUp(self):
        self.a,self.b,self.c,self.d,self.e=[('input',i) for i in range(5)]
        self.source=[('F',(self.a,self.b)),('F',(self.c,self.d)),('G',(self.a,self.e))]
        self.ports=symbols(self.source);self.consumer=rule([atom('F',0,1)],[make('G',2,1)],2)

    def test_distinguishes_previously_identical_attachments(self):
        a=[(0,self.a),(1,self.b)];b=[(0,self.c),(1,self.d)]
        s=state(self.source,self.ports,5)[None,:]
        q=request(self.consumer,a)[None,:]
        np.testing.assert_array_equal(q,request(self.consumer,b)[None,:])
        w=np.zeros((5*D,1),np.float32)
        first=features(s,q,projection(a,self.ports,5)[None,:],w,np)
        second=features(s,q,projection(b,self.ports,5)[None,:],w,np)
        self.assertFalse(np.allclose(first,second))

    def test_next_request_reads_updated_boundary(self):
        s=state(self.source,self.ports,5)[None,:];p=projection([(0,self.a)],self.ports,5)[None,:]
        q=np.zeros((1,D),np.float32);w=np.zeros((5*D,1),np.float32)
        x=features(s,q,p,w,np);coef=np.zeros((x.shape[1],s.shape[1]+1),np.float32)
        coef[0,D:D+B]=.5;coef[0,-1]=1
        predicted,emit=step(s,q,p,w,coef,np)
        self.assertTrue(emit[0]);np.testing.assert_array_equal(predicted[:,:D],s[:,:D])
        self.assertFalse(np.allclose(features(predicted,q,p,w,np),x))

    def test_opaque_renaming_with_same_layout_preserves_state_and_projection(self):
        rename={v:('opaque',100-i) for i,v in enumerate(self.ports)}
        source=[(n,tuple(rename[v] for v in args)) for n,args in self.source]
        ports=[rename[v] for v in self.ports]
        np.testing.assert_allclose(state(source,ports,5),state(self.source,self.ports,5),atol=1e-6)
        np.testing.assert_array_equal(projection([(0,self.a)],self.ports,5),projection([(0,rename[self.a])],ports,5))

    def test_merged_ports_keep_original_boundary_addresses(self):
        a,b=self.a,self.b
        result=state([('F',(a,a))],[a,b],2,[(a,a),(b,a)])[D:].reshape(2,B)
        np.testing.assert_array_equal(result[0],result[1])

    def test_unrepresented_boundary_is_explicit(self):
        with self.assertRaisesRegex(ValueError,'unrepresented'):
            projection([(0,('new',0))],self.ports,5)


if __name__=='__main__':unittest.main()
