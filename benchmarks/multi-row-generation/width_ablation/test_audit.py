"""Conflicts, identity and correlated-control regressions for parallel rows."""
from copy import deepcopy
import json
from pathlib import Path
import unittest
import numpy as np

from audit import DUPLICATE_BINS, duplicate_profile, metrics, paired_layouts
from eclass_ablation.data import dataset


def gold(d):
    first,second=({'active':y[...,0].copy(),'pointers':y[...,1:3].copy(),'rows':y[...,3:].copy()}
                  for y in (d['target1'][:,::-1],d['target2']))
    second['pointers'][...,0]=7-second['pointers'][...,0]
    return first,second


class WidthAudit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path=Path(__file__).resolve().parents[1]/'eclass_ablation/corpus/manifest.json'
        t=next(t for t in json.loads(path.read_text())['templates'] if t['id']=='rule-143')
        cls.data=dataset('test',t,16)

    def test_disjoint_conservation_independent_of_order(self):
        claims=[(0,'A'),(2,'A'),(3,'A'),(5,'A'),(4,'B'),(7,'B')]
        p=duplicate_profile(claims,8,4)
        self.assertEqual([p[k] for k in DUPLICATE_BINS],[2,1,1])
        self.assertEqual((p['duplicate_same_row'],p['duplicate_cross_row']),(1,3))
        self.assertEqual(p,duplicate_profile(list(reversed(claims)),8,4))
        self.assertEqual(duplicate_profile(claims,8,1)['duplicate_later_round_same_row'],4)
        self.assertEqual(duplicate_profile(claims,8,8)['duplicate_same_round_cross_row'],4)

    def test_distinct_requests_may_share_a_parent(self):
        d=self.data;f,s=gold(d)
        r=metrics(d,f,s,4,d['request_legal'])
        self.assertEqual(r['both_complete_graphs'],16)
        self.assertGreater(r['run2']['distinct_requests_reusing_a_parent'],0)
        self.assertEqual(r['run2']['duplicates'],0)
        self.assertEqual(r['complete_intervention_groups'],2)
        self.assertGreater(r['origin_switch']['post']['pairs'],0)
        for values in r['origin_switch'].values():
            self.assertEqual(values['pairs'],values['exact_on_both'])
        self.assertIsNotNone(r['paired_controls'])

    def test_different_physical_slots_same_full_source_witness(self):
        d=self.data;f,s=gold(d);g=3
        legal_slot=int(np.flatnonzero(s['active'][g])[0]);pi,qi=s['pointers'][g,legal_slot]
        duplicate_parent_slot=int(np.flatnonzero(f['active'][g]==0)[0]);new_consumer_slot=int(np.flatnonzero(s['active'][g]==0)[0])
        for k,array in f.items():array[g,duplicate_parent_slot]=array[g,pi]
        for k,array in s.items():array[g,new_consumer_slot]=array[g,legal_slot]
        s['pointers'][g,new_consumer_slot,0]=duplicate_parent_slot
        s['rows'][g,new_consumer_slot,3]=(s['rows'][g,new_consumer_slot,3]+1)%8
        r=metrics(d,f,s,4)
        for stage in ('run1','run2'):
            z=r[stage]['per_graph'][g]
            self.assertEqual((z['duplicates'],z['illegal'],z['missing']),(1,0,0))
            self.assertEqual(sum(z[k] for k in DUPLICATE_BINS),1)
        self.assertEqual(r['run2']['per_graph'][g]['bad_result_row'],1)
        mixed=metrics(d,f,s,(1,8))
        self.assertEqual(mixed['run1']['per_graph'][g]['duplicate_later_round_same_row'],1)
        self.assertEqual(mixed['run2']['per_graph'][g]['duplicate_same_round_cross_row'],1)

    def test_paired_layouts_condition_on_both_frontiers(self):
        d=self.data;f,s=gold(d);reference=metrics(d,f,s,1)
        altered_parent=deepcopy(f);event=0;needed=s['pointers'][event,np.flatnonzero(s['active'][event])[0],0]
        altered_parent['active'][event,needed]=0
        altered_finish=deepcopy(s);event2=4
        altered_finish['active'][event2,np.flatnonzero(s['active'][event2])[0]]=0
        other=metrics(d,altered_parent,altered_finish,4)
        delta=paired_layouts(reference,other)
        self.assertEqual(delta['groups_compared'],2)
        self.assertEqual(delta['nonempty']['baseline_only'],2)
        self.assertEqual((delta['common_parent_ready_nonempty']['graphs'],delta['common_parent_ready_nonempty']['baseline_only']),(15,1))
        reverse=paired_layouts(other,reference)
        self.assertEqual(reverse['common_parent_ready_nonempty']['candidate_only'],1)
        broken=dict(other,graph_keys=list(reversed(other['graph_keys'])))
        with self.assertRaisesRegex(ValueError,'identical source inputs'):paired_layouts(reference,broken)

    def test_timing_subset_does_not_invent_full_counterfactuals(self):
        d=self.data;index=np.array([0,9]);short={k:(v[index] if isinstance(v,np.ndarray) else v) for k,v in d.items()}
        f,s=gold(short);r=metrics(short,f,s,2,short['request_legal'])
        self.assertEqual(r['complete_intervention_groups'],0);self.assertIsNone(r['paired_controls']);self.assertEqual(r['origin_switch']['post']['pairs'],0)
        with self.assertRaisesRegex(ValueError,'row count'):metrics(short,f,s,3)

if __name__=='__main__':unittest.main()
