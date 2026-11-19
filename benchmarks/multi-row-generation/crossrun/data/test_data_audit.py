import unittest
from copy import deepcopy

import numpy as np

from crossrun_audit import audit, audit_twins
from crossrun_data import SPLITS, bindings, dataset


def gold(d):
    # Reverse the first output slots to catch a verifier that assumes source order.
    f = d['target1'][:, ::-1].copy()
    t = d['target2']
    first = dict(active=f[..., 0].copy(), pointers=f[..., 1:3].copy(), fields=f[..., 3:].copy())
    second = dict(active=t[..., 0].copy(), pointers=np.zeros_like(t[..., 1:3]), fields=t[..., 3:].copy())
    for g in range(len(f)):
        for s in np.flatnonzero(second['active'][g]):
            identity = t[g, s, 1:3]
            pi = np.flatnonzero((f[g, :, 0] == 1) & np.all(f[g, :, 1:3] == identity, axis=-1))[0]
            ri = np.flatnonzero(np.all(d['requests'][g, :, :2] == identity, axis=-1))[0]
            second['pointers'][g, s] = pi, ri
    return first, second


class CrossRun(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = {split: dataset(split) for split in SPLITS}

    def test_labels_capacity_collision_split_and_twin_intervention(self):
        seen = set()
        for name, d in self.data.items():
            t1, t2 = d['target1'], d['target2']
            self.assertTrue((t1[..., 0].sum(1) <= 8).all())
            self.assertEqual(len(t1), SPLITS[name][0])
            for g, (a, b, req) in enumerate(zip(d['a'], d['b'], d['requests'])):
                key = a.tobytes()+b.tobytes()+req.tobytes(); self.assertNotIn(key, seen);seen.add(key)
                p = t1[g, t1[g, :, 0] == 1]; payloads = list(map(tuple, p[:, 3:]))
                self.assertEqual(len(p), len(bindings(a,b)))
                self.assertEqual(len(set(map(tuple,req[:,:2]))), 4)
                if name in ('train','iid'):
                    self.assertEqual(len(set(payloads)), len(payloads))
                    continue
                self.assertLess(len(set(payloads)), len(payloads))
                self.assertTrue(1 <= int(t2[g, :, 0].sum()) <= 3)
            if name.endswith('collision'):
                np.testing.assert_array_equal(d['a'][::2], d['a'][1::2])
                np.testing.assert_array_equal(d['b'][::2], d['b'][1::2])
                before, after = d['requests'][::2], d['requests'][1::2]
                np.testing.assert_array_equal(before[...,2],after[...,2])
                diff=(before!=after).any(-1);self.assertTrue((diff.sum(1)==1).all())
                for g, row in enumerate(np.argmax(diff, axis=1)):
                    i,j = before[g,row,:2]; u,v = after[g,row,:2]
                    self.assertEqual(i==u, name=='right_collision');self.assertEqual(j==v,name=='left_collision')
                    np.testing.assert_array_equal(d['a'][2*g,i],d['a'][2*g,u]);np.testing.assert_array_equal(d['b'][2*g,j],d['b'][2*g,v])

    def test_actual_parent_identity_and_semantic_ancestry(self):
        d={k:v[:1] for k,v in self.data['left_collision'].items()};first,second=gold(d)
        def score(one,two):return audit(d['a'], d['b'], d['requests'], one, two)['run2']
        ready=score(first,second)
        self.assertEqual((ready['complete_graphs'],ready['parent_ready_nonempty_complete_graphs']),(1,1))
        # Select the twin with identical fields but a different (i,j) for one output.
        changed=deepcopy(second)
        for s in np.flatnonzero(second['active'][0]):
            pi=second['pointers'][0,s,0]
            twins=np.flatnonzero((first['active'][0]==1)&(first['fields'][0]==first['fields'][0,pi]).all(1)&(np.arange(8)!=pi))
            if len(twins):changed['pointers'][0,s,0]=twins[0];break
        else:self.fail('selective twin absent')
        r=score(first,changed);self.assertEqual((r['illegal'],r['missing'],r['complete_graphs']),(1,1,0))
        bad=deepcopy(first);bad['fields'][0,pi,2]=(bad['fields'][0,pi,2]+1)%4
        r=score(bad,second);self.assertEqual((r['parent_field_errors'],r['field_errors'],r['binding_complete_graphs'],r['complete_graphs']),(1,0,1,0))
        self.assertEqual((r['parent_ready_nonempty_graphs'],r['unavailable_parent_obligations']),(0,1))
        duplicated=deepcopy(second);slot=np.flatnonzero(second['active'][0]==0)[0]
        for k in second:duplicated[k][0,slot]=second[k][0,s]
        self.assertEqual(score(first,duplicated)['duplicates'],1)

    def test_twin_intervention_needs_different_parent_slots(self):
        d=self.data['right_collision'];first,second=gold(d)
        r=audit_twins(d['a'],d['b'],d['requests'],first,second)
        self.assertEqual(r['both_counterfactual_claims_exact'],128)
        self.assertEqual(r['both_emitted_once_same_parent_slot'],0)
        for g in range(1,len(d['a']),2):
            req=np.flatnonzero((d['requests'][g]!=d['requests'][g-1]).any(-1))[0]
            def position(x):
                return np.flatnonzero((second['active'][x]==1)&(second['pointers'][x,:,1]==req))[0]
            second['pointers'][g,position(g),0]=second['pointers'][g-1,position(g-1),0]
        r=audit_twins(d['a'],d['b'],d['requests'],first,second)
        self.assertEqual((r['both_counterfactual_claims_exact'],r['both_emitted_once_same_parent_slot']),(0,128))

    def test_gold_layout_all_splits(self):
        for d in self.data.values():
            first,second=gold(d);r=audit(d['a'],d['b'],d['requests'],first,second)
            self.assertEqual(r['both_complete_graphs'],len(d['a']))
            self.assertEqual(r['run2']['nonempty_complete_graphs'],int((d['target2'][...,0].sum(1)>0).sum()))

if __name__=='__main__':unittest.main()
