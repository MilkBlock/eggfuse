"""Retain the exact prior round's physical pairs when adding a second reader."""
import argparse
from pathlib import Path
import numpy as np
from collect import read
from experiment import study,write

def main(a):
    a.out.mkdir(parents=True,exist_ok=False)
    f=read(a.catalog);library=f['catalogs'][f['chosen']]
    arms={'producer':(library,3,1,False,True,True),'one':(library,3,2,False,True,True),
          'greedy-two':(library,3,3,False,False,True),'nested-two':(library,3,3,False,True,True)}
    report={}
    for n,c in read(a.corpus/'collection.json').items():
        if c['split']=='train':continue
        folder=a.out/n
        measurements=study(n,arms,a,folder,8)
        with np.load(folder/'one-audit/owners.npz') as base:
            for k in ('greedy-two','nested-two'):
                with np.load(folder/(k+'-audit')/'owners.npz') as expanded:
                    old=base['first']
                    retained=np.count_nonzero((old!=0)&(old==expanded['first']))
                    measurements[k]['original_pairs']=int(np.count_nonzero(old))
                    measurements[k]['retained_original_pairs']=int(retained)
                    if k=='nested-two':np.testing.assert_array_equal(old,expanded['first'])
        for m in measurements.values():
            assert m['collisions']==measurements['producer']['collisions']
            assert m['key_probes']==measurements['producer']['key_probes']
        report[n]=measurements;write(a.out/'results.json',report)
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('corpus','reference','weights','catalog','out'):p.add_argument(k,type=Path)
    main(p.parse_args())
