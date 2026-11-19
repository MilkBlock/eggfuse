"""Score frozen greedy two-Run outputs using the unchanged Figure 04 source audit."""
import argparse
import json
from pathlib import Path
import statistics
import time

import numpy as np
from credit_inputs import ARMS, SEEDS, WIDTH, templates, fresh_panel, freeze, save_or_check


def counter_summary(rows):
    fields=('obligations','active_outputs','nonempty','complete','parent_ready','missing','duplicates','illegal',
            'semantic_missing','unavailable_parent_obligations','wrong_parent','wrong_parent_when_available',
            'duplicate_same_round_cross_row','duplicate_later_round','duplicate_cross_row','distinct_requests_reusing_a_parent')
    totals = {k:sum(int(row[k]) for row in rows) for k in fields if k in rows[0]}
    totals.update(graphs=len(rows), nonempty_complete=sum(bool(row['nonempty'] and row['complete']) for row in rows),
                  ready_nonempty=sum(bool(row['parent_ready'] and row['nonempty']) for row in rows))
    return totals


def stratify(d, report):
    strata = {'blind':d['blind']!=0, 'targeted':d['blind']==0}
    for i,state in enumerate(('pre','post','nonmerge','external')):
        condition=d['state']==i;strata[state]=condition
        strata['blind_'+state]=condition & (d['blind']!=0)
        strata['targeted_'+state]=condition & (d['blind']==0)
    return {name: counter_summary([row for row,keep in zip(report['run2']['per_graph'], bits) if keep])
            for name,bits in strata.items()}


def timing_ids(d, ordinal):
    groups=np.unique(d['group_id']);rng=np.random.default_rng(25541+ordinal)
    selected=np.concatenate([rng.choice(groups[even::2],2,replace=False) for even in (0,1)])
    ix=np.concatenate([np.flatnonzero(d['group_id']==k) for k in selected]);return ix


def draw_timing(cases, d, table, setup, ix, gpu, panel_index):
    import torch
    from evaluate_width import check_trace, host, merge, subset
    from fit import transfer
    from audit import metrics
    lanes=list(cases);sample=subset(d,ix)
    retained={k:[] for k in lanes};durations={k:[] for k in lanes}
    def one(k,i):
        model,rows=cases[k]
        return model(*transfer(sample,slice(i,i+1),gpu),table[k],rows=rows,schedule='parallel')
    for name in lanes:
        for i in range(3):
            one(name,i);torch.mps.synchronize()
    for i in range(len(ix)):
        rotation=(i+panel_index)%len(lanes)
        for name in lanes[rotation:]+lanes[:rotation]:
            before=time.perf_counter_ns();output=one(name,i);torch.mps.synchronize()
            durations[name].append((time.perf_counter_ns()-before)/1.e6);retained[name].append(output)
    outcomes={}
    for name in lanes:
        stages,token,rel=merge([host(out) for out in retained[name]])
        check_trace(sample,stages,token)
        probe=metrics(sample,*stages,cases[name][1],rel)['run2'];ms=durations[name]
        bulk=setup[name]
        differences=[int(np.logical_or.reduce([(s[k]!=bulk[j][k][ix]).reshape(len(ix),-1).any(1) for k in s]).sum()) for j,s in enumerate(stages)]
        outcomes[name]=dict(indices=ix.tolist(), samples_ms=ms, median_ms=statistics.median(ms),
                            graphs=len(ix),nonempty=probe['nonempty_graphs'],complete=probe['nonempty_complete_graphs'],
                            complete_per_second=1000*probe['nonempty_complete_graphs']/sum(ms),
                            hard_graph_differences_vs_bulk=differences)
    return outcomes


