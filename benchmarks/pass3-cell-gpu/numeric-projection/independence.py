"""Close ordinary residual matching only in the recognized numeric domain; retain ordinary unrelated rules."""
import argparse,json
from pathlib import Path
import numpy as np
from study import analyze,inputs,read,plan,specialize


def evaluate(a):
    a.out.mkdir(parents=True,exist_ok=False);results={}
    for case in ('sum-bits','dot-product'):
        im,program,gold=inputs(a.corpus,a.ref,case);rules=plan(program,im);ing=read(im/'ingress.json')
        d=read(program)['recipe']['rules']
        for seed in (1703,1709):
            model=read(a.model/f'model-{seed}.json')
            for mode in ('structural','predict','wrong'):
                fn=specialize(rules,ing,model,mode,1,domain_only=True)
                dest=a.out/f'{case}-{seed}-{mode}'
                fn(im/'device.json',a.reader,a.ref/'ports-1703.pt',2048,2,dest)
                report,_,_=analyze(dest,rules,d)
                with np.load(dest/'output.npz') as now,np.load(gold/'output.npz') as source:
                    first=next((i+1 for i,(x,y) in enumerate(zip(now['runs'],source['runs'])) if not np.array_equal(x,y)),None)
                assert report['all'].get('admitted',0)==report['all'].get('total',0)
                if mode=='wrong':assert report['all'].get('total',0)==0
                results[f'{case}/{seed}/{mode}']=dict(first_divergence=first,domain_committed=report['all'].get('total',0),
                                                       concat_committed=report.get('concat',{}).get('total',0))
                (a.out/'results.json').write_text(json.dumps(results,indent=1)+'\n')
                print(case,seed,mode,results[f'{case}/{seed}/{mode}'],flush=True)


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    for k in ('corpus','ref','reader','model','out'):ap.add_argument(k,type=Path)
    evaluate(ap.parse_args())
