"""Paired trials with identical instance membership; factor out directory word scanning."""
import argparse
from pathlib import Path
from collect import read
from experiment import study,write

def main(a):
    a.out.mkdir(parents=True,exist_ok=False)
    f=read(a.catalog)
    library=f['catalogs'][f['chosen']]
    arms={'row':(library,4,3),'instance':(library,2,3),'mask':(library,3,3),
          'row-sparse':(library,4,3,True),'mask-sparse':(library,3,3,True)}
    report={}
    for n,c in read(a.corpus/'collection.json').items():
        if c['split']=='train':continue
        result=study(n,arms,a,a.out/n,10)
        base=result['row']
        for k,r in result.items():
            assert all(r[key]==base[key] for key in ('instances','readers','runs','collisions','key_probes','collision_tests')),(n,k,r,base)
        for k in ('row','mask'):
            assert result[k]['notifications']==result[k+'-sparse']['notifications']
            assert result[k]['repair_rows']==result[k+'-sparse']['repair_rows']
        report[n]=result
        write(a.out/'results.json',report)
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('corpus','reference','weights','catalog','out'):p.add_argument(k,type=Path)
    main(p.parse_args())
