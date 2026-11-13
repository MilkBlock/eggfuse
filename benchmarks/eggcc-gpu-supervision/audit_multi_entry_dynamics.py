"""Frozen-model audit against train-only template means and state dictionaries."""
import argparse
from collections import defaultdict,Counter
import hashlib,json
from pathlib import Path
import numpy as np
from collect_observed_corpus import read_bytes
from multi_entry_ridge import dataset,arrays,pooling,features,replay,metric


def train_catalog(nodes):
    groups=defaultdict(list)
    for n in nodes:
        if n['valid']:groups[n['family']].append(n)
    result={}
    for family,rows in groups.items():
        states={n['state_key']:n['target'] for n in rows}
        frequencies=Counter(n['state_key'] for n in rows)
        mode=min(frequencies,key=lambda k:(-frequencies[k],k))
        result[family]=dict(mode=states[mode],mean=np.mean([n['target'] for n in rows],axis=0),
            keys=list(states),codes=np.array(list(states.values()),np.float32))
    return result


def evaluate(nodes,predictions,catalog):
    target=arrays(nodes)[2];valid=np.array([n['valid'] for n in nodes])
    known=np.array([n['family'] in catalog for n in nodes])
    variable=np.array([len(catalog[n['family']]['keys'])>1 if k else False for n,k in zip(nodes,known)])
    seen=np.array([n['state_key'] in catalog[n['family']]['keys'] if k else False for n,k in zip(nodes,known)])
    template_mean=np.zeros_like(target);template_mode=np.zeros_like(target)
    for i,n in enumerate(nodes):
        if known[i]:
            template_mean[i]=catalog[n['family']]['mean'];template_mode[i]=catalog[n['family']]['mode']
    masks=dict(known_templates=valid&known,variable_training_templates=valid&variable,
        unseen_state_known_template=valid&known&~seen,seen_state=valid&seen,unknown_template=valid&~known)
    reports={}
    for label,mask in masks.items():
        pred={**predictions}
        if label!='unknown_template':pred['template_mean']=template_mean
        reports[label]={name:metric(values,target,mask) for name,values in pred.items()}
    decode={};recovered={}
    # A training-only dictionary is an audit, not a general state decoder.
    for name,values in {**predictions,"template_mean":template_mean,"template_mode":template_mode}.items():
        counts=dict(covered_cases=0,correct=0,ambiguous=0,unseen_target=0,unknown_template=0)
        distinct=defaultdict(list);success=np.zeros(len(nodes),bool)
        for i,n in enumerate(nodes):
            if not valid[i]:continue
            if not known[i]:counts['unknown_template']+=1;continue
            if not seen[i]:counts['unseen_target']+=1;continue
            family=catalog[n['family']];dist=np.sum((family['codes'].astype(np.float64)-values[i])**2,axis=1)
            order=np.argsort(dist);ambiguous=len(order)>1 and dist[order[1]]<=dist[order[0]]+1e-10
            correct=not ambiguous and family['keys'][order[0]]==n['state_key']
            success[i]=correct
            counts['covered_cases']+=1;counts['correct']+=int(correct);counts['ambiguous']+=int(ambiguous)
            distinct[(n['family'],n['state_key'])].append(correct)
        counts['distinct_covered_states']=len(distinct)
        counts['mean_accuracy_per_distinct_state']=float(np.mean([np.mean(v) for v in distinct.values()])) if distinct else None
        decode[name]=counts;recovered[name]=success
    paired={}
    if 'no_provider_refit' in recovered:
        baseline=recovered['no_provider_refit'];covered=valid&seen
        for name,current in recovered.items():
            paired[name]=dict(wins=int((covered&current&~baseline).sum()),
                losses=int((covered&~current&baseline).sum()),both_correct=int((covered&current&baseline).sum()),
                both_wrong=int((covered&~current&~baseline).sum()))
    return dict(subsets=reports,train_dictionary_decode=decode,paired_against_no_provider=paired,
        distinct_test_templates=len({n['family'] for n in nodes if n['valid']}),
        known_test_templates=len({n['family'] for n in nodes if n['valid'] and n['family'] in catalog}),
        variable_training_templates=sum(len(f['keys'])>1 for f in catalog.values()))


def main():
    p=argparse.ArgumentParser();p.add_argument('training',type=Path);p.add_argument('test_trace',type=Path)
    p.add_argument('model',type=Path);p.add_argument('model_report',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
    report=json.loads(a.model_report.read_text());training_bytes=a.training.read_bytes();manifest=json.loads(training_bytes)
    test_raw=read_bytes(a.test_trace)
    if hashlib.sha256(training_bytes).hexdigest()!=report['provenance']['train']:raise ValueError('training manifest mismatch')
    if manifest['partition']!='train':raise ValueError('train partition required')
    if hashlib.sha256(test_raw).hexdigest()!=report['provenance']['test_trace']:raise ValueError('test trace mismatch')
    if hashlib.sha256(a.model.read_bytes()).hexdigest()!=report['model_sha256']:raise ValueError('model mismatch')
    with np.load(a.model) as saved:
        w=saved['w'];coef=saved['coef'];zero=saved['zero_provider_coef']
        channels=int(saved['channels']) if 'channels' in saved else 1
        zero_role_channels=bool(saved['zero_role_channels']) if 'zero_role_channels' in saved else False
    train_nodes=[]
    for entry in manifest['cases']:
        if entry['status']!='complete':continue
        if entry['split']!='train':raise ValueError('non-train case')
        raw=read_bytes(Path(entry['trace']))
        if hashlib.sha256(raw).hexdigest()!=entry['trace_sha256']:raise ValueError('training trace mismatch')
        train_nodes.extend(dataset(json.loads(raw),channels,zero_role_channels))
    test=dataset(json.loads(test_raw),channels,zero_role_channels);seed,q,target=arrays(test)
    predictions=dict(gold_providers=np.tanh(features(seed,q,pooling(test,target),w,np)@coef),
        predicted_providers=replay(test,w,coef,False),
        no_provider_refit=np.tanh(features(seed,q,np.zeros((len(target),channels*128),np.float32),w,np)@zero))
    result=evaluate(test,predictions,train_catalog(train_nodes))
    result.update(scope='frozen-model CPU diagnostic, no new fit or GPU timing',model_sha256=report['model_sha256'],
        training_manifest_sha256=report['provenance']['train'],test_trace_sha256=report['provenance']['test_trace'],
        limitations=['Exact means normalized captured slot state in a known template, not native graph semantics',
            'Train-only dictionary cannot decode unknown states; those remain explicit',
            'No held-out target enters a template mean or state dictionary',
            'CPU re-evaluation of the previously GPU-audited frozen coefficients'])
    a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

if __name__=='__main__':main()
