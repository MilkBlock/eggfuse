"""CPU-only generated-token contract and repeat diagnostics."""
import sys
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'coverage'))
from metrics import check_decode,soft_metrics
from data import N,K,V,Q


def check_token(out,sp):
    check_decode(out,sp);t=out['token'];assert t.shape[-1]==90
    assert np.isfinite(t).all();np.testing.assert_array_equal(t[...,:64],out['latent'])
    decisions=[out['active'],out['pointers'][...,0],out['pointers'][...,1],*np.moveaxis(out['fields'],-1,0)]
    offset=64
    for width,decision in zip((2,N,N,K,V,V),decisions):
        np.testing.assert_array_equal(t[...,offset:offset+width],np.eye(width,dtype=np.float32)[decision]);offset+=width


def repeat_metrics(out,length):
    same=0;later=0
    for g in range(len(out['active'])):
        previous=set()
        for t in range(length):
            current=set()
            for s in range(t,Q,length):
                if not out['active'][g,s]:continue
                pair=tuple(map(int,out['pointers'][g,s]))
                if pair in current:same+=1
                elif pair in previous:later+=1
                current.add(pair)
            previous.update(current)
    return dict(within_round_repeats=same,cross_round_repeats=later)
