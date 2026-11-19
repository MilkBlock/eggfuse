"""Offline transfer of a frozen address head to actual Figure 20 neural frontiers."""
import argparse
from collections import Counter
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys

import numpy as np
import torch
from model import AddressModel, ARMS

HERE = Path(__file__).resolve().parent
FIG20 = HERE.parent / 'eclass_ablation'
STATES = ('pre', 'post', 'nonmerge', 'external')
LAYOUTS = ('owner-row', 'split-handle')


def figure20_data():
    # Import the old audit as its own package instead of aliasing this study's data.py.
    name = 'frozen_fig20_data'
    spec = importlib.util.spec_from_file_location(name, FIG20/'data/__init__.py',
                                                  submodule_search_locations=[str(FIG20/'data')])
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def coordinates(origin, layout):
    owner, handle = origin.long().unbind(-1)
    if layout == 'owner-row':
        return torch.stack((owner, handle//2, handle%2), -1), 4, 2
    if layout == 'split-handle':
        return torch.stack((handle//4, owner, handle%4), -1), 2, 4
    raise ValueError(layout)


def score(model, token, request, previous_active, previous_request, layout):
    # The recorded producer's five emitted scalar fields start at channel 50.
    rows = token[..., 50:55].long()
    query, length, ports = coordinates(request[..., 2:4], layout)
    bank, _, _ = coordinates(rows[..., :2], layout)
    scores = model.address_scores(stage='make', query_coords=query, candidate_coords=bank,
                                  length=length, ports=ports)
    parent = scores.argmax(-1)
    moved = parent.gather(1, previous_request)
    picked = rows.gather(1, moved[...,None].expand(-1,-1,rows.shape[-1]))
    tag = request[...,4].gather(1,previous_request)
    rebuilt = torch.cat((picked[...,:2],tag[...,None],picked[...,3:5]),-1)
    result = {'pointers':torch.stack((moved,previous_request),-1),
              'rows':rebuilt,'active':previous_active}
    return parent, scores, result


def host(x):
    return x.detach().cpu().numpy()


def check_saved(d, token, first):
    origins = first['pointers'].transpose(2,0,1)
    li,ri = origins
    g = np.arange(len(token))[:,None]
    expected=np.concatenate((d['a'][g,li],d['b'][g,ri,1,None]),axis=-1)
    for start,width,decision in [(32,2,first['active']),(34,8,li),(42,8,ri)]:
        np.testing.assert_array_equal(token[...,start:start+width],np.eye(width)[decision])
    np.testing.assert_array_equal(token[...,50:55],expected)
    np.testing.assert_array_equal(token[...,55],d['a_port'][g,li]);np.testing.assert_array_equal(first['rows'],expected)
    if not np.isfinite(token).all():raise ValueError('nonfinite saved token')
    return ((first['active']==1) & (d['a'][g,li,0]==d['b'][g,ri,0]))


def held_pairs(d, legal):
    index={tuple(map(int,k)):g for g,k in enumerate(zip(d['group_id'],d['state'],d['variant']))}
    for group in np.unique(d['group_id']):
        for state in (1,3):
            lhs,rhs=index[int(group),state,0],index[int(group),state,1]
            changed=np.flatnonzero((d['requests'][lhs,:,2:4]!=d['requests'][rhs,:,2:4]).any(-1))
            if len(changed)!=1:raise ValueError('figure 20 changed multiple requested origins')
            q=int(changed[0]);np.testing.assert_array_equal(d['requests'][lhs,q,:2],d['requests'][rhs,q,:2])
            if legal[lhs,q] and legal[rhs,q]:yield lhs,rhs,q,STATES[state]


def request_metrics(d, first, valid, legal, picks, scores):
    if not np.isfinite(scores).all():raise ValueError('nonfinite pointer scores')
    raw_origin = first['rows'][...,:2]
    request_origin = d['requests'][...,2:4]
    same = (raw_origin[:,None,:,:]==request_origin[:,:,None,:]).all(-1)
    copies = (same & valid[:,None,:]).sum(-1)
    g=np.arange(len(picks))[:,None];q=np.arange(picks.shape[1])[None,:]
    selected_origin=same[g,q,picks];selected_valid=valid[g,picks]
    selected_active=first['active'][g,picks].astype(bool)
    right=selected_origin & selected_valid
    tied=scores==np.max(scores,axis=-1,keepdims=True)
    exposed_duplicate=same.sum(-1)>1
    metrics={}
    for label,mask in [('all',np.ones_like(legal)),('blind',d['blind'][:,None]==1),
                       ('nonblind',d['blind'][:,None]==0)]:
        mask=legal & mask
        ready=mask & (copies>0)
        def count(bits):return int(np.sum(bits))
        metrics[label]=dict(legal_requests=count(mask), parents_present=count(ready),
            present_multiple_valid=count(mask & (copies>1)), present_duplicate_origin=count(ready & exposed_duplicate),
            ready_correct=count(ready & right),ready_wrong_origin=count(ready & ~selected_origin),
            ready_correct_origin_but_invalid=count(ready & selected_origin & ~selected_valid),
            ready_inactive_selected=count(ready & ~selected_active),
            ready_active_illegal_selected=count(ready & selected_active & ~selected_valid),
            ready_correct_origin=count(ready & selected_origin),
            ready_any_valid_top_score=count(ready & np.any(tied & same & valid[:,None,:],axis=-1)))
    paired={stratum:{state:Counter(probes=0,both_ready=0,both_selected_origin=0,
                    both_selected_exact_given_ready=0) for state in ('post','external')}
            for stratum in ('all','blind')}
    for lhs,rhs,qi,state in held_pairs(d,legal):
        for label in ('all','blind') if d['blind'][lhs] else ('all',):
            row=paired[label][state];row['probes']+=1
            ready=bool(copies[lhs,qi] and copies[rhs,qi]);row['both_ready']+=int(ready)
            row['both_selected_origin']+=int(selected_origin[lhs,qi] and selected_origin[rhs,qi])
            row['both_selected_exact_given_ready']+=int(ready and right[lhs,qi] and right[rhs,qi])
    return metrics,paired


def same_class(rows):
    return {group:{state:r['same_class_origin_switch_'+state] for state in ('post','external')}
            for group,r in rows.items()}


def aggregate(records):
    """All entries are counts on disjoint graph panels."""
    if isinstance(records[0],dict):
        return {k:aggregate([entry[k] for entry in records]) for k in records[0]}
    return sum(records)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('address_root',type=Path);parser.add_argument('output',type=Path)
    parser.add_argument('--figure20-root',type=Path,required=True)
    parser.add_argument('--cross-seed',action='store_true',help='apply the other address seed to each frozen producer seed')
    parser.add_argument('--device',choices=('cpu','mps'),default='mps');args=parser.parse_args()
    if args.device=='mps' and (not torch.backends.mps.is_available() or os.environ.get('PYTORCH_ENABLE_MPS_FALLBACK','0')!='0'):
        raise RuntimeError('MPS with CPU fallback disabled required')
    choice_dir=args.address_root/('trace-transfer-choices-crossed' if args.cross_seed else 'trace-transfer-choices');choice_dir.mkdir(exist_ok=True)
    source=figure20_data();manifest=json.loads((FIG20/'corpus/manifest.json').read_text());original=json.loads((args.figure20_root/'paired-controls.json').read_text())
    held=[t for t in manifest['templates'] if t['split']=='heldout'];report={};baseline={};hashes={};template_rows={}
    for t in held:template_rows[t['id']]=source.dataset('test',t)
    with torch.inference_mode():
        for seed in (1703,1709):
            name=f'pairwise-{seed}';models={}
            address_seed=(3412-seed) if args.cross_seed else seed
            for arm in ARMS:
                path=args.address_root/f'{arm}-{address_seed}'/'final.pt';hashes[str(path)]=sha(path)
                fit=json.loads((path.parent/'fit.json').read_text())
                assert (fit['weight'],fit['arm'],fit['seed'])==(hashes[str(path)],arm,address_seed)
                m=AddressModel(arm)
                m.load_state_dict(torch.load(path,map_location='cpu',weights_only=True),strict=True);models[arm]=m.eval().to(args.device)
            for t in held:
                tid=t['id'];d=template_rows[tid];path=args.figure20_root/'traces'/f'{tid}-{name}.npz'
                hashes[str(path)]=sha(path);assert hashes[str(path)]==original['trace_hashes'][path.name]
                with np.load(path,allow_pickle=False) as z:
                    token=z['token'];rel=z['rel'].argmax(-1)
                    first,second=({k:z[f'{s}_{k}'] for k in ('active','pointers','rows')} for s in range(2))
                # Complete every pointer intervention on this frontier before auditing
                # any selected slot. No legal/ready mask reaches the GPU scorer.
                def tensor(x):return torch.as_tensor(x,device=args.device)
                args_gpu=[tensor(x) for x in (token,d['requests'],second['active'],second['pointers'][...,1])]
                args_gpu[-1]=args_gpu[-1].long()
                decisions={}
                for layout in LAYOUTS:
                    for arm,m in models.items():
                        pointer,scores,moved=score(m,*args_gpu,layout)
                        decisions[layout,arm]=(host(pointer),host(scores),{k:host(v) for k,v in moved.items()})
                archived=choice_dir/f'{tid}-{name}.npz'
                np.savez_compressed(archived,**{f'{l}_{a}':v[0].astype(np.int16) for (l,a),v in decisions.items()})
                hashes[str(archived)]=sha(archived)
                valid=check_saved(d,token,first);reference=source.audit(d,first,second)
                legal=np.array(reference['request_legal'],dtype=bool)
                base=same_class(source.paired_controls(d,first,second,rel))
                assert base==same_class(original['controls'][tid][name]);baseline[f'{tid}/{name}']=base
                for (layout,arm),(picks,scores,moved) in decisions.items():
                    metrics,paired=request_metrics(d,first,valid,legal,picks,scores)
                    retarget=same_class(source.paired_controls(d,first,moved,rel));after=source.audit(d,first,moved)
                    key=f'{layout}/{arm}-{address_seed}' + (f'__pairwise-{seed}' if args.cross_seed else '')
                    report.setdefault(key,{})[tid]=dict(requests=metrics,paired_retrieval=paired,paired_emission=retarget,
                        nonempty_complete_before=reference['run2']['nonempty_complete_graphs'],
                        nonempty_complete_after=after['run2']['nonempty_complete_graphs'],
                        predicted_slot_sha256=hashlib.sha256(picks.astype('<i8').tobytes()).hexdigest())
    totals={}
    for key,panels in report.items():totals[key]=aggregate([{k:v for k,v in p.items() if k!='predicted_slot_sha256'} for p in panels.values()])
    assert len(held)==3 and len(baseline)==6
    base_totals={str(seed):aggregate([v for key,v in baseline.items() if key.endswith(f'-{seed}')]) for seed in (1703,1709)}
    for seed in (1703,1709):assert base_totals[str(seed)]==same_class(original['aggregate'][f'pairwise-{seed}'])
    result=dict(scope='Frozen-figure-20 frontier retrieval using Figure 03 first-stage address scores, followed by a frozen-activation parent-pointer intervention.',
        seed_pairing='crossed' if args.cross_seed else 'matched',layout_shapes={'owner-row':[2,4,2],'split-handle':[2,2,4]},source_sha256=sha(Path(__file__)),address_model_sha256=sha(HERE/'model.py'),
        reference_audit_sha256=sha(args.figure20_root/'paired-controls.json'),device=args.device,trace_and_weight_hashes=hashes,
        heldout=[t['id'] for t in held],original_paired_emission=base_totals,by_panel=report,totals=totals)
    tmp=args.output.with_suffix('.tmp');tmp.write_text(json.dumps(result,indent=1)+'\n');tmp.replace(args.output)
    for key,v in totals.items():print(key,v['paired_retrieval']['blind']['post'],v['paired_emission']['blind']['post'])


if __name__=='__main__':main()
