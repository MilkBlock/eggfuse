"""Construct one fixed GPU expression from model metadata, never from input data."""
import numpy as np


def forward(model):
    import mlx.core as mx
    kind=str(model.get('kind','quadratic'));degree=int(model.get('degree',2))
    arrays={k:np.asarray(model[k]) for k in ('linear','first','first_bias','nonlinear','bias')}
    if not all(np.isfinite(x).all() for x in arrays.values()):raise ValueError('nonfinite model')
    linear,first,q,nonlinear,bias=[arrays[k] for k in ('linear','first','first_bias','nonlinear','bias')]
    if linear.ndim!=2 or first.ndim!=2 or nonlinear.ndim!=2:raise ValueError('matrix ranks')
    if first.shape[0]!=linear.shape[0] or nonlinear.shape!=(first.shape[1],linear.shape[1]) or q.shape!=(first.shape[1],) or bias.shape!=(linear.shape[1],):raise ValueError('model shapes')
    l,p,q,n,b=[mx.array(x) for x in (linear,first,q,nonlinear,bias)];mx.eval(l,p,q,n,b)
    if kind=='quadratic':
        if degree not in (2,3):raise ValueError('unsupported polynomial')
        return mx.compile(lambda x:x@l+(x@p+q)**degree@n+b)
    if kind=='quadratic_bilinear':
        width=int(model['low_width']);outer=np.asarray(model['bilinear'])
        if width<=0 or width>=linear.shape[0] or outer.shape!=(width*width,linear.shape[1]) or not np.isfinite(outer).all():raise ValueError('bilinear shape')
        h=mx.array(outer);mx.eval(h)
        def execute(x):
            u=x[:,-width:]
            terms=(u[:,:,None]*u[:,None,:]).reshape(x.shape[0],width*width)
            return x@l+(x@p+q)**2@n+terms@h+b
        return mx.compile(execute)
    if kind=='radial':
        square=np.asarray(model['radial_square'])
        if square.shape!=(linear.shape[0],) or not np.isfinite(square).all() or np.any(square<=0):raise ValueError('radial norm weights')
        s=mx.array(square);mx.eval(s)
        return mx.compile(lambda x:x@l+mx.exp(mx.minimum(x@p+q-mx.sum(x*x*s,axis=1,keepdims=True),0))@n+b)
    raise ValueError('unsupported model kind')
