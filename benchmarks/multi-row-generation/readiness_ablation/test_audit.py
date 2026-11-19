"""Regression tests for temporal legality, duplicate receipt identity and keyed provenance."""
from copy import deepcopy
import unittest
import numpy as np
from data import dataset,oracle,source_rows,schedule_banks,schedule_family,KEYS
from audit import metrics


def exact_trace(d,barrier=False):
    e,gold=d['events'],oracle(d['events'],d['seal']);n=len(e);ready=gold['desired_ready'];ticks=np.arange(4)[None,:,None,None]
    fired=ready & (ticks==3) if barrier else ready & (ticks==gold['ready_tick'][:,None]);computed=np.logical_or.accumulate(fired,axis=1)
    previous=np.zeros_like(computed);previous[:,1:]=computed[:,:-1];public=gold['expected_public'];pending=~computed;sealed=np.zeros_like(ready);sealed[:,-1]=gold['sealed_absent'];pending &= ~sealed
    rows=np.where(computed[...,None],gold['expected_rows'],-1);receipt=np.zeros_like(gold['parent_value'])
    for t in range(3):
        for p in range(3):
            for k in range(KEYS):receipt[:,t,p,k]=((e[:,t,:,0]==p+1)&(e[:,t,:,1]==k)).sum(-1)
    witness=np.full((n,4,2,KEYS,2,4),-1,np.int32)
    for g,t,c,k in zip(*np.nonzero(computed)):
        for side,p in enumerate((0,1) if c==0 else (2,)):
            witness[g,t,c,k,side]=[p+1,k,gold['parent_value'][g,t,p,k],gold['parent_first_tick'][g,t,p,k]]
    return dict(**{k:gold[k].copy() for k in ('parent_live','parent_value','parent_version','parent_first_tick')},
        receipt_count=np.cumsum(receipt,axis=1), input_fault=np.zeros((n,4),bool),ready=ready.copy(),runnable=ready&~previous,
        proposal=np.zeros_like(ready),fired=fired.copy(),drained=np.zeros_like(ready),early=np.zeros_like(ready),published=public.copy(),computed=computed,
        hidden=computed&~public,public=public.copy(),pending=pending,sealed_absent=sealed,pending_open=pending&~ready,withheld=pending&ready,
        first_fired_tick=np.where(computed,fired.argmax(axis=1)[:,None],-1),first_publish_tick=np.where(public,3,-1),first_early_tick=np.full(ready.shape,-1),
        rows=rows.copy(),public_rows=np.where(public[...,None],rows,-1),witness=witness)


class WaveAudit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.d=dataset('heldout',16)

    def test_private_execution_and_public_boundary(self):
        for mode in ('barrier','barrier_min','local'):
            t=exact_trace(self.d,barrier=mode.startswith('barrier'));r=metrics(self.d,t,mode)
            self.assertEqual(r['complete_graphs'],16);self.assertEqual(r['paired']['unchanged_unrelated_v_trajectory_groups'],4)
            self.assertEqual(r['totals']['unrelated_v_ready_idle_ticks'],48 if mode.startswith('barrier') else 0)
            self.assertTrue(all(row['rhs_inputs_exact']==16 and row['effective_writes_exact']==16 for row in r['per_run']))
        self.assertEqual(r['paired']['c_follows_both_arrivals_at_earliest_tick'],4)

    def test_wrong_key_even_with_exact_fields(self):
        g=0;d=self.d;f=int(d['focal_key'][g]);other=int(d['unrelated_key'][g]);t=exact_trace(d)
        self.assertEqual(t['witness'][g,0,0,f,1,2],t['parent_value'][g,0,1,other]);t['witness'][g,:,0,f,1,1]=other
        r=metrics(d,t,'local');self.assertEqual(r['totals']['wrong_parent_identity'],1);self.assertEqual(r['totals']['equal_value_wrong_key'],1)
        self.assertEqual(r['final_graph_exact_graphs'],16);self.assertEqual(r['complete_graphs'],15);self.assertEqual(r['per_run'][3]['rhs_inputs_exact'],15)

    def test_retained_receipt_corruption_and_early_visibility(self):
        d=self.d;t=exact_trace(d);k=int(d['focal_key'][0]);t['witness'][0,3,0,k,0,3]=2
        r=metrics(d,t,'local');self.assertEqual(r['complete_graphs'],15);self.assertEqual(r['per_run'][3]['rhs_inputs_exact'],15);self.assertEqual(r['per_graph'][0]['stable_retained_state'],0)
        t=exact_trace(d);other=int(d['unrelated_key'][0]);t['public'][0,0,1,other]=True;t['published'][0,0,1,other]=True;t['public_rows'][0,0,1,other]=t['rows'][0,0,1,other]
        r=metrics(d,t,'local');self.assertEqual(r['final_graph_exact_graphs'],16);self.assertEqual(r['per_run'][0]['visible_graph_exact'],15)
        self.assertEqual((r['totals']['early_publication_events'],r['totals']['duplicate_publications']),(1,1))

    def test_late_vs_absent_and_duplicate_receipts(self):
        d=self.d;k=int(d['focal_key'][0]);np.testing.assert_array_equal(d['events'][2],d['events'][3]);assert d['seal'][2,1,k]!=d['seal'][3,1,k]
        source=source_rows(d['events'][2],d['seal'][2]);self.assertEqual(source['terminal_status']['C'][k],'pending_open');self.assertEqual(source_rows(d['events'][3],d['seal'][3])['terminal_status']['C'][k],'sealed_absent')
        self.assertGreaterEqual(sum(x['transport_duplicates'] for x in source['runs']),2)
        t=exact_trace(d);t['sealed_absent'][2,-1,0,k]=True;t['pending_open'][2,-1,0,k]=False;t['pending'][2,-1,0,k]=False
        r=metrics(d,t,'local');self.assertEqual(r['totals']['pending_open_disagreements'],1);self.assertEqual(r['totals']['sealed_absent_disagreements'],1)
        self.assertEqual(r['final_graph_exact_graphs'],16);self.assertEqual(r['complete_graphs'],15)

    def test_schedule_holds_out_a_family_not_just_labels(self):
        banks=schedule_banks()
        for name,patterns in banks.items():
            for plan in patterns:
                for wave in (0,2,-1):
                    schedule=np.array(plan);schedule[0,1]=wave;self.assertEqual(schedule_family(schedule),name)
        with self.assertRaises(ValueError):dataset('heldout',9)
        bad=self.d['events'][:1].copy();k=int(self.d['unrelated_key'][0]);v=int(bad[0,0,(bad[0,0,:,0]==3)&(bad[0,0,:,1]==k),2][0]);slot=int(np.flatnonzero(bad[0,1,:,0]==0)[0]);bad[0,1,slot]=[3,k,(v+1)%8]
        with self.assertRaises(ValueError):oracle(bad,self.d['seal'][:1])

if __name__=='__main__':unittest.main()
