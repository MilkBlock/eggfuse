import unittest
import numpy as np
import mlx.core as mx
from device_slot_owners import pack,read,compile_transfer,transfer
from device_witness_views import compile_view,project
from device_query_join import compile_query,match_inputs
from device_input_features import compile_inputs


def fixture():
    eq=dict(kind='eq',name='E')
    def atom(t,args):return dict(call=dict(table=t),args=[dict(slot=i) for i in args])
    def rule(n,atoms):return dict(slots=[dict(sort=eq,definition='query') for _ in range(n)],query=atoms,effects=[])
    recipe=dict(tables=[dict(name=t,kind='constructor') for t in ('F','G')],rules=[rule(2,[atom('F',[0,1])]),rule(3,[atom('F',[0,1]),atom('G',[1,2])])])
    state=dict(keys=np.array([[0],[1]],np.int32),slots=np.array([[7,91,-1],[7,91,92]],np.int32),slot_roots=np.array([[7,10,-1],[7,10,20]],np.int32),slot_valid=np.array([[True,True,False],[True,True,True]]),present=np.ones(2,bool),visible=np.ones(2,bool),settled=np.ones(2,bool),effect_pc=np.zeros(2,np.int32),generation=np.array([2,5],np.int32))
    entry=dict(producer=0,consumer=1,projection=[0,1,0],projection_valid=[True,True,False])
    plan=compile_transfer(recipe,entry,3)
    return recipe,state,plan


