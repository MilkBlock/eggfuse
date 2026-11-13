"""Absolute tanh Cell readout; normalization uses compiler/source-only bounds."""
import numpy as np
from boundary_cell_ridge import D,B
from corpus_cell_ridge import features
from bake_stop_features import evaluate


def normalize(values,bounds,xp):
    return xp.concatenate([values[:,:D]/bounds[:,None],values[:,D:]],axis=1)


def readout_features(values,q,a,w,roles,bounds,wiring,xp,moments=None):
    unit=normalize(values,bounds,xp)
    columns=[features(unit,q,a,w,xp,roles),evaluate(unit,*wiring,xp)]
    if moments is not None:columns.append(moments)
    return xp.concatenate(columns,axis=1)


def preactivation(target,bounds):
    if not np.isfinite(bounds).all() or np.any(bounds<=0):raise ValueError('invalid body bounds')
    unit=normalize(target,bounds,np)
    if not np.isfinite(unit).all() or np.any(np.abs(unit)>1.00001):raise ValueError('teacher outside declared range')
    return np.arctanh(np.clip(unit,-1+1e-4,1-1e-4)).astype(np.float32)


def decode(raw,bounds,xp,mode='tanh'):
    if mode not in ('tanh','clip'):raise ValueError('unknown bounded readout')
    unit=xp.tanh(raw) if mode=='tanh' else xp.clip(raw,-1,1)
    return xp.concatenate([unit[:,:D]*bounds[:,None],unit[:,D:]],axis=1)


def port_moments(values,indices,mix,xp):
    channels=values[:,D:].reshape(len(values),-1,B)
    picked=xp.take_along_axis(channels,indices[:,:,None],axis=1)
    square=picked*picked
    projected=[]
    for local in (square,square*picked):
        projected.append(xp.tanh(xp.sum(xp.matmul(local[:,:,None,:],mix)[:,:,0,:],axis=1)))
    return xp.concatenate(projected,axis=1)