def load_models(root,width_root,schema,gpu):
    import torch
    from model import WidthSystem
    from fit import digest
    all_models={};meta={}
    frozen_sha=digest(root/'fresh-credit-inputs.json')
    for seed in SEEDS:
        batch_order=None;critic_initial=None
        folder=width_root/str(seed);base_path=folder/'final.pt'
        base_hash=digest(base_path)
        if json.loads((folder/'fit.json').read_text())['model_sha256']!=base_hash:raise ValueError('incorrect Figure 04 checkpoint')
        for arm in ('frozen1',*ARMS):
            name=f'{arm}-{seed}'
            checkpoint=base_path if arm in ('zero','frozen1') else root/name/'final.pt'
            checkpoint_hash=digest(checkpoint)
            if arm not in ('zero','frozen1'):
                fitted=json.loads((checkpoint.parent/'fit.json').read_text())
                if (fitted['model_sha256'],fitted['parent_sha256'],fitted['test_manifest_sha256'])!=(checkpoint_hash,base_hash,frozen_sha):
                    raise ValueError(f'checkpoint, initialization or evaluation input mismatch for {name}')
                if (fitted['seed'],fitted['arm'],fitted['steps'],fitted['batch'])!=(seed,arm,1024,32):
                    raise ValueError(f'unexpected adaptation recipe for {name}')
                if batch_order is None:batch_order=fitted['data_order']
                if fitted['data_order']!=batch_order:raise ValueError(f'training batches differ for {name}')
                if arm in ('team','counterfactual'):
                    if critic_initial is None:critic_initial=fitted['critic_init']
                    if fitted['critic_init']!=critic_initial:raise ValueError(f'critic initialization differs for {name}')
            model=WidthSystem(schema,seed)
            model.load_state_dict(torch.load(checkpoint,map_location='cpu',weights_only=True),strict=True)
            all_models[name]=model.to(gpu).eval()
            meta[name]=dict(weight_sha256=checkpoint_hash,parent_sha256=base_hash,checkpoint=str(checkpoint))
    return all_models,meta


def sum_counts(entries):
    if isinstance(entries[0],dict):
        return {k:sum_counts([entry[k] for entry in entries]) for k in entries[0]}
    return sum(entries)


def total_report(cases, panels, timings, paired):
    totals = {}
    for name in cases:
        full = [p[name] for p in panels.values()]
        times = [p[name] for p in timings.values()]
        samples = [ms for t in times for ms in t['samples_ms']]
        successes = sum(t['complete'] for t in times)
        row = {k:sum_counts([p[k] for p in full]) for k in ('r1','r2','strata','origin_switch','paired_controls','both_complete_graphs')}
        row['timed'] = dict(graphs=len(samples),successes=successes,
                            nonempty=sum(t['nonempty'] for t in times), median_ms=statistics.median(samples),
                            complete_per_second=1000*successes/sum(samples),
                            hard_graph_differences_vs_bulk=np.sum([t['hard_graph_differences_vs_bulk'] for t in times],axis=0).tolist())
        if 'all_arms_ready' in full[0]:
            row['all_arms_ready']=sum_counts([p['all_arms_ready'] for p in full])
            row['paired']={baseline:{k:sum_counts([p[name][baseline][k] for p in paired.values()])
                                     for k in ('nonempty','common_parent_ready_nonempty')}
                           for baseline in ('frozen1',*ARMS)}
        totals[name]=row
    return totals


