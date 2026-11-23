"""Summarize mode-separated raw audits produced by evaluate.py and prefix_probe.py."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
from statistics import median


def read(path):
    return json.loads(path.read_bytes())


def summary(folder,oracle):
    result=dict(training=read(folder/'actor.training.json'),arms={},prefix_assist={})
    for arm in ('untrained','trained'):
        raw=read(folder/(arm+'-checked.json'))
        compact={k:v for k,v in raw.items() if k!='splits'}
        compact['splits']={}
        for split,r in raw['splits'].items():
            e=r['exclusive']
            cases=e['cases']
            reasons=sum((Counter(c['counts']['rejected']) for c in cases),Counter())
            value={k:v for k,v in e.items() if k!='cases'}
            value.update(issued=sum(c['issued'] for c in cases),duplicates=sum(c['counts']['duplicates'] for c in cases),
                         reject_reasons=reasons,source_runs=sum(c['runs'] for c in cases),
                         neural_waves=sum(c['neural_waves'] for c in cases),
                         receiver_invocations=sum(c['counts']['calls'] for c in cases),
                         remaining_search_calls=sum(c['independent_search_calls'] for c in cases),
                         native_event_tokens=sum(c['native_runtime_events'] for c in cases),
                         median_seconds={k:median(c[k] for c in cases) for k in
                             ('network_seconds','native_verify_seconds','native_repair_seconds','remaining_process_seconds_including_ipc','wall_seconds')})
            if value['issued']!=value['accepted']+value['duplicates']+sum(reasons.values()):
                raise ValueError('proposal ledger differs')
            compact['splits'][split]={**r,'exclusive':value}
        result['arms'][arm]=compact
    prefix=read(folder/'prefix-checked.json')
    for split in sorted({r['split'] for r in prefix['results']}):
        selected=[r for r in prefix['results'] if r['split']==split and r['collision']]
        by_run={}
        for run in sorted({r['run'] for r in selected}):
            group=[r for r in selected if r['run']==run]
            keys=('reference_current','network_issued','accepted_current','duplicates','addr_exact',
                  'actual_new_events','reference_new_events','required_event_consumers',
                  'verified_reference_event_consumers','distinct_parents_collapsed')
            by_run[run]={k:sum(r[k] for r in group) for k in keys}
            by_run[run]['rejected']=sum((Counter(r['rejected']) for r in group),Counter())
        result['prefix_assist'][split]=by_run
    result['eggcc_exclusive']={}
    reference=read(oracle)
    for case in ('sum','dot'):
        raw=json.loads((folder/f'eggcc-{case}-checked.log').read_text().splitlines()[-1])
        r={k:v for k,v in raw.items() if k not in ('source_schedule','rhs_by_run','writes_by_run')}
        r.update(reference_commits=reference[case]['reference_commits'],reference_runs=reference[case]['source_runs_observed'],
                 state_equal=raw['state_sha']==reference[case]['state_sha'])
        result['eggcc_exclusive'][case]=r
    result['weights_file_sha256']=hashlib.sha256((folder/'actor.pt').read_bytes()).hexdigest()
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('folder','oracle','output'):
        p.add_argument(key,type=Path)
    a=p.parse_args()
    a.output.write_text(json.dumps(summary(a.folder,a.oracle),indent=2)+'\n')
