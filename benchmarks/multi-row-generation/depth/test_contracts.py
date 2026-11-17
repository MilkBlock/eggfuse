import unittest
import numpy as np
from contracts import reference,audit
from task import generate,KEYS,VALUES

class AuditTests(unittest.TestCase):
    def test_nonfinite_or_noncanonical_token_cannot_pass_via_argmax(self):
        d=generate(2,3,2,123);p,f=reference(d['a'],d['b'],4);parts=[]
        for col,width in enumerate((KEYS,KEYS,VALUES,VALUES)):parts.append(np.eye(width)[f[...,col]])
        symbols=np.concatenate(parts,-1);h=np.pad(symbols,((0,0),(0,0),(0,0),(0,64-symbols.shape[-1])))
        positions=[d['coords_b']]+[d['coords_a']+np.array([0,(s+1)*3]) for s in range(1,4)]
        out=dict(latent=h,field_logits=symbols,pointer_logits=np.eye(6)[p],pointers=p,addresses=np.stack([pos[idx] for pos,idx in zip(positions,p)]))
        w=np.eye(symbols.shape[-1],64);b=np.zeros(symbols.shape[-1]);args=(d['a'],d['b'],d['coords_a'],d['coords_b'],d['coords_pair'],3)
        self.assertEqual(audit(*args,out,w,b,True)['cumulative_exact_graphs'],[2]*4)
        bad=dict(out,latent=h.copy());bad['latent'][3,0,0,-1]=1
        r=audit(*args,bad,w,b,True);self.assertFalse(r['typed_format_valid']);self.assertEqual(r['cumulative_exact_graphs'][-1],1)
        bad=dict(out,latent=h.copy());bad['latent'][3,0,0,0]=np.nan
        with np.errstate(invalid='ignore'):r=audit(*args,bad,w,b,True)
        self.assertFalse(r['all_finite']);self.assertEqual(r['cumulative_exact_graphs'][-1],1)

if __name__=='__main__':unittest.main()
