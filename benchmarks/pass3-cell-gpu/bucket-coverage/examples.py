"""Locate two distinct same-key source winners when a neural seed's page omits its sibling."""
import argparse
from collections import Counter
import json
from pathlib import Path
import numpy as np
from smoke import inputs,load_catalog,read
from adapter import plans


def examples(families,ref,capture,results):
    report={}
    for case in ('sum-bits','dot-product'):
        image,program,_=inputs(families,ref,case);entries=load_catalog(image,program,ref/'sum-bits/program.json')
        packet=read(image/'ingress.json');masks,_=plans(image,entries,'partial')
        with np.load(capture/case/'neural-inputs.npz') as f,np.load(capture/case/'output.npz') as g:
            pivots=f['pivot'];rhs=g['rhs']
        by_source={(int(ev[0]),int(ev[1]),int(p)-1,int(ev[3])):(i+1,ev) for i,(ev,p) in enumerate(zip(rhs,pivots)) if p}
        with np.load(results/f'{case}-1703-partial-range-omit'/'buckets.npz') as z:log=z['log']
        found=[]
        for t,lane in zip(*np.where(log[:,:,4]==5)):
            data=log[t,lane];leaf=int(data[0])-1;rule,pivot,_,table=entries[leaf]
            seed,omitted=map(int,(data[1]-1,data[7]-1));key=(int(t)+1,rule,pivot)
            if (*key,seed) not in by_source or (*key,omitted) not in by_source:continue
            # Preserve actual source ordinals and inputs; two logical winners must differ.
            r=packet['rules'][rule]; witness=[]
            for row in (seed,omitted):
                ordinal,event=by_source[(*key,row)]
                vals=list(map(int,event[4:4+len(r['inputs'])]))
                bound=dict(zip(r['inputs'],vals))
                fields=r['q'][pivot][1]
                cols=[i for i in range(len(fields)) if masks[leaf]>>i&1]
                if not all(fields[i] in bound for i in cols):break
                witness.append(dict(row=row,rhs_ordinal=ordinal,inputs=vals,projected_key=[bound[fields[i]] for i in cols]))
            if len(witness)!=2:continue
            assert witness[0]['rhs_ordinal']!=witness[1]['rhs_ordinal'] and witness[0]['projected_key']==witness[1]['projected_key']
            found.append(dict(run=int(t)+1,leaf=leaf,rule=rule,pivot=pivot,table=packet['tables'][table]['name'],
                              bucket_extent=int(data[5]),key_columns=cols,neural_seed=witness[0],omitted=witness[1]))
            break
        assert found,case
        categories={}
        for seed in (1703,1709):
            path=results/f'{case}-{seed}-partial-range-intact'/'buckets.npz'
            with np.load(path) as z:normal=z['log']
            counts=Counter()
            for lid in normal[:,:,0][normal[:,:,4]==3]:
                leaf=int(lid)-1
                rid,pivot,_,_=entries[leaf];query=packet['rules'][rid]['q']
                fields=query[pivot][1];arity=len(fields)-1
                other={s for i,(table,args) in enumerate(query) if i!=pivot and isinstance(table,int) for s in args}
                shared=sum(1<<i for i,s in enumerate(fields) if s in other or s<0)
                full=(1<<arity)-1
                counts['source_shared_or_constant' if shared and (shared&full)!=full else
                       'leading_input_projection' if arity>1 else 'reverse_result_projection']+=1
            categories[str(seed)]=dict(counts)
        report[case]=dict(omitted_same_key_winner=found[0],intact_partial_key_claims=categories)
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('families','ref','capture','results','out'):p.add_argument(k,type=Path)
    a=p.parse_args()
    a.out.write_text(json.dumps(examples(a.families,a.ref,a.capture,a.results),indent=1)+'\n')
