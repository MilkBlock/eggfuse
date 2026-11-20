"""Audited Cell merge gate in the compiled, versioned Rust continuation path."""
import argparse
from contextlib import contextmanager
import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from statistics import median
import sys

HERE=Path(__file__).resolve().parent
BASE=HERE.parent/'higher-order-bake'
spec=importlib.util.spec_from_file_location('higher_native',BASE/'study.py')
higher=importlib.util.module_from_spec(spec);spec.loader.exec_module(higher)
TRAIN=('affine-twins','clamped-ramp','segmented-prefix','window-laplacian')
EVAL=('sum-bits','dot-product','gemm-bias-relu','stable-argmax')


def save(path, x):
    path.write_text(json.dumps(x,separators=(',',':'))+'\n')


def digest(obj):
    return hashlib.sha256(json.dumps(obj,sort_keys=True,separators=(',',':')).encode()).hexdigest()


@contextmanager
def session(exp,binary,case,seed,out):
    a=SimpleNamespace(binary=binary,out=out,ref=exp/'pass3-atlas-integration-20261120',
                      corpus=exp/'repair-bake-families-20261120',capture=exp/'recurrent-compositions-20261120',
                      train_capture=exp/'recurrent-compositions-train-20261120',catalog=higher.read(BASE/'catalog.json'))
    proc,req,plans,_,cap=higher.make_session(a,case,seed)
    parent=higher.read(BASE/'growth.json')['second_round']
    def run(policy, audit, mode=3):
        config=dict(higher.config(a,'baked',parent,True,audit),composed=mode,macro_policy=policy)
        v=higher.rpc(proc,dict(req,higher_config=config,audit=audit))
        if 'source_error' in v:raise RuntimeError((case,v['source_error']))
        if not audit:return v['ms'],v['state_sha'],v['runs']
        h=v['higher']
        checked=higher.describe(v,case,a,plans,cap)
        assert checked['source_exact'] and checked['rhs']==checked['neural_rhs'] and checked['direct']*100>=98*checked['fresh']
        endpoints={k:digest(v[k]) for k in ('rhs','writes','resumes','events','cell_ids','schedule')}
        endpoints.update(state=v['state_sha'],winners=digest(h['winners']))
        return dict(charges=h['charges'],boundary=h['boundary'],delta=h.get('delta'),rhs=checked['rhs'],direct=checked['direct'],
                    fresh=checked['fresh'],runs=checked['runs'],children=checked['winners'],chain=checked['max_chain'],
                    endpoints=endpoints)
    try:yield run
    finally:
        proc.stdin.close()
        if proc.wait():raise RuntimeError(proc.stderr.read().decode()[-2500:])


def collect(exp,binary,out):
    out.mkdir(parents=True,exist_ok=False)
    data={}
    for case in TRAIN:
        with session(exp,binary,case,1703,out) as run:
            off=run(None,True,0)
            on=run(None,True)
        assert off['endpoints']==on['endpoints']
        def key(c):return tuple(c[k] for k in ('generation','root','issue','version','owner','producer','effect'))
        assert [key(c) for c in off['charges']]==[key(c) for c in on['charges']]
        assert all(not c['selected'] for c in off['charges']) and all(c['selected'] for c in on['charges'])
        assert sum(c['counts'][2] for c in on['charges'])==on['children']
        data[case]=dict(charges=on['charges'],off_boundary=off['boundary'],on_boundary=on['boundary'],
                        endpoints=on['endpoints'],children=on['children'])
        print(case,len(on['charges']),on['children'],flush=True)
    save(out/'corpus.json',data)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('exp','binary','out'):p.add_argument(k,type=Path)
    a=p.parse_args();collect(a.exp,a.binary,a.out)
