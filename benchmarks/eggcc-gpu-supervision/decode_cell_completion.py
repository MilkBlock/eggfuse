"""GPU dense dictionary decode plus exact CPU checking of finite Bake targets.

Dictionary candidates are scoped by the source producer, NOT by the desired
consumer/target. The dictionary includes test-family Bake structures: this is a
known-catalog decode test, not unseen-state generalization. No nearest-code result
alone authorizes source-Run effects or retiring a token.
"""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import mlx.core as mx
from dominator_completion import freeze
from whole_cell_ridge import encode


def representation(facts,mapping):
    body=sorted(set((n,tuple(freeze(x) for x in xs)) for n,xs,*_ in facts),key=repr)
    ports=sorted(((freeze(a),freeze(b)) for a,b in mapping),key=repr)
    return body,ports


def retention(source,facts,mapping):
    body={freeze(v) for v in representation(facts,mapping)[0]}
    aliases={}
    for a,b in mapping:
        a,b=freeze(a),freeze(b)
        if a in aliases and aliases[a]!=b:return False
        aliases[a]=b
    for name,values,*_ in source:
        values=tuple(freeze(v) for v in values)
        if any(v not in aliases for v in values):return False
        if (name,tuple(aliases[v] for v in values)) not in body:return False
    return True


def dictionary(data):
    candidates=[];index={};expected=[];roots=[];novel=[]
    def add(producer,source,facts,mapping):
        if not retention(source,facts,mapping):raise ValueError('candidate loses source information')
        key=(producer,repr(representation(facts,mapping)))
        if key not in index:
            index[key]=len(candidates);candidates.append(dict(producer=producer,source=source,facts=facts,source_map=mapping))
        return index[key]
    for row in data['targets']:
        producer=row['producer'];source=row['source'];completion=row['completion']
        expected.append(add(producer,source,completion['facts'],completion['source_map']))
        symbols={freeze(v) for _,values,*_ in source for v in values}
        expected.append(add(producer,source,source,[(v,v) for v in symbols]))
        roots.extend([producer,producer]);novel.extend([completion['novel'],False])
    return candidates,np.array(expected,np.int32),np.array(roots,np.int32),np.array(novel,bool)


def gpu_decode(values,prototypes,roots,candidate_roots):
    # One dense float matrix operation; source interface eligibility is exact
    # integer metadata. No desired consumer/target is provided to this function.
    distance=mx.sum(values*values,axis=1)[:,None]+mx.sum(prototypes*prototypes,axis=1)[None,:]-2*(values@prototypes.T)
    distance=mx.where(roots[:,None]==candidate_roots[None,:],distance,mx.inf)
    selected=mx.argmin(distance,axis=1)
    best=mx.take_along_axis(distance,selected[:,None],axis=1)[:,0]
    alternatives=mx.where(mx.arange(prototypes.shape[0])[None,:]==selected[:,None],mx.inf,distance)
    second=mx.min(alternatives,axis=1)
    return selected,best,second-best


def main():
    p=argparse.ArgumentParser();p.add_argument('targets',type=Path);p.add_argument('predictions',type=Path);p.add_argument('output',type=Path);args=p.parse_args()
    data=json.loads(args.targets.read_text());prediction=json.loads(args.predictions.read_text())
    if prediction['targets_sha256']!=hashlib.sha256(args.targets.read_bytes()).hexdigest() or prediction['program_sha256']!=data['program_sha256']:raise ValueError('artifact mismatch')
    candidates,expected,roots,novel=dictionary(data)
    if roots.tolist()!=prediction['producer_roots']:raise ValueError('prediction order mismatch')
    vectors=np.array([encode(c['facts']) for c in candidates],np.float32);values=np.array(prediction['predictions'],np.float32);emit=np.array(prediction['emitted'],bool)
    assert mx.metal.is_available();mx.set_default_device(mx.gpu)
    selected,distance,margin=mx.compile(gpu_decode)(mx.array(values),mx.array(vectors),mx.array(roots),mx.array([c['producer'] for c in candidates],mx.int32));mx.eval(selected,distance,margin)
    selected=np.array(selected);margin=np.array(margin)
    # Refuse near ties. Independent CPU f64 distances verify the chosen minimum
    # and count ties; FP32 cancellation must not turn ambiguity into acceptance.
    cpu_selected=[];ambiguous=[]
    for value,root,choice in zip(values,roots,selected):
        d=np.sum((vectors.astype(np.float64)-value.astype(np.float64))**2,axis=1)
        d[np.array([c['producer'] for c in candidates])!=root]=np.inf
        best=d.min();ties=np.flatnonzero(d<=best+1e-6)
        if d[choice]>best+1e-4:raise ValueError('GPU decode differs beyond numerical tolerance')
        cpu_selected.append(int(d.argmin()));ambiguous.append(len(ties)>1 or int(choice) not in ties)
    ambiguous=np.array(ambiguous)
    reports={}
    for name,mask in [('train',roots%5>=2),('validation',roots%5==1),('test',roots%5==0)]:
        active=mask&emit
        correct=active&~ambiguous&(selected==expected)&novel
        reports[name]=dict(requests=int(mask.sum()),novel_completions=int((mask&novel).sum()),emitted=int(active.sum()),
            exact_catalog_target=int(correct.sum()),ambiguous_emissions=int((active&ambiguous).sum()),
            wrong_or_spurious_emissions=int((active&~ambiguous&((selected!=expected)|~novel)).sum()),
            missed_emissions=int((mask&novel&~emit).sum()))
    # Test information content independent of regression error. Identical codes
    # for distinct exact interfaces cannot be resolved by a better ridge fit.
    collisions=[]
    for i,c in enumerate(candidates):
        for j in range(i):
            if c['producer']==candidates[j]['producer'] and np.array_equal(vectors[i],vectors[j]):collisions.append([j,i])
    result=dict(scope='finite known-Bake-catalog GPU decode and CPU exact-target audit; no ownership authorization',program_sha256=data['program_sha256'],candidates=len(candidates),exact_code_collision_pairs=len(collisions),collision_examples=collisions[:8],reports=reports,source_retention_checks_pass=True,limitations=['Dictionary includes all supported Bake targets, including test families','Exact target means exact recorded body plus quotient map; alternative alpha-equivalent targets conservatively differ','Candidate certificates are scoped by producer, not by the requested consumer','No live port generation, visibility, source Run order or activation-ownership proof','Decoding appends a candidate reference; it does not replace the generated latent with a teacher code'])
    args.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

if __name__=='__main__':main()
