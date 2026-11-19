"""Evaluate two-row gates with identical published-token semantics and measured body counts."""
import argparse
from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from pathlib import Path
import statistics
import time

import numpy as np
import torch

from gate_model import GateSystem, ROWS, LENGTH
from gate_data import INPUTS, SEEDS, array_digest, fresh_panel, templates
from audit_gate import execution_metrics, metrics, timed_rates, verify_token
from encoder import EClassSchema


@dataclass(frozen=True)
class Lane:
    seed: int
    treatment: str
    policy: str
    mode: str
    backend: str
    threshold: float = 0.5
    mask: tuple = ()

    @property
    def name(self):
        return (('ungated' if self.backend=='original' else f'{self.policy}-{self.backend}') + f'-{self.seed}')

    def calls(self, model, inputs, table, mask=None, *, audit=False):
        if self.backend=='original':
            return model.actor(*inputs,table,rows=2,schedule='parallel')
        override=None if mask is None else mask.expand(inputs[0].shape[0],-1,-1,-1)
        return model(*inputs,table,mode=self.mode,backend=self.backend,threshold=self.threshold,gate_override=override,audit=audit)

    @property
    def timed(self):
        return self.backend!='dense' and not (self.mask and self.backend=='metal_dense')


def make_lanes(calibration):
    lanes=[]
    for seed in SEEDS:
        base=f'gate_p0-{seed}';lanes.append(Lane(seed,base,'ungated','all','original'))
        for mode in ('all','none'):
            for backend in (('dense','metal_dense','metal_skip') if mode=='all' else ('metal_dense','metal_skip')):
                lanes.append(Lane(seed,base,mode,mode,backend))
        for tag in ('p0','p25'):
            treatment=f'gate_{tag}-{seed}';item=calibration['entries'][treatment]
            if item['mode'] not in ('learned','all') or not 0<=item['threshold']<=1:
                raise ValueError(f'invalid calibration for {treatment}')
            mask=np.asarray(item['mask']);
            if mask.shape!=(2,8) or not np.isin(mask,[0,1]).all():raise ValueError('expected one calibrated 8-slot mask per Run')
            fixed=tuple(tuple(map(int,row)) for row in mask)
            for backend in ('dense','metal_dense','metal_skip'):
                lanes.append(Lane(seed,treatment,f'{tag}-default','learned',backend))
                lanes.append(Lane(seed,treatment,f'{tag}-calibrated',item['mode'],backend,item['threshold']))
            for backend in ('metal_dense','metal_skip'):
                lanes.append(Lane(seed,treatment,f'{tag}-static','all',backend,mask=fixed))
    if len({lane.name for lane in lanes})!=len(lanes):raise AssertionError('non-unique gate lane')
    return lanes


def digest(path):return sha256(path.read_bytes()).hexdigest()


def models_for(root,parent,schema,device):
    models={};provenance={}
    for seed in SEEDS:
        base=parent/f'supervised-{seed}'/'final.pt';state=torch.load(base,map_location='cpu',weights_only=True)
        parent_hash=digest(base)
        if parent_hash!=json.loads((base.parent/'fit.json').read_text())['model_sha256']:raise ValueError('parent checkpoint mismatch')
        for tag in ('p0','p25'):
            name=f'gate_{tag}-{seed}';folder=root/name
            fit=json.loads((folder/'fit.json').read_text());gatefile=folder/'gates.pt'
            if fit['parent_sha256']!=parent_hash or fit['gates_sha256']!=digest(gatefile):raise ValueError(f'fitted gate or parent mismatch for {name}')
            model=GateSystem(schema,seed).load_actor(state)
            model.gates.load_state_dict(torch.load(gatefile,map_location='cpu',weights_only=True),strict=True)
            models[name]=model.to(device).eval();provenance[name]=fit
    return models,provenance


def transfer(d,indices,device):
    return tuple(torch.as_tensor(d[k][indices],device=device,dtype=torch.int32) for k in INPUTS)


def compact_output(raw, *, counters=False, full=True):
    stages,token,relation=raw
    selected=('active','pointers','rows','hidden','active_logits','left_logits','right_logits') if full else ('active','pointers','rows')
    keys=selected+(('executed','work_checksum') if counters else ())
    out=[]
    for stage in stages:
        keep={k:stage[k] for k in keys if k in stage}
        keep['gate_open']=stage['gate_open'] if 'gate_open' in stage else torch.ones_like(stage['active'],dtype=torch.bool)
        if full and 'gate_logits' in stage:keep['gate_logits']=stage['gate_logits']
        out.append(keep)
    return out,token,relation


def on_host(raw):
    stages,token,relation=raw
    host=lambda tensor:tensor.detach().cpu().numpy()
    return [{k:host(v) for k,v in s.items()} for s in stages],host(token),host(relation)


