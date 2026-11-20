"""Certify a frozen route without reading any workload or observed model decision."""
from fractions import Fraction
import hashlib
import importlib.util
from itertools import product
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location("binary32_bounds",HERE.parent/"composed-row-dispatch/certify.py")
bounds=importlib.util.module_from_spec(spec)
spec.loader.exec_module(bounds)


def interval(w,b,features):
    # Rust computes the dot with a zero accumulator, then adds the bias.
    lo,hi,e=bounds.affine(list(map(bounds.scalar,w)),Fraction(0),features)
    bias=bounds.scalar(b)
    lo,hi=lo+bias-e,hi+bias+e
    if max(abs(lo),abs(hi))>2**120:raise ValueError('outside finite proof range')
    margin=bounds.UNIT*max(abs(lo),abs(hi))+bounds.TINY
    return lo-margin,hi+margin


def certificate(w):
    if len(w['hidden']) not in (0,8) or len(w['bias'])!=len(w['hidden']):
        raise ValueError('unsupported layer')
    lower,upper=[],[]
    for bits in product((0,1),repeat=5):
        x=[(0,4)]*3+[(v,v) for v in bits]
        if w['hidden']:
            hidden=[interval(line,b,x) for line,b in zip(w['hidden'],w['bias'])]
            x=[(0 if l>=0 else -1, 0 if u<=0 else 1) for l,u in hidden]
        lo,hi=interval(w['output'],w['offset'],x)
        lower.append(lo);upper.append(hi)
    lo,hi=min(lower),max(upper)
    return dict(lower=float(lo),upper=float(hi),mode=2 if lo>0 else 1 if hi<=0 else None,
                sha256=hashlib.sha256(json.dumps(w,sort_keys=True,separators=(',',':')).encode()).hexdigest())


def lower_request(request):
    policy=request.get('request_route_gate') or {}
    if (policy.get('mode')!=3 or policy.get('capture') or request.get('audit')
            or request.get('wake_roots')!=4 or 'connected_requests' not in request):
        return request
    mode=certificate(policy['weights'])['mode']
    if mode is None:return request
    result=dict(request)
    del result['request_route_gate']
    if mode==1:
        del result['connected_requests']
        del result['wake_roots']
    return result


if __name__=='__main__':
    weights=json.loads((HERE/'policies.json').read_bytes())
    out={k:certificate(v['weights']) for k,v in weights.items()}
    (HERE/'certificates.json').write_text(json.dumps(out,indent=1)+'\n')
    print({k:(v['mode'],round(v['lower'],3)) for k,v in out.items()})
