"""Supply wrong but in-range, correctly typed references by reversing one learned output head."""
import argparse
import copy
import json
from pathlib import Path
import numpy as np
from native_study import cli,read,write,inputs,schemas,forest_policy,semantics


def main(a):
    a.out.mkdir(parents=True,exist_ok=False);results={}
    for case in ('sum-bits','dot-product','gemm-bias-relu','stable-argmax'):
        directory=a.anchors if case in ('sum-bits','dot-product') else a.heldout
        gold=a.gold/f'{case}-native-reference'
        if not gold.is_dir():gold=directory/f'{case}-native-reference'
        image,source,_=inputs(a.corpus,a.ref,case)
        p=forest_policy.packet(image,source);layouts,ids=schemas(image,source,p)
        for seed in (1703,1709):
            header=None
            original=read(directory/f'{case}-{seed}-weights.json')
            truth,_,base,_=semantics(directory/f'{case}-{seed}-boundary',gold,True)
            header=truth['neural_policy']['certificate_sha256']
            for shape,outidx in [('valid-wrong-ref',0),('valid-wrong-copy',1)]:
                weights=copy.deepcopy(original);h=weights['variable']
                h['read'][outidx]=[-v for v in h['read'][outidx]];h['out_bias'][outidx]*=-1
                weights_path=a.out/f'{case}-{seed}-{shape}-weights.json';write(weights_path,weights)
                config=read(directory/f"{case}-{seed}-{'all' if outidx==0 else 'fixed6'}-plan.json")
                config['variable']['capacity']=max(t['width'] for t in layouts)
                plan=a.out/f'{case}-{seed}-{shape}-plan.json';write(plan,config)
                dest=a.out/f'{case}-{seed}-{shape}'
                cli(a.build/'runtime',source,weights_path,plan,dest)
                report,actual,winners,_=semantics(dest,gold,True)
                assert report['neural_policy']['certificate_sha256']==header
                ports=actual['ports'];refs,copies=ports['refs'],ports['copies'];damaged=0;equal=0
                faults=np.asarray(ports['faults'])
                for id in base:
                    t=layouts[ids[id]];start=ports['starts'][id]
                    target=[f['address'] for f in t['logical']]
                    chosen=(refs if outidx==0 else copies)[start:start+t['width']]
                    for j,address in enumerate(chosen):
                        assert any(v['address']==address and v['sort']==t['logical'][j]['sort'] for v in t['fields'])
                    if chosen!=target:
                        damaged+=1
                        if outidx==0:assert id not in winners
                        elif id in winners:equal+=1
                assert set(winners)<=set(base) and not ports['overflow']
                results[f'{case}/{seed}/{shape}']=dict(reference=len(base),won=len(winners),different_live_expression=damaged,
                   changed_expression_same_typed_value=equal,undetected_wrong_reference=0 if outidx==0 else None,
                   exact_residual=actual['rhs']-len(actual['static'])-len(winners),source_aligned=True,
                   wrong_members=int((faults[:,0]>0).sum()),wrong_columns=int((faults[:,1]>0).sum()),wrong_values=int((faults[:,2]>0).sum()))
                (a.out/'results.json').write_text(json.dumps(results,indent=1)+'\n')
                print(case,seed,shape,damaged,len(winners),equal,flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('corpus','ref','build','gold','anchors','heldout','out'):p.add_argument(k,type=Path)
    main(p.parse_args())
