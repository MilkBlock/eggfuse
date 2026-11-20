"""Independently autoregress from zeros on the audited causal input stream and compare to Metal."""
import argparse,json
from pathlib import Path
import numpy as np
import torch
from model import Actor,HIDDEN,ROWS

@torch.inference_mode()
def check(capture,trial,output):
    torch.set_num_threads(1);results={}
    for label,arms in json.loads((trial/'results.json').read_bytes()).items():
        n,seed=label.split('/')
        net=Actor();net.load_state_dict(torch.load(capture/f'train-{seed}/actor.pt',map_location='cpu',weights_only=True));net.eval()
        with np.load(capture/n/'neural-inputs.npz') as z:features=torch.tensor(z['features'])
        results[label]={}
        for variant in ('intact','zero-latent','swap-latent'):
            with np.load(trial/f'{n}-{seed}-{variant}/neural-output.npz') as z:expected=z['raw']
            previous=torch.zeros(1,ROWS,HIDDEN+4);maximum=0;discrete=0
            for t,x in enumerate(features):
                _,previous=net.step(x[None],previous,variant)
                values=previous[0].numpy()
                maximum=max(maximum,float(np.max(np.abs(values[:,:HIDDEN]-expected[t,:,:HIDDEN]))))
                discrete+=int((values[:,HIDDEN:]!=expected[t,:,HIDDEN:]).any(-1).sum())
            results[label][variant]=dict(discrete_differences=discrete,max_latent_difference=maximum,runs=len(features))
            if discrete or maximum>.002:raise ValueError((label,variant,results[label][variant]))
    output.write_text(json.dumps(results,indent=1)+'\n')
if __name__=='__main__':
    p=argparse.ArgumentParser()
    for k in ('capture','trial','output'):p.add_argument(k,type=Path)
    a=p.parse_args();check(a.capture,a.trial,a.output)
