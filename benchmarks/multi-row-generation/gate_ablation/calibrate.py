"""Select gates using fresh instances of training-family templates only."""
import argparse
import json
from pathlib import Path

import numpy as np
import torch

from gate_model import GateSystem
from gate_data import templates, dataset, _panel, _base_keys, fresh_panel, SEEDS, array_digest
from train_gates import digest, PRICES
from credit_ablation.reward import team_reward
from fit import transfer, device, EClassSchema


def evaluate(model, panels, tables, mode, threshold, dev):
    exact = 0
    counts = np.zeros((2,8), dtype=np.int64)
    graphs = 0
    for tid, d in panels.items():
        st, token, relations = model(*transfer(d, slice(None),dev), tables[tid], mode=mode,
                                     backend='dense',threshold=threshold)
        target=[torch.as_tensor(d[k],device=dev,dtype=torch.long) for k in ('target1','target2')]
        _,comp=team_reward(*st,*target)
        exact += int(comp['E2'].sum().item())
        for s,stage in enumerate(st):
            counts[s] += stage['gate_open'].sum(0).cpu().numpy()
        graphs += len(d['a'])
    return dict(mode=mode, threshold=threshold, exact=exact, graphs=graphs,
                open_slots=int(counts.sum()),slot_frequencies=(counts/graphs).tolist())


def main():
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('parent',type=Path);args=p.parse_args()
    dev=device();ts=templates();train=[t for t in ts if t['split']=='train'];schema=EClassSchema(train)
    panels={t['id']:_panel(t,2304,2312) for t in train}
    # Check that source histories in calibration have not appeared in training or primary test.
    other=set()
    for t in ts:
        if t['split']=='train':other.update(_base_keys(dataset('train',t)))
        if t['split']=='heldout':other.update(_base_keys(fresh_panel(t)))
    for d in panels.values():assert not _base_keys(d)&other
    entries={}
    for seed in SEEDS:
        base=args.parent/f'supervised-{seed}'/'final.pt'
        for arm in PRICES:
            name=f'{arm}-{seed}';folder=args.root/name
            meta=json.loads((folder/'fit.json').read_text())
            assert meta['parent_sha256']==digest(base) and meta['gates_sha256']==digest(folder/'gates.pt')
            m=GateSystem(schema,seed).load_actor(torch.load(base,map_location='cpu',weights_only=True))
            m.gates.load_state_dict(torch.load(folder/'gates.pt',map_location='cpu',weights_only=True));m.to(dev).eval()
            with torch.inference_mode():
                tables={t['id']:m.encoder.frozen_bank(schema.bank(t,'pairwise',dev)) for t in train}
                baseline=evaluate(m,panels,tables,'all',.5,dev)
                cases=[baseline]+[evaluate(m,panels,tables,'learned',x,dev) for x in (.05,.15,.30,.50,.70,.85,.95)]
            selected=min((e for e in cases if e['exact']>=baseline['exact']),
                         key=lambda e:(e['open_slots'],-e['exact'],e['threshold']))
            masks=[]
            for frequencies in selected['slot_frequencies']:
                k=int(np.floor(sum(frequencies)+.5));order=np.argsort(-np.asarray(frequencies),kind='stable')[:k]
                mask=np.zeros(8,dtype=int);mask[order]=1;masks.append(mask.tolist())
            entries[name]=dict(mode=selected['mode'],threshold=selected['threshold'],mask=masks,
                               selected=selected,baseline=baseline,candidates=cases,fit_sha256=digest(folder/'fit.json'))
            print(name,baseline['exact'],selected['mode'],selected['threshold'],selected['exact'],selected['open_slots'],flush=True)
    result=dict(entries=entries,group_range=[2304,2312],panel_hashes={k:array_digest(d) for k,d in panels.items()},overlap_training_or_primary_base=0)
    (args.root/'calibration.json').write_text(json.dumps(result,indent=2)+'\n')

if __name__=='__main__':main()
