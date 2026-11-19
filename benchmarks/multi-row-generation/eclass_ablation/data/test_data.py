from copy import deepcopy
import json
from pathlib import Path
import unittest
import numpy as np
from freeze import gold,verify_groups
from runtime import CORPUS
from source import dataset
from check import audit
from paired import paired_controls


def slice_graph(d,i):
    return {k:(v[i:i+1] if isinstance(v,np.ndarray) else v) for k,v in d.items()}


class Controls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ts=json.loads((CORPUS/'manifest.json').read_text())['templates'];cls.t=next(t for t in ts if t['id']=='rule-143')
        cls.d=dataset('test',cls.t)

    def test_neural_inputs_and_golden_labels(self):
        verify_groups(self.d);f,s=gold(self.d);out=audit(self.d,f,s)
        self.assertEqual(out['both_complete_graphs'],len(self.d['a']))
        self.assertTrue(np.array_equal(out['request_legal'],self.d['request_legal']))

    def test_wrong_origin_despite_equal_value_class(self):
        d=slice_graph(self.d,3) # committed, second origin choice, targeted probe
        f,s=gold(d);ri=int(np.flatnonzero(d['probe_kind'][0]==2)[0]);read,required=d['requests'][0,ri,:2],d['requests'][0,ri,2:4]
        self.assertFalse(np.array_equal(read,required));slot=int(np.flatnonzero((f['active'][0]==1)&(f['rows'][0,:,:2]==read).all(1))[0])
        out_slot=int(np.flatnonzero((s['active'][0]==1)&(s['pointers'][0,:,1]==ri))[0]);wrong=deepcopy(s);wrong['pointers'][0,out_slot,0]=slot
        r=audit(d,f,wrong)['run2'];self.assertEqual((r['wrong_parent_same_eclass'],r['wrong_parent_when_available'],r['missing']),(1,1,1))

    def test_precommit_and_suppressed_consumer(self):
        d=slice_graph(self.d,3);f,s=gold(d)
        pre=audit(slice_graph(self.d,1),f,s)['run2'];suppressed=audit(slice_graph(self.d,5),f,s)['run2']
        self.assertGreater(pre['early_local_equality'],0);self.assertGreater(suppressed['uncommitted_local_equality'],0)
        self.assertEqual(pre['parent_ready_nonempty_graphs'],1)

    def test_paired_probe_and_emission_separation(self):
        f,s=gold(self.d);blind_self=np.equal(self.d['requests'][...,:2],self.d['requests'][...,2:4]).all(-1)
        r=paired_controls(self.d,f,s,blind_self)['all']['pre_to_post']
        self.assertGreater(r['probes'],0)
        self.assertEqual(r['both_semantic_correct'],0)
        self.assertEqual(r['both_emissions_exact'],r['probes'])
        ok=paired_controls(self.d,f,s,self.d['request_legal'])['all']['same_class_origin_switch_post']
        self.assertGreater(ok['probes'],0);self.assertEqual(ok['both_emissions_exact_given_parents'],ok['probes'])

    def test_cross_instance_pollution(self):
        for i in np.flatnonzero(self.d['state']==3):
            d=slice_graph(self.d,i);cross=int(np.flatnonzero(d['probe_kind'][0]==3)[0]);
            if not d['request_legal'][0,cross]:continue
            f,s=gold(d);post=slice_graph(self.d,i-4);r=audit(post,f,s)['run2']
            self.assertGreater(r['cross_instance_contamination'],0);break
        else:self.fail('no valid external cross-instance request')

if __name__=='__main__':unittest.main()
