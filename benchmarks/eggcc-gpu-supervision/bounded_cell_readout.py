"""Absolute tanh Cell readout; normalization uses compiler/source-only bounds."""
import numpy as np
from boundary_cell_ridge import D
from corpus_cell_ridge import features
from bake_stop_features import evaluate


def normalize(values,bounds,xp):
    return xp.concatenate([values[:,:D]/bounds[:,None],values[:,D:]],axis=1)


def readout_features(values,q,a,w,roles,bounds,wiring,xp):
    unit=normalize(values,bounds,xp)
    return xp.concatenate([features(unit,q,a,w,xp,roles),evaluate(unit,*wiring,xp)],axis=1)


def preactivation(target,bounds):
    if not np.isfinite(bounds).all() or np.any(bounds<=0):raise ValueError('invalid body bounds')
    unit=normalize(target,bounds,np)
    if not np.isfinite(unit).all() or np.any(np.abs(unit)>1.00001):raise ValueError('teacher outside declared range')
    return np.arctanh(np.clip(unit,-1+1e-4,1-1e-4)).astype(np.float32)


def decode(raw,bounds,xp):
    unit=xp.tanh(raw)
    return xp.concatenate([unit[:,:D]*bounds[:,None],unit[:,D:]],axis=1)
