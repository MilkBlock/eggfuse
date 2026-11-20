"""Equal-update contextual bandit policies trained on paired native allocation rewards."""
import argparse
import json
from pathlib import Path
import torch
from collect import DIVERSITY,SYNTHETIC

def fit(a):
    torch.set_num_threads(1);a.out.mkdir(parents=True,exist_ok=False)
    data=json.loads(a.data.read_bytes())
    assert {r['family'] for r in data}==set(DIVERSITY+SYNTHETIC)
    pools={}
    for group in ('workload','synthetic'):
        rows=[r for r in data if r['eligible'] and r['group']==group]
        x=torch.tensor([r['x'] for r in rows],dtype=torch.float64)/8.
        y=torch.tensor([r['saved_bytes'] for r in rows],dtype=torch.float64)/256.
        pools[group]=(x,y)
    pools["pooled"]=tuple(torch.cat(tensors) for tensors in zip(pools["synthetic"],pools["workload"]))
    policies={}
    for name,first,second in [('real','workload','workload'),('synthetic','synthetic','synthetic'),
                              ('mixed','synthetic','workload'),('replay','pooled','pooled'),('regression','pooled','pooled')]:
        w=torch.zeros(8,requires_grad=True,dtype=torch.float64)
        b=torch.zeros((),requires_grad=True,dtype=torch.float64)
        opt=torch.optim.Adam([w,b],lr=.04)
        for group in (first,second):
            x,y=pools[group]
            for _ in range(80):
                # Keep has reward zero; the exact expected paired advantage is p(compose)*bytes saved.
                z=x@w+b
                if name=='regression':
                    task_loss=(z-y).square().mean()
                else:
                    task_loss=-(torch.sigmoid(z)*y).mean()
                loss=task_loss+.001*(w.square().mean()+b.square())
                opt.zero_grad();loss.backward();opt.step()
        # A dyadic export makes scores exact across native/Python JSON parsers.
        def export(tensor):
            return torch.round(tensor.detach()*4096)/4096
        policies[name]=dict(weights=export(w/8).tolist(),intercept=export(b).item())
        (a.out/(name+'.json')).write_text(json.dumps(policies[name],indent=1)+'\n')
    (a.out/'policies.json').write_text(json.dumps(policies,indent=1)+'\n')
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('data','out'):p.add_argument(k,type=Path)
    fit(p.parse_args())
