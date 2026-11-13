import unittest
import numpy as np
from boundary_cell_ridge import B,D,state,symbols,projection,features,step,fit_boundary_basis,compress_state,compress_projection,audit_boundary,output_layout,request_with_roles
from whole_cell_ridge import request
from test_cell_token_successors import rule,atom,make,TABLES
from dominator_completion import compose


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

    def test_folded_projection_matches_reconstructed_boundary(self):
        rng=np.random.default_rng(3)
        basis,_=np.linalg.qr(rng.normal(size=(32,8)))
        basis=basis.astype(np.float32)
        latent=rng.normal(size=(3,8)).astype(np.float32)
        projections=rng.normal(size=(3,32,D)).astype(np.float32)
        folded=compress_projection(projections,basis)
        direct=np.matmul(latent[:,None,:],folded)
        reconstructed=np.matmul((latent@basis.T)[:,None,:],projections)
        np.testing.assert_allclose(direct,reconstructed,rtol=1e-5,atol=1e-5)

    def test_basis_does_not_read_held_out_targets(self):
        rng=np.random.default_rng(4)
        source=rng.normal(size=(8,D+12)).astype(np.float32)
        target=rng.normal(size=source.shape).astype(np.float32)
        training=np.arange(8)<4
        basis=fit_boundary_basis(source,target,training,3)
        source[~training]=1e4;target[~training]=-1e4
        np.testing.assert_array_equal(basis,fit_boundary_basis(source,target,training,3))

    def test_full_basis_preserves_attachment_and_boundary(self):
        s=state(self.source,self.ports,5)[None,:]
        basis=np.eye(5*B,dtype=np.float32)
        compressed=compress_state(s,basis)
        np.testing.assert_array_equal(audit_boundary(compressed,basis),s[:,D:])
        p=projection([(0,self.a)],self.ports,5)[None,:]
        q=np.zeros((1,D),np.float32);w=np.zeros((5*D,1),np.float32)
        np.testing.assert_array_equal(features(s,q,p,w,np),features(compressed,q,compress_projection(p,basis),w,np))

    def test_generated_output_is_reserved_empty_then_available_to_next_request(self):
        source=[('F',(self.a,self.b))]
        first=rule([atom('F',0,1)],[make('G',2,1)],3)
        completion,reason=compose(source,first,[(0,self.a),(1,self.b)],TABLES)
        self.assertIsNone(reason)
        ports,mapping,added=output_layout(source,completion)
        self.assertEqual(len(added),1)
        before=state(source,ports,len(ports),allow_absent=True)
        after=state(completion['facts'],ports,len(ports),mapping)
        index=ports.index(added[0]);start=D+index*B
        np.testing.assert_array_equal(before[start:start+B],np.zeros(B))
        self.assertGreater(float(np.linalg.norm(after[start:start+B])),0)
        next_rule=rule([atom('G',0,1)],[make('F',2,1)],3)
        next_binding=[(0,self.b),(1,added[0])]
        second,reason=compose(completion['facts'],next_rule,next_binding,TABLES)
        self.assertIsNone(reason);self.assertTrue(second['novel'])
        p=projection(next_binding,ports,len(ports))[None,:]
        q=request(next_rule,next_binding)[None,:];w=np.zeros((5*D,1),np.float32)
        self.assertFalse(np.allclose(features(before[None,:],q,p,w,np),features(after[None,:],q,p,w,np)))

    def test_constructor_reuse_does_not_allocate_new_boundary(self):
        source=[('F',(self.a,self.b))]
        consumer=rule([atom('F',0,1)],[make('F',2,0)],3)
        completion,reason=compose(source,consumer,[(0,self.a),(1,self.b)],TABLES)
        self.assertIsNone(reason)
        ports,_,added=output_layout(source,completion)
        self.assertEqual(ports,symbols(source));self.assertEqual(added,[])

    def test_positioned_request_uses_roles_not_physical_ids(self):
        r=rule([atom('F',0,1),atom('F',2,3)],[make('G',4,1),make('G',5,3)])
        left=[(0,('input',0)),(1,('literal','2')),(2,('input',1)),(3,('literal','3'))]
        right=[(0,('input',0)),(1,('literal','3')),(2,('input',1)),(3,('literal','2'))]
        self.assertFalse(np.allclose(request_with_roles(r,left,True),request_with_roles(r,right,True)))
        renamed=[(s,('opaque',500+s) if v[0]=='input' else v) for s,v in left]
        np.testing.assert_allclose(request_with_roles(r,left,True),request_with_roles(r,renamed,True),atol=1e-6)
        np.testing.assert_array_equal(request_with_roles(r,left,False),request(r,left))

    def test_unrepresented_boundary_is_explicit(self):
        with self.assertRaisesRegex(ValueError,'unrepresented'):
            projection([(0,('new',0))],self.ports,5)


if __name__=='__main__':unittest.main()
