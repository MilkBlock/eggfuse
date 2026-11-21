"""Test frozen selection on held-out source programs; no online calibration."""
import argparse,json
from pathlib import Path
from driver import configure,source,base,route
from policy import deploy


def choices(req,a):
    q=base(req);all_programs=set(v[0] for v in a.shapes if v)
    arms={'off':q,'all':route(q,a.shapes,all_programs)}
    for name in a.arms:
        key=f'{name}-{a.seed}' if name.startswith('return-') else name
        arms[name]=route(q,a.shapes,deploy(a.shapes,a.policies[key]))
    return arms


def observe(arm,out,q,rows):
    q.update(library=out['multi']['page_library'],words=out['multi']['word_verifier'],encoding=out['root_recipe']['factor'])
    if arm!='off':
        assert q['library']['invocations']>0
        for f in ('raw','multi','physical','commits','children','wire_hash'):
            assert q[f]==rows['off'][f],(arm,f)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('exp','native','learning','out'):p.add_argument(k,type=Path)
    p.add_argument('--cases',nargs='+',default=['conjugate-gradient','3mm'])
    p.add_argument('--arms',nargs='+',default=['first','one-pass','iterated','return-0','return-8'])
    p.add_argument('--seed',type=int,default=1703);p.add_argument('--repeats',type=int,default=4)
    a=p.parse_args();a.policies=json.loads(a.learning.read_bytes())['policies']
    source.common.config=configure
    source.study(a,choices,observe,None)
