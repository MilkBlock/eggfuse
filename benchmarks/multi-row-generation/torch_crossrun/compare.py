"""Torch MPS parity against frozen MLX traces, plus paired eager timings."""
import argparse
import hashlib
import importlib.metadata
import itertools
import json
import os
from pathlib import Path
import platform
from statistics import median
import sys
import time

import numpy as np

HERE = Path(__file__).resolve().parent
DATA = HERE.parent / 'crossrun' / 'data'
sys.path.insert(0, str(DATA))
from crossrun_data import dataset
from crossrun_audit import audit, audit_twins

NAMES = [f'{arm}-{seed}' for arm in ('learned', 'static', 'aux') for seed in (1703, 1709)]
MASKS = ('none', 'parents', 'parents_latent')
SPLITS = ('left_collision', 'right_collision')
DECISIONS = ('active', 'pointers', 'fields')
INPUTS = ('a', 'b', 'requests')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inputs(panel, index):
    return tuple(panel[name][index] for name in INPUTS)


def read_trace(path):
    with np.load(path, allow_pickle=False) as record:
        return ([{key:record[prefix+key] for key in DECISIONS} for prefix in ('one_', 'two_')],
                record['token'])


def materialize(stages, token, convert):
    decoded = [{k:convert(v) for k, v in stage.items()} for stage in stages]
    token = convert(token)
    if not np.isfinite(token).all():
        raise ValueError('nonfinite generated Pair token')
    groups = [decoded[0]['active'], *decoded[0]['pointers'].transpose(2, 0, 1),
              *decoded[0]['fields'].transpose(2, 0, 1)]
    offset = 64
    for width, selected in zip((2, 4, 4, 8, 4, 4), groups):
        np.testing.assert_array_equal(token[..., offset:offset+width], np.eye(width)[selected])
        offset += width
    return decoded, token


def torch_arrays(tensor):
    return tensor.detach().cpu().numpy()


def merge(chunks):
    stages = [{key:np.concatenate([st[i][key] for st, _ in chunks]) for key in DECISIONS}
              for i in range(2)]
    return stages, np.concatenate([t for _, t in chunks])


def assess(panel, stages, twins=True):
    raw = audit(panel['a'], panel['b'], panel['requests'], *stages)
    metrics = {key:({k:v for k,v in value.items() if k!='per_graph'} if isinstance(value,dict) else value)
               for key, value in raw.items()}
    exact = {key:np.array([g['complete'] for g in raw[key]['per_graph']], dtype=bool)
             for key in ('run1', 'run2')}
    if twins:
        metrics['twins'] = audit_twins(panel['a'], panel['b'], panel['requests'], *stages)
    return metrics, exact


def compare(left, right):
    left_stages, left_token = left
    right_stages, right_token = right
    stages = []
    for a, b in zip(left_stages, right_stages):
        differs = np.zeros(len(a['active']), dtype=bool)
        fields = {}
        for key in DECISIONS:
            x, y = a[key], b[key]
            if x.shape != y.shape:
                raise ValueError(f'output shape mismatch for {key}, {x.shape} versus {y.shape}')
            changed = x != y
            differs |= changed.reshape(len(x), -1).any(1)
            relevant = (a['active'] != 0) | (b['active'] != 0)
            fields[key] = dict(elements=int(x.size), differences=int(changed.sum()),
                               differences_on_either_active=int(changed[relevant].sum()))
        stages.append(dict(fields=fields, any_discrete_difference_graphs=int(differs.sum()),
                           first_differing_graph_ids=np.flatnonzero(differs)[:16].tolist()))
    delta=left_token[..., :64].astype(np.float64)-right_token[..., :64].astype(np.float64)
    return dict(run1=stages[0], run2=stages[1], graphs=len(left_token),
                pair_latent_max_abs=float(np.abs(delta).max()), pair_latent_rms=float(np.sqrt((delta*delta).mean())),
                pair_symbol_differences=int(np.count_nonzero(left_token[...,64:] != right_token[...,64:])))


class TorchLane:
    def __init__(self, torch, model, decode):
        self.torch = torch
        self.model = model.eval()
        self.decode = decode

    def forward(self, arrays, mask):
        device_inputs = [self.torch.as_tensor(v, device='mps') for v in arrays]
        raw, token = self.model(*device_inputs, mask=mask)
        return self.decode(raw), token

    def synchronize(self, outputs):
        self.torch.mps.synchronize()

    def download(self, outputs):
        return materialize(*outputs, torch_arrays)


