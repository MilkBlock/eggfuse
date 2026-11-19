import argparse
import json
from pathlib import Path
from statistics import median
from time import perf_counter_ns

import numpy as np
import torch
from integral import MODES,dataset,study,device,load_producer,upload,device_plan,ingress,run


@torch.inference_mode()
def measure(root,producers):
    dev=device();templates,_,_,schema=study();times={}
    folder=root/'traces';folder.mkdir(parents=True,exist_ok=True)
    good=('source','primary','integral','learned_integral','stable_integral')
    for seed in (1703,1709):
        model=load_producer(schema,seed,producers,dev)
        for t in templates:
            name=t['id'];held=t['split']=='heldout'
            if not held and name not in ('rule-266','rule-267','rule-580'):continue
            panel='heldout' if held else 'secondary'
            table=model.encoder.encode_bank(schema.bank(t,'pairwise',dev));plan=device_plan(name,dev)
            d=dataset('test',t);x=upload(d,slice(None),dev);expected={}
            for mode in MODES:
                first,inputs,admit=ingress(model,x,table,mode)
                arena,frames=run(x,plan,inputs,admit,mode,True)
                data={f'{s}_{k}':v.cpu().numpy() for s,fr in enumerate(frames) for k,v in fr.items()}
                data.update({f'first_{k}':first[k].cpu().numpy() for k in ('active','rows','pointers')})
                data['admission']=admit.cpu().numpy()
                np.savez_compressed(folder/f'{name}-{seed}-{mode}.npz',**data)
                expected[mode]=data['2_pub']
            ids=np.random.default_rng(1818).permutation(len(x[0]))[:20]
            for j,i in enumerate([*ids[:3],*ids]):
                for mode in good[j%len(good):]+good[:j%len(good)]:
                    one=upload(d,slice(i,i+1),dev)
                    _,inputs,admit=ingress(model,one,table,mode)
                    torch.mps.synchronize()
                    begin=perf_counter_ns()
                    arena,_=run(one,plan,inputs,admit,mode);torch.mps.synchronize()
                    schedule_ms=(perf_counter_ns()-begin)/1e6
                    begin=perf_counter_ns()
                    one=upload(d,slice(i,i+1),dev)
                    _,inputs,admit=ingress(model,one,table,mode)
                    arena,_=run(one,plan,inputs,admit,mode);torch.mps.synchronize()
                    whole_ms=(perf_counter_ns()-begin)/1e6
                    np.testing.assert_array_equal(arena.pub.cpu().numpy()[0],expected[mode][i])
                    if j>=3:
                        for scope,ms in [('schedule',schedule_ms),('whole',whole_ms)]:
                            times.setdefault(f'{panel}/{seed}/{mode}/{scope}',[]).append(ms)
            print(seed,name,flush=True)
    (root/'timing.json').write_text(json.dumps(dict(samples=times,medians={k:median(v) for k,v in times.items()}))+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('root',type=Path);p.add_argument('producers',type=Path)
    a=p.parse_args();measure(a.root,a.producers)
