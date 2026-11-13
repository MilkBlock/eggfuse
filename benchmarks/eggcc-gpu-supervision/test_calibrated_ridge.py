import copy
import unittest
import numpy as np
import mlx.core as mx
from calibrated_ridge import typed_roles, select, structured_encode
from context_ridge import prepare


def fixture():
    sort=dict(name='Expr',kind='eq')
    rule=dict(slots=[dict(sort=sort) for _ in range(4)],query=[],effects=[dict(kind='union',args=[dict(slot=0),dict(slot=1)])])
    ports=[dict(slot=i,sort='Expr',before=i+100,after=100) for i in range(2)]
    return dict(recipe=dict(rules=[rule]),runs=[dict(ordinal=1,audit=dict(bindings=[dict(rule=0,eq_ports=ports,values=[])]))])


class Calibrated(unittest.TestCase):
    def test_copy_aliases_have_identical_normalized_roles(self):
        a=fixture();b=copy.deepcopy(a)
        b['recipe']['rules'][0]['effects']=[dict(kind='copy',dst=2,arg=dict(slot=0)),dict(kind='copy',dst=3,arg=dict(slot=1)),dict(kind='union',args=[dict(slot=3),dict(slot=2)])]
        np.testing.assert_array_equal(typed_roles(a,normalize_effects=True),typed_roles(b,normalize_effects=True))

    def test_roles_ignore_outcomes_and_instance_identities(self):
        a=fixture();b=copy.deepcopy(a)
        for p in b['runs'][0]['audit']['bindings'][0]['eq_ports']:p['before']+=9999;p['after']=345
        np.testing.assert_array_equal(typed_roles(a,normalize_effects=True),typed_roles(b,normalize_effects=True))

    def test_test_labels_do_not_change_selection(self):
        rng=np.random.default_rng(8);x=np.column_stack([np.ones(30),rng.normal(size=(30,5))]).astype(np.float32)
        y=(x[:,1]>0).astype(np.float32);train=np.arange(30)<15;valid=(np.arange(30)>=15)&(np.arange(30)<25)
        a,c=select(x,y,train,valid);y[25:]=1-y[25:];b,d=select(x,y,train,valid)
        np.testing.assert_array_equal(a,b);self.assertEqual(c,d)

    @unittest.skipUnless(mx.metal.is_available(),'Metal required')
    def test_pair_features_are_symmetric_on_gpu(self):
        mx.set_default_device(mx.gpu);trace=fixture();a,records,nroots,_=prepare(trace)
        ga={k:mx.array(a[k]) for k in ('owners','roots','local_roots','roles','scalars','left','right','pair_owner')}
        roles=mx.array(typed_roles(trace,normalize_effects=True));rng=np.random.default_rng(803)
        w=[mx.array(rng.normal(0,.1,(i,j)).astype(np.float32)) for i,j in [(16,32),(32,64),(32,64),(256,256)]]
        first=structured_encode(ga,roles,nroots,len(records),w)
        ga['left'],ga['right']=ga['right'],ga['left']
        second=structured_encode(ga,roles,nroots,len(records),w)
        np.testing.assert_array_equal(np.array(first),np.array(second))

if __name__=='__main__':unittest.main()
