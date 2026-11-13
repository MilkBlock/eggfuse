"""Compare native boundary outcomes to the saved observer, summarize actual GPU replay.

This checks the Eq-input-delta contract only, not native egglog equivalence.
"""
import argparse
import hashlib
import json
from pathlib import Path


def summarize(trace, audit):
    expected={}
    for run in trace['runs']:
        for index,binding in enumerate(run['audit']['bindings']):
            ports=binding['eq_ports']
            for i,a in enumerate(ports):
                for b in ports[:i]:
                    if a['sort']==b['sort'] and a['before']!=b['before']:
                        key=(run['ordinal'],index,binding['rule'],min(a['slot'],b['slot']),max(a['slot'],b['slot']))
                        expected[key]=a['after']==b['after']
    actual={}
    assert len(audit['frames'])==len(trace['steps'])
    for frame,step in zip(audit['frames'],trace['steps']):
        assert frame['complete'] and frame['run']==step['ordinal'] and frame['epoch']==step['epoch']
        assert frame['program']==trace['program_sha256']
        for o in frame['outcomes']:
            c=o['claim'];key=(frame['run'],c['binding'],c['rule'],c['left'],c['right'])
            assert key not in actual
            actual[key]=o['equal']
    assert actual==expected
    assert audit['final_graph_equal'] and audit['run_boundaries_equal']
    n=len(trace['steps']);counts={}
    for name,lo,hi in [('all',0,n),('train',0,int(n*.6)),('validation',int(n*.6),int(n*.8)),('test',int(n*.8),n)]:
        selected=[v for f,v in zip(audit['frames'],audit['verdicts']) if lo<f['run']<=hi]
        assert all(v['complete'] and v['protocol_ok'] for v in selected)
        c={k:sum(v[k] for v in selected) for k in ('checked_pairs','true_positives','false_positives','false_negatives','invalid_claims')}
        c['wrong_pair_fraction']=(c['false_positives']+c['false_negatives'])/max(1,c['checked_pairs'])
        counts[name]=c
    return {**{k:v for k,v in audit.items() if k not in ('frames','verdicts')},
        'saved_observer_outcomes_exact':True,'source_runs':n,'counts':counts,
        'timing_scope':'single dev/unoptimized run; serialization excluded; no speedup claim',
        'limitations':['CPU executes original program in full; not a proof-only replacement for CPU execution',
            'Only initially unequal same-sort matched input pairs; not scalar/new-node/mutable/visibility token validation',
            'Saved GPU replay; no live asynchronous GPU queue or correction application',
            'Same-runtime observer/reference checks do not establish native egglog semantic acceptance']}


def main():
    p=argparse.ArgumentParser();p.add_argument('trace',type=Path);p.add_argument('audit',type=Path);p.add_argument('output',type=Path);args=p.parse_args()
    report=summarize(json.loads(args.trace.read_text()),json.loads(args.audit.read_text()))
    report['trace_sha256']=hashlib.sha256(args.trace.read_bytes()).hexdigest()
    args.output.write_text(json.dumps(report,indent=2)+'\n')

if __name__=='__main__':main()