def combine(chunks):
    stage=[{k:np.concatenate([item[0][i][k] for item in chunks]) for k in chunks[0][0][i]} for i in range(2)]
    return stage,np.concatenate([item[1] for item in chunks]),np.concatenate([item[2] for item in chunks])


def fingerprints(output, *, include_gate_logits=True):
    stages,token,rel=output
    wanted={f'{i}_{k}':v for i,s in enumerate(stages) for k,v in s.items() if k not in ('work_checksum','executed') and (include_gate_logits or k!='gate_logits')}
    wanted.update(token=token,rel=rel)
    result={}
    for k,v in wanted.items():
        if v.dtype.kind=='f' and not np.isfinite(v).all():raise ValueError(f'nonfinite output {k}')
        result[k]=sha256(v.tobytes(order='C')).hexdigest()
    return result


def bulk(lane,model,d,table,mask,dev,audit=False):
    chunks=[]
    for lo in range(0,len(d['a']),64):
        raw=lane.calls(model,transfer(d,slice(lo,lo+64),dev),table,mask,audit=audit)
        chunks.append(on_host(compact_output(raw,counters=audit)))
    return combine(chunks)


def instrument(lane,model,d,table,mask,dev,actual):
    replay=bulk(lane,model,d,table,mask,dev,audit=True)
    if fingerprints(replay)!=fingerprints(actual):raise ValueError(f'{lane.name}: instrumentation changed output')
    scored=replay[0];report=execution_metrics(*scored,lane.backend)
    # Analytic FMA/MAC terms for the custom per-row scorer, independently
    # multiplied by its instrumented execution count. Setup and publishing have
    # additional costs and are included in elapsed time. These are not GPU counters.
    for i,(stage,left,right) in enumerate((('run1',d['a'].shape[1],d['b'].shape[1]),('run2',8,d['requests'].shape[1]))):
        item=report[stage];dim=model.actor.decoder.dim;width=model.actor.decoder.token_width
        macs=dim*(width + 2*dim + 2 + left + right)
        item.update(body_macs_per_executed_row=macs,estimated_body_macs=macs*item['executed_scorer_rows'],
                    estimated_saved_body_macs=macs*item['skipped_scorer_rows'])
        # A separate audit dispatch provides these bits; deployment hashes above
        # bind every numerical visible output before attaching the counters.
        for key in ('executed','work_checksum'):actual[0][i][key]=scored[i][key]
    return report


def concise(report):
    return dict(r1={k:v for k,v in report['run1'].items() if k!='per_graph'},r2={k:v for k,v in report['run2'].items() if k!='per_graph'},
                gate={tag:{k:v for k,v in s.items() if k not in ('per_graph','by_group')} for tag,s in report['gate'].items()},
                origin_switch=report['origin_switch'],paired_controls=report['paired_controls'],both_complete_graphs=report['both_complete_graphs'],
                complete_by_graph=[int(g['complete']) for g in report['run2']['per_graph']],parent_ready=[int(g['parent_ready']) for g in report['run2']['per_graph']])


def archive(path,output):
    stages,token,rel=output
    keep=('gate_open','active','pointers','rows','executed','work_checksum')
    arrays={f'{i}_{k}':s[k] for i,s in enumerate(stages) for k in keep if k in s}
    np.savez_compressed(path,token=token,rel=rel,**arrays)


def timed_indices(d,ordinal):
    groups=np.unique(d['group_id']);rng=np.random.default_rng(26641+ordinal)
    chosen=np.concatenate([rng.choice(groups[p::2],2,replace=False) for p in (0,1)])
    return np.concatenate([np.flatnonzero(d['group_id']==g) for g in chosen])


def subset(data,indices):
    return {k:(v[indices] if isinstance(v,np.ndarray) else v) for k,v in data.items()}


