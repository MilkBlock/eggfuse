"""Exactly expand a low-dimensional quadratic branch into static bilinear weights."""
import argparse,json,hashlib
from pathlib import Path
import numpy as np
p=argparse.ArgumentParser()
for k in ('left','right','selection','output'):p.add_argument('--'+k,type=Path,required=True)
a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True);left=dict(np.load(a.left));right=dict(np.load(a.right));report=json.loads(a.selection.read_text());alpha=report['selection']['alpha']
for key,path in [('left',a.left),('right',a.right)]:
 if report['hashes'][key]!=hashlib.sha256(path.read_bytes()).hexdigest():raise ValueError('selection/model mismatch')
if 'state_projection' in left or 'state_projection' not in right or not 0<alpha<1:raise ValueError('expected raw plus reduced branch')
for k in ('op','edge','literal','labels'):
 if not np.array_equal(left[k],right[k]):raise ValueError('input mismatch')
s,t=right['state_projection'],right['state_bias'];d,r=s.shape
p2,q,n,l,b=[right[k].astype(np.float64) for k in ('first','first_bias','nonlinear','linear','bias')]
h=np.einsum('ik,jk,kc->ijc',p2,p2,n)
rl=l+2*p2@(q[:,None]*n);rb=b+(q*q)@n
model={k:left[k] for k in ('op','edge','literal','labels','dimension','pool_ops')}
model.update(kind='quadratic_bilinear',degree=2,low_width=r,
 state_projection=np.concatenate([np.eye(d,dtype=np.float32),s],axis=1),state_bias=np.concatenate([np.zeros(d,np.float32),t]),
 first=np.vstack([left['first'],np.zeros((r,left['first'].shape[1]),np.float32)]),first_bias=left['first_bias'],
 linear=np.vstack([(1-alpha)*left['linear'],alpha*rl]).astype(np.float32),nonlinear=(1-alpha)*left['nonlinear'],
 bias=((1-alpha)*left['bias']+alpha*rb).astype(np.float32),bilinear=(alpha*h.reshape(r*r,-1)).astype(np.float32))
# Arbitrary real inputs test algebra, not just finite corpus points.
rng=np.random.default_rng(827);x=rng.normal(size=(67,d)).astype(np.float32);u=x@s+t
expected=(1-alpha)*(x@left['linear']+(x@left['first']+left['first_bias'])**2@left['nonlinear']+left['bias'])+alpha*(u@right['linear']+(u@right['first']+right['first_bias'])**2@right['nonlinear']+right['bias'])
from gpu_model import forward
import mlx.core as mx
if not mx.metal.is_available():raise RuntimeError('GPU required')
mx.set_default_device(mx.gpu);combined=np.concatenate([x,u],axis=1);y=forward(model)(mx.array(combined));mx.eval(y)
np.testing.assert_allclose(np.array(y),expected,atol=.003,rtol=.003)
np.savez(a.output/'model.npz',**model)
result=dict(scope='Exact polynomial expansion of validation-selected blend; no fitting',alpha=alpha,random_input_max_error=float(abs(np.array(y)-expected).max()),
 state_width=d+r,low_width=r,device_bytes=sum(np.asarray(model[k]).nbytes for k in ('first','first_bias','linear','nonlinear','bias','bilinear')),fixed_matmuls=4,
 source_hashes={k:hashlib.sha256(getattr(a,k).read_bytes()).hexdigest() for k in ('left','right','selection')})
(a.output/'compile.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
