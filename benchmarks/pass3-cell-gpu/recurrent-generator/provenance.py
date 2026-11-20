"""Check each credited neural row against the actual global RHS ordinal and raw emitted anchor."""
import argparse,json
from pathlib import Path
import numpy as np
from capture import inputs,load_catalog,read
from evaluate import run_case

def validate(dest,entries):
    with np.load(dest/'neural-output.npz') as net,np.load(dest/'output.npz') as graph:
        order=net['rhs_ordinal']
        assert np.array_equal(order!=0,net['committed'])
        positive=order[order>0];assert len(np.unique(positive))==len(positive)
        for run,lane in zip(*np.nonzero(order)):
            token=net['raw'][run,lane]
            leaf,anchor,rank,active=map(int,token[-4:])
            assert active and rank>0 and net['verdict'][run,lane,0]==1
            event=graph['rhs'][order[run,lane]-1]
            assert int(event[0])==run+1 and int(event[1])==entries[leaf-1][0] and int(event[3])==anchor-1
        return len(positive)
if __name__=='__main__':
    p=argparse.ArgumentParser()
    for k in ('corpus','ref','reader','capture','study','out'):p.add_argument(k,type=Path)
    a=p.parse_args();a.out.mkdir(parents=True,exist_ok=False);result={}
    for n in ('sum-bits','dot-product','gemm-bias-relu','stable-argmax'):
        image,program,_=inputs(a.corpus,a.ref,n);cat=load_catalog(image,program,a.ref/'sum-bits/program.json')
        for seed in (1703,1709):
            dest=a.out/f'{n}-{seed}'
            report=run_case(a.corpus,a.ref,a.reader,a.capture/f'train-{seed}/actor.json',n,dest,'intact')
            won=validate(dest,cat)
            ref=read(a.study/'results.json')[f'{n}/{seed}']['intact']
            assert won==report['won']==ref['won']
            with np.load(dest/'neural-output.npz') as now,np.load(a.study/f'{n}-{seed}-intact/neural-output.npz') as old:
                np.testing.assert_array_equal(now['raw'],old['raw']);np.testing.assert_array_equal(now['verdict'],old['verdict'])
            result[f'{n}/{seed}']=dict(unique_rhs_ordinals=won,source_rule_and_anchor_agree=True,
                                        checked_runs=report['runs'])
            (a.out/'results.json').write_text(json.dumps(result,indent=1)+'\n')
