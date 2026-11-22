"""Train finite release heads on synthetic bits and compare both readers on frozen token history."""
import argparse
from collections import Counter, defaultdict
from itertools import product
import json
from pathlib import Path

import torch
from joined_history import snapshot_audit


def fit(count, label):
    features = torch.tensor(list(product((0.,1.), repeat=count)))
    labels = torch.tensor([float(label(*row)) for row in features.tolist()])
    head = torch.nn.Linear(count, 1)
    torch.nn.init.zeros_(head.weight)
    torch.nn.init.zeros_(head.bias)
    opt = torch.optim.Adam(head.parameters(), lr=.1)
    for _ in range(180):
        opt.zero_grad()
        loss = torch.nn.functional.binary_cross_entropy_with_logits(head(features)[:,0], labels)
        loss.backward()
        opt.step()
    weights = head.weight.detach().flatten()
    bias = head.bias.detach()[0]
    if not torch.equal((features @ weights + bias > 0), labels.bool()):
        raise ValueError("release head failed generated truth table")
    return weights, bias


def decode(mode, first, pair, left, right, path, fresh, loop_new):
    indices = torch.arange(right.numel(),device=right.device)
    if mode == 'conditional':
        features = torch.stack((path,fresh | loop_new.any()),1).float()
        indices = indices[features @ first[0]+first[1]>0]
        right, path, fresh = right[indices], path[indices], fresh[indices]
    matching = right[:,None] == left[None,:]
    features = torch.stack((matching,path[:,None].expand_as(matching),
                            fresh[:,None] | loop_new[None,:]),-1).float()
    return indices, features @ pair[0]+pair[1]>0


def measure(frames, first, pair, device):
    from statistics import median
    from time import perf_counter
    # Upload once. Synchronize each Run at its output boundary; there is no verifier here.
    host_frames, host_first, host_pair = frames, first, pair
    frames = [tuple(t.to(device) for t in frame) for frame in frames]
    first, pair = [tuple(t.to(device) for t in head) for head in (first,pair)]
    samples = {k:[] for k in ('direct','conditional')}
    for repeat in range(5):
        for mode in (tuple(samples) if repeat%2==0 else tuple(reversed(samples))):
            if device=='mps':
                torch.mps.synchronize()
            start = perf_counter()
            for frame in frames:
                decode(mode,first,pair,*frame)
                if device=='mps':
                    torch.mps.synchronize()
            if repeat:
                samples[mode].append(1000*(perf_counter()-start))
    if device!='cpu':
        for host, frame in zip(host_frames,frames):
            for mode in samples:
                reference = decode(mode,host_first,host_pair,*host)
                actual = decode(mode,first,pair,*frame)
                if not all(torch.equal(a.cpu(),b) for a,b in zip(actual,reference)):
                    raise ValueError((device,mode,'changed selected ports'))
    return {mode:dict(samples_ms=values,median_ms=median(values)) for mode,values in samples.items()}


def benchmark(traces, devices=()):
    # The first read can conservatively retain fresh paths or paths that a fresh loop might join.
    first = fit(2, lambda path, maybe_fresh: path and maybe_fresh)
    pair = fit(3, lambda same_body, path, fresh: same_body and path and fresh)
    result = {}
    for trace in traces:
        frames = []
        totals = {k:Counter() for k in ('direct','conditional')}

        def read(ports, mark, expected):
            # Bake-projected determined context. This token-history join is host work in this prototype.
            path_epochs = defaultdict(dict)
            for a,(body,expr,_) in ports[0].values():
                path_epochs[expr][body] = max(a[-1], path_epochs[expr].get(body,-1))
            paths = {}
            for c,(x,expr) in ports[2].values():
                for body, epoch in path_epochs.get(expr,{}).items():
                    paths[body,x] = max(paths.get((body,x),-1),epoch,c[-1])
            loops = list(ports[1].values())
            ds = list(ports[3].values())
            loop_new = torch.tensor([b[-1]>=mark for b,_ in loops],dtype=torch.bool)
            ids = {}
            def body_id(body):
                return ids.setdefault(body,len(ids))
            left = torch.tensor([body_id(v[1]) for _,v in loops],dtype=torch.long)
            right = torch.tensor([body_id(v[0]) for _,v in ds],dtype=torch.long)
            path = torch.tensor([tuple(v[:2]) in paths for _,v in ds],dtype=torch.bool)
            fresh = torch.tensor([max(d[-1],paths.get(tuple(v[:2]),-1))>=mark for d,v in ds],dtype=torch.bool)
            frame = (left,right,path,fresh,loop_new)
            if devices:
                frames.append(frame)
            for mode, t in totals.items():
                indices, verdict = decode(mode,first,pair,*frame)
                if mode=='conditional':
                    t['first_scores'] += len(ds)
                proposals = {(loops[j][0],ds[int(indices[i])][0]) for i,j in verdict.nonzero().tolist()}
                t.update(pair_scores=verdict.numel(), issued=len(proposals), reference=len(expected),
                         missing=len(expected-proposals), extra=len(proposals-expected))
        snapshot_audit(json.loads(trace.read_text()),read)
        if devices:
            totals['decoder_timing'] = {device: measure(frames,first,pair,device)
                                       for device in devices}
        result[trace.stem]=totals
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('traces',nargs='+',type=Path)
    parser.add_argument('--timing',choices=('cpu','mps'),action='append',default=[])
    args=parser.parse_args()
    torch.set_num_threads(1)
    print(json.dumps(benchmark(args.traces,args.timing),indent=2))
