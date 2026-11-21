"""Train marginal utility of attaching the statically verified candidate root, with no test traces."""
import argparse,json
from pathlib import Path
import torch


def train(source,out):
    data=json.loads(source.read_bytes());assert set(data)=={'sum-bits','dot-product','jacobi-1d'}
    records=[(f,c) for r in data.values() for f,c in r['arms']['all']['features'] if c['admissible']]
    x=torch.tensor([f+[1] for f,_ in records],dtype=torch.float64)
    weights=torch.tensor([c['admissible'] for _,c in records],dtype=torch.float64)
    profiles={}
    for key,field in [('learned-hits','either_valid'),('learned-readers','either_readers')]:
        # One scalar-return regression per candidate side, grouped by identical causal features.
        w=weights/weights.sum()
        reg=torch.eye(x.shape[1],dtype=torch.float64)*.002
        coeffs=[]
        for side in (0,1):
            y=torch.tensor([c[field][side]/c['admissible'] for _,c in records],dtype=torch.float64)
            beta=torch.linalg.solve(x.T@(x*w[:,None])+reg,x.T@(w*y))
            coeffs.extend(beta.tolist())
        profiles[key]=dict(weights=coeffs,examples=int(weights.sum()),distinct=len(records),
                           summed_return=int(sum(sum(c[field]) for _,c in records)))
    out.write_text(json.dumps(profiles,indent=1)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('source',type=Path);p.add_argument('out',type=Path)
    a=p.parse_args();torch.set_num_threads(1);train(a.source,a.out)
