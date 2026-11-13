import unittest
import numpy as np
import mlx.core as mx
from device_witness_views import compile_view,project
from device_constructor_results import execute_site
from compile_constructor_sites import compile_sites


def recipe():
    sort=dict(kind='eq',name='E')
    return dict(tables=[dict(name='F',kind='constructor')],rules=[dict(
        slots=[dict(sort=sort,definition='query' if i==0 else 'effect') for i in range(2)],
        query=[],effects=[dict(kind='construct',call=dict(table='F'),args=[dict(slot=0)],dst=1)])])


def state():
    return dict(keys=np.array([[0,7],[0,7]],np.int32),slots=np.array([[7,-1],[7,-1]],np.int32),
        slot_valid=np.array([[True,False],[True,False]]),present=np.array([True,True]),active=np.array([True,False]),
        visible=np.array([True,True]),settled=np.array([False,False]),effect_pc=np.array([0,0],np.int32))


class WitnessViews(unittest.TestCase):
    def test_newly_produced_result_reused_by_later_cell_on_gpu(self):
        if not mx.metal.is_available():self.skipTest('Metal required')
        mx.set_default_device(mx.gpu)
        r=recipe();p=compile_view(r,0,1);plan={k:mx.array(v) if isinstance(v,np.ndarray) else v for k,v in p.items()}
        site=compile_sites(r)['sites'][0]
        def flow(s):
            view=project(s,plan,mx.array(True),mx.array(True),mx)
            s,a=execute_site(s,site,view,mx.array(100),mx.array(200),mx.array(100),mx)
            # Activate another independent Cell after first result is resident.
            s['active']=mx.array([False,True])
            view=project(s,plan,mx.array(True),mx.array(True),mx)
            s,b=execute_site(s,site,view,a['next_id'],mx.array(200),mx.array(100),mx)
            return s,a,b
        out,a,b=mx.compile(flow)({k:mx.array(v) for k,v in state().items()});mx.eval(out,a,b)
        np.testing.assert_array_equal(np.array(out['slots'])[:,1],[100,100])
        self.assertTrue(np.array(a['new_owner'])[0]);self.assertTrue(np.array(b['reused'])[1])
        self.assertEqual(int(np.array(b['next_id'])),101)

    def test_missing_and_overwritten_live_facts_block_allocation(self):
        r=recipe();s=state();s['effect_pc'][0]=1
        view=project(s,compile_view(r,0,1),True,True,np)
        self.assertFalse(view['complete']);self.assertTrue(view['missing'].any())
        r['rules'][0]['effects'].append(dict(kind='copy',arg=dict(slot=0),dst=1))
        s['slots'][0,1]=7;s['slot_valid'][0,1]=True;s['effect_pc'][0]=2
        view=project(s,compile_view(r,0,1),True,True,np)
        self.assertFalse(view['complete'])

    def test_literal_view_is_unknown_not_empty(self):
        r=recipe();r['rules'][0]['effects'][0]['args']=[dict(literal=4,sort='i64')]
        s=state();s['effect_pc'][0]=1
        view=project(s,compile_view(r,0,1),True,True,np)
        self.assertFalse(view['complete']);self.assertTrue(view['missing'].any())

    def test_inactive_owner_still_supplies_fact_but_hidden_does_not(self):
        r=recipe();s=state();s['active'][0]=False;s['settled'][0]=True
        s['slots'][0,1]=91;s['slot_valid'][0,1]=True
        view=project(s,compile_view(r,0,1),True,True,np)
        self.assertTrue(view['complete']);self.assertTrue(view['live'][0])
        s['visible'][0]=False
        self.assertFalse(project(s,compile_view(r,0,1),True,True,np)['live'].any())

    def test_raw_witness_identity_is_separate_from_current_root(self):
        r=recipe();s=state();s['active'][:]=[False,True]
        s['slots'][0]=[7,91];s['slot_valid'][0]=[True,True];s['effect_pc'][0]=1
        s['slot_roots']=np.array([[3,11],[3,-1]],np.int32)
        view=project(s,compile_view(r,0,1),True,True,np)
        np.testing.assert_array_equal(view['keys'][0],[0,3])
        self.assertEqual(view['ids'][0],91);self.assertEqual(view['roots'][0],11)
        out,m=execute_site(s,compile_sites(r)['sites'][0],view,np.array(100),np.array(200),np.array(10),np)
        self.assertEqual(out['slots'][1,1],91);self.assertEqual(out['slot_roots'][1,1],11)
        self.assertTrue(m['reused'][1])

    def test_external_or_eq_gap_blocks_new_results(self):
        r=recipe();site=compile_sites(r)['sites'][0]
        for external,eq in [(False,True),(True,False)]:
            s=state();view=project(s,compile_view(r,0,1),external,eq,np)
            out,m=execute_site(s,site,view,np.array(100),np.array(200),np.array(10),np)
            np.testing.assert_array_equal(out['slots'],s['slots'])
            self.assertTrue(m['incomplete_witness_view'][0]);self.assertEqual(m['next_id'],100)


if __name__=='__main__':unittest.main()
