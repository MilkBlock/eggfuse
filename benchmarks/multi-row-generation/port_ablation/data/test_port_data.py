from copy import deepcopy
import json
from pathlib import Path
import unittest
import numpy as np
from port_data import dataset,reference
from port_audit import audit, consistent_candidate_reads
from freeze import signature


def one_graph(data, i):
    return {k:(v[i:i+1] if isinstance(v,np.ndarray) else v) for k,v in data.items()}


def gold(data):
    t1,t2=data['target1'],data['target2']
    # A producer slot is not an index into the CPU truth table. Permute all of
    # them and redirect consumer references to the actual physical positions.
    f,s=({k:np.array(value,copy=True) for k,value in (
        ('active',t[...,0]),('pointers',t[...,1:3]),('rows',t[...,3:]))} for t in (t1[:,::-1],t2))
    s['pointers'][...,0]=7-s['pointers'][...,0]
    return f,s


class Cases(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.templates=json.loads((Path(__file__).parents[1]/'corpus/manifest.json').read_text())['templates']

    def test_whole_families_and_gold_parity(self):
        self.assertFalse({signature(t) for t in self.templates if t['split']=='heldout'} &
                         {signature(t) for t in self.templates if t['split']=='train'})
        for t in self.templates:
            d=dataset('collision',t,8);f,s=gold(d);out=audit(d,f,s)
            self.assertEqual((out['run2']['nonempty_graphs'],out['both_complete_graphs'],out['run2']['parent_ready_nonempty_graphs']),(8,8,8))

    def test_wrong_live_twin_vs_absent_parent(self):
        for family in self.templates:
            d=one_graph(dataset('collision',family,2),0);f,s=gold(d);pi,pj,oi,oj,req=d['probe'][0]
            fi=np.flatnonzero((f['active'][0]==1)&(f['pointers'][0]==(pi,pj)).all(1))[0]
            other=np.flatnonzero((f['active'][0]==1)&(f['pointers'][0]==(oi,oj)).all(1))[0]
            where=np.flatnonzero((s['active'][0]==1)&(s['pointers'][0]==(fi,req)).all(1))[0]
            wrong=deepcopy(s);wrong['pointers'][0,where,0]=other
            r=audit(d,f,wrong)['run2']
            self.assertEqual((r['wrong_live_parent'],r['wrong_live_parent_same_payload'],r['probe_wrong_twin'],r['absent_parent_reference'],r['missing']),(1,1,1,0,1))
            absent=deepcopy(s);absent['pointers'][0,where,0]=100
            r=audit(d,f,absent)['run2'];self.assertEqual((r['wrong_live_parent'],r['absent_parent_reference'],r['unavailable_parent_obligations']),(0,1,0))
            missing=deepcopy(f);missing['active'][0,fi]=0
            r=audit(d,missing,s)['run2'];self.assertEqual(r['parent_ready_nonempty_graphs'],0);self.assertGreater(r['unavailable_parent_obligations'],0)

    def test_two_legal_parents_do_not_count_as_wrong(self):
        template=next(t for t in self.templates if t['split']=='train')
        seen=False
        for i in range(32):
            # Two producer events can reference one physical B fact.
            d=one_graph(dataset('iid',template,32),i);f,s=gold(d)
            _,expected=reference(d['stages'],d['a'][0],d['b'][0],d['requests'][0]);by_req={}
            for witness in expected:by_req.setdefault(witness[-1],[]).append(witness[:2])
            for ri,parents in by_req.items():
                if len(parents)<2:continue
                valid=np.flatnonzero((s['active'][0]==1)&(s['pointers'][0,:,1]==ri))
                changed=deepcopy(s);changed['pointers'][0,valid[0]]=s['pointers'][0,valid[1]];changed['rows'][0,valid[0]]=s['rows'][0,valid[1]]
                r=audit(d,f,changed)['run2'];self.assertEqual((r['wrong_live_parent'],r['duplicates'],r['missing']),(0,1,1));seen=True;break
            if seen:break
        self.assertTrue(seen)

    def test_snapshot_compatibility(self):
        stage={'outputs':[(0,0)],'right_width':3}
        self.assertTrue(consistent_candidate_reads(stage,[[1,4,2],[2,4,2]]))
        self.assertFalse(consistent_candidate_reads(stage,[[1,4,2],[2,4,6]]))

if __name__=='__main__':unittest.main()
