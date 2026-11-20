"""Observe exact post-rebuild visibility for constructor outputs with neural publication evidence."""
import argparse
import json
from pathlib import Path
import numpy as np
from study import engine, inputs, load_catalog, pair_joins, read, replace_once, retirement_executor, verify
from supports import graph


def capture(a):
    a.out.mkdir(parents=True,exist_ok=False)
    record={};donor=a.ref/'sum-bits/program.json'
    for case in ('sum-bits','dot-product','gemm-bias-relu','stable-argmax'):
        image,p,gold=inputs(a.corpus,a.ref,case)
        keys=sorted({tuple(k) for seed in (1703,1709) for k in graph(a,case,seed)[3]})
        source=a.paired/f'{case}-1703-batch'
        with np.load(source/'neural-output.npz') as z:raw=z['raw']
        nruns=len(raw)
        assert len(keys)<(2048-nruns)*4
        model=read(a.training/'train-1703/policy.json')
        cfg=dict(catalog=load_catalog(image,p,donor),rows=2,hidden=8,ranks=8,waves=2,weights=model['roots'],
                 compound=dict(joins=pair_joins(read(donor)),child=model['child'],batch=True,replay=raw))
        captured={}
        def bind(_,buffers,definitions,*unused):
            constants=dict((line.split()[1],int(line.split()[2])) for line in definitions.splitlines()
                           if line.startswith('#define NEURAL_BASE '))
            captured.update(meta=buffers['meta'],offset=constants['NEURAL_BASE']+4*4+4*nruns)
        with retirement_executor(False):
            shader=engine.HERE/'recurrent-generator/compound.metal'
            text=shader.read_text()
            pairs=', '.join(str(v) for run,_,row in keys for v in (run,row))
            text=f'constant int visible_at[]={{{pairs}}};\n'+text
            code=f"""
    // Unused tail beyond the frozen stream's last Run, checked against the allocated slot budget.
    for(int g=0;g<{len(keys)};g++)if(visible_at[2*g]+1==state[3]){{
        int row=visible_at[2*g+1];if(row>=state[0]){{state[5]=29;return;}}
        meta[NEURAL_BASE+4*NEURAL_SLOTS+NEURAL_SLOTS*{nruns}+g]=1+meta[6*row+3];
    }}
"""
            shader.write_text(replace_once(text,'    int live=state[75],keep=0;',code+'    int live=state[75],keep=0;'))
            out=a.out/case
            engine.execute(image/'device.json',a.reader,a.ref/'ports-1703.pt',2048,2,out,neural=cfg,measure_resident=bind)
        verify(out,gold,image)
        meta=captured['meta'];base=captured['offset']
        states=meta.reshape(-1)[base:base+len(keys)].cpu().numpy().copy()
        for i,(boundary,_,row) in enumerate(keys):
            if boundary==nruns:states[i]=1+int(meta.reshape(-1)[6*row+3].cpu())
        assert np.all((states>=1)&(states<=3))
        record[case]=[[*map(int,k),int(s-1)] for k,s in zip(keys,states)]
        (a.out/'results.json').write_text(json.dumps(record,separators=(',',':'))+'\n')
        print(case,len(keys),int((states==1).sum()),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('corpus','ref','reader','training','paired','capture','out'):p.add_argument(name,type=Path)
    capture(p.parse_args())
