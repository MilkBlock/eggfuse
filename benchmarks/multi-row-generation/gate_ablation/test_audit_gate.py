"""Conservation and eligibility cases for adaptive row gates."""
from copy import deepcopy
import unittest
import numpy as np

from gate_data import fresh_panel,templates
from audit_gate import metrics,verify_token,timed_rates,execution_metrics,paired_readiness


def subset(d,idx):return {k:(v[idx] if isinstance(v,np.ndarray) else v) for k,v in d.items()}


def gold(d):
    first,second=({'active':y[...,0].copy(),'pointers':y[...,1:3].copy(),'rows':y[...,3:].copy()}
                  for y in (d['target1'][:,::-1],d['target2']))
    second['pointers'][...,0]=7-second['pointers'][...,0]
    return first,second


def apply_gates(stages,bits):
    out=deepcopy(stages)
    for s,x in enumerate(out):
        closed=~bits[:,s].reshape(len(x['active']),8)
        for v in x.values():v[closed]=0
    return out


class SourceGateAudit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d=subset(fresh_panel(next(t for t in templates() if t['id']=='rule-143')),slice(0,16))

    def test_gold_and_source_readiness(self):
        d=self.d;f,s=gold(d);bits=np.ones((len(d['a']),2,2,4),bool)
        r=metrics(d,f,s,bits,d['request_legal']);self.assertEqual(r['both_complete_graphs'],16)
        g1,g2=(r['gate'][key] for key in ('run1','run2'))
        self.assertEqual(g1['source_obligations'],16*6);self.assertEqual(g2['source_obligations'],g2['ready_obligations'])
        self.assertEqual(g2['source_unfinished'],0);self.assertEqual(g2['open_slots']-g2['open_nonemitting'],g2['emitted'])
        self.assertEqual(g2['open_rows_hist_by_round'],[[0,0,16]]*4)
        self.assertEqual(g2['reopens'],0);self.assertEqual(r['complete_intervention_groups'],2)

    def test_all_closed_never_discharges_work(self):
        d=self.d;bits=np.zeros((len(d['a']),2,2,4),bool);f,s=apply_gates(gold(d),bits)
        r=metrics(d,f,s,bits);g1,g2=(r['gate'][key] for key in ('run1','run2'))
        self.assertEqual(r['run2']['nonempty_complete_graphs'],0)
        self.assertEqual((g1['ready_unfinished'],g1['ready_capacity_shortfall']),(96,96))
        self.assertEqual(g2['ready_obligations'],0);self.assertEqual(g2['source_unfinished'],g2['source_obligations'])
        self.assertEqual(g2['ready_capacity_shortfall'],0)
        self.assertEqual(g1['by_round_ready_remaining']['6']['all_closed_with_ready'],16*4)
        self.assertEqual(g2['by_round_ready_remaining']['0']['all_closed_with_only_unavailable'],16*4)
        self.assertEqual(g2['by_round_ready_remaining']['0']['all_closed_after_complete'],0)
        self.assertEqual(g2['open_rows_hist_by_round'],[[16,0,0]]*4)

    def test_reopen_and_early_zero(self):
        d=subset(self.d,slice(0,1));bits=np.ones((1,2,2,4),bool);bits[0,0]=[[1,0,1,1],[0,1,0,1]]
        f,s=apply_gates(gold(d),bits);f['active'].fill(0);s['active'].fill(0)
        r=metrics(d,f,s,bits);g=r['gate']['run1']
        self.assertEqual((g['open_slots'],g['reopens'],g['first_open_after_initial_closure']),(5,2,1))
        self.assertEqual((g['source_unfinished'],g['ready_capacity_shortfall']),(6,1))
        self.assertEqual([e['open_rows'] for e in g['per_graph'][0]['per_round']],[1,1,1,2])
        self.assertEqual(r['complete_intervention_groups'],0)

    def test_paired_source_states_and_temporarily_idle_round(self):
        d=self.d;f,s=gold(d);bits=np.ones((len(d['a']),2,2,4),bool)
        r=metrics(d,f,s,bits);x=paired_readiness(d,r)['pre_to_post']['more_ready']
        self.assertGreater(x['pairs'],0);self.assertEqual(x['pairs'],x['same_open'])
        bits[:,1]=s['active'].reshape(-1,2,4).astype(bool);f,s=apply_gates((f,s),bits)
        r=metrics(d,f,s,bits);x=paired_readiness(d,r)['pre_to_post']['more_ready']
        self.assertEqual(x['pairs'],x['more_open']);self.assertEqual(x['delta_open'],x['delta_ready'])
        # One real consumer can be deferred to the last time in a single lane.
        i=int(np.flatnonzero(d['target2'][...,0].sum(-1)==1)[0]);single=subset(d,slice(i,i+1));f,s=gold(single)
        original=int(np.flatnonzero(s['active'][0])[0]);
        for key in s:s[key][0,3]=s[key][0,original].copy()
        mask=np.ones((1,2,2,4),bool);mask[0,1]=False;mask[0,1,0,3]=True
        f,s=apply_gates((f,s),mask);stats=metrics(single,f,s,mask)['gate']['run2']
        self.assertEqual(stats['complete'],1);self.assertEqual(stats['ready_capacity_shortfall'],0)
        self.assertEqual(stats['by_round_ready_remaining']['1']['all_closed_with_ready'],3)

    def test_corrupt_or_missing_parent_not_ready(self):
        d=subset(self.d,slice(0,1));f,s=gold(d);bits=np.ones((1,2,8),bool)
        pi=s['pointers'][0,np.flatnonzero(s['active'][0])[0],0]
        f['rows'][0,pi,-1]+=10
        r=metrics(d,f,s,bits);g=r['gate']['run2']
        self.assertGreater(g['unavailable_obligations'],0);self.assertLess(g['ready_obligations'],g['source_obligations'])
        self.assertEqual(g['ready_unfinished'],0);self.assertEqual(g['source_unfinished'],g['unavailable_obligations'])
        self.assertEqual(g['closed_slots'],0)

    def test_effective_rate_and_real_execution(self):
        d=subset(self.d,slice(0,2));bits=np.ones((2,2,2,4),bool);bits[0,1]=False
        f,s=apply_gates(gold(d),bits);r=metrics(d,f,s,bits)
        timed=timed_rates(r,[9.,1.]);self.assertEqual(timed['all']['complete_nonempty_per_second'],100.)
        for i,stage in enumerate((f,s)):
            stage['gate_open']=bits[:,i].reshape(2,8);stage['executed']=np.ones((2,8),np.int32)
            stage['work_checksum']=np.ones((2,8))
        dense=execution_metrics(f,s,'metal_dense');self.assertEqual(dense['run2']['executed_on_closed_rows'],8)
        with self.assertRaises(AssertionError):execution_metrics(f,s,'metal_skip')
        for stage in (f,s):
            stage['executed']=stage['gate_open'].astype('i');stage['work_checksum']=stage['executed'].astype(float)
        sparse=execution_metrics(f,s,'metal_skip');self.assertEqual(sparse['run2']['skipped_scorer_rows'],8)
        s['work_checksum'][0,1]=1
        with self.assertRaisesRegex(ValueError,'checksum'):execution_metrics(f,s,'metal_skip')

    def test_zero_retained_token_and_optional_slot_projection(self):
        d=subset(self.d,slice(0,1));f,s=gold(d);bits=np.ones((1,2,2,4),bool)
        # Materialize logits-independent canonical fields even for open-but-null slots.
        g=np.arange(1)[:,None];li,ri=f['pointers'].transpose(2,0,1)
        f['rows']=np.concatenate((d['a'][g,li],d['b'][g,ri,1,None]),-1)
        bits[0,0,0,0]=False;bits[0,1,1,0]=False;f,s=apply_gates((f,s),bits)
        token=np.zeros((1,8,56),np.float32);li,ri=f['pointers'].transpose(2,0,1)
        token[...,32:34]=np.eye(2)[f['active']];token[...,34:42]=np.eye(8)[li];token[...,42:50]=np.eye(8)[ri];token[...,50:55]=f['rows'];token[...,55]=d['a_port'][g,li]
        token[~bits[:,0].reshape(1,8)]=0;pi,qi=s['pointers'].transpose(2,0,1);parent=token[g,pi,50:55]
        s['rows']=np.concatenate((parent[...,:2],d['requests'][g,qi,4,None],parent[...,3:]),-1).astype(np.int32);s['rows'][~bits[:,1].reshape(1,8)]=0
        verify_token(d,f,s,token,bits)
        token[0,0,55]=1
        with self.assertRaisesRegex(ValueError,'closed payload'):verify_token(d,f,s,token,bits)
        f['rows'][0,0,0]=1
        with self.assertRaisesRegex(ValueError,'zero rows'):metrics(d,f,s,bits)


if __name__=='__main__':unittest.main()