def timing(lanes,models,tables,masks,d,dev,ordinal,reference):
    ix=timed_indices(d,ordinal);sample=subset(d,ix);lanes=[lane for lane in lanes if lane.timed]
    kept={l.name:[] for l in lanes};ms={l.name:[] for l in lanes}
    def forward(l,i):
        return l.calls(models[l.treatment],transfer(sample,slice(i,i+1),dev),tables[l.treatment],masks[l.name])
    for lane in lanes:
        for i in range(3):
            forward(lane,i);torch.mps.synchronize()
    for i in range(len(ix)):
        offset=(i+ordinal)%len(lanes)
        for lane in lanes[offset:]+lanes[:offset]:
            start=time.perf_counter_ns();out=forward(lane,i);torch.mps.synchronize()
            ms[lane.name].append((time.perf_counter_ns()-start)/1e6)
            kept[lane.name].append(compact_output(out,full=False))
    results={};timed_fingerprints={}
    for lane in lanes:
        name=lane.name;st,tok,rel=combine([on_host(x) for x in kept[name]])
        verify_token(sample,*st,tok,None);report=metrics(sample,*st,None,rel);times=ms[name]
        timed_fingerprints[name]=fingerprints((st,tok,rel))
        differences=[]
        for k in range(2):
            change=np.logical_or.reduce([(v!=reference[name][k][key][ix]).reshape(len(ix),-1).any(1) for key,v in st[k].items()]);differences.append(int(change.sum()))
        results[name]=dict(indices=ix.tolist(),samples_ms=times,rates=timed_rates(report,times),bulk_hard_differences=differences)
    for lane in lanes:
        if lane.backend!='metal_skip' or lane.mask:continue
        other=lane.name.replace('metal_skip','metal_dense')
        if timed_fingerprints[other]!=timed_fingerprints[lane.name]:raise ValueError(f'timed mask/skip recurrence mismatch {lane.name}')
    return results


def add(rows):
    """Sum count trees, retaining buckets that occur in only some templates."""
    first=rows[0]
    if isinstance(first,dict):
        return {k:add([r[k] for r in rows if k in r]) for k in sorted(set().union(*[r.keys() for r in rows]))}
    if isinstance(first,list):return np.sum(rows,axis=0).tolist()
    return sum(rows)


def summarize(lanes,panels,timings):
    result={}
    for lane in lanes:
        name=lane.name;rs=[panel[name] for panel in panels.values()]
        main={k:add([r[k] for r in rs]) for k in ('r1','r2','gate','origin_switch','paired_controls','both_complete_graphs')}
        if 'execution' in rs[0]:
            entries={}
            for stage in ('run1','run2'):
                counts=[r['execution'][stage] for r in rs];work=counts[0]['body_macs_per_executed_row'];entries[stage]=add(counts)
                entries[stage]['body_macs_per_executed_row']=work
            main['execution']=entries
        if lane.timed:
            measured=[t[name] for t in timings.values()];samples=np.concatenate([t['samples_ms'] for t in measured]);wins=sum(t['rates']['all']['complete_nonempty'] for t in measured)
            observed={}
            for kind in ('source','ready'):
                buckets=set.union(*[set(t['rates'][kind]) for t in measured]);observed[kind]={}
                for b in buckets:
                    parts=[t['rates'][kind][b] for t in measured if b in t['rates'][kind]];ws=sum(x['complete_nonempty'] for x in parts);tm=sum(x['elapsed_ms'] for x in parts)
                    observed[kind][b]=dict(graphs=sum(x['graphs'] for x in parts),complete_nonempty=ws,elapsed_ms=tm,complete_per_second=1000*ws/tm)
            main['timed']=dict(graphs=len(samples),median_ms=float(np.median(samples)),elapsed_ms=float(samples.sum()),successes=wins,complete_per_second=1000*wins/samples.sum(),by_obligations=observed,
                               bulk_hard_differences=np.sum([t['bulk_hard_differences'] for t in measured],axis=0).tolist())
            if lane.backend=='metal_skip' and not lane.mask:
                dense=name.replace('metal_skip','metal_dense');other=np.concatenate([t[dense]['samples_ms'] for t in timings.values()])
                ratios=other/samples
                main['timed']['paired_dense_over_skip_median']=float(np.median(ratios));main['timed']['paired_skip_faster']=int((other>samples).sum())
                # Four complete 8-graph intervention groups per template. Resample
                # groups within each template/blind stratum to retain dependence.
                blocks=ratios.reshape(len(measured),2,2,8)
                rng=np.random.default_rng(62612)
                picks=rng.integers(0,2,(1000,len(measured),2,2))
                resampled=blocks[np.arange(len(measured))[None,:,None,None],np.arange(2)[None,None,:,None],picks]
                interval=np.quantile(np.median(resampled.reshape(1000,-1),axis=1),[.025,.975])
                main['timed']['paired_ratio_group_bootstrap_95']=interval.tolist()
        result[name]=main
    return result


