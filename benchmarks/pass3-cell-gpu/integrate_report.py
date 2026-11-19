"""Verify ablation transcripts against a fully audited execution and summarize them."""
import argparse
import csv
import hashlib
import json
from pathlib import Path

import numpy as np
from endpoint import endpoint


def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def identity(path):
    # Operand slots are already in source order. Lane and pivot are execution
    # choices. The separate Spine stream retains the complete winning origin.
    with np.load(path/'output.npz',allow_pickle=False) as z:
        h=hashlib.sha256()
        for k in ('runs','resumes','writes','rows','meta','parents'):
            a=z[k]
            h.update(str((k,a.shape,a.dtype.str)).encode())
            h.update(a.tobytes())
        rhs=z['rhs']
        for part in (rhs[:,:2],rhs[:,4:]):h.update(part.tobytes())
        groups=np.bincount(rhs[:,2],minlength=2)
        both=len(set(rhs[rhs[:,2]==0,0]).intersection(rhs[rhs[:,2]==1,0]))
        keys=[set(),set()]
        for row in rhs:
            keys[int(row[2])].add((int(row[0]),int(row[1]),row[4:].tobytes()))
        return h.hexdigest(),dict(tokens=groups.tolist(),runs_using_both=both,
                      repeated_within=int(len(rhs)-sum(map(len,keys))),repeated_between=len(keys[0]&keys[1]))


def main(root,out):
    timings=read(out/'cli.json')
    results={}
    for name in ('sum-bits','dot-product'):
        ref=root/f'oracle-{name}';packet=root/f'v3-input-{name}/ingress.json'
        gold=root/f'release-{name}';ok=read(gold/'check.json');ordered=read(gold/'ordered.json')
        assert ok['acceptance']=='pass' and ordered['provenance']['output.npz']==sha(gold/'output.npz')
        sign,_=identity(gold)
        with np.load(gold/'output.npz') as z:
            events=z['resumes'];runs=z['runs'];first=events[0].tolist()
            depth=int(events[:,5].max());res_counts=np.bincount(events[:,0],minlength=len(runs)+1)
        cases={'scan':root/f'certified-{name}-2','scan_one':root/f'certified-{name}-1',
               'point':root/f'batch-{name}-point-0','hash':root/f'batch-{name}-hash-0',
               'two':gold,'one':root/f'release-one-{name}','prune':root/f'prune-{name}'}
        cases.update({f'matched_{mode}':root/f'matched-{name}-{mode}' for mode in ('scan','point','hash')})
        cases.update({f'run_batch_{i}':root/f'batch-{name}-hash-{i}' for i in (1,4,16)})
        cases.update({f'dense_{i}':root/f'tiled-{name}-{i}' for i in (1,4,8)})
        cases.update({f'packed_{i}':root/f'packed-{name}-{i}' for i in (8,16,32)})
        cases.update({f'cap_{i}':root/f'compact-{name}-{i}' for i in (32,64)})
        cases.update({f'scalar_{s}':root/f'primitive-{name}-{s}' for s in ('integer','guarded','lossy')})
        cases.update({f'learned{s}':root/f'release-{name}-learned-{s}' for s in (1703,1709)})
        variants={}
        for label,folder in cases.items():
            r=read(folder/'run.json');signature,metrics=identity(folder)
            if not (signature==sign and r['finished'] and not r['fault']):
                raise ValueError((name,label,'differs from audited semantic transcript',r['state'][:8]))
            if label.startswith('learned') or label in ('one','two','prune'):
                result=read(folder/'check.json')
                assert result['acceptance']=='pass'
            variant={k:r.get(k) for k in ('lanes','lookup','tiles','batch_runs','arena','token_layout','router','token_cap','inference_ms','token_bank_bytes')}
            # Historical dense-bank runs predate compact reporting. Recover
            # actual tensor reservation from the allocation dimensions.
            if variant['token_bank_bytes'] is None:
                layout=read(root/f'spine-input-{name}/device.json')['layout']
                variant['token_bank_bytes']=layout['RULES']*(variant['tiles'] or 1)*r['lanes']*256*(layout['NINPUT']+5)*8
            variant.update(metrics)
            if r.get('profile_prims'):variant.update(primitive_calls=r['state'][19:35],float_calls=r['state'][35:51])
            variants[label]=variant
        dirs={'immediate_canonical':root/f'immediate-{name}','fenced_canonical':root/f'fence-canonical-{name}',
              'immediate_published':root/f'immediate-published-{name}','fenced_published':root/f'fence-published-{name}'}
        ordering={}
        for label,folder in dirs.items():
            checks=endpoint(packet,folder,ref)
            ordering[label]={k:checks[k] for k in ('first_schedule_difference','first_rhs_count_difference',
                'first_write_count_difference','full_typed_graph_equal','completed','gpu_continuations')}
        native=read(root/('native-gpu-sum' if name=='sum-bits' else 'native-gpu-dot')/'check.json')
        assert native['status']=='pass'
        stems={'sum-bits':'sum','dot-product':'dot'}
        accept_file=root/f'native-gpu-{stems[name]}/check.json'
        output=root/f'export-{name}/state.json'
        assert all(timings[name][k]['state_sha256']==sha(output) for k in ('one','two','learned1703','learned1709'))
        results[name]=dict(reference=ok,aligned=ordered['aligned_by_ordinal'],source_sha256=ordered['provenance'],
                           native_contract=dict(status=native['status'],report_sha256=sha(accept_file),
                                                export_sha256=sha(output)),ordering=ordering,variants=variants,
                           first_resume=first,longest_resumed_depth=depth,transcript_sha256=sign)
        sources=read(ref/'report.json')['steps'];rhs=read(ref/'rhs.json');writes=read(ref/'writes.json');res=read(ref/'resumes.json')
        with (out/f'{name}-runs.tsv').open('w') as f:
            w=csv.writer(f,delimiter='\t',lineterminator='\n')
            w.writerow(('run','ruleset','rhs_count','effective_writes','spine_count','rhs_sha256','writes_sha256','spine_sha256'))
            for i,s in enumerate(runs):
                rr=ordered['runs'][i]
                assert all(rr[k] for k in ('schedule','rhs','writes','spine','known_class_roots'))
                w.writerow((i+1,sources[i]['ruleset'],int(s[1]),int(s[2]),int(res_counts[i+1]),rhs[i],writes[i][1],res[i][1]))
    (out/'integration.json').write_text(json.dumps(results,indent=1)+'\n')
    print({n:(r['reference']['completed'],r['reference']['acceptance'],len(r['variants'])) for n,r in results.items()})


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('out',type=Path)
    a=p.parse_args();main(a.root,a.out)
