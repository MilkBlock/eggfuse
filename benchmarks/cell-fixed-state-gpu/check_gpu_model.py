"""Check folded fixed GPU functions against direct CPU feature formulas."""
import numpy as np
import mlx.core as mx
from gpu_model import forward
if not mx.metal.is_available():raise RuntimeError('GPU required')
mx.set_default_device(mx.gpu);rng=np.random.default_rng(305)
x=rng.normal(size=(17,8)).astype(np.float32);centers=rng.normal(size=(11,8)).astype(np.float32)
mean=rng.normal(size=8).astype(np.float32);scale=rng.uniform(.2,2,size=8).astype(np.float32)
w=rng.normal(size=(19,5)).astype(np.float32);b=rng.normal(size=5).astype(np.float32)
linear=w[:8]/scale[:,None];bias=b-mean@linear
for kind in ('quadratic','radial'):
 for radius in (.25,1.,4.):
    z=(x-mean)/scale
    if kind=='quadratic':
        first=centers.T/(8*scale[:,None]);q=1-mean@first;square=np.zeros(8,np.float32)
        features=(1+z@centers.T/8)**2
    else:
        square=1/(scale*scale*8*radius);first=2*centers.T/(8*radius*scale[:,None])+2*(mean*square)[:,None]
        q=-(centers*centers).sum(1)/(8*radius)-(mean*mean*square).sum()-2*(mean/scale)@centers.T/(8*radius)
        features=np.exp(-np.sum((z[:,None,:]-centers[None,:,:])**2,axis=2)/(8*radius))
    m=dict(kind=kind,degree=2,first=first,first_bias=q,linear=linear,nonlinear=w[8:],bias=bias,radial_square=square)
    result=forward(m)(mx.array(x));mx.eval(result)
    np.testing.assert_allclose(np.array(result),np.concatenate([z,features],axis=1)@w+b,rtol=2e-4,atol=2e-4)
    bad=dict(m,kind='unknown')
    try:forward(bad)
    except ValueError:pass
    else:raise AssertionError('unknown model accepted')
print('six fixed GPU/CPU folding checks and unknown-kind rejection: pass')
