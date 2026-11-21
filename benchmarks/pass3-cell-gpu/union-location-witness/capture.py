"""Observe raw positive and negative physical slot labels AFTER the candidate features are fixed."""
import argparse,json
from pathlib import Path
from common import source,settings

DONORS=('sum-bits','dot-product','jacobi-1d')
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('exp','native','out'):p.add_argument(k,type=Path)
    a=p.parse_args();a.seed=1703;a.out.mkdir(parents=True,exist_ok=False);data={}
    for name in DONORS:
        prog,plans,req=source.common.config(a,name)
        with source.base.session(a.exp/'compact-vanilla-20261121/vanilla',prog) as get:gold=get({})
        with source.base.session(a.native,prog,plans) as get:
            v=get(dict(settings(req),union_locator={'mode':1}))
        assert v['state_sha']==gold['state_sha'] and v['runs']==gold['runs'] and v['multi']['total_rhs']==gold['rhs_count']
        d=v['union_locator'];assert d['features'] and d['stats']['applied']==0
        data[name]=dict(graph=v['state_sha'],rhs=gold['rhs_count'],features=d['features'],unions=d['stats']['unions'])
        (a.out/'donors.json').write_text(json.dumps(data,separators=(',',':'))+'\n')
        print(name,len(d['features']),sum(a[1][1] for a in d['features']),flush=True)
