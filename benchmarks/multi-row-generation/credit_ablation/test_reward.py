"""Strict credit for generated witnesses on the frozen two-Run Cell interface."""
from copy import deepcopy
import json
import unittest

import numpy as np
import torch

from reward import team_reward
from replay import CORPUS, audit_source, numpy_reward
from eclass_ablation.data import dataset


def gold(d):
    # True source labels have canonical parent order. Reverse the generated
    # frontier to prove that the reward follows actual decoded physical indices.
    one,two=({'active':y[...,0].copy(),'pointers':y[...,1:3].copy(),'rows':y[...,3:].copy()}
             for y in (d['target1'][:,::-1],d['target2']))
    two['pointers'][...,0]=one['active'].shape[1]-1-two['pointers'][...,0]
    return one,two


def check_scores(case,d,first,second,device='cpu'):
    def tensors(raw):return {k:torch.as_tensor(v,device=device) for k,v in raw.items()}
    targets=[torch.as_tensor(d[k],device=device) for k in ('target1','target2')]
    score,parts=team_reward(tensors(first),tensors(second),*targets)
    truth,expected=numpy_reward(d,first,second)
    case.assertEqual(set(parts),set(expected));case.assertFalse(score.requires_grad)
    np.testing.assert_allclose(score.cpu().numpy(),truth,rtol=2e-6,atol=2e-7)
    for key,val in parts.items():
        case.assertFalse(val.requires_grad,key);actual=val.cpu().numpy()
        if actual.dtype.kind in 'biu':np.testing.assert_array_equal(actual,expected[key],err_msg=key)
        else:np.testing.assert_allclose(actual,expected[key],rtol=2e-6,atol=2e-7,err_msg=key)
    return truth,expected


class Rewards(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        templates=json.loads((CORPUS/'manifest.json').read_text())['templates']
        cls.d=dataset('test',next(t for t in templates if t['id']=='rule-143'),16)

    def test_exact_empty_irrelevant_and_entirely_invalid(self):
        d=self.d;first,second=gold(d)
        out,parts=check_scores(self,d,first,second);np.testing.assert_array_equal(out,1.)
        self.assertTrue((parts['consumed_parents']==parts['required_parents']).all())
        second['active'].fill(0);out,_=check_scores(self,d,first,second);np.testing.assert_array_equal(out,0.)
        # Emit just one legal parent, known unused by every gold request in each graph.
        for g in range(len(out)):
            used=d['target2'][g,d['target2'][g,:,0].astype(bool),1]
            keep=next(index for index in np.flatnonzero(first['active'][g]) if 7-index not in used)
            first['active'][g]=0;first['active'][g,keep]=1
        out,p=check_scores(self,d,first,second);np.testing.assert_allclose(out,-5/24);np.testing.assert_array_equal(p['P'],0.)
        first['active'].fill(0);out,_=check_scores(self,d,first,second);np.testing.assert_array_equal(out,-.25)
        first['active'].fill(1);first['pointers'].fill(123);second['active'].fill(1);second['pointers'].fill(-1)
        out,_=check_scores(self,d,first,second);np.testing.assert_array_equal(out,-.75)

    def test_extra_duplicate_and_extra_illegal_are_not_completion(self):
        d=self.d;f,s=gold(d);cf=deepcopy(f)
        for g in range(len(d['a'])):
            added=np.flatnonzero(f['active'][g]==0)[0];sample=np.flatnonzero(f['active'][g])[0]
            for k in f:cf[k][g,added]=f[k][g,sample]
        out,p=check_scores(self,d,cf,s);np.testing.assert_array_equal(out,31/32);np.testing.assert_array_equal(p['run1_duplicates'],1)
        for illegal in (False,True):
            cs=deepcopy(s)
            for g in range(len(d['a'])):
                added=np.flatnonzero(s['active'][g]==0)[0];sample=np.flatnonzero(s['active'][g])[0]
                for k in s:cs[k][g,added]=s[k][g,sample]
                if illegal:cs['pointers'][g,added,0]=-2
            out,p=check_scores(self,d,f,cs);np.testing.assert_array_equal(out,23/32)
            np.testing.assert_array_equal(p['E2'],0.);np.testing.assert_array_equal(p['W2'],1/8)
            np.testing.assert_array_equal(p['run2_illegal' if illegal else 'run2_duplicates'],1)

    def test_wrong_equal_parent_and_tainted_parent_row(self):
        g=3;d={k:v[g:g+1] if isinstance(v,np.ndarray) else v for k,v in self.d.items()}
        f,s=gold(d);ri=np.flatnonzero(d['probe_kind'][0]==2)[0];wanted=d['requests'][0,ri]
        self.assertFalse(np.array_equal(wanted[:2],wanted[2:4]));incorrect_parent=np.flatnonzero((f['active'][0]==1)&(f['rows'][0,:,:2]==wanted[:2]).all(1))[0]
        emission=np.flatnonzero((s['active'][0]==1)&(s['pointers'][0,:,1]==ri))[0];bad=deepcopy(s)
        bad['pointers'][0,emission,0]=incorrect_parent
        source_report=audit_source(d,f,bad)['run2'];self.assertEqual(source_report['wrong_parent_same_eclass'],1)
        out,p=check_scores(self,d,f,bad);self.assertLess(float(out[0]),.75);self.assertEqual(int(p['run2_illegal'][0]),1);self.assertEqual(float(p['E2'][0]),0)
        # Leave the correct consumer fields and pointers intact but corrupt the
        # selected make payload. Downstream credit must depend on its ancestry.
        bad=deepcopy(f);pi=s['pointers'][0,emission,0];bad['rows'][0,pi,3]=(bad['rows'][0,pi,3]+1)%8
        out,p=check_scores(self,d,bad,s);self.assertEqual(int(p['run2_missing'][0]),0)
        self.assertGreater(int(p['run2_semantic_missing'][0]),0);self.assertFalse(bool(p['parent_ready'][0]));self.assertLess(float(p['P'][0]),1)

    def test_consumers_do_not_multiply_parent_credit(self):
        d=self.d;first,second=gold(d);out,p=check_scores(self,d,first,second)
        self.assertTrue((d['target2'][...,0].sum(1)>p['required_parents']).any())
        self.assertTrue((p['run2_unique_correct']>=p['consumed_parents']).all())
        # Actions are sampled, not decoded again from these deliberately conflicting logits.
        altered={**first,'active_logits':torch.zeros(1,requires_grad=True).detach().numpy()}
        same,_=check_scores(self,d,altered,second);np.testing.assert_array_equal(out,same)

    def test_label_permutation_and_random_corruption(self):
        d={**self.d};f,s=gold(d);rng=np.random.default_rng(50711)
        batch=np.arange(len(f['active']))[:,None];order=np.stack([rng.permutation(8) for _ in batch]);inverse=np.argsort(order,axis=1)
        d['target1']=d['target1'][batch,order].copy();d['target2']=d['target2'].copy()
        d['target2'][...,1]=inverse[batch,d['target2'][...,1]]
        d['target2']=d['target2'][batch,order];out,_=check_scores(self,d,f,s);np.testing.assert_array_equal(out,1.)
        for k in ('pointers','active','rows'):
            for stage in (f,s):
                x=stage[k];replace=rng.random(x.shape)<.15
                if k=='active':x[replace]=1-x[replace]
                else:x[replace]=rng.integers(-1,9,size=int(replace.sum()))
        check_scores(self,d,f,s)
        if torch.backends.mps.is_available():check_scores(self,d,f,s,device='mps')

if __name__=='__main__':unittest.main()
