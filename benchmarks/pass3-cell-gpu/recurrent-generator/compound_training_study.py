"""Change the root training target and measure child completions on the same full schedule."""
import argparse
import json
from pathlib import Path
from statistics import median
from time import perf_counter_ns

import numpy as np
import torch

from capture import execute,inputs,load_catalog,read,verify
from compound_model import pair_joins
from compound_study import metrics
from feedback_study import bind_session


def study(args):
    donor=args.ref/'sum-bits/program.json';joins=pair_joins(read(donor))
    args.out.mkdir(parents=True,exist_ok=False)
    report={}
    for case in ('sum-bits','dot-product','gemm-bias-relu','stable-argmax'):
        image,program,gold=inputs(args.corpus,args.ref,case)
        entries=load_catalog(image,program,donor)
        for seed in (1703,1709):
            arms={};sessions={}
            for name,training in [('leaf',args.leaf),('continuation',args.continuation)]:
                model=read(training/f'train-{seed}/policy.json')
                assert model.get('root_target','continuation')==name and list(map(list,joins))==model['joins']
                folder=args.out/f'{case}-{seed}-{name}'
                cfg=dict(catalog=entries,weights=model['roots'],rows=2,hidden=8,ranks=8,waves=2,
                         compound=dict(joins=joins,child=model['child'],batch=True))
                execute(image/'device.json',args.reader,args.ref/'ports-1703.pt',2048,2,folder,
                        neural=cfg,measure_resident=bind_session(sessions,name))
                verify(folder,gold,image)
                arms[name]=metrics(folder)
                arms[name]['ms']=[]
            for t in range(6):
                for name in (('leaf','continuation') if t%2==0 else ('continuation','leaf')):
                    reset,infer,buf=sessions[name];reset();torch.mps.synchronize()
                    start=perf_counter_ns();infer();torch.mps.synchronize()
                    arms[name]['ms'].append((perf_counter_ns()-start)/1e6)
                    state=buf['state'].cpu().tolist()
                    assert state[7] and not state[5] and state[9]==arms[name]['rhs']
            for arm in arms.values():arm['median_ms']=median(arm['ms'])
            report[f'{case}/{seed}']=arms
            (args.out/'results.json').write_text(json.dumps(report,indent=1)+'\n')
            sessions.clear()

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for k in ('corpus','ref','reader','leaf','continuation','out'):parser.add_argument(k,type=Path)
    with torch.inference_mode():study(parser.parse_args())
