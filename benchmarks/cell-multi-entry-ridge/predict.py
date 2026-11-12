"""Read-only completion candidate prediction from a real runtime entry export."""
import argparse
import json
from pathlib import Path
import numpy as np
from dataset import canonical,extension,digest
from train import Encoder,features,field_moments


def main():
    p=argparse.ArgumentParser();p.add_argument('--model',type=Path,required=True)
    p.add_argument('--catalog',type=Path,required=True);p.add_argument('--graph',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--top-k',type=int,default=3)
    args=p.parse_args();weights=dict(np.load(args.model));catalog=json.loads(args.catalog.read_text())
    if str(weights['catalog_sha256'])!=digest(catalog):raise ValueError('model/catalog digest mismatch')
    if str(weights['encoder_schema'])!='entry-projection/v1':raise ValueError('unsupported encoder')
    if set(str(v) for v in weights['labels'])!=set(catalog):raise ValueError('model/catalog labels differ')
    if args.top_k<=0:raise ValueError('top-k must be positive')
    entry,runtime_to_entry=canonical(json.loads(args.graph.read_text()))
    vectors=[Encoder(int(seed))(entry) for seed in weights['encoder_seeds']]
    if bool(weights['field_moments']):vectors.append(field_moments(entry))
    x=(np.concatenate(vectors)[None,:]-weights['mean'])/weights['scale']
    ff=features(x,str(weights['kind']),weights['centers'],weights['projection'],weights['bias'])
    scores=((ff@weights['w']+weights['b'])@weights['codes'].T)[0]
    candidates=[]
    for choice in np.argsort(scores)[::-1][:args.top_k]:
        key=str(weights['labels'][choice]);completion=catalog[key];mapping=extension(entry,completion)
        candidates.append(dict(completion=key,score=float(scores[choice]),entry_to_completion=mapping,
                               necessary_containment_pass=mapping is not None,
                               completion_graph=completion,authorized_for_execution=False))
    result=dict(candidates=candidates,runtime_to_entry=runtime_to_entry,
                scope='Learned candidate completion and exact input embedding, not a derivability certificate or graph mutation')
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='candidates'}))
    print(json.dumps([{k:v for k,v in c.items() if k!='completion_graph'} for c in candidates]))


if __name__=='__main__':main()
