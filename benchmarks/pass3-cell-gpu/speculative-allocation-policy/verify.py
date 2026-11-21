import json,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'pair-source-frontier'))
from evidence import checked

def verify(folder):
    read=lambda f:json.loads((folder/f).read_bytes())
    d=read('donors.json');w=read('policy.json');assert set(d)==set(w['donors'])=={'sum-bits','dot-product','jacobi-1d'}
    for t in ('run','page'):
        truth=0
        for case,row in d.items():
            a=row[t];assert sum(n for x,o,wins,f,n in a['events'])==a['total']
            assert sum(f*n for x,o,wins,f,n in a['events'])==a['fresh']>0
            assert all(len(x)==8 and x[0]==1 and (t=='page' or x[7]==0) and wins<=o for x,o,wins,f,n in a['events'])
            truth+=a['fresh']
        assert all(len(v['weights'])==8 and v['truth']==truth for v in w['models'][t].values())
    data=checked(folder,('results.json',),('conjugate-gradient','3mm'))
    for case,arms in data.items():
        for k,q in arms.items():
            if k in ('off','vanilla'):continue
            c=q['storage']['counts']
            assert c['requested']>=c['granted']==c['used']+c['unused'] and c['fresh']==q['root_allocated']>0
            if k=='run-capacity':assert c['preconstructed']==0
            else:assert c['preconstructed']==c['granted'] and c['used']==c['payload_identity']>0
        p,n=[arms[k]['storage']['counts'] for k in ('run-pool','run-named')]
        assert p['granted']==n['granted'] and p['used']>=n['used']
    return data
if __name__=='__main__':print('Verified donor-only trained Run/page forecasts and real source/physical admissions on',len(verify(HERE)),'held-out programs')