class SlotOwners(unittest.TestCase):
    def test_gpu_transfer_releases_storage_and_keeps_logical_query_after_reuse(self):
        recipe,state,plan=fixture();packed=pack(state)
        self.assertNotIn('slots',packed);self.assertNotIn('slot_valid',packed)
        query=compile_query(recipe,1)
        query['atoms']=[dict(a,view={k:mx.array(v) if isinstance(v,np.ndarray) else v for k,v in a['view'].items()}) for a in query['atoms']]
        layout={k:mx.array(v) for k,v in compile_inputs(recipe['rules'][1]).items()}
        dp={k:mx.array(v) if isinstance(v,np.ndarray) else v for k,v in plan.items()}
        def flow(s):
            out,marks=transfer(s,dp,mx.array(0),mx.array(1),mx.array(2),mx.array(5),mx.array(True),mx)
            # Reuse the released physical row, while retaining both logical Cells.
            out['owner_slots']=out['owner_slots'].at[0].add(mx.full((3,),1000,mx.int32))
            out['owner_live']=mx.array([True,True])
            bindings,features,encoding=match_inputs(out,query,layout,8,mx.array(True),mx.array(True),mx)
            return out,marks,bindings,features
        out,marks,bindings,features=mx.compile(flow)({k:mx.array(v) for k,v in packed.items()});mx.eval(out,marks,bindings,features)
        self.assertTrue(bool(marks['transferred']));self.assertEqual(int(marks['released_rows']),1)
        np.testing.assert_array_equal(np.array(out['slot_owner']),[1,1])
        self.assertEqual(np.array(bindings['live']).sum(),1)
        np.testing.assert_array_equal(np.array(bindings['slots'])[0],[7,91,92])
        self.assertTrue(np.array(features['input_ready'])[0])
        np.testing.assert_array_equal(np.array(out['generation']),[2,5])

    def test_unshared_source_fields_move_to_free_tail_with_scalar_metadata(self):
        recipe,state,_=fixture()
        for key in ('slots','slot_roots','slot_valid'):
            state[key]=np.concatenate([state[key],np.full((2,1),False if key=='slot_valid' else -1,state[key].dtype)],axis=1)
        state['slots'][1,1]=222
        state['scalar_numbers']=np.array([[1,2,0,0],[1,4,5,0]],np.float32)
        state['scalar_numeric']=state['slot_valid'].copy();state['scalar_valid']=state['slot_valid'].copy()
        state['scalar_codes']=np.zeros((2,4,64),np.float32)
        s=pack(state)
        plan=compile_transfer(recipe,dict(producer=0,consumer=1,projection=[0,0,0],projection_valid=[True,False,False]),4)
        view=compile_view(recipe,0,1);before=project(s,view,True,True,np,True)
        dp={k:mx.array(v) if isinstance(v,np.ndarray) else v for k,v in plan.items()}
        out,marks=mx.compile(lambda x:transfer(x,dp,mx.array(0),mx.array(1),mx.array(2),mx.array(5),mx.array(True),mx))({k:mx.array(v) for k,v in s.items()});mx.eval(out,marks)
        self.assertTrue(bool(marks['transferred']));self.assertEqual(int(marks['copied_fields']),1)
        out={k:np.array(v) for k,v in out.items()};after=project(out,view,True,True,np,True)
        for key in ('keys','ids','roots','live','complete'):np.testing.assert_array_equal(after[key],before[key])
        self.assertEqual(read(out,'scalar_numbers',np.array(0),np.array(1),np),2)
        self.assertEqual(out['owner_slots'][1,3],91)
        self.assertFalse(read(out,'slot_valid',np.array(1),np.array(3),np))
        occupied=pack(state);occupied['owner_slot_valid'][1,3]=True
        self.assertFalse(transfer(occupied,plan,np.array(0),np.array(1),np.array(2),np.array(5),np.array(True),np)[1]['transferred'])

    def test_second_transfer_remaps_existing_aliases_and_preserves_padding(self):
        recipe,state,plan=fixture()
        for key,value in list(state.items()):state[key]=np.concatenate([value,value[1:]],axis=0)
        s=pack(state)
        out,m=transfer(s,plan,np.array(0),np.array(1),np.array(2),np.array(5),np.array(True),np)
        next_plan=compile_transfer(recipe,dict(producer=1,consumer=1,projection=[0,1,2],projection_valid=[True]*3),3)
        out,m=transfer(out,next_plan,np.array(1),np.array(2),np.array(5),np.array(5),np.array(True),np)
        self.assertTrue(m['transferred']);np.testing.assert_array_equal(out['owner_live'],[False,False,True])
        np.testing.assert_array_equal(out['slot_owner'],[2,2,2])
        self.assertFalse(read(out,'slot_valid',np.array(0),np.array(2),np))
        np.testing.assert_array_equal(read(out,'slots',np.array(0),np.array([0,1]),np),[7,91])

    def test_value_generation_and_quiescence_obligations_block_transfer(self):
        _,state,plan=fixture()
        for case in ('value','generation','quiescence','owner_epoch'):
            s=pack(state)
            if case=='value':s['owner_slots']=s['owner_slots'].copy();s['owner_slots'][1,1]=123
            if case=='owner_epoch':s['owner_epoch'][0]=9
            out,m=transfer(s,plan,np.array(0),np.array(1),np.array(9 if case=='generation' else 2),np.array(5),np.array(case!='quiescence'),np)
            self.assertFalse(m['transferred'],case);self.assertTrue(out['owner_live'].all())

    def test_compiler_marks_combined_capacity_and_preserves_overwritten_input(self):
        recipe,_,_=fixture();entry=dict(producer=0,consumer=1,projection=[0,0,0],projection_valid=[True,True,False])
        self.assertFalse(compile_transfer(recipe,entry,3)['covered'])
        self.assertTrue(compile_transfer(recipe,entry,4)['copied'][1])
        entry['projection']=[0,1,0];recipe['rules'][1]['effects']=[dict(kind='copy',dst=1,arg=dict(slot=0))]
        self.assertFalse(compile_transfer(recipe,entry,3)['covered'])
        self.assertTrue(compile_transfer(recipe,entry,4)['copied'][1])

    def test_logical_receiver_retirement_does_not_retire_shared_payload(self):
        recipe,state,plan=fixture()
        out,marks=transfer(pack(state),plan,np.array(0),np.array(1),np.array(2),np.array(5),np.array(True),np)
        out['present'][1]=False;out['visible'][1]=False
        view=project(out,compile_view(recipe,0,1),True,True,np)
        self.assertTrue(view['live'][0]);self.assertTrue(view['complete'])
        self.assertEqual(view['ids'][0],91)

    def test_stale_owner_generation_invalidates_witness_view(self):
        recipe,state,_=fixture();s=pack(state);s['owner_generation'][0]+=1
        v=project(s,compile_view(recipe,0,1),True,True,np)
        self.assertFalse(v['complete']);self.assertTrue(v['missing'].any())

if __name__=='__main__':unittest.main()
