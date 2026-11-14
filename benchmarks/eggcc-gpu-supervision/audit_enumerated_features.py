"""Diagnose information collisions and input coverage; never fit on validation."""
import argparse,collections,hashlib,json
from pathlib import Path
import numpy as np
from calibrate_semantic_family import load,semantic_family,align_features
from fit_completion_classifier import inputs_for_case,training_policy
from device_completion_states import compile_states


def feature_key(x,required):
    x=np.asarray(x,dtype=np.float32).copy()
    if not np.isfinite(x).all():raise ValueError('nonfinite feature')
    x[x==0]=0  # normalize signed zero, which has identical arithmetic meaning
    return (x.tobytes(),np.asarray(required,dtype=bool).tobytes())


def diagnose(train,validation):
    x=np.stack([r['x'] for r in train]);mean=x.mean(0);scale=np.maximum(x.std(0),.02)
    groups={}
    for r in train:groups.setdefault(feature_key(r['x'],r['required']),[]).append(r)
    conflicts=[g for g in groups.values() if len({r['target'] for r in g})>1]
    examples=[]
    for g in conflicts[:10]:
        examples.append([dict(case=r['case'],sample=r['sample'],target=r['target']) for r in g[:8]])
    val=[]
    for r in validation:
        same=groups.get(feature_key(r['x'],r['required']),[])
        distance=np.sqrt(np.mean(((x-r['x'])/scale)**2,axis=1));j=int(distance.argmin())
        val.append(dict(case=r['case'],sample=r['sample'],generated=r['generated'],target=r['target'],exact_input_matches=len(same),matching_target=any(s['target']==r['target'] for s in same),nearest_standardized_rms=float(distance[j]),nearest_target=train[j]['target'],nearest_case=train[j]['case']))
    hist=lambda rows:dict(collections.Counter(str(r['target']) for r in rows))
    return dict(training_rows=len(train),unique_inputs=len(groups),conflicting_input_groups=len(conflicts),conflicting_rows=sum(map(len,conflicts)),conflict_examples=examples,training_states=hist(train),validation_states=hist(validation),validation=val)


def main():
    p=argparse.ArgumentParser();p.add_argument('manifest',type=Path);p.add_argument('model',type=Path);p.add_argument('output',type=Path);p.add_argument('--validation',type=Path,action='append',required=True);a=p.parse_args()
    manifest=json.loads(a.manifest.read_text())
    if not manifest['collection_complete']:raise ValueError('incomplete training collection')
    with np.load(a.model) as d:model=dict(d)
    buckets={};family=None;sources=[]
    paths=[('train',Path(r['path'])) for r in manifest['records']]+[('validation',p) for p in a.validation]
    for split,path in paths:
        d,m=load(path,split)
        if split=='train':training_policy(m)
        sf=semantic_family(m)
        if family is not None and family!=sf:raise ValueError('family mismatch')
        family=sf;plans=[compile_states(r) for r in sf]
        d['features'],_=align_features(d,model,True)
        detail=inputs_for_case(path,m,d,plans)
        sources.append(dict(split=split,case=m['capture']['case'],sha256=m['capture']['artifact_sha256']))
        for rid,v in detail.items():
            bucket=buckets.setdefault(int(rid),dict(train=[],validation=[]))
            for lane,i in enumerate(v['ids']):
                bucket[split].append(dict(x=d['features'][i],required=v['required'][lane],target=int(v['target'][lane].argmax()),case=m['capture']['case'],sample=int(i),generated=bool(d['generated_source'][i])))
    report=dict(scope='exact feature plus required-Eq collisions and training-standardized distances; no fitting or runtime acceptance',model_sha256=hashlib.sha256(a.model.read_bytes()).hexdigest(),sources=sources,rules={str(k):diagnose(v['train'],v['validation']) for k,v in buckets.items()})
    a.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:{n:v[n] for n in ['training_rows','unique_inputs','conflicting_input_groups','training_states','validation_states']} for k,v in report['rules'].items()}))
if __name__=='__main__':main()
