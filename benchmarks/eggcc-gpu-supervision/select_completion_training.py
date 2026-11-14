"""Select new short training programs from actual rule-application coverage.

No validation labels or scores are inspected. Selection is by existing program
split and smallest observed binding population, with recorded source hashes.
"""
import argparse,hashlib,json
from collections import Counter
from pathlib import Path
from collect_observed_corpus import read_bytes


def inspect_case(case,raw):
    if case.get('split')!='train' or case.get('status')!='complete':raise ValueError('not a complete training case')
    if hashlib.sha256(raw).hexdigest()!=case['trace_sha256']:raise ValueError('trace provenance')
    trace=json.loads(raw)
    if trace['program_sha256']!=case['program_sha256']:raise ValueError('program identity')
    if not all(trace.get(k) is True for k in ('strict_audit_reference_equal','run_control_counts_equal')):raise ValueError('unverified source execution')
    seconds=trace['reference_execution_seconds']
    if not 0<=seconds<=1:return dict(case=case['case'],status='too_slow',reference_seconds=seconds)
    counts=Counter();first={}
    for run in trace['runs']:
        for b in run['audit']['bindings']:
            if b['rule'] in (283,290,293):
                counts[b['rule']]+=1;first.setdefault(b['rule'],run['ordinal'])
    return dict(case=case['case'],status='eligible' if counts[293] and counts[283] else 'missing_target_rules',
        reference_seconds=seconds,rule_counts=dict(counts),first_runs=first,source_trace_sha256=case['trace_sha256'])


def main():
    p=argparse.ArgumentParser();p.add_argument('corpus',type=Path);p.add_argument('exclude',type=Path);p.add_argument('output',type=Path)
    p.add_argument('--max-cases',type=int,default=2);a=p.parse_args()
    if a.max_cases<1:raise ValueError('positive case count')
    corpus_raw=a.corpus.read_bytes();corpus=json.loads(corpus_raw);old=json.loads(a.exclude.read_text())
    sha=hashlib.sha256(corpus_raw).hexdigest()
    if old['partition']!='train' or old['manifest_sha256']!=sha:raise ValueError('exclusion provenance')
    seen={c['case'] for c in old['cases']};selected=[];observations=[]
    candidates=sorted([c for c in corpus['cases'] if c.get('split')=='train' and c['status']=='complete' and c['case'] not in seen],
                      key=lambda c:(c['summary']['observed_bindings'],c['case']))
    for c in candidates:
        observation=inspect_case(c,read_bytes(Path(c['trace'])));observations.append(observation)
        if observation['status']=='eligible':selected.append(c)
        if len(selected)==a.max_cases:break
    if len(selected)!=a.max_cases:raise ValueError('insufficient eligible training programs')
    out=dict(partition='train',manifest_sha256=sha,exclusion_sha256=hashlib.sha256(a.exclude.read_bytes()).hexdigest(),
        selection='first unseen complete training programs by increasing actual binding count, under 1s saved CPU reference, with rule 283 and 293 applications',
        cases=selected,observations=observations)
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(out,indent=2)+'\n')
    print(json.dumps(dict(cases=[c['case'] for c in selected],observations=observations),indent=2))

if __name__=='__main__':main()
