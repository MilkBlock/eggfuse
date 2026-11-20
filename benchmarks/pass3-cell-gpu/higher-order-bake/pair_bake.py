"""Learn sibling rules sharing the entire sealed pointer prefix and one complementary i64 condition."""
import argparse,json
from collections import Counter
from pathlib import Path
import sys
import numpy as np

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'ordinary-witness'))
from plan import sealed_plans


def discover(image):
    p=json.loads((image/'ingress.json').read_bytes());plans=sealed_plans(image)
    groups={}
    for rid,(r,plan) in enumerate(zip(p['rules'],plans)):
        if not plan or not r['semi']:continue
        ins=plan['ins'];tail=[i for i,pick,_ in ins if not pick]
        if len(tail)!=1 or ins[-1][0]!=tail[0]:continue
        idx=tail[0];op,args=r['q'][idx]
        if op not in ('<','>') or len(args)!=3 or any(a<0 for a in args):continue
        # Every source-typed independent row is selected before the guard.
        if not all(isinstance(r['q'][i][0],int) for i,pick,_ in ins if pick):continue
        q=list(r['q']);q[idx]=['cmp',args]
        sets=tuple(sorted(k for k,v in p['sets'].items() if rid in v))
        key=json.dumps([plan,q,r['inputs'],sets],sort_keys=True)
        groups.setdefault(key,{}).setdefault(op,[]).append(rid)
    return [(v['<'][0],v['>'][0]) for v in groups.values() if len(v.get('<',[]))==len(v.get('>',[]))==1]


def main(a):
    counts={}
    for n,c in json.loads((a.corpus/'collection.json').read_bytes()).items():
        if c['split']!='train':continue
        pairs=discover(a.corpus/n/'input')
        with np.load(a.corpus/n/'device/output.npz') as z:ordinal=Counter(map(int,z['rhs'][:,1]))
        for l,r in pairs:counts.setdefault((l,r),{})[n]=[ordinal[l],ordinal[r]]
    selected=[list(k) for k,v in counts.items() if sum(x+y>0 for x,y in v.values())>=2 and sum(x for x,y in v.values()) and sum(y for x,y in v.values())]
    data=dict(pairs=sorted(selected),training={str(k):v for k,v in counts.items()})
    a.out.write_text(json.dumps(data,indent=1)+'\n');print(data,flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('corpus',type=Path);p.add_argument('out',type=Path);main(p.parse_args())
