import unittest
import numpy as np
import mlx.core as mx
from device_slot_owners import read,compile_transfer,transfer,pack
from device_constructor_results import execute_site
from device_copy_effects import execute_copy
from device_witness_views import compile_view,project
from compile_constructor_sites import compile_sites


class OwnerEffects(unittest.TestCase):
    def test_gpu_admission_constructor_refresh_and_witness_from_reused_owner(self):
        from test_device_owner_admission import setup
        from test_device_join_transition import device_plan
        from device_join_transition import compile_transition,step
        from device_token_refresh import refresh
        from multi_entry_ridge import template
        from device_query_join import compile_query,match_inputs
        from device_input_features import compile_inputs
        from test_device_query_join import device_plan as query_plan
        recipe,state,_,model=setup()
        for key in ('owner_slots','owner_slot_roots','owner_slot_valid'):
            state[key]=np.concatenate([state[key],np.full((2,1),False if key=='owner_slot_valid' else -1,state[key].dtype)],axis=1)
        state['owner_projection']=np.concatenate([state['owner_projection'],np.full((3,1),-1,np.int32)],axis=1)
        recipe['tables'].append(dict(name='H',kind='constructor'))
        recipe['rules'][2]['slots'].append(dict(sort=dict(kind='eq',name='E'),definition='effect'))
        recipe['rules'][2]['effects']=[dict(kind='construct',call=dict(table='H'),args=[dict(slot=2)],dst=3)]
        recipe['rules'].append(dict(metadata=dict(source_set='s'),slots=[dict(sort=dict(kind='eq',name='E'),definition='query') for _ in range(2)],query=[dict(call=dict(table='H'),args=[dict(slot=0),dict(slot=1)])],effects=[]))
        later=query_plan(compile_query(recipe,3));later_layout={k:mx.array(v) for k,v in compile_inputs(recipe['rules'][3]).items()}
        tp=compile_transfer(recipe,dict(producer=0,consumer=1,projection=[0,1,0],projection_valid=[True,True,False]),4)
        tp={k:mx.array(v) if isinstance(v,np.ndarray) else v for k,v in tp.items()}
        qp=device_plan(compile_transition(recipe,2));dm={k:mx.array(v) for k,v in model.items()}
        site=compile_sites(recipe)['sites'][0];vp=compile_view(recipe,2,1)
        vp={k:mx.array(v) if isinstance(v,np.ndarray) else v for k,v in vp.items()}
        roles=np.zeros((3,4,64),np.float32);roles[2]=template(recipe['rules'][2])[0]
        required=np.zeros((3,4),bool);required[2]=True
        def run(s):
            s,_=transfer(s,tp,mx.array(0),mx.array(1),mx.array(2),mx.array(5),mx.array(True),mx)
            s,admission=step(s,qp,dm,8,mx.array(True),mx.array(True),mx)
            view=project(s,vp,mx.array(True),mx.array(True),mx)
            s,effect=execute_site(s,site,view,mx.array(500),mx.array(600),mx.array(100),mx)
            s,encoding=refresh(s,mx.zeros((3,4),mx.int32),mx.ones((3,4),mx.bool_),mx.array(required),mx.array(roles),mx.zeros((3,4,64)),mx.ones((3,4),mx.bool_),mx.array(True),mx)
            later_bindings,later_features,_=match_inputs(s,later,later_layout,4,mx.array(True),mx.array(True),mx)
            return s,admission,effect,encoding,project(s,vp,mx.array(True),mx.array(True),mx),later_bindings,later_features
        out,admission,effect,encoding,view,later_bindings,later_features=mx.compile(run)({k:mx.array(v) for k,v in state.items()});mx.eval(out,admission,effect,encoding,view,later_bindings,later_features)
        self.assertEqual(int(effect['next_id']),501);self.assertTrue(bool(out['settled'][2]))
        self.assertTrue(bool(encoding['refreshed'][2]));self.assertFalse(bool(out['token_dirty'][2]))
        self.assertEqual(int(out['owner_slots'][0,3]),500);self.assertEqual(int(out['effect_pc'][2]),1)
        self.assertEqual(np.array(view['ids'])[np.array(view['live'])].tolist(),[500])
        np.testing.assert_array_equal(np.array(out['slot_owner']),[1,1,0])
        self.assertNotIn('slots',out)
        self.assertEqual(np.array(later_bindings['live']).sum(),1)
        np.testing.assert_array_equal(np.array(later_bindings['slots'])[0],[92,500])
        self.assertTrue(bool(later_features['input_ready'][0]))

    def shared(self,free=True):
        s=dict(keys=np.array([[0],[0],[0]],np.int32),slots=np.array([[7,8],[7,8],[0,0]],np.int32),slot_roots=np.array([[7,8],[7,8],[0,0]],np.int32),slot_valid=np.array([[1,1],[1,1],[0,0]],bool),present=np.array([1,1,0],bool),visible=np.array([1,1,0],bool),active=np.array([1,0,0],bool),settled=np.array([0,1,0],bool),effect_pc=np.zeros(3,np.int32),token_dirty=np.zeros(3,bool),generation=np.ones(3,np.int32))
        s['scalar_numbers']=np.array([[3,4],[3,4],[0,0]],np.float32)
        s=pack(s);s['slot_owner'][1]=0;s['owner_live'][1]=False
        if not free:s['owner_live'][:]=True
        return s

    def test_shared_copy_detaches_before_writing_scalar_and_eq_fields(self):
        s=self.shared();site=dict(rule=0,operation=0,src=0,dst=1,last_effect=True)
        out,m=mx.compile(lambda x:execute_copy(x,site,mx))({k:mx.array(v) for k,v in s.items()});mx.eval(out,m)
        self.assertTrue(bool(m['ready'][0]));np.testing.assert_array_equal(np.array(out['slot_owner'])[:2],[1,0])
        out={k:np.array(v) for k,v in out.items()}
        self.assertEqual(read(out,'slots',np.array(0),np.array(1),np),7)
        self.assertEqual(read(out,'slots',np.array(1),np.array(1),np),8)
        self.assertEqual(read(out,'scalar_numbers',np.array(0),np.array(1),np),3)
        self.assertEqual(read(out,'scalar_numbers',np.array(1),np.array(1),np),4)

    def test_no_detach_capacity_keeps_effect_pending_without_writes(self):
        s=self.shared(False);out,m=execute_copy(s,dict(rule=0,operation=0,src=0,dst=1,last_effect=True),np)
        self.assertTrue(m['storage_blocked'][0]);self.assertFalse(m['ready'].any());self.assertTrue(m['needs_attention'])
        np.testing.assert_array_equal(out['owner_slots'],s['owner_slots']);self.assertEqual(out['effect_pc'][0],0)

    def test_outstanding_reader_blocks_mutation_even_with_free_rows(self):
        s=self.shared();s['readers']=np.array([True,False,False])
        out,m=execute_copy(s,dict(rule=0,operation=0,src=0,dst=1,last_effect=True),np)
        self.assertTrue(m['storage_blocked'][0]);self.assertFalse(m['ready'].any())
        np.testing.assert_array_equal(out['owner_generation'],s['owner_generation'])
        np.testing.assert_array_equal(out['owner_slots'],s['owner_slots'])

    def test_failed_constructor_does_not_consume_owner_or_identity_capacity(self):
        site=dict(rule=0,operation=0,table=0,args=[0],dst=1,last_effect=True)
        witness=dict(keys=np.array([[0,7],[0,7]],np.int32),ids=np.array([10,11],np.int32),roots=np.array([10,11],np.int32),live=np.ones(2,bool),complete=True)
        s=self.shared();out,m=execute_site(s,site,witness,np.array(100),np.array(200),np.array(20),np)
        self.assertTrue(m['conflict'][0]);self.assertEqual(m['next_id'],100)
        for key in ('owner_live','owner_generation','slot_owner','owner_slots'):np.testing.assert_array_equal(out[key],s[key])
        s=self.shared(False);witness['live'][:]=False
        out,m=execute_site(s,site,witness,np.array(100),np.array(200),np.array(20),np)
        self.assertTrue(m['storage_blocked'][0]);self.assertEqual(m['next_id'],100)
        self.assertEqual(out['effect_pc'][0],0)

if __name__=='__main__':unittest.main()