class MLXLane:
    def __init__(self, mx, model, decode):
        self.mx = mx
        self.model = model
        self.decode = decode

    def forward(self, arrays, mask):
        raw, token = self.model(*[self.mx.array(v) for v in arrays], mask=mask)
        return self.decode(raw), token

    def synchronize(self, outputs):
        self.mx.eval(outputs)
        self.mx.synchronize()

    def download(self, outputs):
        return materialize(*outputs, np.asarray)


def run_bulk(lane, panel, mask):
    parts = []
    for begin in range(0, len(panel['a']), 64):
        outputs = lane.forward(inputs(panel, slice(begin, begin+64)), mask)
        lane.synchronize(outputs)
        parts.append(lane.download(outputs))
    return merge(parts)


def timed(lanes, panel, mask, indices, warmups):
    # CPU materialization and truth audits happen after all timed forwards.
    selected = {key:panel[key][indices] for key in INPUTS}
    for i in range(warmups):
        for key in (('torch','mlx') if i%2==0 else ('mlx','torch')):
            lane=lanes[key]
            output=lane.forward(inputs(selected,slice(i,i+1)), mask)
            lane.synchronize(output)
    samples = {key:[] for key in lanes}
    collected = {key:[] for key in lanes}
    for i in range(len(indices)):
        arrays = inputs(selected, slice(i, i+1))
        order = ('torch', 'mlx') if i%2==0 else ('mlx','torch')
        for key in order:
            start=time.perf_counter_ns()
            output=lanes[key].forward(arrays,mask)
            lanes[key].synchronize(output)
            samples[key].append((time.perf_counter_ns()-start)/1e6)
            collected[key].append(output)
    summaries = {}
    outputs = {}
    for key in lanes:
        outputs[key]=merge([lanes[key].download(result) for result in collected[key]])
        metrics,_=assess(selected,outputs[key][0],twins=False)
        ok=metrics['run2']['nonempty_complete_graphs']
        summaries[key]=dict(samples_ms=samples[key],median_ms=median(samples[key]),
                            nonempty_complete_graphs=ok,complete_nonempty_graphs_per_second=1000*ok/sum(samples[key]),
                            audit=metrics)
    return dict(implementations=summaries,indices=indices.tolist(),warmups=warmups,
                direct_batch_one_parity=compare(outputs['torch'],outputs['mlx']))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--torch-root', type=Path, required=True)
    parser.add_argument('--mlx-root', type=Path, required=True)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--mlx-reference', type=Path, default=HERE.parent/'mlx_reference')
    parser.add_argument('--samples', type=int, default=32)
    parser.add_argument('--warmups', type=int, default=4)
    args=parser.parse_args()
    if not 1 <= args.warmups <= args.samples <= 256:
        parser.error('require 1 <= warmups <= samples <= 256')
    if os.environ.get('PYTORCH_ENABLE_MPS_FALLBACK','0') != '0':
        raise RuntimeError('PYTORCH_ENABLE_MPS_FALLBACK must be disabled')
    os.environ['PYTORCH_ENABLE_MPS_FALLBACK']='0'
    import torch
    import mlx.core as mx
    from model import CrossRun, decode
    if not (torch.backends.mps.is_available() and mx.metal.is_available()):
        raise RuntimeError('both Apple MPS and MLX Metal backends required')
    reference=args.mlx_reference.resolve()
    sys.path.insert(0, str(reference))
    import eggfuse
    if not Path(eggfuse.__file__).resolve().is_relative_to(reference):
        raise RuntimeError(f'expected frozen MLX baseline from {reference}, got {eggfuse.__file__}')
    mx.set_default_device(mx.gpu)
    data={name:dataset(name) for name in SPLITS}
    frozen_manifest=json.loads((DATA/'split-manifest.json').read_text())
    for name, panel in data.items():
        for key in INPUTS:
            if hashlib.sha256(panel[key].tobytes()).hexdigest()!=frozen_manifest[name]['sha256'][key]:
                raise ValueError(f'{name} {key} input hash mismatch')
    metrics={};timings={};models={};trace_hashes={}
    output= args.output.resolve()
    trace_dir=output.parent/(output.stem+'-torch-traces');trace_dir.mkdir(parents=True,exist_ok=True)
    with torch.inference_mode():
        for name in NAMES:
            arm=name.split('-')[0]
            weights=args.torch_root/name/'final.pt'
            state=torch.load(weights,map_location='cpu',weights_only=True)
            model=CrossRun(arm,args.plan)
            model.load_state_dict(state,strict=True);model.to('mps')
            if any(param.device.type!='mps' or param.dtype!=torch.float32 for param in model.parameters()):
                raise ValueError('all torch parameters must be MPS float32')
            lanes=dict(torch=TorchLane(torch,model,decode),
                       mlx=MLXLane(mx,eggfuse.load_model(args.mlx_root/name,args.plan),eggfuse.decode))
            models[name]=dict(torch_sha256=digest(weights),mlx_sha256=digest(args.mlx_root/name/'model.safetensors'))
            for split, mask in itertools.product(SPLITS,MASKS):
                label=f'{name}-{split}-{mask}';panel=data[split]
                ref_path=args.mlx_root/'traces'/(label+'.npz');frozen=read_trace(ref_path)
                trace_hashes[label]=digest(ref_path)
                fresh={key:run_bulk(lane,panel,mask) for key,lane in lanes.items()}
                # Capture complete generated tensors for an external post-run replay.
                torch_stages,token=fresh['torch'];dump={'token':token}
                for prefix,stage in zip(('one_','two_'),torch_stages):dump.update({prefix+k:v for k,v in stage.items()})
                np.savez_compressed(trace_dir/(label+'.npz'),**dump)
                checks={};exact={}
                for key, record in {**fresh,'frozen':frozen}.items():
                    checks[key],exact[key]=assess(panel,record[0])
                mismatches={k:int(np.count_nonzero(exact['torch'][k] != exact['frozen'][k])) for k in exact['torch']}
                metrics[label]=dict(audits=checks, torch_vs_frozen=compare(fresh['torch'],frozen),
                                    eager_mlx_vs_frozen=compare(fresh['mlx'],frozen),
                                    eager_torch_vs_eager_mlx=compare(fresh['torch'],fresh['mlx']),
                                    changed_whole_graph_verdicts=mismatches)
                ids=np.random.default_rng(81911).choice(256,args.samples,replace=False)
                timings[label]=timed(lanes,panel,mask,ids,args.warmups)
                first=metrics[label]['torch_vs_frozen']['run1']['any_discrete_difference_graphs']
                second=metrics[label]['torch_vs_frozen']['run2']['any_discrete_difference_graphs']
                print(label,'discrete differences',first,second,'complete',checks['torch']['run2']['nonempty_complete_graphs'],flush=True)
    report=dict(scope='Six translated checkpoints compared on 512 held-out graphs, in two 256-graph panels; same graph set for each mask and model.',
                methodology='Eager Torch MPS and eager MLX Metal; same-process, matched int32 host inputs, alternating order per sample, each lane synchronizes GPU. Batch=1 prep/upload/2 Runs/decode/full Pair token included. No compilation or CPU semantic checks in timing. Bulk parity uses batch 64 with independent NumPy audit after generation.',
                environment=dict(torch=torch.__version__,mlx=importlib.metadata.version('mlx'),python=platform.python_version(),machine=platform.machine(),os=platform.platform(),torch_mps_fallback=os.environ['PYTORCH_ENABLE_MPS_FALLBACK']),
                inputs={s:{k:frozen_manifest[s]['sha256'][k] for k in INPUTS} for s in SPLITS},
                hashes=dict(plan=digest(args.plan),comparison=digest(Path(__file__)),torch_source=digest(HERE/'model.py'),
                            mlx_sources={p.name:digest(p) for p in sorted((reference/'eggfuse').glob('*.py'))},
                            frozen_trace_sha256=trace_hashes),models=models,panels=metrics,timings=timings)
    tmp=output.with_suffix(output.suffix+'.tmp');tmp.write_text(json.dumps(report,indent=2)+'\n');tmp.replace(output)
    print(f'Wrote {len(metrics)} bulk comparisons plus paired timings to {output}')

if __name__=='__main__':
    main()
