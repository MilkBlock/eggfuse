"""Separate statically checkable winners, actual suffix-table checks and unused sealed proposals."""
import argparse
import json
from pathlib import Path
import sys
import numpy as np
from policy import packet
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'recurrent-generator'))
from capture import inputs


def compute(corpus,ref,study):
    result={}
    for label,arms in json.loads((study/'results.json').read_text()).items():
        case,seed=label.split('/');image,program,_=inputs(corpus,ref,case)
        p=packet(image,program);c=p['candidates'];layout=json.loads((image/'device.json').read_text())['layout']
        with np.load(image/'device.npz') as z:rom=z['rom']
        data={}
        for name in ('learned','point','all','none','wrong-parent','no-residual'):
            summary=arms[name]
            with np.load(study/f'{case}-{seed}-{name}'/'forest.npz') as z:audit=z['children']
            won=np.flatnonzero(audit[:,2]);direct=local=lookups=lookup_tokens=0
            for i in won:
                _,_,rid,_,path,*_=c[i]
                if name!='point' and p['projections'][rid]>=0:direct+=1;continue
                n=int(rom[layout['RULE']+7*rid])
                reads=sum(rom[path+4*j]>=0 for j in range(1,n))
                if reads:lookup_tokens+=1;lookups+=int(reads)
                else:local+=1
            assert len(won)==direct+local+lookup_tokens and direct==summary['projection_rhs']
            data[name]=dict(issued=summary['proposals'],global_bad_parent=summary['proposals'] if name=='wrong-parent' else 0,
                            unused=summary['proposals']-len(won),global_conditional_proofs=summary['global_projection_proofs'],
                            globally_projected_winners=direct,local_recheck_winners=local,
                            suffix_lookup_winners=lookup_tokens,suffix_reads_for_winners=lookups,neural_winners=len(won),
                            compiler_root_winners=summary['static_roots'],exact_residual=summary['exact_residual'])
        result[label]=data
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('corpus','ref','study','out'):p.add_argument(k,type=Path)
    a=p.parse_args();a.out.write_text(json.dumps(compute(a.corpus,a.ref,a.study),indent=1)+'\n')