def run(root,width_root,freeze_only):
    root.mkdir(exist_ok=True,parents=True);source=freeze();save_or_check(source,root/'fresh-credit-inputs.json')
    if freeze_only:
        print(json.dumps(source,indent=2));return
    import torch
    from audit import metrics, paired_layouts
    from evaluate_width import host, merge, check_trace, compact
    from fit import device, transfer, EClassSchema, digest
    gpu=device();ts=templates();schema=EClassSchema([t for t in ts if t['split']=='train'])
    held=[t for t in ts if t['split']=='heldout'];models,metadata=load_models(root,width_root,schema,gpu)
    cases={name:(model,1 if name.startswith('frozen1-') else 2) for name,model in models.items()}
    traces=root/'traces';traces.mkdir(exist_ok=True);panels={};timings={};paired={};hashes={}
    retention={};retention_dir=root/'retention-traces';retention_dir.mkdir(exist_ok=True);retention_hashes={}
    with torch.inference_mode():
        for n,t in enumerate(held):
            tid=t['id'];d=fresh_panel(t);bank=schema.bank(t,'pairwise',gpu)
            tables={name:m.encoder.frozen_bank(bank) for name,m in models.items()}
            raw={};stages_for_timing={};panels[tid]={};paired[tid]={}
            for name,(model,rows) in cases.items():
                chunks=[host(model(*transfer(d,slice(i,i+64),gpu),tables[name],rows=rows,schedule='parallel'))
                        for i in range(0,len(d['a']),64)]
                stages,token,rel=merge(chunks);check_trace(d,stages,token)
                path=traces/f'{tid}-{name}.npz';np.savez_compressed(path,token=token,rel=rel,
                    **{f'{i}_{k}':v for i,s in enumerate(stages) for k,v in s.items()});hashes[path.name]=digest(path)
                report=metrics(d,*stages,rows,rel);raw[name]=report;stages_for_timing[name]=stages
                panels[tid][name]=dict(**compact(report),strata=stratify(d,report),paired_controls=report['paired_controls'])
            # A separate compatibility diagnostic checks the same adapted weights
            # when they return to one row. These lanes are absent from all timings.
            retention[tid]={}
            for name,(model,rows) in cases.items():
                if name.startswith(('frozen1-', 'zero-')):continue
                chunks=[host(model(*transfer(d,slice(i,i+64),gpu),tables[name],rows=1,schedule='parallel'))
                        for i in range(0,len(d['a']),64)]
                st,tok,rel=merge(chunks);check_trace(d,st,tok);summary=metrics(d,*st,1,rel)
                trace=retention_dir/f'{tid}-{name}.npz'
                np.savez_compressed(trace,token=tok,rel=rel,**{f'{i}_{k}':v for i,frame in enumerate(st) for k,v in frame.items()})
                retention_hashes[trace.name]=digest(trace)
                seed=name.rsplit('-',1)[1]
                retention[tid][name]=dict(r1=compact(summary)['r1'],r2=compact(summary)['r2'],
                    paired_to_frozen=paired_layouts(raw['frozen1-'+seed],summary))
            for seed in SEEDS:
                for arm in ARMS:
                    name=f'{arm}-{seed}';paired[tid][name]={}
                    for baseline in ('frozen1',*ARMS):
                        key=f'{baseline}-{seed}';paired[tid][name][baseline]=paired_layouts(raw[key],raw[name])
            # The common-ready set for ALL four two-row arms is more stringent
            # than the pairwise intersection used in a comparison to baseline.
            for seed in SEEDS:
                names=[f'{a}-{seed}' for a in ARMS]
                rows={name:raw[name]['run2']['per_graph'] for name in names}
                keep=[all(rows[name][i]['parent_ready'] and rows[name][i]['nonempty'] for name in names)
                      for i in range(len(d['a']))]
                for name in names:
                    panels[tid][name]['all_arms_ready']={'graphs':sum(keep),'complete':sum(int(v['complete']) for v,b in zip(rows[name],keep) if b)}
            timings[tid]=draw_timing(cases,d,tables,stages_for_timing,timing_ids(d,n),gpu,n)
            print(tid,{key:p['r2']['nonempty_complete_graphs'] for key,p in panels[tid].items()},flush=True)
    totals=total_report(cases,panels,timings,paired)
    result=dict(totals=totals,one_row_retention=retention,retention_sha256=retention_hashes,frozen_inputs=source,models=metadata,panels=panels,timings=timings,paired=paired,trace_sha256=hashes,
                audit_sha256=digest(WIDTH/'audit.py'),evaluation_sha256=digest(Path(__file__)),torch=torch.__version__,
                timed_scope='batch one, device input transfer, greedy make and finish, actual Pair token and MPS sync; cached template table; warmup, offline training, CPU audit excluded')
    tmp=root/'results.tmp';tmp.write_text(json.dumps(result,separators=(',',':'))+'\n');tmp.replace(root/'results.json')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('root',type=Path);parser.add_argument('--width-root',type=Path,default=Path('/Volumes/EggFuseWorkspace/experiments/single-to-multi-width-20261119'));parser.add_argument('--freeze-only',action='store_true')
    args=parser.parse_args();run(args.root,args.width_root,args.freeze_only)