def main():
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('--parent-root',type=Path,default=Path('/Volumes/EggFuseWorkspace/experiments/two-row-credit-20261119'));args=p.parse_args()
    if not torch.backends.mps.is_available():raise RuntimeError('requires MPS')
    import os
    if os.environ.get('PYTORCH_ENABLE_MPS_FALLBACK','0')!='0':raise RuntimeError('requires CPU fallback off')
    root=args.root;cfg=json.loads((root/'calibration.json').read_text());lanes=make_lanes(cfg);ts=templates()
    schema=EClassSchema([t for t in ts if t['split']=='train']);held=[t for t in ts if t['split']=='heldout'];dev=torch.device('mps')
    models,provenance=models_for(root,args.parent_root,schema,dev);frozen=json.loads((root/'fresh-gate-inputs.json').read_text());folder=root/'traces';folder.mkdir(exist_ok=True)
    masks={l.name:(torch.tensor(l.mask,device=dev,dtype=torch.bool).reshape(1,2,ROWS,LENGTH) if l.mask else None) for l in lanes}
    panels={};timings={};checks={};hashes={}
    with torch.inference_mode():
        for n,t in enumerate(held):
            tid=t['id'];d=fresh_panel(t);require=frozen['panels'][tid]
            if array_digest(d)!=require['digest']:raise ValueError(f'changed frozen panel {tid}')
            bank=schema.bank(t,'pairwise',dev);tables={name:m.encoder.frozen_bank(bank) for name,m in models.items()}
            panels[tid]={};checks[tid]={};fingerprints_by_name={};reference={};float_ref={}
            for lane in lanes:
                name=lane.name;model=models[lane.treatment];actual=bulk(lane,model,d,tables[lane.treatment],masks[name],dev)
                st,tok,rel=actual;verify_token(d,*st,tok,None);report=metrics(d,*st,None,rel);record=concise(report)
                prints=fingerprints(actual);fingerprints_by_name[name]=prints
                reference[name]=[{k:s[k] for k in ('gate_open','active','pointers','rows')} for s in st]
                if lane.backend in ('original','dense'):float_ref[name]=(tok.copy(),rel.copy())
                if lane.backend=='dense' and lane.policy=='all':
                    ref=f'ungated-{lane.seed}'
                    if fingerprints(actual,include_gate_logits=False)!=fingerprints_by_name[ref]:raise ValueError('force-all Torch failed to reproduce ungated actor')
                if lane.backend.startswith('metal'):
                    record['execution']=instrument(lane,model,d,tables[lane.treatment],masks[name],dev,actual)
                if lane.backend=='metal_skip':
                    ref=name.replace('metal_skip','metal_dense')
                    if prints!=fingerprints_by_name[ref]:raise ValueError(f'full mask/skip recurrence mismatch {name}')
                    checks[tid][name]=dict(dense_reference=ref,all_byte_equal=True,output_hashes=prints)
                if lane.backend=='metal_dense' and lane.policy not in ('none',) and not lane.mask:
                    ref=(f'ungated-{lane.seed}' if lane.policy=='all' else name.replace('metal_dense','dense'))
                    old=reference[ref];base_tok,base_rel=float_ref[ref]
                    def changed(st,keys):
                        return int(np.logical_or.reduce([(old[st][key]!=reference[name][st][key]).reshape(len(d['a']),-1).any(1)
                                                         for key in keys]).sum())
                    record['torch_reference']=dict(name=ref,hard_graph_changes=[changed(i,('active','pointers','rows')) for i in range(2)],
                        gate_graph_changes=[changed(i,('gate_open',)) for i in range(2)],token_max_abs=float(np.abs(tok-base_tok).max()),
                        rel_max_abs=float(np.abs(rel-base_rel).max()))
                archive(folder/f'{tid}-{name}.npz',actual);hashes[f'{tid}-{name}.npz']=digest(folder/f'{tid}-{name}.npz');panels[tid][name]=record
            timings[tid]=timing(lanes,models,tables,masks,d,dev,n,reference)
            print(tid,{l.name:panels[tid][l.name]['r2']['nonempty_complete_graphs'] for l in lanes if l.backend in ('original','metal_skip')},flush=True)
    totals=summarize(lanes,panels,timings)
    result=dict(schema='eggfuse.row-gates.greedy/v1',frozen_inputs=frozen,calibration=cfg,calibration_sha256=digest(root/'calibration.json'),
        lanes={l.name:asdict(l) for l in lanes},fit=provenance,trace_sha256=hashes,panels=panels,timings=timings,totals=totals,scorer_parity=checks,
        source_sha256={f:digest(HERE/f) for f in ('evaluate.py','gate_model.py','metal_stage.py','audit_gate.py','gate_data.py')},
        cost_scope='MAC estimates for instrumented per-row Metal scoring only. Prepared inputs, gates, publishing, finish relation and all GPU dispatches also enter the synchronized single-graph latency. CPU audit and encoder cache preparation are outside timing.')
    tmp=root/'results.tmp';tmp.write_text(json.dumps(result,separators=(',',':'))+'\n');tmp.replace(root/'results.json')
    print('completed',len(hashes),'frozen bulk traces')


HERE=Path(__file__).resolve().parent
if __name__=='__main__':main()
