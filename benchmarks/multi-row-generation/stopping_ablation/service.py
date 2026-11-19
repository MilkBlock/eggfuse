"""Preload generated graph inputs; measure only the bounded device schedule."""
import argparse
import json
from pathlib import Path
from statistics import median
import numpy as np
import torch

from measure import LANES,load_gates
from queue_gpu import Queue,device,study,load_producer,dataset,upload,inputs,device_plan


@torch.inference_mode()
def main(root,producers,out):
    dev=device();ts,_,_,schema=study();seed=1703
    model=load_producer(schema,seed,producers,dev);weights,_=load_gates(root,seed,dev)
    report={}
    for t in ts:
        name=t['id']
        if name not in ('rule-134','rule-266'):continue
        d=dataset('test',t);table=model.encoder.encode_bank(schema.bank(t,'pairwise',dev))
        plan=device_plan(name,dev)
        for panel in ('ordinary','late_union'):
            x=upload(d,slice(None),dev)
            _,args=inputs(model,x,table,plan,panel,torch.arange(len(x[0]),device=dev))
            with np.load(root/'traces'/f'{seed}-{name}-{panel}.npz') as archive:
                for batch in (1,128,4096):
                    ix=(np.arange(batch)+6)%len(x[0]);di=torch.as_tensor(ix,device=dev)
                    prepared=(args[0][di],args[1],args[2][di],args[3][di])
                    lanes=('exact','fixed4','fixed8','ledger_guard','blind_guard')
                    samples={key:[] for key in lanes}
                    for j in range(15):
                        for lane in lanes[j%len(lanes):]+lanes[:j%len(lanes)]:
                            mode,k,arm=LANES[lane];q=Queue(batch,plan[3],dev)
                            start=torch.mps.Event(enable_timing=True);end=torch.mps.Event(enable_timing=True)
                            torch.mps.synchronize();start.record()
                            q.advance(prepared,weights[arm],mode,k,48,arm=='blind')
                            end.record();end.synchronize();ms=start.elapsed_time(end)
                            if j>=5:samples[lane].append(ms*1000)
                            np.testing.assert_array_equal(q.state.cpu().numpy(),archive[lane+'_48_state'][ix])
                            np.testing.assert_array_equal(q.visible.cpu().numpy(),archive[lane+'_48_visible'][ix])
                    report[f'{name}/{panel}/{batch}']=dict(samples_us=samples,median_us={k:median(v) for k,v in samples.items()})
    out.write_text(json.dumps(report,indent=1)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for k in ('root','producers','out'):p.add_argument(k,type=Path)
    a=p.parse_args();main(a.root,a.producers,a.out)
