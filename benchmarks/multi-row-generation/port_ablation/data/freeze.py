"""Recreate input hashes, validate the structural split and report gold witness counts."""
from collections import Counter
from hashlib import sha256
from itertools import combinations
from pathlib import Path
import argparse
import json
import numpy as np
from port_data import dataset, reference
from port_audit import consistent_candidate_reads, source_witnesses


def signature(t):
    normalized=[]
    for stage in t['stages']:
        predicates=sorted(tuple(sorted(map(tuple,pair))) for pair in stage['checks'])
        normalized.append([stage['left_width'],stage['right_width'],predicates,stage['outputs']])
    return sha256(json.dumps(normalized,separators=(',',':')).encode()).hexdigest()


def digest_panel(panel):
    return {k:sha256(panel[k].tobytes()).hexdigest() for k in ['a','b','requests','target1','target2','probe']}


def panel_stats(panel):
    a,b,r=panel['a'],panel['b'],panel['requests'];probes=panel['probe']
    one,two=(y[...,0].sum(1) for y in [panel['target1'],panel['target2']]);sharing=Counter()
    for i,(a0,b0,r0) in enumerate(zip(a,b,r)):
        assert len(set(map(tuple,b0[:,:-1])))==4
        src,finish=reference(panel['stages'],a0,b0,r0)
        assert len(src)==one[i] and len(finish)==two[i]
        assert (src,finish)==source_witnesses(panel['stages'],a0,b0,r0)
        label=panel['target1'][i]
        for active,p,ri,*projected in panel['target2'][i].tolist():
            if active:
                _,li,bi,*unused=label[p].tolist()
                assert tuple(projected)==finish[li,bi,ri]
        probe=probes[i]
        if probe[0]>=0:
            l,u=tuple(probe[:2]),tuple(probe[2:4]);ri=int(probe[4]);shared=sum(x==y for x,y in zip(src[l],src[u]))
            assert shared>0 and (*l,ri) in finish and (*u,ri) not in finish
            if i%2==0:
                assert np.array_equal(a[i],a[i+1]) and np.array_equal(b[i],b[i+1])
                different=np.flatnonzero((r[i]!=r[i+1]).any(-1));assert list(different)==[ri]
                assert tuple(probes[i+1,:2])==u
            sharing[f'{shared}/{len(src[l])}']+=1
    return dict(graphs=len(a), source_obligations=[int(one.sum()),int(two.sum())],nonempty=[int((one>0).sum()),int((two>0).sum())],
                graphs_with_consistent_residual_candidates=sum(consistent_candidate_reads(panel['stages'][1],r0) for r0 in r),
                run2_count_histogram={str(k):int(v) for k,v in sorted(Counter(two).items())},
                probe_partial_equal_columns=dict(sorted(sharing.items())),actual_value_range=[int(min(a.min(),b.min(),r.min())),int(max(a.max(),b.max(),r.max()))],
                sha256=digest_panel(panel))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('output',type=Path);args=parser.parse_args()
    path=Path(__file__).parents[1]/'corpus/manifest.json';families=json.loads(path.read_text())['templates']
    signatures={part:{signature(t) for t in families if t['split']==part} for part in ('train','heldout')}
    assert not signatures['train']&signatures['heldout']
    assert not {t['family_id'] for t in families if t['split']=='train'}&{t['family_id'] for t in families if t['split']=='heldout'}
    reports={}; fingerprints={}; shared_inputs={}; example=None
    for family in families:
        reports[family['id']]={};keys={}
        for split in (('train','iid','collision') if family['split']=='train' else ('iid','collision')):
            panel=dataset(split,family);reports[family['id']][split]=panel_stats(panel)
            src=(panel['a'],panel['b'],panel['requests']);shapes=str([list(v.shape[1:]) for v in src]).encode()
            keys[split]={sha256(shapes+b''.join(z.tobytes() for z in row)).digest() for row in zip(*src)}
            assert len(keys[split])==len(src[0])
            if split=='collision':
                shared_inputs[family['id']]=src
                if example is None and family['split']=='heldout':
                    one,two=panel['probe'][:2]
                    table,_=reference(family['stages'],panel['a'][0],panel['b'][0],panel['requests'][0])
                    req=int(one[-1])
                    example=dict(template=family['id'],family=family['family_id'],request_slot=req,
                        parents=[dict(source_indices=p[:2].tolist(),row=table[tuple(p[:2])],
                                      request=panel['requests'][i,req].tolist()) for i,p in enumerate((one,two))],
                        consumer_checks=family['stages'][1]['checks'])
        assert not any(x&y for x,y in combinations(keys.values(),2))
        fingerprints[family['id']]=keys
    train=set().union(*(v['train'] for v in fingerprints.values() if 'train' in v))
    held=set().union(*(v['collision'] | v['iid'] for v in fingerprints.values() if 'train' not in v))
    assert not train&held
    # Use identical fixed integer arrays on differently wired templates of equal
    # side widths to check that the choice of template actually changes answers.
    switches=[]
    for t,u in combinations(families,2):
        if t['family_id']==u['family_id']:continue
        widths=lambda f:[(s['left_width'],s['right_width']) for s in f['stages']]
        if widths(t)!=widths(u):continue
        diff=[0,0];identity_changes=[0,0]
        for row in zip(*shared_inputs[t['id']]):
            original=reference(t['stages'],*row);alternate=reference(u['stages'],*row)
            for i in range(2):
                diff[i]+=int(original[i]!=alternate[i])
                identity_changes[i]+=int(original[i].keys()!=alternate[i].keys())
        switches.append(dict(template=t['id'],substituted=u['id'],graphs=len(shared_inputs[t['id']][0]),changed_source_witness_sets=diff,changed_binding_identities=identity_changes))
    if switches and not any(any(v['changed_source_witness_sets']) for v in switches):raise ValueError('equal-width distinct wiring had no observed effect')
    result=dict(schema='eggfuse.port-ablation.frontier-data/v1',corpus_sha256=sha256(path.read_bytes()).hexdigest(),
                source_sha256=sha256((Path(__file__).parent/'port_data.py').read_bytes()).hexdigest(),
                distinct_unsorted_type_erased_boundary_signatures={k:len(v) for k,v in signatures.items()},
                heldout_overlap_with_training_wiring=0,input_hash_overlap_train_with_heldout=0,
                equal_width_different_template_probes=switches,counterfactual_example=example,panels=reports)
    args.output.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    for split in ('train','iid','collision'):
        for part in ('train','heldout'):
            stats=[reports[t['id']][split] for t in families if t['split']==part and split in reports[t['id']]]
            print(part,split,'graphs',sum(s['graphs'] for s in stats),'nonempty2',sum(s['nonempty'][1] for s in stats),'witness2',sum(s['source_obligations'][1] for s in stats),flush=True)

if __name__=='__main__':main()
