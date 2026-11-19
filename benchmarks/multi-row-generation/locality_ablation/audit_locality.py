"""CPU-only source replay and request placement for Figure 14."""
import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

CORPUS = Path(__file__).resolve().parents[1] / 'eclass_ablation'
sys.path.insert(0,str(CORPUS))
from data import audit, dataset, STATES

PANELS = ('original','all-home','half-cross','all-cross','hot-cross')
LANES = ('global','local','drop','stale','mute','resend','certified')


def change_requests(data, panel):
    if panel == 'original':
        return data
    d = dict(data, requests=data['requests'].copy(),request_ports=data['request_ports'].copy())
    for i, row in enumerate(d['requests']):
        sources = {(int(a[0]),int(p)):int(a[1]) for a,p in zip(d['a'][i],d['a_port'][i])}
        for j,req in enumerate(row):
            home,port = int(req[0]),int(d['request_ports'][i,j,1])
            owner = home if panel=='all-home' or (panel=='half-cross' and j%2==0) else 1-home
            if panel=='hot-cross':
                # The same parent port serves all reads from a given destination.
                port = int(d['a_port'][i,0])
            req[2:4]=owner,sources[owner,port]
            d['request_ports'][i,j,1]=port
    # Original labels apply only to the original request layout.
    for key in ('target2','legal_parents','request_legal'):
        d.pop(key)
    return d


def count(data,first,second,pending):
    reference=audit(data,first,second)
    truth=np.asarray(reference['request_legal'],bool)
    if 'request_legal' in data:np.testing.assert_array_equal(truth,data['request_legal'])
    cross=data['requests'][...,0]!=data['requests'][...,2]
    selected=second['active'].astype(bool)
    result={}
    for label,mask in [('all',np.ones(len(truth),bool)),
                       *((name,data['state']==i) for i,name in enumerate(STATES))]:
        rows=[r for r,m in zip(reference['run2']['per_graph'],mask) if m]
        totals=Counter()
        for row in rows:totals.update({k:int(v) for k,v in row.items()})
        keys=('nonempty','obligations','specified_origin_exact','wrong_parent','absent_parent',
              'illegal_producer','duplicates','illegal','missing','secondary_obligations','secondary_correct')
        out={k:totals[k] for k in keys}
        out.update(graphs=len(rows),nonempty_complete=sum(r['nonempty'] and r['complete'] for r in rows),
                   complete=totals['complete'],both_runs_complete=sum(r['complete'] and s['complete']
                       for r,s,m in zip(reference['run1']['per_graph'],reference['run2']['per_graph'],mask) if m),
                   run1_complete=sum(r['complete'] for r,m in zip(reference['run1']['per_graph'],mask) if m),
                   pending=int(pending[mask].sum()))
        for n,eligible in [('local',~cross),('cross',cross)]:
            sel=eligible & mask[:,None]
            for metric,bits in [('reads',sel),('legal',sel & truth),('fn',sel & truth & ~selected),
                                ('fp',sel & ~truth & selected)]:
                out[n+'_'+metric]=int(bits.sum())
        result[label]=out
    return result


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def replay(root, previous, summary):
    recorded=json.loads((root/'results.json').read_text())
    templates=json.loads((CORPUS/'corpus/manifest.json').read_text())['templates']
    panels={};files={};pos_diffs={}
    for seed in (1703,1709):
        for t in templates:
            held=t['split']=='heldout'
            if not held and t['id'] not in ('rule-266','rule-267','rule-580'):
                continue
            base=dataset('test',t)
            for panel in (PANELS if held else ('seen-secondary',)):
                d=base if not held else change_requests(base,panel)
                path=root/'traces'/f"{seed}-{t['id']}-{panel}.npz"
                files[path.name]=sha(path)
                assert files[path.name]==recorded['inputs_outputs_sha256'][path.name]
                with np.load(path,allow_pickle=False) as z:
                    first={k:z['first_'+k] for k in ('active','pointers','rows')}
                    if held:
                        src=previous/'traces'/f"{t['id']}-pairwise-{seed}.npz"
                        assert sha(src)==recorded['inputs_outputs_sha256'][src.name]
                        with np.load(src,allow_pickle=False) as orig:
                            for k,v in first.items():np.testing.assert_array_equal(v,orig['0_'+k])
                    for lane in LANES:
                        second={k:z[lane+'_'+k] for k in first}
                        pending=z[lane+'_pending']
                        cross=d['requests'][...,0]!=d['requests'][...,2]
                        np.testing.assert_array_equal(pending,cross if lane in ('stale','drop') else np.zeros_like(cross))
                        if lane in ('resend','stale','drop'):
                            for k in first:
                                mask=np.ones_like(cross) if lane=='resend' else ~cross
                                np.testing.assert_array_equal(second[k][mask],z['local_'+k][mask])
                            assert not np.any(second['active'][pending])
                        scored=count(d,first,second,pending)
                        for stratum,r in scored.items():
                            name=f'{seed}/{panel}/{lane}/{stratum}'
                            panels.setdefault(name,Counter()).update(r)
                    # Compare graph by graph even where two aggregate counts coincide.
                    rr={}
                    for lane in ('global','local','mute'):
                        sec={k:z[lane+'_'+k] for k in first}
                        rr[lane]=np.array([g['complete'] for g in audit(d,first,sec)['run2']['per_graph']])
                    for a,b in (('global','local'),('local','mute')):
                        c=pos_diffs.setdefault(f'{seed}/{panel}/{a}-to-{b}',Counter())
                        c.update(gained=int((rr[b]&~rr[a]).sum()),lost=int((rr[a]&~rr[b]).sum()))
    assert panels==recorded['panels']
    if 'torch' in sys.modules:raise RuntimeError('CPU audit imported PyTorch')
    summary.mkdir(parents=True,exist_ok=True)
    with (summary/'metrics.tsv').open('w') as f:
        writer=csv.writer(f,delimiter='\t',lineterminator='\n')
        fields=list(next(iter(panels.values())))
        writer.writerow(['seed','workload','scope','union_state',*fields])
        for name,values in panels.items():writer.writerow([*name.split('/'),*(values[k] for k in fields)])
    report=dict(evaluation_sha256=sha(root/'results.json'),trace_count=len(files),trace_sha256=files,
                median_ms=recorded['median_ms'],weights=recorded['weights'],
                unaffected_home_state=recorded['unperturbed_owner_bitwise_equal'],paired_graph_changes=pos_diffs,
                compiler_reference_sha256={p:sha(CORPUS/'corpus'/p) for p in ('manifest.json','replay-evidence.json','extra-events.json')})
    (summary/'replay.json').write_text(json.dumps(report,indent=2)+'\n')
    print('CPU replay passed:',len(files),'traces,',len(panels),'source comparisons')


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    for name in ('root','producers','summary'):parser.add_argument(name,type=Path)
    args=parser.parse_args()
    replay(args.root,args.producers,args.summary)
