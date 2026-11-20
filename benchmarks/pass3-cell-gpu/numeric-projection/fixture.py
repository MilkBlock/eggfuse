"""Execute two deliberate min conflicts through a source-compiled fixture, then read via the visible fact."""
import argparse,json,subprocess,sys
from pathlib import Path
import numpy as np
from adapter import specialize
from plan import plan,read
from study import analyze
GPU=Path(__file__).resolve().parents[1];sys.path.insert(0,str(GPU/'set-memory'))
from check import check


def trial(a):
    a.out.mkdir(parents=True,exist_ok=False)
    # Reference: independent CPU audit of real source execution including its effective writes.
    reference=a.out/'native'
    check(a.program,reference,a.reader,a.ports,a.runtime,16)
    image=reference/'input'
    rules=plan(a.program,image);ingress=read(image/'ingress.json');definition=read(a.program)['recipe']['rules']
    model=read(a.model/'model-1703.json')
    # Fixture rule ids differ from training. Use coefficients of the same compiled sum/copy expression shape.
    model={**model,'numeric':{},'thresholds':{}}
    # This fixture deliberately admits all structurally matching paths to exercise each arithmetic counterexample.
    # Report its coverage separately from the learned selector's real-workload outputs.
    model['selector']=[0.]*7+[1.]
    result={}
    for name,mode,direct in [('point','structural',0),('visible','structural',1),('wrong-field','structural',2),('predicted','predict',1)]:
        fn=specialize(rules,ingress,model,mode,direct)
        dest=a.out/name
        fn(image/'device.json',a.reader,a.ports,16,2,dest)
        from capture import verify
        verify(dest,reference/'gpu',image)
        stats,_,_=analyze(dest,rules,definition)
        with np.load(dest/'numeric.npz') as z:
            out=z['outcomes'];port_map=z['input_ports']
            pairs=[];consumers=[];predictions=[]
            for ordinal,o in enumerate(out,1):
                if not o[0]:continue
                if any(r['rule']==o[1] and len(r['slots'])==2 for r in rules):
                    pairs.append((int(o[3]),int(o[4]),int(o[5]),bool(o[6])))
                    if mode=='predict':predictions.append([int(o[12]),int(o[4]),int(o[8])])
                elif o[7]:
                    parents=[int(k) for k in port_map[o[7]-1,:,1] if k]
                    consumers.append(dict(rhs=ordinal,visible=int(o[4]),parents=parents))
                    assert any(out[k-1,5]==o[4] for k in parents)
            expected=([(30000000,16777223,16777223,True),(30000000,16777224,16777224,True)] if a.precision
                      else [(9,11,9,False),(15,11,11,True)])
            assert sorted(pairs)==expected,pairs
            assert sorted(x['visible'] for x in consumers)==sorted(x[2] for x in expected)
            if a.precision and mode=='predict':
                assert len(set(q[0] for q in predictions))==1 and any(q[2]==2 for q in predictions)
            if not a.precision and name=='wrong-field':assert sum(stats['ports'][2:])>0
            result[name]=dict(numeric_prediction=predictions,writes=pairs,consumer_visible_ports=consumers,port_counts=stats['ports'],source_checked=True)
    (a.out/'results.json').write_text(json.dumps(result,indent=1)+'\n')
    print(result,flush=True)


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    for k in ('program','reader','ports','runtime','model','out'):ap.add_argument(k,type=Path)
    ap.add_argument('--precision',action='store_true')
    trial(ap.parse_args())
