"""Select a recurrent donor shape using only typed donor rules, counts and transportable fingerprints."""
import json
from pathlib import Path
HERE=Path(__file__).resolve().parent

def frozen():
    source=HERE.parent/'strict-composition-opportunities'
    catalog=json.loads((source/'catalog.json').read_bytes())['pairs']
    hashes=json.loads((source/'shape-counts.json').read_bytes())['rule_fingerprints']['dot-product']
    options=[]
    for key,r in catalog.items():
        pr,ch,offset,wiring,count=r['shape']
        if count==2 and offset==1 and all(r['donor_counts']) and wiring[0][1]==wiring[1][1]=='op' and wiring[1][2]<wiring[0][2]:
            options.append((sum(r['donor_counts']),key,r))
    n,key,r=max(options,key=lambda x:(x[0],x[1]))
    pr,ch,offset,wiring,_=r['shape']
    return dict(pair_shape=key,producer=hashes[pr],consumer=hashes[ch],ops=[w[2] for w in wiring],distance=offset,
                donor_counts=r['donor_counts'],donors=['dot-product','jacobi-1d'])
if __name__=='__main__':
    (HERE/'template.json').write_text(json.dumps(frozen(),indent=1)+'\n')
