import unittest
import numpy as np
import mlx.core as mx
from device_constructor_results import resolve,execute_site


def run(keys,wkeys=None,ids=None,roots=None,live=None,active=None,next_id=100,limit=200,quota=100,xp=np):
    if wkeys is None:wkeys=[[-1]*len(keys[0])];ids=[0];roots=[0];live=[False]
    if roots is None:roots=ids
    if live is None:live=[True]*len(ids)
    if active is None:active=[True]*len(keys)
    args=[xp.array(x,dtype=xp.int32) for x in (keys,wkeys,ids,roots)]
    return resolve(args[0],xp.array(active),args[1],args[2],args[3],xp.array(live),
        xp.array(next_id,xp.int32),xp.array(limit,xp.int32),xp.array(quota,xp.int32),xp)


class ConstructorResults(unittest.TestCase):
    def test_existing_foreign_result_and_shared_new_identity(self):
        out=run([[1,7],[1,8],[1,8],[2,8]],[[1,7]],[42])
        np.testing.assert_array_equal(out['result'],[42,100,100,101])
        np.testing.assert_array_equal(out['new_owner'],[False,True,False,True])
        self.assertEqual(out['next_id'],102)
        self.assertFalse(out['needs_attention'])

    def test_conflicting_roots_are_pending_but_forwarded_aliases_can_reuse(self):
        out=run([[1,7]],[[1,7],[1,7]],[40,41],[40,41])
        self.assertFalse(out['ready'][0]);self.assertTrue(out['conflict'][0]);self.assertEqual(out['next_id'],100)
        out=run([[1,7]],[[1,7],[1,7]],[40,41],[12,12])
        self.assertEqual(out['result'][0],40)

    def test_capacity_retires_nothing_and_duplicates_use_one_identity(self):
        out=run([[1,7],[1,7],[2,7]],quota=1)
        np.testing.assert_array_equal(out['result'],[100,100,-1])
        self.assertTrue(out['capacity'][2]);self.assertEqual(out['next_id'],101)
        out=run([[1,7],[2,7]],next_id=2147483646,limit=2147483647)
        np.testing.assert_array_equal(out['result'],[2147483646,-1]);self.assertEqual(out['next_id'],2147483647)

    def test_inactive_and_dead_lanes_do_not_claim_results(self):
        out=run([[1,7],[1,7]],[[1,7]],[42],live=[False],active=[False,True])
        np.testing.assert_array_equal(out['result'],[-1,100])
        self.assertFalse(out['shared_new'][1])
        bad=run([[1,7]],[[1,7]],[100])
        self.assertTrue(bad['invalid_namespace']);self.assertFalse(bad['ready'][0])

    def test_generated_constructor_results_feed_compiled_successor(self):
        if not mx.metal.is_available():self.skipTest('Metal required')
        from compile_constructor_sites import compile_sites
        from cell_token_successors import compile_catalog
        from lower_device_entries import lower,tensors
        from device_token_commit import closed_entry_proposals,commit
        mx.set_default_device(mx.gpu)
        sort=dict(kind='eq',name='E')
        def slots(n,k):return [dict(sort=sort,definition='query' if i<k else 'effect') for i in range(n)]
        def op(t,a,d):return dict(kind='construct',call=dict(table=t),args=[dict(slot=a)],dst=d)
        recipe=dict(tables=[dict(name=t,kind='constructor') for t in ('Input','F','G')],rules=[
            dict(metadata=dict(source_set='s'),slots=slots(3,1),query=[dict(call=dict(table='Input'),args=[dict(slot=0)])],effects=[op('F',0,1),op('G',1,2)]),
            dict(metadata=dict(source_set='s'),slots=slots(2,2),query=[dict(call=dict(table='G'),args=[dict(slot=0),dict(slot=1)])],effects=[])])
        sites=compile_sites(recipe)['sites'];layout=lower(recipe,compile_catalog(recipe),source_slots=True)
        ep=tensors(layout,np.array([np.eye(3)],np.float32),np.zeros((1,3),np.float32));plan={k:mx.array(v) for k,v in ep.items()}
        state=dict(keys=mx.array([[0,7,-1],[-1,-1,-1]],mx.int32),slots=mx.array([[7,-1,-1],[-1,-1,-1]],mx.int32),
            slot_valid=mx.array([[True,False,False],[False,False,False]]),tokens=mx.array([[.2,.3,.4],[0.,0.,0.]]),
            present=mx.array([True,False]),active=mx.array([True,False]),visible=mx.array([True,False]),settled=mx.array([False,False]),
            readers=mx.array([False,False]),generation=mx.array([1,0],mx.int32),effect_pc=mx.zeros((2,),mx.int32))
        witness=dict(keys=mx.array([[-1,-1]],mx.int32),ids=mx.array([0],mx.int32),roots=mx.array([0],mx.int32),live=mx.array([False]))
        def flow(s):
            next_id=mx.array(100)
            for site in sites:
                s,result=execute_site(s,site,witness,next_id,mx.array(200),mx.array(100),mx)
                next_id=result['next_id']
            return commit(s,closed_entry_proposals(s,plan,mx.array(0),mx),mx)
        out,marks=mx.compile(flow)(state);mx.eval(out,marks)
        np.testing.assert_array_equal(np.array(out['slots'])[0],[7,100,101])
        np.testing.assert_array_equal(np.array(out['keys'])[1],[1,100,101])
        self.assertTrue(np.array(out['settled']).all())
        self.assertEqual(np.array(marks['accepted']).sum(),1)

    def test_new_results_are_written_to_cell_slots_in_effect_order(self):
        if not mx.metal.is_available():self.skipTest('Metal required')
        mx.set_default_device(mx.gpu)
        state=dict(keys=mx.array([[0,7],[0,7],[0,8]],mx.int32),slots=mx.array([[7,-1,-1],[7,-1,-1],[8,-1,-1]],mx.int32),
            slot_valid=mx.array([[True,False,False]]*3),present=mx.array([True]*3),active=mx.array([True]*3),
            visible=mx.array([True]*3),settled=mx.array([False]*3),effect_pc=mx.zeros((3,),mx.int32))
        witness=dict(keys=mx.array([[-1,-1]],mx.int32),ids=mx.array([0],mx.int32),roots=mx.array([0],mx.int32),live=mx.array([False]))
        first=dict(rule=0,operation=0,table=1,args=[0],dst=1,last_effect=False)
        second=dict(rule=0,operation=1,table=2,args=[1],dst=2,last_effect=True)
        def flow(s):
            s,a=execute_site(s,first,witness,mx.array(100),mx.array(200),mx.array(100),mx)
            s,b=execute_site(s,second,witness,a['next_id'],mx.array(200),mx.array(100),mx)
            return s,a,b
        out,a,b=mx.compile(flow)(state);mx.eval(out,a,b)
        np.testing.assert_array_equal(np.array(out['slots']),[[7,100,102],[7,100,102],[8,101,103]])
        self.assertTrue(np.array(out['settled']).all());self.assertEqual(int(np.array(b['next_id'])),104)
        blocked,_=execute_site(state,second,witness,mx.array(100),mx.array(200),mx.array(100),mx);mx.eval(blocked)
        np.testing.assert_array_equal(np.array(blocked['slots']),np.array(state['slots']))

    def test_two_gpu_fragments_use_allocated_results_without_host_read(self):
        if not mx.metal.is_available():self.skipTest('Metal required')
        mx.set_default_device(mx.gpu)
        def flow(inputs):
            first=resolve(inputs,mx.array([True,True,True]),mx.array([[-1,-1]],mx.int32),mx.array([0],mx.int32),
                mx.array([0],mx.int32),mx.array([False]),mx.array(100),mx.array(200),mx.array(100),mx)
            # Second static fragment consumes first fragment's actual output.
            keys=mx.stack([mx.full((3,),2,mx.int32),first['result']],axis=1)
            second=resolve(keys,first['ready'],mx.array([[2,100]],mx.int32),mx.array([77],mx.int32),
                mx.array([77],mx.int32),mx.array([True]),first['next_id'],mx.array(200),mx.array(100),mx)
            return first,second
        a,b=mx.compile(flow)(mx.array([[1,7],[1,7],[1,8]],mx.int32));mx.eval(a,b)
        np.testing.assert_array_equal(np.array(a['result']),[100,100,101])
        np.testing.assert_array_equal(np.array(b['result']),[77,77,102])
        self.assertEqual(int(np.array(b['next_id'])),103)


if __name__=='__main__':unittest.main()
