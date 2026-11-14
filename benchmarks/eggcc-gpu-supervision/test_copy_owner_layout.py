import unittest
import numpy as np
import mlx.core as mx
from device_slot_owners import sealed_copy_aliases,compile_transfer,pack,transfer,read
from audit_snapshot_queries import device

class CopyOwnerLayout(unittest.TestCase):
    def fixture(self):
        eq=dict(kind='eq',name='E')
        source=dict(slots=[dict(sort=eq,definition='query') for _ in range(3)],effects=[dict(kind='copy',dst=2,arg=dict(slot=1))])
        source['slots'][2]['definition']=0
        target=dict(slots=[dict(sort=eq,definition='query') for _ in range(2)],effects=[])
        recipe=dict(rules=[source,target]);entry=dict(producer=0,consumer=1,projection=[0,0],projection_valid=[True,False])
        state=dict(keys=np.array([[0],[1]],np.int32),slots=np.array([[7,91,91],[7,92,-1]],np.int32),slot_roots=np.array([[7,10,10],[7,20,-1]],np.int32),slot_valid=np.array([[True,True,True],[True,True,False]]),present=np.ones(2,bool),visible=np.ones(2,bool),settled=np.ones(2,bool),generation=np.array([2,5],np.int32))
        return recipe,entry,state

    def test_compiled_gpu_copy_aliases_fit_without_slack(self):
        recipe,entry,state=self.fixture();plan=compile_transfer(recipe,entry,3)
        self.assertTrue(plan['covered']);np.testing.assert_array_equal(plan['projection'],[0,2,2])
        baseline=pack(state);dp=device(plan)
        out,marks=mx.compile(lambda s:transfer(s,dp,mx.array(0),mx.array(1),mx.array(2),mx.array(5),mx.array(True),mx))(device(baseline));mx.eval(out,marks)
        self.assertTrue(bool(marks['transferred']));self.assertEqual(int(marks['copied_fields']),1)
        out={k:np.array(v) for k,v in out.items()}
        for key in ('slots','slot_roots','slot_valid'):
            before=read(baseline,key,np.arange(2)[:,None],np.arange(3)[None,:],np)
            after=read(out,key,np.arange(2)[:,None],np.arange(3)[None,:],np)
            np.testing.assert_array_equal(before,after)
        bad=pack(state);bad['owner_slots'][0,2]=93
        _,m=transfer(bad,plan,np.array(0),np.array(1),np.array(2),np.array(5),np.array(True),np)
        self.assertFalse(m['transferred']);self.assertTrue(m['value_mismatch'])

    def test_ordered_overwrites_and_union_do_not_create_alias_proofs(self):
        recipe,entry,_=self.fixture();rule=recipe['rules'][0]
        self.assertEqual(sealed_copy_aliases(rule),[0,1,1])
        rule['effects'].append(dict(kind='construct',dst=1))
        self.assertEqual(sealed_copy_aliases(rule),[0,1,2])
        self.assertFalse(compile_transfer(recipe,entry,3)['covered'])
        rule['effects']=[dict(kind='union',args=[dict(slot=1),dict(slot=2)])]
        self.assertEqual(sealed_copy_aliases(rule),[0,1,2])

if __name__=='__main__':unittest.main()
